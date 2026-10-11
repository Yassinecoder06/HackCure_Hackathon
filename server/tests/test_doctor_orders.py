"""Doctor orders: the remote doctor's message to the nurses, durable and encrypted (ADR 0008)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import borj_contracts as bc
from borj_server.integrity import IntegrityGate
from borj_server.mqtt import MqttListener
from borj_server.store import events
from sqlalchemy import select

from .conftest import login, make_client, openapi_validator

BASE = "/api/v1/wards/W1"
TEXT = "Recheck observations in 30 minutes and call me back."


def test_order_is_durable_encrypted_and_listed_newest_first(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))  # ADM-0004 in B04
        login(c, "DR1")
        first = c.post(f"{BASE}/doctor/orders", json={"bed": "B04", "orderText": TEXT})
        assert first.status_code == 201, first.text
        assert not list(openapi_validator("DoctorOrder").iter_errors(first.json()))
        assert first.json()["doctorName"] == "Doctor F"
        later = {"schemaVersion": 1, "ward": "W1", "simTs": "2099-01-01T00:00:00Z", "speed": 1, "scenario": "t",
                 "running": True}
        ingestor.handle("borj/W1/sim/clock", later)
        second = c.post(f"{BASE}/doctor/orders", json={"bed": "B04", "orderText": "Stop the oxygen trial."}).json()
        login(c, "N1")
        listed = c.get(f"{BASE}/doctor/orders").json()
        ingestor.rebuild()  # replayed from the event log, as after a restart
        replayed = {o.order_id for o in ingestor.twin.doctor_orders.values()}
        with ingestor.store.engine.connect() as conn:
            raw = b"".join(v if isinstance(v, bytes) else str(v).encode() for r in conn.execute(select(events)).all()
                           for v in r)
        audit = ingestor.store.audit_entries()

    assert [o["orderId"] for o in listed] == [second["orderId"], first.json()["orderId"]]
    assert replayed == {first.json()["orderId"], second["orderId"]}
    assert TEXT.encode() not in raw  # free clinical text is encrypted at rest (invariant 10)
    assert any(a["actor"] == "DR1" and a["action"] == "doctor.order_created" for a in audit)
    assert any(a["actor"] == "N1" and a["action"] == "doctor.orders_read" for a in audit)


def test_order_rules(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        c.app.state.ingestor.handle(*make_event("binding"))
        body = {"bed": "B04", "orderText": TEXT}
        login(c, "N1")
        assert c.post(f"{BASE}/doctor/orders", json=body).status_code == 403  # doctors only
        login(c, "DR1")
        assert c.post(f"{BASE}/doctor/orders", json={**body, "bed": "B05"}).status_code == 409  # nobody admitted
        assert c.post(f"{BASE}/doctor/orders", json={**body, "bed": "B99"}).status_code == 404
        assert c.post(f"{BASE}/doctor/orders", json={**body, "orderText": ""}).status_code == 422
        assert c.post(f"{BASE}/doctor/orders", json={**body, "orderText": "x" * 501}).status_code == 422


def test_order_is_attached_to_the_beds_active_alert(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:12:40Z",
                                              "speed": 1, "scenario": "t", "running": True})
        ingestor.handle(*make_event("binding", bed="B06", admissionId="ADM-0006"))
        ingestor.handle(*make_event("call"))  # assist call from B06
        ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:17:40Z",
                                              "speed": 1, "scenario": "t", "running": True})
        login(c, "DR1")
        assert c.post(f"{BASE}/doctor/orders", json={"bed": "B06", "orderText": TEXT}).status_code == 201
        alert = next(a for a in c.get(f"{BASE}/snapshot").json()["alerts"] if a["type"] == "call_escalated")
    assert alert["instructions"][0]["text"] == TEXT


def test_internal_topics_are_refused_over_mqtt(tmp_path, make_event):
    """Prescriptions, family consents and doctor orders are written only by the server after an authenticated
    REST action. A message for one of those topics on the broker is forged, whatever its signature says."""
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        forged = [
            ("borj/W1/B04/order", {"schemaVersion": 1, "eventId": "01K80000000000000000FORG01",
                                   "ts": "2026-10-10T23:00:00Z", "ward": "W1", "bed": "B04", "source": "attacker",
                                   "sourceType": "staff_app", "admissionId": "ADM-0004", "orderId": "ORD-FORGED",
                                   "doctorId": "DR1", "orderText": "Give 10x the dose."}),
            make_event("prescription", eventId="01K80000000000000000FORG02"),
            make_event("family-event", eventId="01K80000000000000000FORG03"),
        ]
        before = len(list(ingestor.store.events()))
        key = b"K" * 32
        for mode in ("off", "verify", "require"):
            gate = IntegrityGate({"sim-k1": key}, mode)
            listener = MqttListener(ingestor, "localhost", 1883, gate=gate)
            for topic, payload in forged:
                signed = bc.sign(payload, key, "sim-k1")  # even a correctly signed one
                message = SimpleNamespace(topic=topic, payload=json.dumps(signed).encode())
                listener._on_message(None, None, message)
        audit = ingestor.store.audit_entries()
        stored = len(list(ingestor.store.events()))
        orders = dict(ingestor.twin.doctor_orders)
    assert stored == before and not orders
    assert sum(a["action"] == "integrity.rejected" for a in audit) == 9
