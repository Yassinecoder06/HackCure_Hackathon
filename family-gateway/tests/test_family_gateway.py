"""family-gateway: the allow-list at the door, consent first, immediate revocation, rate limits (invariants 2-4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from borj_family_gateway.app import Settings, create_app
from borj_server.family import hash_code
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "synthetic-publisher-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
CODE = "482915"


def ulid(n: int) -> str:
    return f"01K80000000000000000{n:06d}"  # 26 characters, digits only: always a valid ULID


INVITE_ID = ulid(1)
SECOND_INVITE_ID = ulid(2)


def example(name: str) -> dict:
    return json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text(encoding="utf-8"))


def invite(**overrides) -> dict:
    payload = {**example("family-invite"), "inviteId": INVITE_ID, "codeHash": hash_code(CODE),
               "consentRecordedAt": "2026-10-10T18:00:00Z", "expiresAt": "2026-10-24T18:00:00Z"}
    return {**payload, **overrides}


def update(n: int = 1, **overrides) -> dict:
    payload = {**example("family-update"), "updateId": ulid(100 + n)}
    return {**payload, **overrides}


def make_gateway(tmp_path, **overrides):
    settings = Settings(publisher_token=TOKEN, data_key=b"K" * 32, db_path=str(tmp_path / "family.sqlite"),
                        **overrides)
    return TestClient(create_app(settings))


def seed(c) -> None:
    assert c.post("/ingest/v1/invites", json=invite(), headers=AUTH).status_code == 202


def redeem(c, code=CODE, invite_id=INVITE_ID):
    body = {"code": code, **({"inviteId": invite_id} if invite_id else {})}
    return c.post("/family/v1/redeem", json=body)


def feed(c, token):
    return c.get("/family/v1/feed", headers={"Authorization": f"Bearer {token}"})


def test_only_the_ward_publisher_can_push(tmp_path):
    with make_gateway(tmp_path) as c:
        assert c.post("/ingest/v1/invites", json=invite()).status_code == 401
        assert c.post("/ingest/v1/invites", json=invite(), headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.post("/ingest/v1/updates", json=update()).status_code == 401
        assert c.get("/ingest/v1/views?linkId=FL-7Q2M").status_code == 401


@pytest.mark.parametrize("extra", [
    {"vitals": {"pulse": 112}}, {"news2": 8}, {"drug": "Paracetamol"}, {"dose": "1 g"}, {"staffId": "N1"},
    {"bed": "B04"}, {"location": "room 3"}, {"approval": {"approved": True, "approvedAt": "2026-10-10T20:04:30Z",
                                                          "approvedBy": "N1"}},
])
def test_nothing_off_the_allow_list_gets_in(tmp_path, extra):
    """Invariant 2: a forbidden field in an update is refused, nested or not."""
    with make_gateway(tmp_path) as c:
        seed(c)
        assert c.post("/ingest/v1/updates", json={**update(), **extra}, headers=AUTH).status_code == 422


@pytest.mark.parametrize("text", ["Her SpO2 is 93% today.", "Tension 120/80, all fine.", "Fièvre à 38,5 cette nuit.",
                                  "His NEWS2 went down.", "He got his mg this morning."])
def test_clinical_text_is_refused_even_if_the_ward_let_it_through(tmp_path, text):
    with make_gateway(tmp_path) as c:
        seed(c)
        refused = c.post("/ingest/v1/updates", json=update(text=text), headers=AUTH)
        assert refused.status_code == 422 and "clinical data" in refused.json()["detail"]
        assert c.post("/ingest/v1/updates", json=update(text="A quiet evening."), headers=AUTH).status_code == 202


def test_consent_first_no_update_without_a_live_invite(tmp_path):
    with make_gateway(tmp_path) as c:
        assert c.post("/ingest/v1/updates", json=update(), headers=AUTH).status_code == 409  # no invite at all
        seed(c)
        assert c.post("/ingest/v1/updates", json=update(), headers=AUTH).status_code == 202
        assert c.post("/ingest/v1/updates", json=update(2, linkId="FL-OTHER"), headers=AUTH).status_code == 409


def test_redeem_with_qr_and_code_then_read_the_feed(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        c.post("/ingest/v1/updates", json=update(1), headers=AUTH)
        meal = update(2, kind="meal_served", publishedAt="2026-10-10T20:10:00Z")
        del meal["text"]  # a meal update carries no free text
        c.post("/ingest/v1/updates", json=meal, headers=AUTH)
        wrong = redeem(c, code="000000")
        assert wrong.status_code == 401
        ok = redeem(c)
        assert ok.status_code == 200
        token = ok.json()["sessionToken"]
        seen = feed(c, token)
        assert seen.status_code == 200
        body = seen.json()
        assert [u["kind"] for u in body["updates"]] == ["meal_served", "nurse_note"]  # newest first
        assert body["wardContact"] and "emergency" in body["notice"].lower()
        # the response matches the contract exactly (additionalProperties false: nothing extra can leak)
        spec = yaml.safe_load((ROOT / "contracts" / "family-gateway.openapi.yaml").read_text(encoding="utf-8"))
        assert not list(Draft202012Validator(spec["components"]["schemas"]["FamilyFeed"]).iter_errors(body))
        french = c.get("/family/v1/feed", headers={"Authorization": f"Bearer {token}", "Accept-Language": "fr-TN"})
        assert "urgence" in french.json()["notice"]


def test_the_one_time_code_works_once(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        assert redeem(c).status_code == 200
        assert redeem(c).status_code == 401  # used up: a second device needs a new invite


def test_code_only_redeem_finds_the_invite(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        assert redeem(c, invite_id=None).status_code == 200


def test_feed_only_shows_the_kinds_the_patient_consented_to(tmp_path):
    with make_gateway(tmp_path) as c:
        c.post("/ingest/v1/invites", json=invite(allowedKinds=["visiting_info"]), headers=AUTH)
        c.post("/ingest/v1/updates", json=update(), headers=AUTH)  # a nurse_note: not consented
        c.post("/ingest/v1/updates", json={"schemaVersion": 1, "updateId": ulid(199),
                                           "linkId": "FL-7Q2M", "kind": "visiting_info", "text": "Visits 13:00-15:00.",
                                           "publishedAt": "2026-10-10T20:20:00Z",
                                           "approval": {"approved": True, "approvedAt": "2026-10-10T20:19:00Z"}},
                headers=AUTH)
        body = feed(c, redeem(c).json()["sessionToken"]).json()
        assert body["allowedKinds"] == ["visiting_info"]
        assert [u["kind"] for u in body["updates"]] == ["visiting_info"]


def test_revocation_is_immediate_and_deletes_the_updates(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        c.post("/ingest/v1/updates", json=update(), headers=AUTH)
        token = redeem(c).json()["sessionToken"]
        assert feed(c, token).status_code == 200
        revocation = {**example("family-revocation"), "linkId": "FL-7Q2M", "reason": "discharge",
                      "effectiveAt": "2026-10-11T08:00:00Z"}
        revocation.pop("inviteId", None)
        assert c.post("/ingest/v1/revocations", json=revocation, headers=AUTH).status_code == 202
        assert feed(c, token).status_code == 401           # the open session died with it
        assert redeem(c).status_code == 401
        assert c.post("/ingest/v1/updates", json=update(3), headers=AUTH).status_code == 409
        assert b"quiet evening" not in c.app.state.store.raw_dump()  # nothing left to read
        again = c.post("/ingest/v1/revocations", json=revocation, headers=AUTH)
        assert again.json() == {"applied": False}  # idempotent


def test_revoking_one_invite_leaves_the_others(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        c.post("/ingest/v1/invites", json=invite(inviteId=SECOND_INVITE_ID, relativeLabel="Son",
                                                 codeHash=hash_code("111222")), headers=AUTH)
        c.post("/ingest/v1/updates", json=update(), headers=AUTH)
        daughter = redeem(c).json()["sessionToken"]
        son = redeem(c, code="111222", invite_id=SECOND_INVITE_ID).json()["sessionToken"]
        revocation = {**example("family-revocation"), "linkId": "FL-7Q2M", "inviteId": INVITE_ID,
                      "reason": "consent_withdrawn", "effectiveAt": "2026-10-11T08:00:00Z"}
        c.post("/ingest/v1/revocations", json=revocation, headers=AUTH)
        assert feed(c, daughter).status_code == 401 and feed(c, son).status_code == 200


def test_expired_invite_is_refused_on_the_wards_own_clock(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        # the ward's clock moves past the invite's expiry (here via a later update from the ward)
        c.post("/ingest/v1/updates", json=update(4, publishedAt="2026-10-25T09:00:00Z"), headers=AUTH)
        assert redeem(c).status_code == 401


def test_brute_forcing_is_rate_limited_and_locks_the_invite(tmp_path):
    with make_gateway(tmp_path, redeem_attempts=3, lock_invite_after=5) as c:
        seed(c)
        assert [redeem(c, code=f"00000{i}").status_code for i in range(3)] == [401, 401, 401]
        blocked = redeem(c, code="000009")
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
        assert redeem(c).status_code == 429  # even the right code, while blocked
    (tmp_path / "b").mkdir()
    with make_gateway(tmp_path / "b", redeem_attempts=100, lock_invite_after=5) as c:
        seed(c)
        for i in range(5):
            redeem(c, code=f"00001{i}")
        assert redeem(c).status_code == 401  # five wrong guesses from anywhere and the invite is revoked


def test_nurse_text_is_encrypted_at_rest_and_views_are_audited(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        c.post("/ingest/v1/updates", json=update(), headers=AUTH)
        token = redeem(c).json()["sessionToken"]
        feed(c, token)
        feed(c, token)
        dump = c.app.state.store.raw_dump()
        assert b"quiet evening" not in dump and CODE.encode() not in dump and token.encode() not in dump
        views = c.get("/ingest/v1/views", params={"linkId": "FL-7Q2M"}, headers=AUTH).json()
        assert [v["what"] for v in views] == ["feed", "feed", "redeem"]
        assert all(set(v) == {"ts", "session", "client", "what"} for v in views)  # no address, no token


def test_invalid_session_and_garbage_are_refused(tmp_path):
    with make_gateway(tmp_path) as c:
        seed(c)
        assert c.get("/family/v1/feed").status_code == 401
        assert feed(c, "not-a-token").status_code == 401
        assert c.post("/family/v1/redeem", json={"code": "1"}).status_code == 422
        assert c.post("/family/v1/redeem", json={"code": "123456", "inviteId": "../x"}).status_code == 422
        assert c.post("/family/v1/redeem", json={"code": "123456", "extra": 1}).status_code in (200, 401, 422)


def test_the_gateway_has_no_route_that_reads_ward_data(tmp_path):
    with make_gateway(tmp_path) as c:
        paths = {route.path for route in c.app.routes}
    ward_words = ("vitals", "beds", "snapshot", "wards", "news2")
    assert paths and not any(word in path for path in paths for word in ward_words)
