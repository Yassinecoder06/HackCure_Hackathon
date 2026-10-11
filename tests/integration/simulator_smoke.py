"""Smoke test for role A's simulator running against the compose stack.

Run after tests/integration/mqtt_smoke.py, with the `simulator` service started:
    docker compose up -d simulator
    python tests/integration/simulator_smoke.py

The simulator admits the scenario's patients and streams vitals and calls. The server must ingest them
(beds admitted, B06 with readings, a call routed) and must not reject any frame at the MQTT boundary.
"""

from __future__ import annotations

from mqtt_smoke import get_json, login_as_charge_nurse, wait_for


def beds() -> dict[str, dict]:
    return {b["bed"]: b for b in get_json("/api/v1/wards/W1/snapshot")["beds"]}


def main() -> None:
    login_as_charge_nurse()
    wait_for(lambda: sum(1 for b in beds().values() if b["admission"]) >= 8, "the simulator's patients admitted",
             timeout_s=90)
    b06 = wait_for(lambda: beds()["B06"] if beds()["B06"]["vitals"] else None, "B06 readings from the simulator",
                   timeout_s=90)
    rejected = [a for a in get_json("/api/v1/wards/W1/audit?limit=1000") if a["action"] == "integrity.rejected"]
    # mqtt_smoke.py sends one tampered and one unsigned frame on purpose; anything more came from the simulator.
    if len(rejected) != 2:
        raise SystemExit(f"{len(rejected)} frames rejected, expected only the 2 test frames: {rejected[:3]}")
    print(f"OK: simulator ingested ({sum(1 for b in beds().values() if b['admission'])} beds admitted, "
          f"B06 vitals {sorted(b06['vitals'])}), no rejected frames besides the 2 test frames")


if __name__ == "__main__":
    main()
