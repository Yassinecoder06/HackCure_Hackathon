from __future__ import annotations

from .conftest import login, make_client, openapi_validator


def on_ward(ingestor, make_event, staff=("N1", "N2", "N3", "CA1")):
    for s in staff:
        ingestor.handle(*make_event("staff-presence", staffId=s, onWard=True, reason="shift_start",
                                    ts="2026-10-10T21:55:00Z"))
    for bed in ("B01", "B02", "B03", "B04", "B05", "B06"):
        ingestor.handle(*make_event("binding", bed=bed, admissionId=f"ADM-{bed}", ts="2026-10-10T22:00:00Z"))


def test_nurse_called_away_what_if(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        on_ward(c.app.state.ingestor, make_event)
        login(c, "CN1")
        body = {"disruptions": [{"type": "staff_leaves", "atMin": 30, "staffId": "N3"},
                                {"type": "call_surge", "atMin": 0, "callsPerHour": 20}],
                "horizonMin": 180, "seeds": 30}
        resp = c.post("/api/v1/wards/W1/whatif/runs", json=body)
        audit = [(e["actor"], e["action"]) for e in c.app.state.ingestor.store.audit_entries()]
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert not list(openapi_validator("WhatIfResult").iter_errors(result))
    assert result["seeds"] == 30 and result["horizonMin"] == 180
    assert (result["scenario"]["nurse_utilization"]["median"]
            > result["baseline"]["nurse_utilization"]["median"])
    assert any("NEWS2" in a for a in result["assumptions"])  # beds without a score are disclosed
    assert ("CN1", "whatif.run") in audit


def test_what_if_validation_and_unavailable(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        on_ward(c.app.state.ingestor, make_event)
        login(c, "CN1")
        bad = c.post("/api/v1/wards/W1/whatif/runs",
                     json={"disruptions": [{"type": "staff_leaves", "atMin": 0, "staffId": "DR1"}]})
        assert bad.status_code == 422
    with make_client(tmp_path, auto_suggest=False) as c:  # no inference service
        login(c, "CN1")
        down = c.post("/api/v1/wards/W1/whatif/runs", json={"disruptions": []})
    assert down.status_code == 503
