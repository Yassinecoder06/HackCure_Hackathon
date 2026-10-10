"""Ward Device Gateway implementation.

Reads device frames, checks quality/plausibility, binds devices to beds,
signs payloads with HMAC-SHA256, and forwards to the broker (or local AES-256-GCM outbox).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import borj_contracts as bc
import paho.mqtt.client as mqtt
from borj_contracts import generate_ulid
from paho.mqtt.enums import CallbackAPIVersion

from .binding import BindingRegistry
from .outbox import GatewayOutbox
from .quality import QualityChecker

log = logging.getLogger(__name__)


class WardGateway:
    def __init__(
        self,
        ward: str = "W1",
        broker_host: str = "localhost",
        broker_port: int = 1883,
        gateway_id: str = "gateway-ward",
        signing_key: bytes | None = None,
        signing_key_id: str = "gw-k1",
        db_path: Path | str = ":memory:",
        data_encryption_key: bytes | None = None,
    ) -> None:
        self.ward = ward
        self.gateway_id = gateway_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.signing_key = signing_key
        self.signing_key_id = signing_key_id

        self.quality = QualityChecker()
        self.bindings = BindingRegistry()
        self.outbox = GatewayOutbox(db_path=db_path, key=data_encryption_key)

        self.is_connected = False
        self._lock = threading.Lock()

        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.gateway_id,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)

    def start(self) -> None:
        log.info("Starting WardGateway for ward %s (broker: %s:%d)", self.ward, self.broker_host, self.broker_port)
        try:
            self._client.connect_async(self.broker_host, self.broker_port, keepalive=30)
            self._client.loop_start()
        except Exception as exc:
            log.warning("Could not initiate gateway MQTT connection: %s", exc)

    def stop(self) -> None:
        log.info("Stopping WardGateway")
        self._client.loop_stop()
        self._client.disconnect()
        self.outbox.close()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("Gateway MQTT connection failed: %s", reason_code)
            self.is_connected = False
            return
        self.is_connected = True
        log.info("Gateway MQTT connected! Subscribing to ward bindings...")
        # Listen for binding events to update device-to-bed mappings
        client.subscribe(f"borj/{self.ward}/+/binding", qos=1)
        threading.Thread(target=self._drain_outbox, daemon=True, name="gw-drain").start()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.is_connected = False
        log.warning("Gateway MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload)
            if message.topic.endswith("/binding"):
                self.bindings.apply_binding_event(payload)
        except Exception as exc:
            log.warning("Error processing binding on gateway: %s", exc)

    def process_reading(
        self,
        device_id: str,
        params: dict[str, Any],
        ts_utc: str | None = None,
        raw_flags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Processes a raw reading, validates plausibility, signs, and forwards."""
        bed = self.bindings.get_bed_for_device(device_id)
        if not bed:
            log.warning("Received reading from unbound device %s; cannot route to bed", device_id)
            return None

        # Check clinical plausibility & freshness
        quality_res = self.quality.check(params, flags=raw_flags)
        now_ts = ts_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        topic = bc.topic("vitals", self.ward, bed=bed)

        payload = {
            "schemaVersion": 1,
            "eventId": generate_ulid(),
            "ts": now_ts,
            "tsSource": "gateway",
            "ward": self.ward,
            "bed": bed,
            "source": self.gateway_id,
            "sourceType": "device",
            "deviceId": device_id,
            "params": params,
            "quality": quality_res.to_dict(),
        }

        # Sign with HMAC-SHA256 if key is provided (safety invariant 13)
        if self.signing_key:
            payload = bc.sign(payload, self.signing_key, self.signing_key_id)

        # Enforce contract schema validation
        bc.validate_message(topic, payload)

        if not self.is_connected:
            log.warning("Broker offline: queuing vitals in encrypted outbox")
            self.outbox.enqueue(topic, payload)
            return payload

        try:
            raw = json.dumps(payload).encode("utf-8")
            self._client.publish(topic, raw, qos=1)
            log.debug("Gateway published vitals for %s on %s", device_id, topic)
            return payload
        except Exception as exc:
            log.warning("Publish vitals failed (%s); queuing in outbox", exc)
            self.outbox.enqueue(topic, payload)
            return payload

    def _drain_outbox(self) -> None:
        pending = self.outbox.get_pending()
        if not pending:
            return

        log.info("Gateway draining %d pending event(s) from encrypted outbox", len(pending))
        for topic, payload in pending:
            # Mark late delivery in quality flags
            replay = dict(payload)
            q = dict(replay.get("quality", {}))
            flags = list(q.get("flags", []))
            if "late_delivery" not in flags:
                flags.append("late_delivery")
            q["flags"] = flags
            replay["quality"] = q

            if self.signing_key:
                replay = bc.sign(replay, self.signing_key, self.signing_key_id)

            try:
                bc.validate_message(topic, replay)
                raw = json.dumps(replay).encode("utf-8")
                self._client.publish(topic, raw, qos=1)
                self.outbox.mark_delivered(payload["eventId"])
                time.sleep(0.02)
            except Exception as exc:
                log.warning("Failed to replay outbox event %s: %s", payload.get("eventId"), exc)
