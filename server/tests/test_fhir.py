"""Read-only FHIR R4 export. Resources are validated with fhir.resources (R4B models, same as R4 here)."""

from __future__ import annotations

import json

from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.encounter import Encounter
from fhir.resources.R4B.medicationadministration import MedicationAdministration
from fhir.resources.R4B.observation import Observation
from fhir.resources.R4B.operationoutcome import OperationOutcome
from fhir.resources.R4B.patient import Patient

from .conftest import login, make_client

MODELS = {"Patient": Patient, "Encounter": Encounter, "Observation": Observation,
          "MedicationAdministration": MedicationAdministration}


def validate_bundle(body: dict) -> list[dict]:
    Bundle.model_validate(body)
    resources = [e["resource"] for e in body["entry"]]
    for resource in resources:
        MODELS[resource["resourceType"]].model_validate(resource)
    return resources


def ward_with_history(c, make_event):
    ingestor = c.app.state.ingestor
    ingestor.handle(*make_event("vitals.device", ts="2026-10-10T21:30:00Z"))  # before admission: someone else's
    ingestor.handle(*make_event("binding"))                                    # ADM-0004 at 22:00
    ingestor.handle(*make_event("vitals.device"))                              # 22:03:21
    ingestor.handle(*make_event("vitals.device", ts="2026-10-10T22:08:00Z", params={"pulse": 118},
                                quality={"valid": False, "stale_after_s": 900, "flags": ["artifact"]}))
    ingestor.handle(*make_event("vitals.manual"))
    ingestor.clock.update_from_message({"simTs": "2026-10-10T22:10:00Z"})
    ingestor.handle(*make_event("prescription", times=["23:00"]))
    return ingestor


def test_patient_is_pseudonymised_and_valid(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ward_with_history(c, make_event)
        login(c, "DR1")
        resp = c.get("/fhir/r4/Patient/ADM-0004")
        missing = c.get("/fhir/r4/Patient/NOPE")
    assert resp.headers["content-type"].startswith("application/fhir+json")
    patient = Patient.model_validate(resp.json())
    assert patient.meta.security[0].code == "PSEUDED"
    assert "name" not in resp.json() and "address" not in resp.json()
    assert missing.status_code == 404
    OperationOutcome.model_validate(missing.json())


def test_observations_carry_the_admission_history_with_loinc(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        ward_with_history(c, make_event)
        login(c, "DR1")
        observations = validate_bundle(c.get("/fhir/r4/Observation?patient=Patient/ADM-0004").json())
        pulse = validate_bundle(c.get("/fhir/r4/Observation?encounter=ADM-0004&code=http://loinc.org|8867-4").json())
        late = validate_bundle(c.get("/fhir/r4/Observation?patient=ADM-0004&code=8867-4"
                                     "&date=ge2026-10-10T22:05:00Z").json())
        encounters = validate_bundle(c.get("/fhir/r4/Encounter?patient=ADM-0004").json())
        audit = [(e["actor"], e["action"]) for e in c.app.state.ingestor.store.audit_entries(20)]

    # Two pulse readings after admission (the 21:30 one belonged to someone else and is not attached).
    assert [o["valueQuantity"]["value"] for o in pulse] == [112, 118]
    assert pulse[1]["note"][0]["text"].startswith("Flagged by the device gateway (artifact)")
    assert [o["effectiveDateTime"] for o in late] == ["2026-10-10T22:08:00Z"]
    codes = {c["code"] for o in observations for c in o["code"]["coding"]}
    assert {"9279-1", "59408-5", "8480-6", "8867-4", "8310-5", "acvpu", "on-oxygen", "news2-total"} <= codes
    news2 = next(o for o in observations if o["code"]["text"] == "NEWS2")
    assert news2["valueInteger"] >= 0 and "Advisory only" in news2["note"][0]["text"]
    assert encounters[0]["class"]["code"] == "IMP" and encounters[0]["status"] == "in-progress"
    assert ("DR1", "fhir.read") in audit


def test_only_nurse_recorded_doses_are_exported(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = ward_with_history(c, make_event)
        login(c, "N1")
        dose = c.get("/api/v1/wards/W1/meds/timeline?hours=4").json()["doses"][0]
        ingestor.handle(*make_event("med.patient-reported", bed="B04", admissionId="ADM-0004",
                                    doseId=dose["doseId"], ts="2026-10-10T22:01:00Z"))
        assert validate_bundle(c.get("/fhir/r4/MedicationAdministration?patient=ADM-0004").json()) == []
        c.post(f"/api/v1/wards/W1/doses/{dose['doseId']}/administration",
               json={"action": "given", "presence": "wristband_scan"})
        exported = validate_bundle(c.get("/fhir/r4/MedicationAdministration?patient=ADM-0004").json())
    assert len(exported) == 1
    assert exported[0]["status"] == "completed"
    assert exported[0]["performer"][0]["actor"]["reference"] == "Practitioner/N1"
    assert "Paracetamol" in exported[0]["medicationCodeableConcept"]["text"]


def test_fhir_requires_login_and_has_no_write_methods(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        assert c.get("/fhir/r4/Encounter").status_code == 401
        login(c, "DR1")
        writes = [c.post("/fhir/r4/Observation", content=json.dumps({"resourceType": "Observation"})).status_code,
                  c.put("/fhir/r4/Patient/ADM-0004", json={}).status_code,
                  c.delete("/fhir/r4/Patient/ADM-0004").status_code]
    assert all(code == 405 for code in writes)
