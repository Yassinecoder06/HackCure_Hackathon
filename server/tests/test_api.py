from __future__ import annotations

from borj_inference.main import create_app as create_inference_app
from borj_server.config import Settings
from borj_server.main import create_app
from fastapi.testclient import TestClient

from .conftest import SEED, openapi_validator


def client(tmp_path, with_inference: bool = False) -> TestClient:
    """Ward server app. with_inference=True plugs in the real inference app in-process."""
    settings = Settings(seed_path=SEED, db_path=str(tmp_path / "borj.sqlite"), mqtt_enabled=False,
                        inference_url=None)
    inference_http = TestClient(create_inference_app()) if with_inference else None
    return TestClient(create_app(settings, inference_http=inference_http))


def bed(body: dict, bed_id: str) -> dict:
    return next(b for b in body["beds"] if b["bed"] == bed_id)


def test_health(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_snapshot_endpoint(tmp_path, make_event):
    with client(tmp_path) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        body = c.get("/api/v1/wards/W1/snapshot").json()

    assert not list(openapi_validator("WardSnapshot").iter_errors(body))
    b04 = bed(body, "B04")
    assert b04["admission"]["patientRef"] == "Patient 04"
    assert b04["room"] == "R2"
    assert bed(body, "B01")["news2Status"] == "not_admitted"


def test_unknown_ward_is_404(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/api/v1/wards/W9/snapshot").status_code == 404


def test_twin_survives_restart(tmp_path, make_event):
    with client(tmp_path) as c:
        c.app.state.ingestor.handle(*make_event("binding"))
    with client(tmp_path) as c:  # new app, same database: twin rebuilt from the log
        body = c.get("/api/v1/wards/W1/snapshot").json()
    assert bed(body, "B04")["admission"]["admissionId"] == "ADM-0004"


def test_snapshot_carries_news2_from_inference(tmp_path, make_event):
    with client(tmp_path, with_inference=True) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        ingestor.handle(*make_event("vitals.device"))  # resp 22, SpO2 93, BP 104, pulse 112, temp 38.4
        ingestor.handle(*make_event("vitals.manual"))  # alert, on air
        ingestor.clock.update_from_message({"simTs": "2026-10-10T22:10:00Z"})
        body = c.get("/api/v1/wards/W1/snapshot").json()

    assert not list(openapi_validator("WardSnapshot").iter_errors(body))
    b04 = bed(body, "B04")
    assert b04["news2Status"] == "ok"
    news2 = b04["news2"]
    assert (news2["total"], news2["band"], news2["complete"]) == (8, "high", True)
    assert 0.5 < news2["confidence"]["value"] < 1.0  # readings are a few minutes old


def test_stale_readings_make_the_score_partial(tmp_path, make_event):
    """Invariant 5 end to end: twin freshness -> inference -> labelled partial score."""
    with client(tmp_path, with_inference=True) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        ingestor.handle(*make_event("vitals.device"))
        ingestor.handle(*make_event("vitals.manual"))
        ingestor.clock.update_from_message({"simTs": "2026-10-10T22:30:00Z"})  # device data now 27 min old
        news2 = bed(c.get("/api/v1/wards/W1/snapshot").json(), "B04")["news2"]

    assert news2["complete"] is False
    assert set(news2["stale"]) == {"resp_rate", "spo2", "sys_bp", "pulse", "temp_c"}
    assert news2["total"] == 0
    assert news2["label"].startswith("Partial NEWS2")


def test_inference_down_shows_unavailable_never_a_guess(tmp_path, make_event):
    with client(tmp_path) as c:  # no inference service configured
        c.app.state.ingestor.handle(*make_event("binding"))
        body = c.get("/api/v1/wards/W1/snapshot").json()
    b04 = bed(body, "B04")
    assert (b04["news2Status"], b04["news2"]) == ("unavailable", None)
