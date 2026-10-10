"""Read-only FHIR R4 endpoints (contracts/openapi.yaml, tag fhir). Every request is audited."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from .. import fhir
from ..auth import Principal, require_staff
from ..live import news2_by_bed
from ..meds import dose_id, due_times
from ..timeutil import format_ts

router = APIRouter(prefix="/fhir/r4")
Staff = Annotated[Principal, Depends(require_staff)]
FHIR_JSON = "application/fhir+json"


def _respond(body: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=FHIR_JSON)


def _not_found(what: str) -> JSONResponse:
    return _respond({"resourceType": "OperationOutcome",
                     "issue": [{"severity": "error", "code": "not-found", "diagnostics": what}]}, 404)


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/fhir/r4"


def _audit(request: Request, who: Principal, resource: str, query: dict[str, Any]) -> None:
    request.app.state.ingestor.store.audit(who.staff_id, "fhir.read", resource,
                                           {k: v for k, v in query.items() if v})


def _ref_id(value: str | None) -> str | None:
    """Accept 'ADM-0004' or 'Patient/ADM-0004' / 'Encounter/ADM-0004'."""
    return value.split("/")[-1] if value else None


@router.get("/Patient/{patient_id}")
def get_patient(patient_id: str, request: Request, who: Staff) -> JSONResponse:
    _audit(request, who, "Patient", {"id": patient_id})
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        found = next((p for p in fhir.patients(ingestor.twin).values() if p["id"] == patient_id), None)
    return _respond(found) if found else _not_found(f"Patient/{patient_id}")


@router.get("/Encounter")
def search_encounters(request: Request, who: Staff, patient: str | None = None) -> JSONResponse:
    _audit(request, who, "Encounter", {"patient": patient})
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        found = [e for e in fhir.encounters(ingestor.twin).values()
                 if patient is None or e["subject"]["reference"].endswith(f"/{_ref_id(patient)}")]
    return _respond(fhir.bundle(found, _base(request)))


@router.get("/Observation")
def search_observations(request: Request, who: Staff, patient: str | None = None, encounter: str | None = None,
                        code: str | None = None, date: Annotated[list[str] | None, Query()] = None) -> JSONResponse:
    _audit(request, who, "Observation", {"patient": patient, "encounter": encounter, "code": code, "date": date})
    ingestor = request.app.state.ingestor
    news2 = news2_by_bed(request.app)
    vitals = [e.payload for e in ingestor.store.events() if e.schema == "vitals"]
    with ingestor.lock:
        found = fhir.vital_observations(ingestor.twin, vitals) + fhir.news2_observations(ingestor.twin, news2)
    who_ref = _ref_id(patient or encounter)
    found = [
        o for o in found
        if (who_ref is None or o["subject"]["reference"].endswith(f"/{who_ref}"))
        and (code is None or any(c["code"] == code.split("|")[-1] for c in o["code"]["coding"]))
        and (not date or fhir.date_matches(o["effectiveDateTime"], date))
    ]
    return _respond(fhir.bundle(found, _base(request)))


@router.get("/MedicationAdministration")
def search_administrations(request: Request, who: Staff, patient: str | None = None,
                           encounter: str | None = None) -> JSONResponse:
    _audit(request, who, "MedicationAdministration", {"patient": patient, "encounter": encounter})
    ingestor = request.app.state.ingestor
    cfg = request.app.state.meds_config
    with ingestor.lock:
        twin = ingestor.twin
        now = ingestor.clock.now()
        doses = []
        for rx in twin.prescriptions.values():
            bed = twin.beds.get(rx.bed)
            if bed is None or bed.admission is None or bed.admission.admission_id != rx.admission_id:
                continue
            for due in due_times(rx, bed.admission.admitted_at - timedelta(days=1), now + timedelta(days=1), cfg):
                doses.append({"doseId": dose_id(rx.prescription_id, due), "admissionId": rx.admission_id,
                              "due": format_ts(due), "label": f"{rx.drug} {rx.dose} {rx.route}"})
        found = fhir.medication_administrations(twin, doses)
    who_ref = _ref_id(patient or encounter)
    found = [m for m in found if who_ref is None or m["subject"]["reference"].endswith(f"/{who_ref}")]
    return _respond(fhir.bundle(found, _base(request)))
