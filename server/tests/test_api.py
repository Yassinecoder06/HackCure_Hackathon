from __future__ import annotations

from borj_server.config import Settings
from borj_server.main import create_app
from fastapi.testclient import TestClient

from .conftest import SEED, openapi_validator


def client(tmp_path) -> TestClient:
    settings = Settings(seed_path=SEED, db_path=str(tmp_path / "borj.sqlite"), mqtt_enabled=False)
    return TestClient(create_app(settings))


def test_health(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_snapshot_endpoint(tmp_path, make_event):
    with client(tmp_path) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        body = c.get("/api/v1/wards/W1/snapshot").json()

    assert not list(openapi_validator("WardSnapshot").iter_errors(body))
    b04 = next(b for b in body["beds"] if b["bed"] == "B04")
    assert b04["admission"]["patientRef"] == "Patient 04"
    assert b04["room"] == "R2"


def test_unknown_ward_is_404(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/api/v1/wards/W9/snapshot").status_code == 404


def test_twin_survives_restart(tmp_path, make_event):
    with client(tmp_path) as c:
        c.app.state.ingestor.handle(*make_event("binding"))
    with client(tmp_path) as c:  # new app, same database: twin rebuilt from the log
        body = c.get("/api/v1/wards/W1/snapshot").json()
    assert next(b for b in body["beds"] if b["bed"] == "B04")["admission"]["admissionId"] == "ADM-0004"
