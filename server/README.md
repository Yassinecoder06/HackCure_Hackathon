# server/ (owner: B)

FastAPI ward server. Spec and task list: [`docs/roles/B-brain.md`](../docs/roles/B-brain.md).

## Status

P0 done: event log (SQLite, deduped by `eventId`), live twin rebuilt from the log, MQTT ingest with contract
validation, demo clock, `GET /health`, `GET /api/v1/wards/{ward}/snapshot`, audit log table.

## Run

```bash
# with the broker (from repo root)
docker compose -f infra/docker-compose.yml up --build
curl localhost:8000/api/v1/wards/W1/snapshot

# without docker, API only (e.g. for UI work)
PYTHONPATH="contracts;server" BORJ_MQTT_ENABLED=0 .venv/Scripts/python -m uvicorn borj_server.main:app --reload

# tests (from repo root)
.venv/Scripts/pip install -r requirements-dev.txt -r server/requirements.txt
.venv/Scripts/python -m pytest
```

On Linux/macOS use `:` instead of `;` in `PYTHONPATH` and `.venv/bin/`.

## How the twin works

`events` table = source of truth. `ingest.py` validates every message against `contracts/`, stores it
(duplicates are no-ops), and applies it to the in-memory twin (`twin/handlers.py`). Every update is guarded by
event time; if an event arrives out of order the twin is rebuilt from the log, so live state always equals a
replay. The twin is also rebuilt on startup. Readings are labelled fresh/stale/invalid against the ward clock
when serialised (`twin/views.py`), and a new admission never inherits the previous patient's readings.

## Layout

```
server/
  borj_server/
    main.py           # FastAPI app, MQTT subscriber, WebSocket
    twin/             # ward state store + idempotent event handlers
    engines/
      news2/          # deterministic NEWS2 with missing/stale handling + explanation
      calls/          # call state machine, routing, escalation timers
      assignment/     # OR-Tools suggestion (never auto-applied)
      whatif/         # SimPy, many seeds, median + p5-p95, Erlang-C oracle test
      meds/           # prescriptions -> doses, overdue, clashes (never chooses drugs)
      explain/        # template sentences from rule traces
      family/         # consent, privacy filter, outbound publisher
    api/              # routes matching contracts/openapi.yaml
  config/             # news2.yaml, calls.yaml, whatif.yaml (clinical params: TO BE CONFIRMED BY A CLINICIAN)
  tests/
```

API contract: [`contracts/openapi.yaml`](../contracts/openapi.yaml).
