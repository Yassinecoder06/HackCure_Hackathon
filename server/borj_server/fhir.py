"""Read-only FHIR R4 export (HackCure section 5 interoperability, ADR 0011, contracts/fhir-mapping.md).

Translates the ward's data into FHIR resources so a hospital information system (SIH) could read
it later. Nothing is ever written back. Rules:
- Pseudonymised: the Patient id is the synthetic admission id, with no name or national id, and the
  resource carries the HL7 "pseudonymised" security label.
- Vital signs come from the EVENT LOG (the full history of the admission, not just the latest
  value), LOINC-coded with UCUM units. Readings the gateway flagged as invalid keep their value
  but carry a note saying they were not used for NEWS2.
- NEWS2 is exported as a survey Observation with one component per scored parameter; a partial
  score is `preliminary`, with its label and confidence in a note.
- Only nurse-recorded administrations are exported; patient reports never are.
- Codes still to confirm against the LOINC release use a clearly named local code system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .timeutil import format_ts, parse_ts
from .twin.state import WardTwin

LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
LOCAL = "https://borj.local/fhir/CodeSystem/observation"
CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
PSEUDED = {"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue", "code": "PSEUDED",
           "display": "pseudonymized"}

# param -> (codings, unit) following contracts/fhir-mapping.md
VITALS: dict[str, tuple[list[dict[str, str]], str | None]] = {
    "resp_rate": ([{"system": LOINC, "code": "9279-1", "display": "Respiratory rate"}], "/min"),
    "spo2": ([{"system": LOINC, "code": "59408-5", "display": "Oxygen saturation in Arterial blood by Pulse oximetry"},
              {"system": LOINC, "code": "2708-6", "display": "Oxygen saturation in Arterial blood"}], "%"),
    "sys_bp": ([{"system": LOINC, "code": "8480-6", "display": "Systolic blood pressure"}], "mm[Hg]"),
    "pulse": ([{"system": LOINC, "code": "8867-4", "display": "Heart rate"}], "/min"),
    "temp_c": ([{"system": LOINC, "code": "8310-5", "display": "Body temperature"}], "Cel"),
    "on_oxygen": ([{"system": LOCAL, "code": "on-oxygen", "display": "Supplemental oxygen in use"}], None),
    "consciousness": ([{"system": LOCAL, "code": "acvpu", "display": "Level of consciousness (ACVPU)"}], None),
}
NEWS2_CODE = {"system": LOCAL, "code": "news2-total", "display": "NEWS2 aggregate score"}


def _fhir_id(*parts: str) -> str:
    """FHIR ids allow [A-Za-z0-9-.], up to 64 characters."""
    return "-".join(parts).replace("_", "-")[:64]


def _category(code: str) -> list[dict[str, Any]]:
    return [{"coding": [{"system": CATEGORY, "code": code}]}]


def bundle(resources: list[dict[str, Any]], base: str) -> dict[str, Any]:
    return {
        "resourceType": "Bundle", "type": "searchset", "total": len(resources),
        "entry": [{"fullUrl": f"{base}/{r['resourceType']}/{r['id']}", "resource": r} for r in resources],
    }


def patients(twin: WardTwin) -> dict[str, dict[str, Any]]:
    """Current admissions as pseudonymised Patients, keyed by admission id."""
    out = {}
    for bed in twin.beds.values():
        if bed.admission is None:
            continue
        adm = bed.admission.admission_id
        out[adm] = {
            "resourceType": "Patient", "id": _fhir_id(adm),
            "meta": {"security": [PSEUDED]},
            "identifier": [{"system": "https://borj.local/fhir/admission", "value": adm}],
            "active": True,
        }
    return out


def encounters(twin: WardTwin) -> dict[str, dict[str, Any]]:
    out = {}
    for bed in twin.beds.values():
        if bed.admission is None:
            continue
        adm = bed.admission.admission_id
        out[adm] = {
            "resourceType": "Encounter", "id": _fhir_id(adm), "status": "in-progress",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP",
                      "display": "inpatient encounter"},
            "subject": {"reference": f"Patient/{_fhir_id(adm)}"},
            "period": {"start": format_ts(bed.admission.admitted_at)},
            "location": [{"location": {"display": f"{twin.ward} / {bed.room} / {bed.bed}"}}],
        }
    return out


def vital_observations(twin: WardTwin, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every vitals reading of the current admissions, from the event log."""
    current = {b.bed: b.admission for b in twin.beds.values() if b.admission is not None}
    out = []
    for payload in events:
        admission = current.get(payload["bed"])
        if admission is None or parse_ts(payload["ts"]) < admission.admitted_at:
            continue  # another patient's data, never attached to this admission
        adm = _fhir_id(admission.admission_id)
        quality = payload["quality"]
        for param, value in payload["params"].items():
            if param not in VITALS:
                continue  # spo2_scale is a clinician's setting, not an observation
            codings, unit = VITALS[param]
            obs: dict[str, Any] = {
                "resourceType": "Observation", "id": _fhir_id(payload["eventId"], param), "status": "final",
                "category": _category("vital-signs"), "code": {"coding": codings, "text": param},
                "subject": {"reference": f"Patient/{adm}"}, "encounter": {"reference": f"Encounter/{adm}"},
                "effectiveDateTime": payload["ts"],
            }
            if param == "on_oxygen":
                obs["valueBoolean"] = bool(value)
            elif param == "consciousness":
                obs["valueCodeableConcept"] = {"coding": [{"system": f"{LOCAL}-acvpu", "code": value}], "text": value}
            else:
                obs["valueQuantity"] = {"value": value, "unit": unit, "system": UCUM, "code": unit}
            if payload.get("deviceId"):
                obs["device"] = {"display": payload["deviceId"]}
            if not quality["valid"]:
                flags = ", ".join(quality.get("flags", [])) or "invalid"
                obs["note"] = [{"text": f"Flagged by the device gateway ({flags}); not used for NEWS2."}]
            out.append(obs)
    return out


