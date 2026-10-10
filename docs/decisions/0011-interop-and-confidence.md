# 0011. FHIR interoperability and a confidence index on every algorithmic output

Status: accepted (2026-10-10)

## Interoperability (HackCure section 5)

The specification asks for structured JSON exchange that is **compatible with HL7 / FHIR**, so the system can later plug into the hospital information system (SIH).

- Our internal contracts stay as they are (JSON Schema + OpenAPI).
- The server exposes a **read-only FHIR R4 export**: `Patient` (pseudonymised), `Encounter` (admission), `Observation` (vitals with LOINC codes, and the NEWS2 score), `MedicationAdministration`. The mapping lives in [`contracts/fhir-mapping.md`](../../contracts/fhir-mapping.md).
- Writing into a real SIH is out of scope.

## Confidence index and explanation (HackCure section 6)

"Every algorithmic decision must provide a measurable confidence index and, where applicable, a contextual explanation." Black boxes are forbidden. Our engines are deterministic, so the confidence reflects **how trustworthy the inputs are**, not a model's probability:

| Output | Confidence | Explanation |
|---|---|---|
| NEWS2 score | Share of the 7 parameters that are fresh and valid, discounted by data age (0–1) | Points per parameter, plus which parameters are missing or stale |
| Alert / escalation | Inherits the trigger's confidence | The trigger rule and its values (e.g. "no ack after 120 s", "NEWS2 6, pulse 3 points") |
| Assignment suggestion | Solver status (optimal / feasible) and the share of beds with fresh acuity data | Reasons per change, workload before and after |
| What-if result | The p5–p95 band over N seeds | The assumptions list |

The UI shows each confidence next to the result, and labels every suggestion **advisory: a clinician decides**. Validating or rejecting an alert or a suggestion takes **3 steps at most** (HackCure section 5, ergonomics).
