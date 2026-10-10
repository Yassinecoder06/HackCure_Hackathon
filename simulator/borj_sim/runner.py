"""Simulation runner loop and MQTT publisher for borj_sim."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import borj_contracts as bc
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .config import ScenarioConfig, WardConfig
from .generator import EventGenerator

log = logging.getLogger(__name__)


class SimulationRunner:
    def __init__(
        self,
        scenario: ScenarioConfig,
        ward: WardConfig,
        speed: float = 1.0,
        dry_run: bool = False,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        key: bytes | None = None,
        key_id: str | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.scenario = scenario
        self.ward = ward
        self.speed = speed
        self.dry_run = dry_run
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.key = key
        self.key_id = key_id or "sim-k1"
        self.on_event = on_event

        self.generator = EventGenerator(scenario, ward)
        self.is_running = False

        self._client: mqtt.Client | None = None
        if not dry_run:
            self._client = mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=f"borj-sim-{scenario.name}",
            )

    def start_broker(self) -> None:
        if self._client:
            log.info("Connecting simulator to MQTT broker %s:%d", self.broker_host, self.broker_port)
            self._client.connect(self.broker_host, self.broker_port)
            self._client.loop_start()

    def stop_broker(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self.key and "integrity" not in payload and "eventId" in payload:
            payload = bc.sign(payload, self.key, self.key_id)

        if self.on_event:
            self.on_event(topic, payload)

        if self.dry_run:
            print(json.dumps({"topic": topic, "payload": payload}))
            return

        if self._client:
            is_retained = topic.endswith("/clock") or topic.endswith("/call/state")
            qos = 0 if topic.endswith("/clock") else 1
            raw = json.dumps(payload).encode("utf-8")
            self._client.publish(topic, raw, qos=qos, retain=is_retained)

    def run(self, max_minutes: int | None = None) -> int:
        """Runs the simulation to completion. Returns count of published events."""
        self.is_running = True
        event_count = 0
        target_minutes = min(self.scenario.duration_min, max_minutes) if max_minutes else self.scenario.duration_min

        log.info(
            "Starting simulation '%s': duration=%d min, speed=%.1fx, start=%s",
            self.scenario.name,
            target_minutes,
            self.speed,
            self.scenario.start,
        )

        if not self.dry_run:
            self.start_broker()

        try:
            # 1. Emit initial events (bindings, clock, staff)
            initial = self.generator.initial_events()
            for topic, payload in initial:
                self.publish(topic, payload)
                event_count += 1

            # 2. Main simulation loop
            step_min = 1
            while self.is_running and self.generator.current_min < target_minutes:
                # Advance step
                step_events = self.generator.generate_step(step_min=step_min)
                for topic, payload in step_events:
                    self.publish(topic, payload)
                    event_count += 1

                if self.speed > 0:
                    sleep_s = (step_min * 60.0) / self.speed
                    time.sleep(sleep_s)

        finally:
            self.is_running = False
            if not self.dry_run:
                self.stop_broker()

        log.info("Simulation completed: %d events published", event_count)
        return event_count

    def stop(self) -> None:
        self.is_running = False