def news2_observations(twin: WardTwin, news2: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    out = []
    for bed in twin.beds.values():
        result = news2.get(bed.bed)
        if bed.admission is None or result is None:
            continue
        adm = _fhir_id(bed.admission.admission_id)
        components = []
        for c in result["components"]:
            if "points" not in c or c["param"] not in VITALS:
                continue
            components.append({"code": {"coding": VITALS[c["param"]][0], "text": f"{c['param']} points"},
                               "valueInteger": c["points"]})
        computed = result.get("computedAt", "")
        out.append({
            "resourceType": "Observation",
            "id": _fhir_id("news2", adm, computed.replace(":", "").replace("Z", "")),
            "status": "final" if result["complete"] else "preliminary",
            "category": _category("survey"), "code": {"coding": [NEWS2_CODE], "text": "NEWS2"},
            "subject": {"reference": f"Patient/{adm}"}, "encounter": {"reference": f"Encounter/{adm}"},
            "effectiveDateTime": computed, "valueInteger": result["total"], "component": components,
            "note": [{"text": f"{result['label']}. Confidence {result['confidence']['value']}: "
                              f"{result['confidence']['basis']}. Advisory only."}],
        })
    return out


def medication_administrations(twin: WardTwin, doses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nurse-recorded doses only (patient reports are never administrations)."""
    out = []
    for dose in doses:
        record = twin.administrations.get(dose["doseId"])
        if record is None:
            continue
        adm = _fhir_id(dose["admissionId"])
        resource: dict[str, Any] = {
            "resourceType": "MedicationAdministration", "id": _fhir_id("ma", dose["doseId"]),
            "status": "completed" if record.action == "given" else "not-done",
            "medicationCodeableConcept": {"text": dose["label"]},
            "subject": {"reference": f"Patient/{adm}"}, "context": {"reference": f"Encounter/{adm}"},
            "effectiveDateTime": format_ts(record.ts),
            "performer": [{"actor": {"reference": f"Practitioner/{_fhir_id(record.staff_id)}"}}],
        }
        if record.action == "not_given" and record.reason:
            resource["statusReason"] = [{"text": record.reason}]
        out.append(resource)
    return out


def date_matches(value: str, criteria: list[str]) -> bool:
    """FHIR date search with ge/le/gt/lt/eq prefixes on full timestamps, e.g. date=ge2026-10-10T22:00:00Z."""
    when = parse_ts(value)
    for criterion in criteria:
        prefix, raw = (criterion[:2], criterion[2:]) if criterion[:2] in ("ge", "le", "gt", "lt", "eq") else (
            "eq", criterion)
        bound: datetime = parse_ts(raw if "T" in raw else f"{raw}T00:00:00Z")
        if not {"ge": when >= bound, "le": when <= bound, "gt": when > bound, "lt": when < bound,
                "eq": when == bound}[prefix]:
            return False
    return True
