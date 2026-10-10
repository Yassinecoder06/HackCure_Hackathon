"""End-to-end smoke test: MQTT -> server ingest -> twin -> inference (NEWS2) -> REST snapshot.

Needs the compose stack running (mosquitto + server):
    docker compose -f infra/docker-compose.yml up -d --build
    python tests/integration/mqtt_smoke.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "contracts"))
import borj_contracts as bc  # noqa: E402

API = "http://localhost:8000"


def wait_for(fn, what: str, timeout_s: float = 60) -> object:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            result = fn()
            if result:
                return result
        except Exception:  # server not up yet
            pass
        time.sleep(1)
    raise SystemExit(f"timed out waiting for {what}")


def get_json(path: str) -> dict:
    with urllib.request.urlopen(API + path, timeout=5) as resp:
        return json.load(resp)


def main() -> None:
    wait_for(lambda: get_json("/health")["status"] == "ok", "server health")

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="mqtt-smoke")
    client.connect("localhost", 1883)
    client.loop_start()
    # Pin the demo clock so freshness (and therefore NEWS2) is deterministic.
    clock = {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:10:00Z", "speed": 1,
             "scenario": "smoke", "running": True}
    client.publish("borj/W1/sim/clock", json.dumps(clock), qos=1, retain=True).wait_for_publish(5)
    for name in ("binding", "vitals.device", "vitals.manual", "device-status"):
        payload = json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        topic = bc.topic(name.split(".")[0], payload["ward"], bed=payload["bed"])
        client.publish(topic, json.dumps(payload), qos=1).wait_for_publish(5)
    client.loop_stop()
    client.disconnect()

    def b04_has_vitals():
        beds = get_json("/api/v1/wards/W1/snapshot")["beds"]
        b04 = next(b for b in beds if b["bed"] == "B04")
        return b04 if b04["admission"] and {"pulse", "consciousness"} <= set(b04["vitals"]) else None

    b04 = wait_for(b04_has_vitals, "B04 vitals in snapshot", timeout_s=20)
    news2 = b04["news2"]
    if b04["news2Status"] != "ok" or (news2["total"], news2["band"], news2["complete"]) != (8, "high", True):
        raise SystemExit(f"unexpected NEWS2: {b04['news2Status']} {news2}")
    print("OK: events flowed MQTT -> twin -> inference -> API (NEWS2 8, high, complete)")
    print(json.dumps(b04, indent=2))


if __name__ == "__main__":
    main()
