"""Manual fast entry of observations: POST .../beds/{bed}/observations."""

from __future__ import annotations

import borj_contracts as bc

from .conftest import login, make_client, openapi_validator

BASE = "/api/v1/wards/W1"


def test_manual_entry_becomes_a_manual_vitals_event(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))  # ADM-0004 in B04
        login(c, "N1")
        resp = c.post(f"{BASE}/beds/B04/observations", json={"consciousness": "V", "on_oxygen": True})
        assert resp.status_code == 201, resp.text
        assert not list(openapi_validator("Accepted").iter_errors(resp.json()))
        bed = next(b for b in c.get(f"{BASE}/snapshot").json()["beds"] if b["bed"] == "B04")
        stored = next(e for e in ingestor.store.events() if e.payload["eventId"] == resp.json()["eventId"])
        audit = ingestor.store.audit_entries()

    assert (bed["vitals"]["consciousness"]["value"], bed["vitals"]["consciousness"]["sourceType"]) == ("V", "manual")
    assert bed["vitals"]["on_oxygen"]["value"] is True
    assert "resp_rate" not in bed["vitals"]  # not entered, so absent: never 0 (invariant 5)
    bc.validate("vitals", stored.payload)
    assert stored.payload["staffId"] == "N1" and set(stored.payload["params"]) == {"consciousness", "on_oxygen"}
    assert stored.payload["quality"]["stale_after_s"] == c.app.state.observations_config.stale_after_s
    assert any(a["actor"] == "N1" and a["action"] == "vitals.manual_entry" and a["target"] == "B04" for a in audit)


def test_manual_entry_rejects_bad_input(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        c.app.state.ingestor.handle(*make_event("binding"))
        login(c, "N1")
        for body in ({}, {"spo2": 101}, {"consciousness": "X"}, {"news2": 5}, {"resp_rate": 18.5}):
            assert c.post(f"{BASE}/beds/B04/observations", json=body).status_code == 422, body
        assert c.post(f"{BASE}/beds/B05/observations", json={"pulse": 80}).status_code == 409  # nobody admitted
        assert c.post(f"{BASE}/beds/B99/observations", json={"pulse": 80}).status_code == 404
        login(c, "DR1")
        assert c.post(f"{BASE}/beds/B04/observations", json={"pulse": 80}).status_code == 403
