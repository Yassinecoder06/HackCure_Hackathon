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
- P1: **live stream** `GET /api/v1/wards/{ward}/stream` (WebSocket; the token is offered as subprotocols `["bearer", token]` so it never appears in URLs or access logs;
  audited):
  first a `snapshot`, then `bed` / `staff` / `clock` updates as events arrive, and `metrics` every 5 s.
  Ingest (MQTT thread) only notes which beds changed; each client coroutine merges bursts, rebuilds those beds with
  NEWS2 in a worker thread and sends them (`stream.py`, `live.py`). All beds are re-pushed every 30 s so readings
  visibly age into "stale" without new events. `metrics.triageLatencyMs` (p50/p95 over 60 s) is the server's share
  of the triage latency budget: event received to update sent.
- P2: **call engine** (`calls.py`, rules in [`config/calls.yaml`](config/calls.yaml)).
  - Assist calls go to nurses, comfort calls to care assistants.
  - Escalation: unacknowledged after 120 s → level 1; after 300 s → level 2 (charge nurse, plus the on-call
    doctor for assist calls). A repeated press escalates one level. A press from a patient with NEWS2 ≥ 5
    escalates at once. Timers run on the ward clock, from the patient's *original* press time (late-delivered
    calls escalate sooner).
  - Every decision is a server-published, retained `call/state` event that goes through normal ingest, so
    replays rebuild call states without re-running timers. Escalations are audited as `system`.
  - One-tap `POST .../calls/{id}/ack` and `.../resolve` record a staff `ack` event (audited).
- P2: **alerts** (`alerts.py`), derived from the twin: NEWS2 band (`news2_high`, `news2_single_param_3`),
  escalated calls, stale data, offline devices. Each alert has a priority on the ladder (low / medium /
  critical), a **confidence** and **explanation** sentences. `POST .../alerts/{id}/ack` silences an alert while
  its condition lasts. The stream sends `call` and `alert` messages; a cleared alert is sent once with
  `active: false`.
- P3: **assignment suggestions** (`assignment.py`). The server sends the live twin to the inference
  optimiser and keeps the result as a **pending** suggestion. It is audited when created and changes nothing.
  - Only `POST .../suggestions/{id}/decision` by a **charge nurse** applies it, as a server-only `assignment`
    event (stored, replayable, audited with the decider). Safety invariant 1 is enforced in code, with a static
    check in `tests/test_invariants.py`.
  - A newer suggestion expires older pending ones. Approving a plan the ward has moved past is refused as
    `stale_suggestion`.
  - Suggestions are made automatically (debounced, off the MQTT thread) when staff presence or admissions
    change, and pushed on the stream as `assignment_suggestion`.
  - The snapshot shows `assignedNurse` per bed and `assignedBeds` per staff member.
