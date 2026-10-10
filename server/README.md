# server/ (owner: B)

FastAPI ward server. Spec and task list: [`docs/roles/B-brain.md`](../docs/roles/B-brain.md).

## Status

- P0 done: event log (SQLite, deduped by `eventId`), live twin rebuilt from the log, MQTT ingest with contract
  validation, demo clock, `GET /health`, `GET /api/v1/wards/{ward}/snapshot`, audit log table.
- P1: event log and audit log in **PostgreSQL** (compose) / SQLite (tests, local dev) through one SQLAlchemy Core
  code path (`store.py`). Every payload and audit detail is **encrypted with AES-256-GCM** before it reaches the
  database (`crypto.py`): a per-row random nonce, the row id bound in as associated data, and a key id per row for
  rotation. Only routing metadata stays in clear (event id, schema, topic, ward, timestamp). The key comes from
  `BORJ_DATA_KEY` (`python infra/gen_secrets.py` writes it to `infra/.env`).
- P1 (in progress): the snapshot carries **NEWS2 per admitted bed** from the [inference layer](../inference/README.md)
  (`news2Status`: `ok` / `unavailable` / `not_admitted`). The server decides each reading's freshness against the ward
  clock and sends it to inference (`scoring.py`, `inference_client.py`, 0.5 s timeout). If inference is down, NEWS2
  shows as `unavailable`, never as a guess.
- P1: **login** (`POST /api/v1/auth/login`): demo PINs for the synthetic staff (`BORJ_STAFF_PINS` in `infra/.env`) are
  hashed with argon2id at startup, and a successful login returns a short-lived HS256 token (4 h). Five failures
  lock the staff id for 5 minutes. **Every access to patient data needs a token and is audited with the actor's
  name.** The audit log is **hash-chained** (`store.verify_audit_chain`, `GET /api/v1/wards/{ward}/audit/verify`,
  charge nurse only), so editing or deleting any entry is detected.
- P1: **live stream** `GET /api/v1/wards/{ward}/stream` (WebSocket, token in the `token` query parameter, audited):
  first a `snapshot`, then `bed` / `staff` / `clock` updates as events arrive, and `metrics` every 5 s.
  Ingest (MQTT thread) only notes which beds changed; each client coroutine merges bursts, rebuilds those beds with
  NEWS2 in a worker thread and sends them (`stream.py`, `live.py`). All beds are re-pushed every 30 s so readings
  visibly age into "stale" without new events. `metrics.triageLatencyMs` (p50/p95 over 60 s) is the server's share
  of the triage latency budget: event received to update sent.
- Still to come in P1: HMAC checks on incoming frames.

## Run

```bash
# with the broker (from repo root)
docker compose -f infra/docker-compose.yml up --build
curl localhost:8000/api/v1/wards/W1/snapshot

# without docker, API only (e.g. for UI work)
python infra/gen_secrets.py   # once; then load infra/.env into your shell (BORJ_DATA_KEY)
PYTHONPATH="contracts;server" BORJ_MQTT_ENABLED=0 BORJ_DATA_KEY=<from infra/.env> .venv/Scripts/python -m uvicorn borj_server.main:app --reload

# tests (from repo root)
.venv/Scripts/pip install -r requirements-dev.txt -r server/requirements.txt -r inference/requirements.txt
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
