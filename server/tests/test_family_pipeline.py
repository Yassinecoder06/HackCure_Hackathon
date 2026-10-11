"""The whole Family Care Link, both halves: ward server -> outbound publisher -> family-gateway -> the relative's feed.

The only thing the relative ever sees is what the nurse approved, and the ward is never contacted by the gateway
(the publisher pushes; nothing in this test gives the gateway a way back).
"""

from __future__ import annotations

import json

import httpx
from borj_family_gateway.app import Settings, create_app
from borj_server.family_publisher import FamilyPublisher
from fastapi.testclient import TestClient

from .conftest import login, make_client

BASE = "/api/v1/wards/W1"
ADM = f"{BASE}/admissions/ADM-0004/family"
TOKEN = "synthetic-publisher-token"


def push_to(gateway: TestClient) -> httpx.Client:
    """An httpx client whose every request lands on the gateway app (what the publisher would send over the network)."""
    def handler(request: httpx.Request) -> httpx.Response:
        sent = gateway.post(request.url.path, content=request.content, headers={
            "Authorization": request.headers["authorization"], "Content-Type": "application/json"})
        return httpx.Response(sent.status_code, content=sent.content)
    return httpx.Client(base_url="http://family-gateway", transport=httpx.MockTransport(handler))


def test_consent_to_approved_update_to_the_relatives_phone_and_revocation(tmp_path, make_event):
    gateway = TestClient(create_app(Settings(publisher_token=TOKEN, data_key=b"K" * 32,
                                             db_path=str(tmp_path / "gateway.sqlite"))))
    (tmp_path / "ward").mkdir()
    with make_client(tmp_path / "ward", auto_suggest=False) as ward, gateway:
        ingestor = ward.app.state.ingestor
        ingestor.handle(*make_event("binding"))               # ADM-0004 in B04
        ingestor.handle(*make_event("vitals.device"))         # a patient with a pulse of 112 and an SpO2 of 93
        login(ward, "N1")
        consent = ward.post(f"{ADM}/consents", json={"relativeLabel": "Daughter", "givenBy": "patient",
                                                     "allowedKinds": ["nurse_note", "meal_served"]}).json()
        invite = ward.post(f"{ADM}/invites", json={"consentId": consent["consentId"]}).json()
        draft = ward.post(f"{ADM}/updates", json={"kind": "nurse_note", "text": "A quiet evening; he ate well."}).json()
        publisher = FamilyPublisher(ingestor.store, push_to(gateway), TOKEN)
        assert publisher.publish_once() == 1                   # the invite; the draft is still the nurse's
        ward.post(f"{BASE}/family/updates/{draft['updateId']}/decision", json={"decision": "approve"})
        assert publisher.publish_once() == 1                   # the approved update

        # The relative scans the QR code (inviteId) and types the code the nurse read out.
        assert invite["qrUrl"].endswith(f"/r/{invite['inviteId']}")
        redeemed = gateway.post("/family/v1/redeem",
                                json={"inviteId": invite["inviteId"], "code": invite["oneTimeCode"]})
        assert redeemed.status_code == 200, redeemed.text
        headers = {"Authorization": f"Bearer {redeemed.json()['sessionToken']}"}
        feed = gateway.get("/family/v1/feed", headers=headers).json()
        seen = [(u["kind"], u.get("text")) for u in feed["updates"]]
        assert seen == [("nurse_note", "A quiet evening; he ate well.")]
        readable = json.dumps(feed)
        stored = gateway.app.state.store.raw_dump().decode("latin-1")  # BLOBs are hex here, so only words can match
        for secret in ("112", "93", "pulse", "spo2", "news2", "B04", "ADM-0004", "N1", "Patient 04", "staff"):
            assert secret.lower() not in readable.lower(), secret
        for secret in ("pulse", "spo2", "news2", "ADM-0004", "Patient 04", "staffId", "bed"):
            assert secret not in stored, secret

        # Withdrawing consent on the ward cuts the relative off at the gateway straight away.
        ward.post(f"{ADM}/consents/{consent['consentId']}/revoke")
        assert publisher.publish_once() == 1
        assert gateway.get("/family/v1/feed", headers=headers).status_code == 401
