"""MQTT client for the bedside node.

Publishes call events and device status.
Subscribes to the retained `borj/{ward}/{bed}/call/state` topic.
Enforces contract validation and optional HMAC-SHA256 signing (invariants 6, 13).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC
from typing import Any

import borj_contracts as bc
import paho.mqtt.client as mqtt
from borj_contracts import mqtt as bc_mqtt
from paho.mqtt.enums import CallbackAPIVersion

log = logging.getLogger(__name__)


class NodeMqttClient:
    def __init__(
        self,
        ward: str,
        bed: str,
        host: str = "10.42.0.1",
        port: int = 1883,
        client_id: str | None = None,
        key: bytes | None = None,
        key_id: str | None = None,
        on_call_state: Callable[[dict[str, Any]], None] | None = None,
        on_connected_cb: Callable[[], None] | None = None,
        on_disconnected_cb: Callable[[], None] | None = None,
    ) -> None:
        self.ward = ward
        self.bed = bed
        self.host = host
        self.port = port
        self.client_id = client_id or f"node-{ward}-{bed}"
        self.key = key
        self.key_id = key_id or f"node-{bed}"
        self.on_call_state = on_call_state
        self.on_connected_cb = on_connected_cb
        self.on_disconnected_cb = on_disconnected_cb

        self.is_connected = False
        self.call_state_topic = bc.topic("call-state", ward, bed=bed)
        self.call_topic = bc.topic("call", ward, bed=bed)
        self.status_topic = bc.topic("device-status", ward, bed=bed)

        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
        )
        bc_mqtt.configure(self._client)  # TLS 1.3 + broker account from the environment
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)

    def start(self) -> None:
        log.info("Node MQTT connecting to %s:%d as %s", self.host, self.port, self.client_id)
        try:
            self._client.connect_async(self.host, self.port, keepalive=30)
            self._client.loop_start()
        except Exception as exc:
            log.warning("Could not initiate MQTT connection to %s:%d: %s", self.host, self.port, exc)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("Node MQTT connection failed: %s", reason_code)
            self.is_connected = False
            return
        self.is_connected = True
        log.info("Node MQTT connected! Subscribing to %s", self.call_state_topic)
        client.subscribe(self.call_state_topic, qos=1)
        if self.on_connected_cb:
            self.on_connected_cb()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.is_connected = False
        log.warning("Node MQTT disconnected (%s)", reason_code)
        if self.on_disconnected_cb:
            self.on_disconnected_cb()

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload)
        except Exception as exc:
            log.warning("Invalid JSON received on %s: %s", message.topic, exc)
            return

        if message.topic == self.call_state_topic:
            try:
                bc.validate_message(message.topic, payload)
            except Exception as exc:
                log.warning("call/state validation error: %s", exc)
                return
            log.info("Received call/state update: state=%s", payload.get("state"))
            if self.on_call_state:
                self.on_call_state(payload)

    def publish_call(self, payload: dict[str, Any]) -> bool:
        if self.key:
            payload = bc.sign(payload, self.key, self.key_id)

        # Ensure matches contract before publishing
        try:
            bc.validate_message(self.call_topic, payload)
        except Exception as exc:
            log.error("Contract violation for call message: %s", exc)
            return False

        if not self.is_connected:
            log.warning("Cannot publish call (MQTT disconnected)")
            return False

        try:
            raw = json.dumps(payload).encode("utf-8")
            info = self._client.publish(self.call_topic, raw, qos=1)
            info.wait_for_publish(timeout=2.0)
            log.info("Published call %s to %s", payload.get("callId"), self.call_topic)
            return True
        except Exception as exc:
            log.warning("Publish call failed: %s", exc)
            return False

    def publish_status(self, status: str = "ok", detail: str = "") -> bool:
        from datetime import datetime

        from borj_contracts import generate_ulid

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload = {
            "schemaVersion": 1,
            "eventId": generate_ulid(),
            "ts": now,
            "ward": self.ward,
            "bed": self.bed,
            "source": self.client_id,
            "sourceType": "bedside_node",
            "deviceId": f"NODE-{self.bed}",
            "deviceType": "bedside_node",
            "status": status,
        }
        if detail:
            payload["detail"] = detail

        if self.key:
            payload = bc.sign(payload, self.key, self.key_id)

        try:
            bc.validate_message(self.status_topic, payload)
            if self.is_connected:
                raw = json.dumps(payload).encode("utf-8")
                self._client.publish(self.status_topic, raw, qos=1)
                return True
        except Exception as exc:
            log.warning("Failed to publish node status: %s", exc)
        return False

    def publish_ack(self, call_id: str, staff_id: str = "N1") -> bool:
        from datetime import UTC, datetime

        from borj_contracts import generate_ulid

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        topic = f"borj/{self.ward}/ack"
        payload = {
            "schemaVersion": 1,
            "eventId": generate_ulid(),
            "ts": now,
            "ward": self.ward,
            "source": self.client_id,
            "sourceType": "bedside_node",
            "staffId": staff_id,
            "target": "call",
            "targetId": call_id,
            "action": "acknowledge",
        }
        if self.key:
            payload = bc.sign(payload, self.key, self.key_id)
        try:
            bc.validate_message(topic, payload)
            if self.is_connected:
                raw = json.dumps(payload).encode("utf-8")
                self._client.publish(topic, raw, qos=1)
                log.info("Published bedside ack for call %s to %s", call_id, topic)
                return True
        except Exception as exc:
            log.warning("Failed to publish bedside ack: %s", exc)
        return False
