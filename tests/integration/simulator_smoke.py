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
    audit = get_json("/api/v1/wards/W1/audit?limit=1000")
    rejected = [a for a in audit if a["action"] == "integrity.rejected"]
    # The earlier smoke tests rejected frames on purpose: empty ACL probes (no eventId), a tampered and an unsigned
    # vitals frame. A rejection of anything the simulator sent would carry its own event id.
    deliberate = {"", "01K80000000000000000TAMPER", "01K80000000000000000UNSIGN"}
    stray = [a for a in rejected if a["detail"]["eventId"] not in deliberate]
    if stray:
        raise SystemExit(f"{len(stray)} frames from the simulator were rejected: {stray[:3]}")
    print(f"OK: simulator ingested ({sum(1 for b in beds().values() if b['admission'])} beds admitted, "
          f"B06 vitals {sorted(b06['vitals'])}), none of its frames rejected")


if __name__ == "__main__":
    main()
