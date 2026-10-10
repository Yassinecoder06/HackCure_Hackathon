"""Bedside Node State Machine and Orchestrator.

Coordinates physical buttons, LEDs, speaker audio, local SQLite outbox,
and MQTT communications for the bedside patient unit (Whitepaper 4.2, ADR 0003).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from borj_contracts import generate_ulid

from .audio import AudioManager
from .buttons import ButtonController
from .client import NodeMqttClient
from .encoder import RotaryEncoderController
from .leds import LedController
from .outbox import NodeOutbox

log = logging.getLogger(__name__)


class BedsideNode:
    def __init__(
        self,
        ward: str = "W1",
        bed: str = "B06",
        broker_host: str = "10.42.0.1",
        broker_port: int = 1883,
        pin_assist: int = 27,
        pin_comfort: int = 17,
        pin_led_green: int | None = 25,
        pin_led_red: int | None = 22,
        pin_led_amber: int | None = None,
        pin_clk: int | None = 23,
        pin_dt: int | None = 24,
        db_path: Path | str = ":memory:",
        key: bytes | None = None,
        key_id: str | None = None,
        receipt_timeout_s: float = 4.0,
        volume: int = 90,
        mock_gpio: bool = False,
        audio_enabled: bool = True,
    ) -> None:
        self.ward = ward
        self.bed = bed
        self.receipt_timeout_s = receipt_timeout_s

        # Subsystems
        self.audio = AudioManager(enabled=audio_enabled)
        self.leds = LedController(
            pin_green=pin_led_green,
            pin_red=pin_led_red,
            pin_amber=pin_led_amber,
            mock=mock_gpio,
        )
        self.encoder = None
        if pin_clk is not None and pin_dt is not None:
            self.encoder = RotaryEncoderController(
                pin_clk=pin_clk,
                pin_dt=pin_dt,
                initial_percent=volume,
                mock=mock_gpio,
            )
        self.outbox = NodeOutbox(db_path=db_path)

        self.mqtt = NodeMqttClient(
            ward=ward,
            bed=bed,
            host=broker_host,
            port=broker_port,
            key=key,
            key_id=key_id,
            on_call_state=self._on_call_state,
            on_connected_cb=self._on_mqtt_connected,
            on_disconnected_cb=self._on_mqtt_disconnected,
        )

        self.buttons = ButtonController(
            pin_assist=pin_assist,
            pin_comfort=pin_comfort,
            on_assist=lambda: self.on_button_press("assist"),
            on_comfort=lambda: self.on_button_press("comfort"),
            mock=mock_gpio,
        )

        # Call tracking state
        self._lock = threading.Lock()
        self.active_call_id: str | None = None
        self.active_kind: str | None = None
        self.active_press_count: int = 0
        self.current_state: str = "idle"  # idle | pressed | sent | not_sent | acknowledged | escalated | resolved

        self._receipt_timer: threading.Timer | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def start(self) -> None:
        log.info("Starting BedsideNode for Ward %s, Bed %s", self.ward, self.bed)
        self.mqtt.start()
        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, args=(self,), daemon=True, name="node-hb")
        self._heartbeat_thread.start()

    def stop(self) -> None:
        log.info("Stopping BedsideNode")
        self._heartbeat_stop.set()
        self._cancel_receipt_timer()
        if self.encoder:
            self.encoder.close()
        self.buttons.close()
        self.leds.close()
        self.audio.stop()
        self.mqtt.stop()

    def _cancel_receipt_timer(self) -> None:
        if self._receipt_timer:
            self._receipt_timer.cancel()
            self._receipt_timer = None

    def on_button_press(self, kind: str) -> None:
        """Invoked when the patient presses Assist or Comfort button."""
        with self._lock:
            # If an alert is active and the green (comfort/presence) button is pressed,
            # this represents nurse presence arriving at the bedside to acknowledge the call
            if kind == "comfort" and self.active_call_id and self.current_state in ("sent", "escalated"):
                log.info("Bedside nurse presence: Green button pressed to acknowledge call %s", self.active_call_id)
                self.audio.play_beep()
                self.mqtt.publish_ack(self.active_call_id, staff_id="N1")
                return

            # Immediate feedback to patient (whitepaper 4.2)
            self.audio.play_beep()
            self.leds.show_pressed()

            # Repeat press logic: reuse active callId if still open and unacknowledged/escalated
            if self.active_call_id and self.current_state in ("sent", "not_sent", "escalated"):
                self.active_press_count += 1
                call_id = self.active_call_id
                log.info("Repeat press on call %s (count: %d)", call_id, self.active_press_count)
                # If patient taps multiple times on emergency button, play reassurance cue
                if kind == "assist" and self.active_press_count >= 2:
                    self.audio.play_ack_reassurance()
            else:
                call_id = f"C-{self.bed}-{int(time.time() * 1000) % 10000000:07d}"
                self.active_call_id = call_id
                self.active_kind = kind
                self.active_press_count = 1

            now_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            event_id = generate_ulid()

            payload = {
                "schemaVersion": 1,
                "eventId": event_id,
                "ts": now_utc,
                "tsSource": "device_rtc",
                "ward": self.ward,
                "bed": self.bed,
                "source": f"node-{self.bed}",
                "sourceType": "bedside_node",
                "callId": call_id,
                "kind": kind,
                "pressCount": self.active_press_count,
            }

            # Enqueue in local outbox for durability
            self.outbox.enqueue(self.mqtt.call_topic, payload)

            if not self.mqtt.is_connected:
                log.warning("MQTT not connected: triggering not_sent immediately")
                self._trigger_not_sent()
                return

            # Publish call over MQTT
            success = self.mqtt.publish_call(payload)
            if not success:
                self._trigger_not_sent()
                return

            # Expect call/state from server within timeout
            self._cancel_receipt_timer()
            self._receipt_timer = threading.Timer(self.receipt_timeout_s, self._on_receipt_timeout)
            self._receipt_timer.start()

    def _on_receipt_timeout(self) -> None:
        with self._lock:
            # If server has not acknowledged with call/state within timeout, trigger not_sent
            if self.current_state not in ("sent", "acknowledged", "resolved"):
                log.warning("Timed out waiting for call/state from server (timeout: %.1fs)", self.receipt_timeout_s)
                self._trigger_not_sent()

    def _trigger_not_sent(self) -> None:
        self.current_state = "not_sent"
        self.leds.show_not_sent()
        # Requirement A: Buzzer alert + voice prompt ("Veuillez utiliser la sonnette d'urgence")
        self.audio.play_outage_alert()
        log.warning("🚨 [NOT_SENT] Alerting patient via red blink, buzzer and emergency bell voice prompt")

    def _on_call_state(self, payload: dict[str, Any]) -> None:
        with self._lock:
            call_id = payload.get("callId")
            state = payload.get("state")

            # Check if this relates to current call or recent call
            if self.active_call_id and call_id != self.active_call_id and state != "resolved":
                log.debug("call/state for another call %s (active is %s)", call_id, self.active_call_id)
                return

            self._cancel_receipt_timer()
            self.current_state = state or "idle"

            # In all non-not_sent confirmations, mark current call delivered in outbox
            if state in ("sent", "acknowledged", "escalated", "resolved") and self.active_call_id:
                # Mark all events with this callId as delivered
                for _topic, p in self.outbox.get_pending():
                    if p.get("callId") == call_id:
                        self.outbox.mark_delivered(p["eventId"])

            if state == "sent":
                log.info("Call %s delivered to ward tower (SENT)", call_id)
                self.leds.show_sent()

            elif state == "acknowledged":
                ack_by = payload.get("acknowledgedBy", "staff")
                log.info("Call %s acknowledged by %s (ACKNOWLEDGED)", call_id, ack_by)
                self.leds.show_acknowledged()
                # Requirement C: Double-chime + spoken "Votre appel a été pris en compte, un soignant arrive."
                self.audio.play_ack_reassurance()

            elif state == "escalated":
                level = payload.get("escalationLevel", 1)
                log.info("Call %s escalated (level %d)", call_id, level)
                self.leds.show_sent()

            elif state == "resolved":
                log.info("Call %s resolved by staff (RESOLVED)", call_id)
                self.leds.show_off()
                self.active_call_id = None
                self.active_kind = None
                self.active_press_count = 0
                self.current_state = "idle"

            elif state == "not_sent":
                self._trigger_not_sent()

    def _on_mqtt_connected(self) -> None:
        log.info("MQTT link active: draining pending outbox events")
        self.mqtt.publish_status("ok", "node online")
        threading.Thread(target=self._drain_outbox, daemon=True, name="node-drain").start()

    def _on_mqtt_disconnected(self) -> None:
        log.warning("MQTT link lost: if active call, showing not_sent")
        with self._lock:
            if self.active_call_id and self.current_state not in ("acknowledged", "resolved"):
                self._trigger_not_sent()

    def _drain_outbox(self) -> None:
        """Replay stored events with deliveredLate: True."""
        pending = self.outbox.get_pending()
        if not pending:
            return

        log.info("Draining %d pending outbox event(s) with deliveredLate=True", len(pending))
        for _topic, payload in pending:
            # Clone and mark deliveredLate
            replay = dict(payload)
            replay["deliveredLate"] = True
            if self.mqtt.publish_call(replay):
                self.outbox.mark_delivered(payload["eventId"])
                time.sleep(0.05)


def _heartbeat_loop(node: BedsideNode) -> None:
    while not node._heartbeat_stop.wait(30.0):
        if node.mqtt.is_connected:
            node.mqtt.publish_status("ok")
