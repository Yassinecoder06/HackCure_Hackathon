"""Contract checks: schemas, examples, topic routing and both OpenAPI files."""

import json
from pathlib import Path

import borj_contracts as bc
import pytest
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.readers import read_from_filename

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "contracts" / "examples").glob("*.json"))


def load_example(name: str) -> dict:
    return json.loads((ROOT / "contracts" / "examples" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", bc.schema_names())
def test_schema_is_valid_json_schema(name):
    Draft202012Validator.check_schema(bc.load_schema(name))


def test_every_schema_has_an_example():
    covered = {p.name.split(".")[0] for p in EXAMPLES}
    assert set(bc.schema_names()) - {"common"} <= covered


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_validates(path):
    bc.validate(path.name.split(".")[0], json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("spec", ["openapi.yaml", "family-gateway.openapi.yaml"])
def test_openapi_is_valid(spec):
    document, base_uri = read_from_filename(str(ROOT / "contracts" / spec))
    validate_openapi(document, base_uri=base_uri)


@pytest.mark.parametrize(
    ("topic", "schema"),
    [
        ("borj/W1/B04/vitals", "vitals"),
        ("borj/W1/B04/device/status", "device-status"),
        ("borj/W1/B04/call", "call"),
        ("borj/W1/B04/call/state", "call-state"),
        ("borj/W1/B04/med", "med"),
        ("borj/W1/B04/binding", "binding"),
        ("borj/W1/staff/N1/ack", "ack"),
        ("borj/W1/staff/N1/presence", "staff-presence"),
        ("borj/W1/sim/clock", "clock"),
        ("borj/W1/assignment", "assignment"),
        ("borj/W1/B04/prescription", "prescription"),
        ("borj/W1/B04/family", "family-event"),
        ("borj/W1/B04/order", "doctor-order"),
    ],
)
def test_topic_routing(topic, schema):
    assert bc.route(topic).schema == schema


@pytest.mark.parametrize("topic", ["borj/W1/staff/vitals", "borj/W1/B04/unknown", "other/W1/B04/vitals"])
def test_unknown_topics_rejected(topic):
    with pytest.raises(bc.ContractError):
        bc.route(topic)


def test_topic_payload_mismatch_rejected():
    payload = load_example("vitals.device.json")  # bed B04
    with pytest.raises(bc.ContractError):
        bc.validate_message("borj/W1/B05/vitals", payload)


# --- Rules encoded in the schemas -------------------------------------------------------


def test_absent_not_null():
    """Invariant 5: a missing parameter is absent, never null."""
    payload = load_example("vitals.device.json")
    payload["params"]["consciousness"] = None
    with pytest.raises(bc.ContractError):
        bc.validate("vitals", payload)


def test_device_vitals_need_device_id_and_manual_need_staff_id():
    device = load_example("vitals.device.json")
    del device["deviceId"]
    manual = load_example("vitals.manual.json")
    del manual["staffId"]
    for name, payload in (("vitals", device), ("vitals", manual)):
        with pytest.raises(bc.ContractError):
            bc.validate(name, payload)


def test_patient_report_can_never_close_a_dose():
    """Whitepaper 4.3: patient_reported can only be patient_reported_taken."""
    payload = load_example("med.patient-reported.json")
    payload["action"] = "given"
    with pytest.raises(bc.ContractError):
        bc.validate("med", payload)


FORBIDDEN_FAMILY_FIELDS = {
    "params": {"spo2": 93},
    "vitals": {"pulse": 110},
    "news2": 5,
    "score": 5,
    "risk": "high",
    "drug": "Paracetamol",
    "dose": "1 g",
    "staffId": "N1",
    "nurse": "Nurse B",
    "lastVisitMin": 12,
    "responseTimeMin": 4,
    "bed": "B04",
    "admissionId": "ADM-0004",
    "otherPatients": [],
}


@pytest.mark.parametrize("field", sorted(FORBIDDEN_FAMILY_FIELDS))
def test_family_update_rejects_forbidden_fields(field):
    """Invariant 2 at the contract level: the family-update schema is an allow-list."""
    payload = load_example("family-update.json")
    payload[field] = FORBIDDEN_FAMILY_FIELDS[field]
    with pytest.raises(bc.ContractError):
        bc.validate("family-update", payload)


def test_instruction_must_target_an_alert_and_carry_text():
    payload = load_example("ack.instruction.json")
    bc.validate("ack", payload)
    for broken in ({"target": "call"}, {"note": ""}):
        with pytest.raises(bc.ContractError):
            bc.validate("ack", {**payload, **broken})
    with pytest.raises(bc.ContractError):
        bc.validate("ack", {k: v for k, v in payload.items() if k != "note"})


def test_family_update_requires_nurse_approval():
    payload = load_example("family-update.json")
    payload["approval"]["approved"] = False
    with pytest.raises(bc.ContractError):
        bc.validate("family-update", payload)


def test_integrity_sign_and_verify():
    """Invariant 13: a signed message verifies, validates, and any tampering breaks it."""
    keys = {"MON-B04": b"synthetic-test-key-not-a-secret"}
    signed = bc.sign(load_example("vitals.device.json"), keys["MON-B04"], "MON-B04")
    bc.validate("vitals", signed)
    assert bc.verify(signed, keys)

    tampered = json.loads(json.dumps(signed))
    tampered["params"]["spo2"] = 99
    assert not bc.verify(tampered, keys)
    assert not bc.verify(signed, {"OTHER": b"x"})
    assert not bc.verify(load_example("vitals.device.json"), keys)  # unsigned
