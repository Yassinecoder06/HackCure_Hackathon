"""MQTT subscriber: every contract topic goes through the ingest pipeline."""

from __future__ import annotations

import json
import logging

import borj_contracts as bc
import paho.mqtt.client as mqtt
from borj_contracts import mqtt as bc_mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .ingest import Ingestor
from .integrity import IntegrityGate

log = logging.getLogger(__name__)


class MqttListener:
    def __init__(self, ingestor: Ingestor, host: str, port: int, client_id: str = "borj-server",
                 gate: IntegrityGate | None = None) -> None:
        self.ingestor = ingestor
        self.gate = gate or IntegrityGate({}, "off")
        self.host = host
        self.port = port
        self.client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=client_id)
        bc_mqtt.configure(self.client)  # TLS 1.3 + broker account from MQTT_CA_CERT / MQTT_USERNAME / MQTT_PASSWORD
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.enable_logger(logging.getLogger("borj_server.paho"))

    def publish_retained(self, topic: str, payload: dict) -> None:
        """Publish a server decision (call/state). Retained so a rebooting bedside node gets its state back."""
        self.client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=1, retain=True)

    def start(self) -> None:
        log.info("connecting to MQTT %s:%d", self.host, self.port)
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        client.subscribe(bc.SUBSCRIBE_ALL, qos=1)
        log.info("MQTT connected, subscribed to %s", bc.SUBSCRIBE_ALL)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties) -> None:
        log.warning("MQTT disconnected (%s), will reconnect", reason_code)

    def _on_message(self, _client, _userdata, message: mqtt.MQTTMessage) -> None:
        # Our own call/state publications (P2) are stored like any other event; dedupe makes it safe.
        try:
            result = self.gate.handle_raw(self.ingestor, message.topic, message.payload)
        except Exception:
            # Never let one failing message (e.g. a database error) kill the MQTT thread: log and go on.
            log.exception("ingest failed for message on %s", message.topic)
            return
        if result.status == "accepted" and message.topic.endswith("/binding"):
            log.info("binding on %s: %s", message.topic, result.detail)
