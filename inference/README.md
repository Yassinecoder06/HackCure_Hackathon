# inference/ (owner: B)

The **inference layer** ([ADR 0009](../docs/decisions/0009-layers-and-postgres.md)): a stateless FastAPI service, reachable only on the internal ward network (no published port in compose). The server sends inputs, and this service returns results with their rule trace and a **confidence index**. It stores and changes nothing.

| Engine | Status | What it returns |
|---|---|---|
| `news2` | ✅ | Total, band, points per component, missing/stale lists, a "partial" label, the response text, **confidence** |
| `assignment` | ✅ | OR-Tools suggestion with reasons, workload before/after, confidence. Never applied by itself |
| `whatif` | ✅ | SimPy results over N seeds: median and p5–p95, plus the assumptions list |
| `explain` | P3 | Template sentences from rule traces |

Deterministic by design, with no black-box model (HackCure section 6). Outputs are **language-neutral**: assignment
reasons and what-if assumptions are `{code, params}` items (`reasonItems`, `assumptionItems`,
`confidence.basisItem`), rendered in English or French by the server (`server/borj_server/explain.py`). NEWS2 still
returns English `label`/`response`/`basis` defaults for direct use; the server re-renders them per viewer.

## NEWS2: how it works

- **Thresholds:** [`config/news2.yaml`](config/news2.yaml), transcribed from the RCP NEWS2 chart. Every block is marked **"TO BE CONFIRMED BY A CLINICIAN"** (invariant 8). The code contains no thresholds.
- **Input:** per bed, each reading with a status (`fresh`/`stale`/`invalid`) already decided by the server, which owns the ward clock.
- **Only fresh, valid readings are scored.** Missing, stale or invalid ones are listed, and the result is labelled *"Partial NEWS2, at least N: …"*. The total is a minimum, because unscored parameters could only add points (invariant 5).
- **SpO2 scale 2** is used only if a clinician has set `spo2_scale: 2` for the patient. Above 92% it needs a fresh oxygen status, otherwise SpO2 is left unscored.
- **Bands:**
  - total ≥ 7 → `high`;
  - total ≥ 5 → `medium`;
  - otherwise any single parameter scoring 3 → `low_medium`;
  - otherwise `low`.
- **Confidence** (0–1): the average over the 7 parameters. A fresh reading counts 1 when new, decaying linearly to 0.5 at its stale threshold; missing, stale or invalid readings count 0. It measures **input quality, not certainty about the patient**.

## Assignment: how it works

- `POST /v1/assignment` with `{nurses: [{staffId, skills}], beds: [{bed, room, acuity, news2Total, news2Fresh, currentNurse, locked, requiredSkills}]}`.
- **Hard constraints:** every occupied bed gets exactly one nurse on the ward; skills are respected; locked beds keep their nurse; at most N beds per nurse (raised automatically if there are too few nurses).
- **Objective** (weights in [`config/assignment.yaml`](config/assignment.yaml)), in decreasing weight:
  1. the busiest nurse's workload (acuity + 0.5 × NEWS2) → balance;
  2. beds moved away from their current nurse → continuity of care;
  3. rooms per nurse → walking. Staff are never tracked; only room membership is used.
- It returns the changes, `loadBefore`/`loadAfter`, reason sentences and a confidence (1.0 if optimal, 0.8 if only feasible, scaled by the share of beds with a fresh NEWS2).
- CP-SAT runs single-threaded with a fixed seed, so the same ward gives the same suggestion. It never applies anything: the server keeps it pending until a charge nurse decides.

## What-if: how it works

- `POST /v1/whatif` with `{ward: {nurses, careAssistants, beds: [[bed, band]], routeComfort}, disruptions: [...], horizonMin, seeds}`.
- **Model (SimPy):** nurses and care assistants are limited resources. The work is:
  - bedside calls (Poisson; comfort calls go to care assistants only when routing is on);
  - observation rounds paced by each bed's NEWS2 band;
  - medication doses;
  - admission assessments.
- **Disruptions:** `staff_leaves` / `staff_joins` (nurse or care assistant), `admissions`, `call_surge`, `route_comfort_to_assistants`, `patient_deteriorates`.
- **Honest statistics:** N seeds; baseline and scenario use the **same seeds**; every random stream has its own generator. Each metric is reported as median and p5–p95. The metrics: wait for a nurse, longest wait, queue length, nurse utilisation, overdue medications, patients without observations.
- **Validated against queueing theory first.** `tests/test_whatif_engine.py` reproduces the whitepaper's Erlang-C table from the simulator alone (26 calls/h, 8 min each):

  | Nurses | All calls to nurses (theory → simulated) | 40% routed to care assistants |
  |---|---|---|
  | 3 | unbounded → waits keep growing | 4.2 → 4.25 min |
  | 4 | 10.8 → 10.5 min | 0.8 → 0.83 min |
  | 5 | 1.9 → 1.94 min | |

- Rates and durations in [`config/whatif.yaml`](config/whatif.yaml) are **illustrative** until calibrated with pilot timings, and every result lists its assumptions. It compares scenarios; it does not predict patient outcomes.

## API

`POST /v1/news2/batch`

```json
{"asOf": "2026-10-10T22:10:00Z",
 "beds": [{"bed": "B04", "spo2Scale": 1,
           "params": {"pulse": {"value": 112, "status": "fresh", "ageS": 399, "staleAfterS": 900}}}]}
```

It returns `{"results": {"B04": <News2Result>}}`, where `News2Result` is defined in [`contracts/openapi.yaml`](../contracts/openapi.yaml). `GET /health` is the liveness probe.

## Run

```bash
# from the repo root
.venv/Scripts/pip install -r inference/requirements.txt
PYTHONPATH=inference .venv/Scripts/python -m uvicorn borj_inference.main:app --port 8001
.venv/Scripts/python -m pytest inference/tests
```

In compose, the server reaches it at `http://inference:8001` (`INFERENCE_URL`). If it's down, the server shows NEWS2 as **unavailable**, never as a guess.
