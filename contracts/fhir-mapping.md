# FHIR R4 mapping (contract v1)

How Borj data maps to FHIR R4 for the **read-only export** (`/fhir/r4/*` in [`openapi.yaml`](openapi.yaml)). The goal is HackCure's interoperability requirement: compatible with HL7/FHIR, so the system can integrate with the hospital information system (SIH) later. See [ADR 0011](../docs/decisions/0011-interop-and-confidence.md).

Rules:
- **Pseudonymised only.** No names, national ids or addresses. `Patient.identifier` holds the synthetic admission-scoped id.
- Only data the ward already holds is exported. **Nothing is written back** into any external system.
- Every export request is audited (invariant 11).
- Codes marked _to confirm_ must be checked against the current LOINC release before any real integration. Until then, a local code system is used.

## Resources

| Borj | FHIR resource | Key fields |
|---|---|---|
| Admission (`binding` admit) | `Patient` + `Encounter` | `Patient.id` = pseudonymous id; `Encounter.status` = `in-progress`/`finished`; `Encounter.class` = `IMP` (inpatient); `Encounter.location` = ward/bed |
| Vitals reading (one parameter) | `Observation` | `status` = `final`; `category` = `vital-signs`; `code` (LOINC); `subject`, `encounter`; `effectiveDateTime` = `ts`; `valueQuantity` (UCUM) |
| Stale or invalid reading | `Observation` | Exported with `status` = `final` plus a `dataAbsentReason` or an interpretation note. Never presented as a current normal value (invariant 5) |
| NEWS2 result | `Observation` | `code` = NEWS2 total score (_to confirm_, local fallback below); `valueInteger`; `component[]` per parameter score; a note for partial scores and the confidence |
| Nurse administration (`med`, `recordedBy: nurse`) | `MedicationAdministration` | `status` = `completed` / `not-done`; `effectiveDateTime`; `performer` = pseudonymous staff id. Patient-reported entries are **not** exported as administrations |

## Vital-sign codes

| Borj param | LOINC | Display | UCUM unit |
|---|---|---|---|
| `resp_rate` | 9279-1 | Respiratory rate | `/min` |
| `spo2` | 59408-5 (and 2708-6) | Oxygen saturation by pulse oximetry | `%` |
| `sys_bp` | 8480-6 | Systolic blood pressure | `mm[Hg]` |
| `pulse` | 8867-4 | Heart rate | `/min` |
| `temp_c` | 8310-5 | Body temperature | `Cel` |
| `on_oxygen` | _to confirm_ | Supplemental oxygen in use | boolean (`valueBoolean`) |
| `consciousness` | _to confirm_ | Level of consciousness (ACVPU) | coded (`valueCodeableConcept`) |
| NEWS2 total | _to confirm_ | NEWS2 aggregate score | `{score}` |

Local fallback code system for codes still to confirm: `https://borj.local/fhir/CodeSystem/observation`, with codes `on-oxygen`, `acvpu`, `news2-total`.
