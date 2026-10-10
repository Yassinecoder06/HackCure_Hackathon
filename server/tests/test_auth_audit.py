"""Login, tokens and the hash-chained access audit (ADR 0010, invariant 11)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from borj_server.auth import Auth, AuthError, TooManyAttempts
from borj_server.crypto import DataCipher
from borj_server.store import EventStore, audit
from borj_server.timeutil import utcnow
from sqlalchemy import update

from .conftest import TEST_PINS, login, make_client, openapi_validator

KEY = b"k" * 32


def make_auth(**kwargs) -> Auth:
    return Auth({"N1": "222222"}, {"N1": "nurse", "CN1": "charge_nurse"}, KEY, ttl_s=3600, **kwargs)


def test_login_issues_a_token_naming_the_staff_member():
    auth = make_auth()
    token, _ = auth.login("N1", "222222")
    principal = auth.verify(token)
    assert (principal.staff_id, principal.role) == ("N1", "nurse")


@pytest.mark.parametrize(("staff_id", "secret"), [("N1", "000000"), ("CN1", "222222"), ("X9", "222222")])
def test_bad_credentials_are_refused(staff_id, secret):
    with pytest.raises(AuthError):
        make_auth().login(staff_id, secret)


def test_repeated_failures_lock_the_account_then_release():
    clock = [utcnow()]
    auth = make_auth(max_failures=3, lockout_s=300, now=lambda: clock[0])
    for _ in range(3):
        with pytest.raises(AuthError):
            auth.login("N1", "000000")
    with pytest.raises(TooManyAttempts):
        auth.login("N1", "222222")  # even the right PIN, while locked
    clock[0] += timedelta(seconds=301)
    assert auth.login("N1", "222222")


def test_expired_or_forged_tokens_are_refused():
    past = utcnow() - timedelta(hours=5)
    expired, _ = make_auth(now=lambda: past).login("N1", "222222")
    with pytest.raises(AuthError):
        make_auth().verify(expired)
    forged, _ = Auth({"N1": "222222"}, {"N1": "nurse"}, b"x" * 32, ttl_s=3600).login("N1", "222222")
    with pytest.raises(AuthError):
        make_auth().verify(forged)


def test_patient_data_requires_login(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/api/v1/wards/W1/snapshot").status_code == 401
        c.headers["Authorization"] = "Bearer not-a-token"
        resp = c.get("/api/v1/wards/W1/snapshot")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


def test_login_endpoint_and_lockout(tmp_path):
    with make_client(tmp_path) as c:
        body = login(c, "N1")
        assert body["staff"]["staffId"] == "N1"
        for _ in range(5):
            assert c.post("/api/v1/auth/login", json={"staffId": "DR1", "secret": "999999"}).status_code == 401
        locked = c.post("/api/v1/auth/login", json={"staffId": "DR1", "secret": TEST_PINS["DR1"]})
    assert locked.status_code == 429


def test_every_access_is_audited_with_a_named_actor(tmp_path):
    with make_client(tmp_path) as c:
        login(c, "N1")
        c.get("/api/v1/wards/W1/snapshot")
        login(c, "CN1")
        entries = c.get("/api/v1/wards/W1/audit").json()

    actions = [(e["actor"], e["action"]) for e in reversed(entries)]
    assert actions == [("N1", "auth.login"), ("N1", "snapshot.read"), ("CN1", "auth.login"), ("CN1", "audit.read")]
    validator = openapi_validator("AuditEntry")
    assert all(not list(validator.iter_errors(e)) for e in entries)


def test_only_the_charge_nurse_reads_the_audit_log(tmp_path):
    with make_client(tmp_path) as c:
        login(c, "N1")
        assert c.get("/api/v1/wards/W1/audit").status_code == 403
        assert c.get("/api/v1/wards/W1/audit/verify").status_code == 403


def test_audit_chain_verifies_and_detects_tampering():
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    for i in range(5):
        store.audit("N1", "snapshot.read", "W1", {"i": i})
    assert store.verify_audit_chain() == {"valid": True, "entries": 5}

    with store.engine.begin() as conn:  # someone edits who did it
        conn.execute(update(audit).where(audit.c.seq == 3).values(actor="CN1"))
    result = store.verify_audit_chain()
    assert result["valid"] is False
    assert result["firstBrokenAuditId"] == store.audit_entries(5)[2]["auditId"]


def test_deleting_an_audit_entry_breaks_the_chain():
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    for i in range(3):
        store.audit("N1", "snapshot.read", "W1", {"i": i})
    with store.engine.begin() as conn:
        conn.execute(audit.delete().where(audit.c.seq == 2))
    assert store.verify_audit_chain()["valid"] is False


def test_verify_endpoint(tmp_path):
    with make_client(tmp_path) as c:
        login(c, "CN1")
        c.get("/api/v1/wards/W1/snapshot")
        result = c.get("/api/v1/wards/W1/audit/verify").json()
    assert result["valid"] is True
    assert result["entries"] >= 2
