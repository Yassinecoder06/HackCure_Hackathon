"""Assignment suggestions are advisory: only a charge nurse's approval changes anything (invariant 1)."""

from __future__ import annotations

from .conftest import login, make_client, openapi_validator


def setup_ward(ingestor, make_event, nurses=("N1", "N2"), beds=("B01", "B02", "B03")):
    for n in nurses:
        ingestor.handle(*make_event("staff-presence", staffId=n, onWard=True, reason="shift_start",
                                    ts="2026-10-10T21:55:00Z"))
    for i, bed in enumerate(beds):
        ingestor.handle(*make_event("binding", bed=bed, admissionId=f"ADM-{bed}", patientRef=f"Patient {bed}",
                                    acuity=2 + i % 2, ts="2026-10-10T22:00:00Z"))


def test_suggest_then_approve(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        setup_ward(ingestor, make_event)
        login(c, "N1")
        resp = c.post("/api/v1/wards/W1/assignments/suggestions")
        assert resp.status_code == 201, resp.text
        suggestion = resp.json()
        assert not list(openapi_validator("AssignmentSuggestion").iter_errors(suggestion))
        assert suggestion["status"] == "pending"
        assert {ch["bed"] for ch in suggestion["changes"]} == {"B01", "B02", "B03"}
        assert suggestion["reasons"] and 0 < suggestion["confidence"]["value"] <= 1
        assert ingestor.twin.assignments == {}  # a suggestion changes nothing

        url = f"/api/v1/wards/W1/assignments/suggestions/{suggestion['suggestionId']}/decision"
        assert c.post(url, json={"decision": "approve"}).status_code == 403  # a nurse cannot approve

        login(c, "CN1")
        decided = c.post(url, json={"decision": "approve", "reason": "start of shift"}).json()
        assert (decided["status"], decided["decidedBy"]) == ("approved", "CN1")
        assert c.post(url, json={"decision": "approve"}).status_code == 409

        snap = c.get("/api/v1/wards/W1/snapshot").json()
        audit = [(e["actor"], e["action"]) for e in ingestor.store.audit_entries()]

    assigned = {b["bed"]: b.get("assignedNurse") for b in snap["beds"] if b["admission"]}
    assert set(assigned.values()) <= {"N1", "N2"} and None not in assigned.values()
    staff = {s["staffId"]: s["assignedBeds"] for s in snap["staff"]}
    assert sorted(staff["N1"] + staff["N2"]) == ["B01", "B02", "B03"]
    assert ("system", "suggestion.created") in audit and ("CN1", "suggestion.approved") in audit


def test_reject_and_stale_and_superseded(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        setup_ward(ingestor, make_event)
        login(c, "CN1")
        first = c.post("/api/v1/wards/W1/assignments/suggestions").json()
        second = c.post("/api/v1/wards/W1/assignments/suggestions").json()
        base = "/api/v1/wards/W1/assignments/suggestions"
        assert c.post(f"{base}/{first['suggestionId']}/decision", json={"decision": "approve"}).status_code == 409
        assert c.get(f"{base}?status=pending").json()[0]["suggestionId"] == second["suggestionId"]

        # Someone else's approved change lands first: the pending plan is now stale.
        ingestor.handle(*make_event("assignment", changes=[{"bed": "B01", "toStaffId": "N2"}]))
        stale = c.post(f"{base}/{second['suggestionId']}/decision", json={"decision": "approve"})
        assert (stale.status_code, stale.json()["error"]) == (409, "stale_suggestion")

        third = c.post(base).json()
        rejected = c.post(f"{base}/{third['suggestionId']}/decision",
                          json={"decision": "reject", "reason": "N2 is on break soon"}).json()
        assert (rejected["status"], rejected["decisionReason"]) == ("rejected", "N2 is on break soon")


def drain(service) -> None:
    """Automatic suggestions run on one worker thread: a no-op queued behind them returns when they are done."""
    service._executor.submit(lambda: None).result(timeout=15)


def test_nurse_called_away_triggers_a_suggestion_automatically(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True) as c:
        ingestor = c.app.state.ingestor
        service = c.app.state.assignment
        setup_ward(ingestor, make_event, nurses=("N1", "N2", "N3"))
        login(c, "CN1")
        drain(service)  # the burst of admissions gives one (debounced) suggestion, possibly a second behind it
        drain(service)
        first = service.list("pending")[0]
        c.post(f"/api/v1/wards/W1/assignments/suggestions/{first['suggestionId']}/decision",
               json={"decision": "approve"})
        for leftover in service.list("pending"):  # settle what the admissions left, so only the new one remains
            c.post(f"/api/v1/wards/W1/assignments/suggestions/{leftover['suggestionId']}/decision",
                   json={"decision": "reject", "reason": "superseded in test"})

        ingestor.handle(*make_event("staff-presence", staffId="N3", onWard=False, reason="called_away",
                                    ts="2026-10-10T23:00:00Z"))
        drain(service)
        pending = service.list("pending")
    assert pending and pending[0]["trigger"] == "N3: called away"
    assert all(ch["toStaffId"] in {"N1", "N2"} for ch in pending[0]["changes"])
