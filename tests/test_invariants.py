"""One test per safety invariant (CLAUDE.md).

Tests that need components which do not exist yet are skipped with the phase and role
that will turn them on. Remove the skip when the component lands; never skip a test that
used to pass.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_1_advisory_only():
    """Suggestions change nothing; only a recorded human approval does, and both are audited.
    Prescriptions are created only by a doctor and never by the system."""
    import re

    from borj_server.assignment import AssignmentService
    from borj_server.clock import Clock
    from borj_server.crypto import DataCipher
    from borj_server.ingest import Ingestor
    from borj_server.store import EventStore
    from borj_server.twin.layout import WardLayout

    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    ingestor = Ingestor(WardLayout.load(ROOT / "seed" / "ward-W1.yaml"), store, Clock("wall"))
    plan = {"status": "optimal", "changes": [{"bed": "B01", "toStaffId": "N1"}],
            "reasonItems": [{"code": "assign.rooms", "params": {"max": 1}}],
            "confidence": {"value": 1.0, "basisItem": {"code": "assign.basis",
                                                       "params": {"status": "optimal", "fresh": 1, "total": 1}}},
            "loadBefore": {}, "loadAfter": {}}
    service = AssignmentService(ingestor, solve=lambda nurses, beds: plan, news2_by_bed=dict)

    suggestion = service.suggest("test")
    assert ingestor.twin.assignments == {}, "a suggestion must never change assignments"
    service.decide(suggestion["suggestionId"], "approve", "CN1", None)
    assert ingestor.twin.assignments == {"B01": "N1"}
    actions = [(e["actor"], e["action"]) for e in store.audit_entries()]
    assert ("system", "suggestion.created") in actions and ("CN1", "suggestion.approved") in actions

    # Statically: the only code that emits an `assignment` event is the approval path.
    emitters = [p.relative_to(ROOT).as_posix() for p in (ROOT / "server" / "borj_server").rglob("*.py")
                if re.search(r"topic\(\s*\"assignment\"", p.read_text(encoding="utf-8"))]
    assert emitters == ["server/borj_server/assignment.py"]
    assert "def _apply" in (ROOT / "server" / "borj_server" / "assignment.py").read_text(encoding="utf-8")
    service.close()

    # Prescriptions: only a doctor's REST entry creates one; nothing in the system writes or changes one,
    # and none is ever published on MQTT (drug names stay in the encrypted log and on staff screens).
    sources = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
               for p in (ROOT / "server" / "borj_server").rglob("*.py")}
    rx_emitters = [name for name, code in sources.items() if re.search(r'topic\(\s*"prescription"', code)]
    assert rx_emitters == ["server/borj_server/api/routes.py"]
    routes = sources["server/borj_server/api/routes.py"]
    create = routes[routes.index("def create_prescription"):routes.index("def meds_timeline")]
    assert 'require_role(who, "doctor")' in create
    publishers = [name for name, code in sources.items() if "publish_retained" in code]
    assert sorted(publishers) == ["server/borj_server/main.py", "server/borj_server/mqtt.py"]
    assert "prescription" not in sources["server/borj_server/calls.py"]


def _family_ward():
    """A ward full of clinical data: vitals, a prescription, staff, a call; plus a family link."""
    import json

    import borj_contracts as bc
    from borj_server.clock import Clock
    from borj_server.crypto import DataCipher
    from borj_server.family import FamilyConfig, FamilyService
    from borj_server.ingest import Ingestor
    from borj_server.store import EventStore
    from borj_server.twin.layout import WardLayout

    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    ingestor = Ingestor(WardLayout.load(ROOT / "seed" / "ward-W1.yaml"), store, Clock("wall"))
    family = FamilyService(ingestor, FamilyConfig.load())
    ingestor.listeners.append(family.on_event)
    for name in ("binding", "vitals.device", "vitals.manual", "prescription", "call", "staff-presence"):
        payload = json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        schema = name.split(".")[0]
        topic = (bc.topic(schema, "W1", staff_id=payload["staffId"]) if schema == "staff-presence"
                 else bc.topic(schema, "W1", bed=payload["bed"]))
        ingestor.handle(topic, payload)
    return ingestor, family


def test_2_family_never_sees_forbidden_fields():
    """Every payload that can leave the ward is allow-list-only and carries no clinical or staff data."""
    import json

    import borj_contracts as bc
    from borj_server.family import FamilyError
    from borj_server.family_publisher import SCHEMA_FOR_TARGET, outbound_items

    ingestor, family = _family_ward()
    consent = family.record_consent("ADM-0004", "Daughter", ["visiting_info", "meal_served", "nurse_note",
                                                             "medication_round_completed", "ward_contact"],
                                    "patient", "N1")
    family.create_invite("ADM-0004", consent["consentId"], "N1")
    for kind, text in (("meal_served", None), ("medication_round_completed", None),
                       ("nurse_note", "A calm night. Visiting hours tomorrow are 13:00 to 15:00.")):
        family.decide_update(family.draft_update("ADM-0004", kind, text, "N1")["updateId"], "approve", "N1", None)
    for clinical in ("SpO2 93%", "pulse is 112", "Paracetamol given", "NEWS2 is 8", "BP 104/70"):
        with pytest.raises(FamilyError):
            family.draft_update("ADM-0004", "nurse_note", clinical, "N1")
    family.revoke_consent("ADM-0004", consent["consentId"], "N1")

    items = outbound_items(ingestor.store)
    assert [i.target for i in items] == ["invites", "updates", "updates", "updates", "revocations"]
    random_or_time = {"schemaVersion", "updateId", "inviteId", "revocationId", "linkId", "codeHash", "publishedAt",
                      "approval", "expiresAt", "consentRecordedAt", "effectiveAt"}
    for item in items:
        bc.validate(SCHEMA_FOR_TARGET[item.target], item.payload)  # allow-list schemas (additionalProperties false)
        # Random ids and hashes can contain any characters by chance, so search the human-readable fields,
        # and check separately that the opaque link id is not derived from patient or bed identifiers.
        readable = json.dumps({k: v for k, v in item.payload.items() if k not in random_or_time})
        for forbidden in ("Paracetamol", "params", "pulse", "spo2", "112", "93", "news2", "NEWS2", "N1", "CN1",
                          "B04", "ADM-0004", "Patient 04", "MON-B04", "call"):
            assert forbidden not in readable, (item.target, forbidden)
        assert not any(x in item.payload["linkId"] for x in ("ADM", "B04", "0004"))


@pytest.mark.skip(reason="P4, A: family-gateway on dmz network cannot resolve or reach mosquitto/server")
def test_3_outbound_only():
    pass


def test_4_consent_first():
    """No invite or update without an active consent; withdrawal is immediate; discharge revokes the link."""
    import borj_contracts as bc
    from borj_server.family import FamilyError
    from borj_server.family_publisher import outbound_items

    ingestor, family = _family_ward()
    with pytest.raises(FamilyError):
        family.create_invite("ADM-0004", "CS-NONE", "N1")
    with pytest.raises(FamilyError):
        family.draft_update("ADM-0004", "meal_served", None, "N1")

    consent = family.record_consent("ADM-0004", "Son", ["meal_served"], "patient", "N1")
    pending = family.draft_update("ADM-0004", "meal_served", None, "N1")
    family.revoke_consent("ADM-0004", consent["consentId"], "N1")
    with pytest.raises(FamilyError):
        family.decide_update(pending["updateId"], "approve", "N1", None)  # withdrawal took effect at once

    family.record_consent("ADM-0004", "Daughter", ["meal_served"], "patient", "N1")
    ingestor.handle(bc.topic("binding", "W1", bed="B04"), {
        "schemaVersion": 1, "eventId": "01K80000000000000000DSCHG0", "ts": "2026-10-11T08:00:00Z", "ward": "W1",
        "bed": "B04", "source": "staff-app", "sourceType": "staff_app", "action": "discharge",
        "admissionId": "ADM-0004", "method": "wristband_scan"})
    assert not any(c.active for c in ingestor.twin.consents.values())
    assert outbound_items(ingestor.store)[-1].payload["reason"] == "discharge"


def test_5_missing_or_stale_is_labelled():
    """A stale reading that would score 3 is excluded, listed, and the score is labelled partial."""
    from borj_inference.news2 import News2Config, Reading, score

    readings = {
        "resp_rate": Reading(16, "fresh", 60, 900),
        "pulse": Reading(140, "stale", 1800, 900),  # would score 3 if it were (wrongly) used
        "temp_c": Reading(37.0, "invalid", 60, 900),
    }
    result = score(readings, News2Config.load())
    assert result["total"] == 0
    assert result["complete"] is False
    assert result["stale"] == ["pulse"]
    assert {"temp_c", "consciousness", "spo2", "on_oxygen", "sys_bp"} <= set(result["missing"])
    assert result["label"].startswith("Partial NEWS2")
    assert result["confidence"]["value"] < 1


def test_6_idempotency():
    """Replaying every contract example twice leaves the event log and the twin unchanged."""
    import json

    import borj_contracts as bc
    from borj_server.clock import Clock
    from borj_server.crypto import DataCipher
    from borj_server.ingest import Ingestor
    from borj_server.store import EventStore
    from borj_server.timeutil import parse_ts
    from borj_server.twin.layout import WardLayout
    from borj_server.twin.views import snapshot_view

    store = EventStore("sqlite://", DataCipher({"test": b"T" * 32}, "test"))
    ingestor = Ingestor(WardLayout.load(ROOT / "seed" / "ward-W1.yaml"), store, Clock("wall"))
    messages = []
    for path in sorted((ROOT / "contracts" / "examples").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "eventId" not in payload:
            continue  # clock and family payloads are not ward events
        schema = path.name.split(".")[0]
        if schema in ("ack", "staff-presence"):
            topic = bc.topic(schema, payload["ward"], staff_id=payload["staffId"])
        elif schema == "assignment":
            topic = bc.topic(schema, payload["ward"])
        else:
            topic = bc.topic(schema, payload["ward"], bed=payload["bed"])
        messages.append((topic, payload))

    for topic, payload in messages:
        ingestor.handle(topic, payload)
    now = parse_ts("2026-10-11T01:00:00Z")
    count, twin = ingestor.store.count(), snapshot_view(ingestor.twin, now, "wall")

    for topic, payload in messages:
        assert ingestor.handle(topic, payload).status == "duplicate"
    assert ingestor.store.count() == count
    assert snapshot_view(ingestor.twin, now, "wall") == twin


def test_7_no_env_files_committed():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    leaked = [f for f in tracked if Path(f).name.startswith(".env") and Path(f).name != ".env.example"]
    assert not leaked, f".env files must not be committed: {leaked}"


def test_8_clinical_parameters_are_config():
    """Every clinical config block names who must validate it, and the engine reads thresholds from it."""
    import yaml

    for path in sorted(ROOT.glob("*/config/*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        blocks = list(cfg.get("parameters", {}).values()) + [v for k, v in cfg.items() if k != "parameters"]
        missing = [b for b in blocks if isinstance(b, dict) and not b.get("validated_by")]
        assert not missing, f"{path}: blocks without validated_by"

    engine = (ROOT / "inference" / "borj_inference" / "news2.py").read_text(encoding="utf-8")
    for threshold in ("upto: 91", "<= 91", "< 92", ">= 131"):
        assert threshold not in engine, "NEWS2 thresholds must come from config, not code"


def test_10a_encrypted_at_rest():
    """No patient data in clear in the database; the payload still reads back intact."""
    import json

    from borj_server.crypto import DataCipher
    from borj_server.store import EventStore, events
    from sqlalchemy import select

    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    payload = json.loads((ROOT / "contracts" / "examples" / "vitals.device.json").read_text(encoding="utf-8"))
    store.append("borj/W1/B04/vitals", "vitals", payload)
    with store.engine.connect() as conn:
        rows = conn.execute(select(events)).all()
    raw = b"".join(v if isinstance(v, bytes) else str(v).encode() for row in rows for v in row)
    assert b'"pulse":112' not in raw and b'"params"' not in raw
    assert next(store.events()).payload == payload


def test_10b_encrypted_in_transit():
    """The broker listens on the network only with TLS 1.3 and authentication; plain MQTT is loopback-only."""
    import re

    import yaml

    conf = (ROOT / "infra" / "mosquitto" / "mosquitto.conf").read_text(encoding="utf-8")
    lines = [line.split("#")[0].strip() for line in conf.splitlines()]
    blocks: list[list[str]] = []
    for line in lines:
        if line.startswith("listener "):
            blocks.append([line])
        elif line and blocks:
            blocks[-1].append(line)
    network = [b for b in blocks if not re.match(r"listener \d+ 127\.0\.0\.1$", b[0])]
    assert len(network) == 1 and network[0][0] == "listener 8883", "the only network listener is the TLS port"
    block = network[0]
    assert "tls_version tlsv1.3" in block and "allow_anonymous false" in block
    for required in ("password_file ", "acl_file "):
        assert any(line.startswith(required) for line in block), required
    plain = [b for b in blocks if b is not network[0]]
    assert all(b[0].endswith("127.0.0.1") for b in plain), "plain MQTT may only listen on the container's loopback"

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    published = [str(p) for p in compose["services"]["mosquitto"].get("ports", [])]
    assert published == ["8883:8883"], "no plain MQTT port is published"

    # HTTP: nginx (local) and Caddy (hosted) accept TLS 1.3 only, and port 80 only redirects.
    nginx = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "ssl_protocols TLSv1.3;" in nginx and "ssl_protocols TLSv1.2" not in nginx
    port80 = nginx.split("listen 80;", 1)[1].split("listen 443", 1)[0]
    assert "return 301 https://" in port80 and "proxy_pass http://frontend" not in port80
    assert "443:443" in compose["services"]["nginx"]["ports"]
    assert "protocols tls1.3" in (ROOT / "infra" / "Caddyfile").read_text(encoding="utf-8")


def test_11_non_repudiation():
    """Audit entries name their actor, the chain verifies, and any edit is detected."""
    from borj_server.crypto import DataCipher
    from borj_server.store import EventStore, audit
    from sqlalchemy import update

    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    store.audit("N1", "snapshot.read", "W1")
    store.audit("CN1", "assignment.approved", "S-1", {"reason": "N3 called away"})
    assert store.verify_audit_chain() == {"valid": True, "entries": 2}
    assert [e["actor"] for e in store.audit_entries()] == ["CN1", "N1"]
    with store.engine.begin() as conn:
        conn.execute(update(audit).where(audit.c.seq == 1).values(actor="DR1"))
    assert store.verify_audit_chain()["valid"] is False


def test_12_explainable_and_advisory():
    """Every NEWS2 result and every alert carries a confidence index and an explanation.
    (Assignment suggestions and what-if join this test in P3.)"""
    from borj_inference.news2 import News2Config, Reading, score
    from borj_server.alerts import FirstSeen, derive_alerts
    from borj_server.calls import CallConfig
    from borj_server.timeutil import parse_ts
    from borj_server.twin.layout import WardLayout
    from borj_server.twin.state import Admission, Call, Device, WardTwin

    result = score({"pulse": Reading(135, "fresh", 10, 900), "consciousness": Reading("C", "fresh", 10, 14400)},
                   News2Config.load())
    assert 0 <= result["confidence"]["value"] <= 1 and result["confidence"]["basis"]
    assert result["components"] and result["label"]

    now = parse_ts("2026-10-10T23:00:00Z")
    twin = WardTwin(WardLayout.load(ROOT / "seed" / "ward-W1.yaml"))
    twin.beds["B04"].admission = Admission("ADM-0004", "Patient 04", 2, now)
    twin.beds["B07"].devices["MON-B07"] = Device("MON-B07", "bedside_monitor", "offline", now)
    twin.calls["C1"] = Call("C1", "B06", "assist", now, state="escalated", escalation_level=2,
                            escalation_reason="unacknowledged_timeout")
    alerts = derive_alerts(twin, {"B04": {**result, "computedAt": "x"}}, now, CallConfig.load(), FirstSeen())
    assert {a["type"] for a in alerts} >= {"news2_high", "device_offline", "call_escalated"}
    for alert in alerts:
        assert alert["explanation"] and alert["confidence"]["basis"]
        assert 0 <= alert["confidence"]["value"] <= 1


def test_13_frame_integrity():
    """Bad, unknown-key, wrong-bed and (in require mode) unsigned frames never reach the log; each is audited."""
    import json

    import borj_contracts as bc
    from borj_server.clock import Clock
    from borj_server.crypto import DataCipher
    from borj_server.ingest import Ingestor
    from borj_server.integrity import IntegrityGate
    from borj_server.store import EventStore
    from borj_server.twin.layout import WardLayout

    keys = {"sim-k1": b"S" * 32, "node-B04": b"4" * 32, "node-B01": b"1" * 32}  # synthetic test keys
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    ingestor = Ingestor(WardLayout.load(ROOT / "seed" / "ward-W1.yaml"), store, Clock("wall"))
    gate = IntegrityGate(keys, "require")

    def example(name, event_id):
        payload = json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        return {**payload, "eventId": event_id}

    def send(payload):
        return gate.handle_raw(ingestor, bc.topic("vitals", "W1", bed="B04"), json.dumps(payload).encode())

    binding = bc.sign(example("binding", "01K80000000000000000000BND"), keys["node-B04"], "node-B04")
    assert gate.handle_raw(ingestor, bc.topic("binding", "W1", bed="B04"),
                           json.dumps(binding).encode()).status == "accepted"
    good = bc.sign(example("vitals.device", "01K80000000000000000000G00"), keys["sim-k1"], "sim-k1")
    tampered = {**good, "eventId": "01K80000000000000000000T00", "params": {**good["params"], "pulse": 60}}
    forged = bc.sign(example("vitals.device", "01K80000000000000000000F00"), b"X" * 32, "gw-k9")
    other_bed = bc.sign(example("vitals.device", "01K80000000000000000000W00"), keys["node-B01"], "node-B01")
    unsigned = example("vitals.device", "01K80000000000000000000Z00")

    assert send(good).status == "accepted"
    assert [send(p).detail for p in (tampered, forged, other_bed, unsigned)] == [
        "bad_signature", "unknown_key", "key_not_for_this_bed", "unsigned"]
    stored = {e.payload["eventId"] for e in store.events()}
    assert good["eventId"] in stored and not stored & {"01K80000000000000000000T00", "01K80000000000000000000F00",
                                                        "01K80000000000000000000W00", "01K80000000000000000000Z00"}
    assert ingestor.twin.beds["B04"].vitals["pulse"].value == good["params"]["pulse"]
    rejected = [a for a in store.audit_entries() if a["action"] == "integrity.rejected"]
    assert len(rejected) == 4 and {a["actor"] for a in rejected} == {"mqtt"}
    assert store.verify_audit_chain()["valid"]

    clock = {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:00:00Z", "speed": 1, "scenario": "t",
             "running": True}
    assert gate.handle_raw(ingestor, "borj/W1/sim/clock", json.dumps(clock).encode()).status != "integrity"
    assert IntegrityGate(keys, "verify").check(bc.topic("vitals", "W1", bed="B04"), unsigned) is None
