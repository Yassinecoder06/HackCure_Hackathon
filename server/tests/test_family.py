"""Family Care Link, ward side: consent first, privacy filter, outbound-only publishing (invariants 2-4)."""

from __future__ import annotations

import json

import httpx
from borj_server.family import verify_code
from borj_server.family_publisher import FamilyPublisher, outbound_items

from .conftest import login, make_client, openapi_validator

BASE = "/api/v1/wards/W1"
ADM = f"{BASE}/admissions/ADM-0004/family"


def setup(c, make_event):
    ingestor = c.app.state.ingestor
    ingestor.handle(*make_event("binding"))                    # ADM-0004 in B04
    ingestor.handle(*make_event("vitals.device"))              # pulse 112, SpO2 93 ...
    ingestor.handle(*make_event("prescription", times=["23:00"]))  # Paracetamol
    login(c, "N1")
    return ingestor


def consent(c, kinds=("visiting_info", "meal_served", "nurse_note", "ward_contact")) -> dict:
    resp = c.post(f"{ADM}/consents", json={"relativeLabel": "Daughter", "allowedKinds": list(kinds),
                                           "givenBy": "patient"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_consent_then_invite_with_one_time_code(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = setup(c, make_event)
        given = consent(c)
        assert not list(openapi_validator("Consent").iter_errors(given))
        invite = c.post(f"{ADM}/invites", json={"consentId": given["consentId"]})
        assert invite.status_code == 201, invite.text
        body = invite.json()
        assert not list(openapi_validator("InviteCreated").iter_errors(body))
        assert c.post(f"{ADM}/invites", json={"consentId": given["consentId"]}).status_code == 409  # one per relative
        items = outbound_items(ingestor.store)
        log = json.dumps([e.payload for e in ingestor.store.events()])

    sent = items[-1]
    assert sent.target == "invites" and sent.payload["linkId"] == body["linkId"]
    assert verify_code(body["oneTimeCode"], sent.payload["codeHash"])
    assert not verify_code("000000" if body["oneTimeCode"] != "000000" else "111111", sent.payload["codeHash"])
    assert f'"{body["oneTimeCode"]}"' not in log  # the code itself is never stored, only its hash
    assert body["qrUrl"].endswith(f"/r/{body['inviteId']}")


def test_nothing_without_consent(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        setup(c, make_event)
        assert c.post(f"{ADM}/invites", json={"consentId": "CS-NOPE"}).status_code == 409
        assert c.post(f"{ADM}/updates", json={"kind": "meal_served"}).status_code == 409
        consent(c, kinds=["visiting_info"])
        refused = c.post(f"{ADM}/updates", json={"kind": "nurse_note", "text": "Quiet evening."})
        assert (refused.status_code, refused.json()["error"]) == (409, "no_consent")  # kind not consented


def test_privacy_filter_refuses_clinical_text_and_publishes_only_the_allow_list(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = setup(c, make_event)
        consent(c)
        for text in ("Her SpO2 is 93% today.", "Tension 120/80, all fine.", "We gave Paracetamol at 23:00.",
                     "Fièvre à 38,5 cette nuit.", "His NEWS2 went down."):
            refused = c.post(f"{ADM}/updates", json={"kind": "nurse_note", "text": text})
            assert (refused.status_code, refused.json()["error"]) == (422, "clinical_data_in_text"), text

        note = "Your father had a quiet evening and ate most of his dinner."
        draft = c.post(f"{ADM}/updates", json={"kind": "nurse_note", "text": note}).json()
        assert draft["status"] == "pending_approval"
        assert outbound_items(ingestor.store) == []  # a draft never leaves the ward
        approved = c.post(f"{BASE}/family/updates/{draft['updateId']}/decision", json={"decision": "approve"})
        assert approved.status_code == 200, approved.text
        assert not list(openapi_validator("FamilyUpdate").iter_errors(approved.json()))
        assert approved.json()["status"] == "published"
        sent = outbound_items(ingestor.store)[-1]

    assert sent.target == "updates"
    assert set(sent.payload) == {"schemaVersion", "updateId", "linkId", "kind", "text", "publishedAt", "approval"}
    assert sent.payload["text"] == note and sent.payload["approval"]["approved"] is True
    readable = json.dumps({k: v for k, v in sent.payload.items() if k in ("kind", "text")})  # ids are random
    for secret in ("N1", "B04", "ADM-0004", "112", "Paracetamol"):
        assert secret not in readable  # no staff identity, bed, admission, vitals or drugs
    assert "approvedBy" not in sent.payload["approval"]  # the approving nurse is never named to families


def test_withdrawal_is_immediate(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = setup(c, make_event)
        given = consent(c)
        invite = c.post(f"{ADM}/invites", json={"consentId": given["consentId"]}).json()
        draft = c.post(f"{ADM}/updates", json={"kind": "meal_served"}).json()
        revoked = c.post(f"{ADM}/consents/{given['consentId']}/revoke").json()
        assert revoked["active"] is False and "revokedAt" in revoked
        late = c.post(f"{BASE}/family/updates/{draft['updateId']}/decision", json={"decision": "approve"})
        assert (late.status_code, late.json()["error"]) == (409, "no_consent")
        sent = outbound_items(ingestor.store)[-1]
    assert sent.target == "revocations"
    assert (sent.payload["inviteId"], sent.payload["reason"]) == (invite["inviteId"], "consent_withdrawn")


def test_discharge_revokes_the_whole_link(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = setup(c, make_event)
        given = consent(c)
        c.post(f"{ADM}/invites", json={"consentId": given["consentId"]})
        ingestor.handle(*make_event("binding", action="discharge", ts="2026-10-10T23:30:00Z"))
        sent = outbound_items(ingestor.store)[-1]
        consents = ingestor.twin.consents
    assert sent.target == "revocations" and sent.payload["reason"] == "discharge" and "inviteId" not in sent.payload
    assert not any(cn.active for cn in consents.values())


def test_only_nurses_manage_the_family_link(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        setup(c, make_event)
        login(c, "DR1")
        assert c.post(f"{ADM}/consents", json={"relativeLabel": "Son", "allowedKinds": ["visiting_info"],
                                               "givenBy": "patient"}).status_code == 403


def test_publisher_forwards_outbound_in_order_and_retries(tmp_path, make_event):
    received: list[tuple[str, dict, str]] = []
    gateway_up = {"value": False}

    def gateway(request: httpx.Request) -> httpx.Response:
        if not gateway_up["value"]:
            return httpx.Response(503)
        received.append((request.url.path, json.loads(request.content), request.headers["authorization"]))
        return httpx.Response(202)

    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = setup(c, make_event)
        given = consent(c)
        c.post(f"{ADM}/invites", json={"consentId": given["consentId"]})
        draft = c.post(f"{ADM}/updates", json={"kind": "meal_served"}).json()
        c.post(f"{BASE}/family/updates/{draft['updateId']}/decision", json={"decision": "approve"})

        publisher = FamilyPublisher(ingestor.store, httpx.Client(base_url="http://fgw", transport=httpx.MockTransport(
            gateway)), token="synthetic-test-token")
        assert publisher.publish_once() == 0      # gateway down: nothing lost, retried later
        gateway_up["value"] = True
        assert publisher.publish_once() == 2
        assert publisher.publish_once() == 0      # delivered once, never twice
    assert [path for path, _, _ in received] == ["/ingest/v1/invites", "/ingest/v1/updates"]
    assert all(auth == "Bearer synthetic-test-token" for _, _, auth in received)
