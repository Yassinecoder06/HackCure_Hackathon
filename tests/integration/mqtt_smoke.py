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
HEADERS: dict[str, str] = {}


def env() -> dict[str, str]:
    """Demo secrets live in the git-ignored infra/.env written by infra/gen_secrets.py."""
    return dict(line.split("=", 1) for line in (ROOT / "infra" / ".env").read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#"))


def login_as_charge_nurse() -> None:
    pins = dict(pair.split(":", 1) for pair in env()["BORJ_STAFF_PINS"].split(","))
    body = json.dumps({"staffId": "CN1", "secret": pins["CN1"]}).encode()
    req = urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        HEADERS["Authorization"] = "Bearer " + json.load(resp)["token"]


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


def post_json(path: str) -> dict:
    req = urllib.request.Request(API + path, data=b"", headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


def get_json(path: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=HEADERS), timeout=5) as resp:
        return json.load(resp)


def main() -> None:
    wait_for(lambda: get_json("/health")["status"] == "ok", "server health")
    login_as_charge_nurse()

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="mqtt-smoke")
    client.connect("localhost", 1883)
    client.loop_start()
    # Pin the demo clock so freshness (and therefore NEWS2) is deterministic.
    clock = {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:10:00Z", "speed": 1,
             "scenario": "smoke", "running": True}
    client.publish("borj/W1/sim/clock", json.dumps(clock), qos=1, retain=True).wait_for_publish(5)
    # Signed like the simulator does (invariant 13). A tampered copy (pulse changed after signing) goes first:
    # the server must reject it, so B04 ends up with the genuine pulse and the rejection is audited.
    key = bc.parse_keys(env()["BORJ_DEVICE_KEYS"])["sim-k1"]
    tampered = bc.sign(json.loads((ROOT / "contracts" / "examples" / "vitals.device.json").read_text(encoding="utf-8")),
                       key, "sim-k1")
    tampered["params"]["pulse"] = 60
    tampered["eventId"] = "01K80000000000000000TAMPER"
    for name in ("binding", "vitals.tampered", "vitals.device", "vitals.manual", "device-status"):
        payload = tampered if name == "vitals.tampered" else bc.sign(
            json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text(encoding="utf-8")), key, "sim-k1")
        topic = bc.topic(name.split(".")[0], payload["ward"], bed=payload["bed"])
        client.publish(topic, json.dumps(payload), qos=1).wait_for_publish(5)
    client.loop_stop()
    client.disconnect()

    def b04_has_vitals():
        beds = get_json("/api/v1/wards/W1/snapshot")["beds"]
        b04 = next(b for b in beds if b["bed"] == "B04")
        return b04 if b04["admission"] and {"pulse", "consciousness"} <= set(b04["vitals"]) else None

    try:
        b04 = wait_for(b04_has_vitals, "B04 vitals in snapshot", timeout_s=20)
    except SystemExit:
        beds = get_json("/api/v1/wards/W1/snapshot")["beds"]
        print("B04 at timeout:", json.dumps(next(b for b in beds if b["bed"] == "B04"), indent=2))
        raise
    news2 = b04["news2"]
    if b04["news2Status"] != "ok" or (news2["total"], news2["band"], news2["complete"]) != (8, "high", True):
        raise SystemExit(f"unexpected NEWS2: {b04['news2Status']} {news2}")
    # A bedside call: press over MQTT -> server routes it -> one-tap ack over REST.
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="mqtt-smoke-call")
    client.connect("localhost", 1883)
    client.loop_start()
    call = json.loads((ROOT / "contracts" / "examples" / "call.json").read_text(encoding="utf-8"))
    client.publish(bc.topic("call", "W1", bed=call["bed"]), json.dumps(call), qos=1).wait_for_publish(5)
    client.loop_stop()
    client.disconnect()
    wait_for(lambda: any(c["callId"] == call["callId"] for c in get_json("/api/v1/wards/W1/snapshot")["calls"]),
             "call routed by the server", timeout_s=20)
    if post_json(f"/api/v1/wards/W1/calls/{call['callId']}/ack")["state"] != "acknowledged":
        raise SystemExit("call ack failed")

    if b04["vitals"]["pulse"]["value"] == 60:
        raise SystemExit("a tampered message was ingested")
    audit = get_json("/api/v1/wards/W1/audit?limit=1000")
    if not any(a["action"] == "integrity.rejected" for a in audit):
        raise SystemExit("tampered message was not rejected and audited")
    if not get_json("/api/v1/wards/W1/audit/verify")["valid"]:
        raise SystemExit("audit chain does not verify")
    print("OK: login -> MQTT -> twin -> inference -> API (NEWS2 8, high, complete); call routed and acked; "
          "tampered frame rejected; audit chain valid")
    print(json.dumps(b04, indent=2))


if __name__ == "__main__":
    main()
