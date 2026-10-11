"""Endpoints added by the app teams: who may call them, what is audited, and what browsers may reach them."""

from __future__ import annotations

from borj_server.main import PRIVATE_ORIGIN

from .conftest import login, make_client

BASE = "/api/v1/wards/W1"


def admit_b06(c, make_event):
    c.app.state.ingestor.handle(*make_event("binding", bed="B06", admissionId="ADM-0006"))


def test_presence_you_can_mark_yourself_only_the_charge_nurse_marks_others(tmp_path):
    body = {"onWard": False, "reason": "break_start", "expectedBackMin": 15}
    with make_client(tmp_path, auto_suggest=False) as c:
        login(c, "N1")
        assert c.post(f"{BASE}/staff/N1/presence", json=body).status_code == 201
        assert c.post(f"{BASE}/staff/CN1/presence", json=body).status_code == 403  # a nurse can't mark the charge nurse
        login(c, "CN1")
        assert c.post(f"{BASE}/staff/N1/presence", json={"onWard": True, "reason": "returned"}).status_code == 201


def test_demo_trigger_is_off_by_default_and_charge_nurse_only_and_audited(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        admit_b06(c, make_event)
        login(c, "CN1")
        assert c.post("/api/v1/demo/trigger-peak").status_code == 404  # disabled unless BORJ_DEMO_ENDPOINTS=1
    (tmp_path / "demo").mkdir()
    with make_client(tmp_path / "demo", auto_suggest=False, demo_endpoints=True) as c:
        admit_b06(c, make_event)
        login(c, "N1")
        assert c.post("/api/v1/demo/trigger-peak").status_code == 403
        login(c, "CN1")
        assert c.post("/api/v1/demo/trigger-peak").status_code == 200
        calls = [x for x in c.get(f"{BASE}/snapshot").json()["calls"] if x["bed"] == "B06"]
        audit = c.app.state.ingestor.store.audit_entries()
    assert len(calls) == 1 and calls[0]["kind"] == "assist"  # the call really exists, not just an "ok"
    assert any(a["actor"] == "CN1" and a["action"] == "demo.trigger_peak" for a in audit)


def test_demo_trigger_refuses_an_empty_bed(tmp_path):
    with make_client(tmp_path, auto_suggest=False, demo_endpoints=True) as c:
        login(c, "CN1")
        assert c.post("/api/v1/demo/trigger-peak").status_code == 409  # nothing in B06: never a silent "ok"


def test_reading_doctor_orders_is_audited(tmp_path):
    with make_client(tmp_path, auto_suggest=False) as c:
        login(c, "N1")
        assert c.get(f"{BASE}/doctor/orders").status_code == 200
        audit = c.app.state.ingestor.store.audit_entries()
    assert any(a["actor"] == "N1" and a["action"] == "doctor.orders_read" for a in audit)


def test_cors_allows_local_and_lan_origins_only(tmp_path):
    import re

    for ok in ("http://localhost:5173", "http://127.0.0.1:5174", "http://192.168.1.20:5173", "http://10.0.0.5",
               "http://172.20.3.4:80"):
        assert re.match(PRIVATE_ORIGIN, ok), ok
    for bad in ("https://evil.example.org", "http://localhost.evil.org", "http://172.32.0.1", "http://192.168.1.1.evil.org"):
        assert not re.match(PRIVATE_ORIGIN, bad), bad
    with make_client(tmp_path, cors_origins="https://borj.example.org") as c:
        def allowed(origin: str) -> str | None:
            r = c.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
            return r.headers.get("access-control-allow-origin")
        assert allowed("http://localhost:5173") == "http://localhost:5173"
        assert allowed("https://borj.example.org") == "https://borj.example.org"
        assert allowed("https://evil.example.org") is None
