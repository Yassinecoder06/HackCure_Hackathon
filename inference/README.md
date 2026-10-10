# inference/ (owner: B)

The **inference layer** ([ADR 0009](../docs/decisions/0009-layers-and-postgres.md)): a stateless FastAPI service, reachable only on the internal ward network (no published port in compose). The server sends inputs, and this service returns results with their rule trace and a **confidence index**. It stores and changes nothing.

| Engine | Status | What it returns |
|---|---|---|
| `news2` | ✅ | Total, band, points per component, missing/stale lists, a "partial" label, the response text, **confidence** |
| `assignment` | P3 | OR-Tools suggestion with reasons, workload before/after, confidence. Never applied by itself |
| `whatif` | P3 | SimPy results over N seeds: median and p5–p95, plus the assumptions list |
| `explain` | P3 | Template sentences from rule traces |

Deterministic by design, with no black-box model (HackCure section 6).

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