- P3: **what-if** `POST .../whatif/runs`. The server describes the live ward (nurses and care assistants on the ward,
  each occupied bed's NEWS2 band) to the inference simulator, adds the disruptions, and returns baseline vs scenario
  (median, p5–p95) with the assumptions. Beds without a complete NEWS2 are disclosed in the assumptions. Audited;
  never touches live state.
- P3: **medication timeline** (`meds.py`, rules in [`config/meds.yaml`](config/meds.yaml)).
  - **Only a doctor** creates a prescription (`POST .../prescriptions`). It is stored as an internal event in
    the encrypted log and **never published on MQTT** (it contains drug names).
  - Doses are generated from the daily times in ward local time (UTC+1).
  - **Only a nurse's record** (`POST .../doses/{id}/administration`, given / not given with a reason) closes a
    dose. A patient's "I took my pills" is shown separately and never closes one.
  - Overdue doses raise `dose_overdue` alerts. **Clashes** (too many doses, or more than one infusion, due for
    the same nurse in 15 min) are listed in `GET .../meds/timeline`.
  - The system never selects drugs or doses (invariant 1, statically checked).
- P3: **read-only FHIR R4 export** (`fhir.py`, `api/fhir_routes.py`, mapping in
  [`contracts/fhir-mapping.md`](../contracts/fhir-mapping.md)): `GET /fhir/r4/Patient/{id}`, `Encounter`,
  `Observation` and `MedicationAdministration` searches, returned as `application/fhir+json`.
  - Pseudonymised patients carry the HL7 `PSEUDED` label.
  - Vital signs come from the **event log** (the admission's full history), with LOINC codes and UCUM units.
    Flagged readings carry a note.
  - NEWS2 is a survey Observation with its components; a partial score is `preliminary`.
  - Only nurse-recorded doses are exported.
  - Every request is audited; there are no write methods (405).
  - Tests validate every resource with `fhir.resources` (R4B models).
- P3: **remote doctor instructions** (`POST .../alerts/{id}/instructions`, doctor only): the on-call doctor answers an
  escalation with a short instruction, stored as a staff `ack` event (`action: instruct`) and shown on the alert as
  `instructions` for the nurses. Audited; survives replays.
- P3: **explainer, English and French** (`explain.py`): every user-facing sentence lives in one bilingual
  module, so a clinician reviews all wording in one sitting and the jury sees it in French. The language comes from
  `?lang=en|fr`, then `Accept-Language`, then `BORJ_LANG`, and applies per stream connection too. Times are shown
  in ward local time. The inference layer returns language-neutral reason codes, and the server renders them.
  - **NEWS2 trend:** each bed's score 30 and 60 minutes ago, recomputed from its reading history (`news2Trend`).
  - **Priority:** every admitted bed is ranked (band, escalated or open calls, score, overdue doses) with reasons,
    e.g. "NEWS2 rose from 0 to 8 in the last 60 min." / "Le NEWS2 est passé de 0 à 8 en 60 min."
  - Style rule: say what the data shows, never what the patient has.
- P4: **Family Care Link, ward side** (`family.py`, `family_publisher.py`, `api/family_routes.py`, rules in
  [`config/family.yaml`](config/family.yaml)). Nurses only; everything audited; stored as internal `family` events
  (encrypted log, never MQTT).
  - **Consent first:** no invite, draft or publication without an active consent covering that kind of update.
    Withdrawal is immediate, and discharge or transfer revokes the whole link automatically.
  - **Invites:** QR + 6-digit one-time code. The code appears only in the response; only a salted scrypt hash
    leaves the ward (`hash_code` / `verify_code`).
  - **Privacy filter:** an approved update is rebuilt from allow-listed fields only, validated against
    `family-update.schema.json` (fails closed), and free text mentioning vital signs, scores, doses or the
    patient's own drug names is refused (422). No staff identity is ever included.
  - **Outbound only:** each event stores the exact payload in `outbound`. `python -m borj_server.family_publisher`
    (compose service `family-publisher`, profile `family`, ward + DMZ networks, **no ports**) forwards only those,
    in order, retrying until family-gateway accepts.
- **Frame integrity (invariant 13, `integrity.py`):** every MQTT message is checked before ingest. A signature
  that is present must verify with the key named by `keyId` (`BORJ_DEVICE_KEYS`), and a bedside node's key
  (`node-B04`) only signs for its own bed. In `require` mode, unsigned measurements (`vitals`, `device-status`,
  `binding`, `call`) are refused too. Each rejection is logged and written to the audit chain (actor `mqtt`,
  action `integrity.rejected`), so it never reaches the event log or the twin. Compose runs `verify` until
  role A's signers load their keys, then switches to `require`.
- **Doctor orders** (`POST/GET .../doctor/orders`, doctors write, every read audited): the remote doctor's free-text
  message to the nurses about an admitted bed. An encrypted `doctor-order` event (internal topic `.../order`),
  so it survives a restart and replays on rebuild. It never changes a prescription, an assignment or a score,
  and it is also attached to the bed's active alert as the doctor's instruction.
- **Internal topics are refused over MQTT** (`prescription`, `family`, `order`; `bc.INTERNAL_SCHEMAS`): only the
  server writes them, after an authenticated REST action. A forged one on the broker is dropped and audited in
  every integrity mode. (Broker ACLs, role A, should also stop devices publishing outside their own bed's topics.)
- Still to come: SMS fallback (stub logs only).

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
