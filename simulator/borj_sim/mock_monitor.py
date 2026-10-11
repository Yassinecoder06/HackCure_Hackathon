"""Interactive / standalone Mock Medical Monitor for Bedside Node (Chamber 3 / Bed B06).

Simulates medical instruments connected to the patient:
- Cardiac Monitor / ECG: Pulse (Heart Rate)
- Pulse Oximeter: SpO2 (%)
- Digital Blood Pressure Monitor: Systolic BP (mmHg)
- Respiratory Rate Sensor: Breaths/min
- Digital Clinical Thermometer: Temperature (°C)

Publishes validated contract messages directly to the MQTT broker:
    borj/{ward}/{bed}/vitals
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import sys
import time
from datetime import UTC, datetime
from typing import Any

import borj_contracts as bc
import paho.mqtt.client as mqtt
from borj_contracts import generate_ulid
from borj_contracts import mqtt as bc_mqtt
from paho.mqtt.enums import CallbackAPIVersion

log = logging.getLogger("mock_monitor")

PROFILES = {
    "normal": {
        "pulse": (72, 78),
        "spo2": (97, 99),
        "sys_bp": (118, 124),
        "resp_rate": (14, 16),
        "temp_c": (36.6, 37.1),
    },
    "mild": {
        "pulse": (92, 98),
        "spo2": (94, 96),
        "sys_bp": (110, 116),
        "resp_rate": (18, 20),
        "temp_c": (37.6, 38.0),
    },
    "deteriorate": {
        "pulse": (115, 128),
        "spo2": (90, 93),
        "sys_bp": (92, 100),
        "resp_rate": (23, 27),
        "temp_c": (38.8, 39.4),
    },
    "critical": {
        "pulse": (130, 145),
        "spo2": (87, 90),
        "sys_bp": (85, 94),
        "resp_rate": (28, 34),
        "temp_c": (39.3, 40.1),
    },
}


class MockMedicalMonitor:
    def __init__(
        self,
        ward: str = "W1",
        bed: str = "B06",
        device_id: str | None = None,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        profile: str = "normal",
        interval_s: float = 5.0,
    ) -> None:
        self.ward = ward
        self.bed = bed
        self.device_id = device_id or f"MON-{bed}"
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.profile = profile
        self.interval_s = interval_s
        self.is_running = False

        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"borj-mon-{bed}",
        )
        bc_mqtt.configure(self._client)  # TLS 1.3 + broker account from the environment
        self._key, self._key_id = bc_mqtt.signing_key("sim-k1")  # stands in for a device behind the gateway

    def start(self) -> None:
        log.info("Connecting Mock Medical Monitor to %s:%d...", self.broker_host, self.broker_port)
        self._client.connect(self.broker_host, self.broker_port)
        self._client.loop_start()
        self.is_running = True

        # Ensure patient binding exists on bed
        self.publish_admission()

    def stop(self) -> None:
        self.is_running = False
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass

    def _signed(self, payload: dict[str, Any]) -> dict[str, Any]:
        return bc.sign(payload, self._key, self._key_id) if self._key else payload

    def publish_admission(self) -> None:
        """Publishes bed admission/binding so bed is active on station board."""
        now_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        topic = bc.topic("binding", self.ward, bed=self.bed)
        payload = {
            "schemaVersion": 1,
            "eventId": generate_ulid(),
            "ts": now_utc,
            "ward": self.ward,
            "bed": self.bed,
            "source": "app-N1",
            "sourceType": "staff_app",
            "action": "admit",
            "admissionId": f"ADM-{self.bed}",
            "patientRef": f"Patient {self.bed}",
            "acuity": 2,
            "method": "wristband_scan",
            "staffId": "N1",
        }
        bc.validate_message(topic, payload)
        self._client.publish(topic, json.dumps(self._signed(payload)), qos=1)
        log.info("Published admission binding for %s (%s)", self.bed, topic)

    def generate_reading(self) -> dict[str, Any]:
        spec = PROFILES.get(self.profile, PROFILES["normal"])
        reading = {
            "pulse": round(random.uniform(*spec["pulse"])),
            "spo2": round(random.uniform(*spec["spo2"])),
            "sys_bp": round(random.uniform(*spec["sys_bp"])),
            "resp_rate": round(random.uniform(*spec["resp_rate"])),
            "temp_c": round(random.uniform(*spec["temp_c"]), 1),
        }
        return reading

    def publish_vitals(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if params is None:
            params = self.generate_reading()

        now_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        topic = bc.topic("vitals", self.ward, bed=self.bed)
        payload = {
            "schemaVersion": 1,
            "eventId": generate_ulid(),
            "ts": now_utc,
            "tsSource": "device_rtc",
            "ward": self.ward,
            "bed": self.bed,
            "source": f"mon-{self.bed}",
            "sourceType": "device",
            "deviceId": self.device_id,
            "params": params,
            "quality": {
                "valid": True,
                "stale_after_s": 900,
            },
        }

        bc.validate_message(topic, payload)
        self._client.publish(topic, json.dumps(self._signed(payload)), qos=1)
        return payload

    def run_loop(self) -> None:
        self.start()
        print("=" * 65)
        print(f"  Mock Medical Monitor running for Ward {self.ward} / Bed {self.bed}")
        print(f"  Device: {self.device_id} (Cardiac Monitor, SpO2, BP, Temp, RR)")
        print(f"  Mode: {self.profile.upper()} | Update Interval: {self.interval_s}s")
        print(f"  Broker: {self.broker_host}:{self.broker_port}")
        print("=" * 65)

        try:
            while self.is_running:
                vitals = self.publish_vitals()
                p = vitals["params"]
                print(
                    f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                    f"HR: {p['pulse']} bpm | "
                    f"SpO2: {p['spo2']}% | "
                    f"BP: {p['sys_bp']} mmHg | "
                    f"RR: {p['resp_rate']}/min | "
                    f"Temp: {p['temp_c']}°C  (Profile: {self.profile})",
                    flush=True,
                )
                time.sleep(self.interval_s)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
        finally:
            self.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock Bedside Medical Monitor")
    parser.add_argument("--ward", default="W1", help="Ward ID (default: W1)")
    parser.add_argument("--bed", default="B06", help="Bed ID (default: B06)")
    parser.add_argument("--broker", default="localhost:1883", help="MQTT broker host:port")
    parser.add_argument(
        "--profile",
        choices=["normal", "mild", "deteriorate", "critical"],
        default="normal",
        help="Vitals profile (default: normal)",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="Publish interval in seconds (default: 5.0)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    host, port_str = (args.broker.split(":", 1) if ":" in args.broker else (args.broker, "1883"))
    port = int(port_str)

    monitor = MockMedicalMonitor(
        ward=args.ward,
        bed=args.bed,
        broker_host=host,
        broker_port=port,
        profile=args.profile,
        interval_s=args.interval,
    )

    def _sig(sig, frame):
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    monitor.run_loop()


if __name__ == "__main__":
    main()
