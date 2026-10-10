from __future__ import annotations

from .conftest import login, make_client, openapi_validator


def test_one_tap_ack_and_resolve_over_rest(tmp_path, make_event):
    with make_client(tmp_path) as c:
        login(c, "N1")
        c.app.state.ingestor.handle(*make_event("call"))
        acked = c.post("/api/v1/wards/W1/calls/C-B06-0001/ack")
        assert acked.status_code == 200, acked.text
        assert not list(openapi_validator("Call").iter_errors(acked.json()))
        assert (acked.json()["state"], acked.json()["acknowledgedBy"]) == ("acknowledged", "N1")

        assert c.post("/api/v1/wards/W1/calls/C-B06-0001/resolve").json()["state"] == "resolved"
        assert c.post("/api/v1/wards/W1/calls/C-B06-0001/resolve").status_code == 409
        assert c.post("/api/v1/wards/W1/calls/NOPE/ack").status_code == 404
        snapshot = c.get("/api/v1/wards/W1/snapshot").json()
        audit = [(e["actor"], e["action"]) for e in c.app.state.ingestor.store.audit_entries()]

    assert snapshot["calls"] == []
    assert ("N1", "call.acknowledge") in audit and ("N1", "call.resolve") in audit


def test_news2_alert_can_be_acknowledged(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True) as c:
        login(c, "CN1")
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        ingestor.handle(*make_event("vitals.device"))
        ingestor.handle(*make_event("vitals.manual"))
        ingestor.clock.update_from_message({"simTs": "2026-10-10T22:10:00Z"})
        alerts = c.get("/api/v1/wards/W1/snapshot").json()["alerts"]
        validator = openapi_validator("Alert")
        assert all(not list(validator.iter_errors(a)) for a in alerts)
        high = next(a for a in alerts if a["type"] == "news2_high")
        assert high["priority"] == "critical" and "acknowledgedBy" not in high
        assert high["confidence"]["value"] > 0.5

        acked = c.post(f"/api/v1/wards/W1/alerts/{high['alertId']}/ack").json()
        assert acked["acknowledgedBy"] == "CN1"
        assert c.post("/api/v1/wards/W1/alerts/news2-0000000000000000/ack").status_code == 404


def test_stream_carries_call_and_alert_messages(tmp_path, make_event):
    with make_client(tmp_path, stream_metrics_interval_s=5) as c:
        token = login(c, "N1")["token"]
        ingestor = c.app.state.ingestor
        with c.websocket_connect("/api/v1/wards/W1/stream", subprotocols=["bearer", token]) as ws:
            assert ws.receive_json()["type"] == "snapshot"
            ingestor.handle(*make_event("call"))  # pressed 22:12:40
            ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:17:40Z",
                                                  "speed": 1, "scenario": "t", "running": True})
            seen = {}
            for _ in range(40):
                message = ws.receive_json()
                assert not list(openapi_validator("StreamMessage").iter_errors(message))
                if message["type"] == "call":
                    seen["call"] = message["data"]
                if message["type"] == "alert" and message["data"]["type"] == "call_escalated":
                    seen["alert"] = message["data"]
                if seen.get("alert", {}).get("priority") == "critical":
                    break
    assert seen["call"]["callId"] == "C-B06-0001"
    assert seen["alert"]["escalatedTo"] == ["nurse", "charge_nurse", "doctor"]
