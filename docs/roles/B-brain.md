# Role B: Brain ("what the system decides")

**Owns:** `server/` (twin, engines, REST/WebSocket API, audit log, family privacy filter and outbound publisher) and `contracts/openapi.yaml`. Shared contract reviews with A and C.

**Good fit if you like:** Python backend, algorithms and optimisation, simulation, clean testable logic.

Read first: [whitepaper](../Borj_PiCare_Whitepaper_v2.pdf) sections 5 and 6, [ARCHITECTURE](../ARCHITECTURE.md), [`contracts/openapi.yaml`](../../contracts/openapi.yaml), [`contracts/mqtt-topics.md`](../../contracts/mqtt-topics.md).

---

## First task (P0): server skeleton + ingest

Build `server/` as a FastAPI app (`borj_server`) with this layout: `twin/`, `engines/{news2,calls,assignment,whatif,meds,explain,family}/`, `api/`, `config/`.

Acceptance criteria:
- [ ] `GET /health` works, with a Dockerfile and a service in `infra/docker-compose.yml` (coordinate with A).
- [ ] MQTT subscriber on `borj/#` validates every message with `borj_contracts.validate_message` and logs and rejects invalid ones.
- [ ] **Idempotent ingest**: events are stored in an SQLite `events` table keyed by `eventId`, and a duplicate is a no-op (invariant 6). Unit-tested with `contracts/examples/*.json`.
- [ ] Out-of-order and late events (`deliveredLate`, `late_delivery`) are stored with their original `ts`.
- [ ] Demo clock: when `sim/clock` is present, "now" = `simTs`, otherwise wall-clock UTC.
- [ ] `GET /api/v1/wards/{ward}/snapshot` returns beds from `seed/ward-W1.yaml` plus bound admissions (no NEWS2 yet).
- [ ] An audit log table and helper exist from day one.

## P1: Twin + NEWS2 (vertical slice)

- **Twin**: the state per bed (admission, latest reading per parameter with `ts` and `sourceType`, devices), staff and presence, open calls, alerts. Rebuildable by replaying stored events.
- **NEWS2 engine** (`engines/news2/`):
  - [ ] Thresholds in `server/config/news2.yaml`, following the RCP NEWS2 chart, each block commented "TO BE CONFIRMED BY A CLINICIAN" (invariant 8).
  - [ ] Uses only fresh, valid parameters. Missing/stale/invalid ones are listed, and the result is labelled partial (invariant 5).
  - [ ] SpO2 scale 2 only when a clinician has set `spo2_scale: 2`.
  - [ ] Bands: 0–4 low, a 3 in any single parameter means low-medium (urgent ward review), 5–6 medium, 7+ high. Response texts come from config.
  - [ ] Explains itself: points per component, as in `News2Result` in the OpenAPI.
  - [ ] Unit tests for each parameter boundary, missing/stale cases and the single-parameter-3 rule.
- **API**: `snapshot` plus the WebSocket `stream` (an initial snapshot, then `bed`/`call`/`alert`/`clock` messages), and `POST .../observations` for manual fast entry, which publishes `vitals` with `sourceType: manual`.

## P2: Calls and escalation

- A state machine as in [`mqtt-topics.md`](../../contracts/mqtt-topics.md). Only the server publishes `call/state` (retained).
- Routing: `assist` goes to nurses; `comfort` goes to care assistants and stays visible to nurses.
- Escalation on: `ack_timeout_s` → re-alert (level 1); `escalate_timeout_s` → charge nurse (level 2); repeated press; current NEWS2 ≥ 5. All timers live in `server/config/calls.yaml`.
- Alerts follow the escalation ladder (low = silent badge, medium = notification, critical = persistent until acked).
- `POST .../calls/{id}/ack|resolve`, `POST .../alerts/{id}/ack`, staff `presence`. All are logged in the audit log.
- Tests: an unacknowledged call escalates on the demo clock, a repeated press escalates, and a replayed `call` event changes nothing.

## P3: Decisions

- **Assignment** (`engines/assignment/`, OR-Tools CP-SAT):
  - Inputs: acuity-weighted load (acuity + NEWS2), skills, proximity (from `seed/` positions), continuity of care, locked assignments, breaks.
  - Output: an `AssignmentSuggestion` with human-readable reasons and load before/after.
  - **Never auto-applied**: only `POST .../decision` by a charge nurse changes assignments (invariant 1). Write a test that no code path changes assignments without a logged human decision.
  - Triggered on staff presence changes, admissions and NEWS2 jumps.
- **What-if** (`engines/whatif/`, SimPy):
  - Clone the twin, apply the disruptions, simulate `horizonMin` ahead, over `seeds` runs.
  - The baseline and the scenario use the **same seeds**. Report the median and p5–p95 per metric (`MetricSet`).
  - **Erlang-C oracle test**: with steady Poisson arrivals and exponential 8-minute service times, the simulator must reproduce the whitepaper table within tolerance. With 26 calls/h the waits are: 3 nurses unbounded, 4 nurses 10.8 min, 5 nurses 1.9 min. With 40% of calls routed to care assistants: 4.2, 0.8 and 0.2 min. The analytic values are already verified.
  - Return the `assumptions` list so the UI can show them.
- **Medications** (`engines/meds/`):
  - A doctor enters the prescription; the engine generates scheduled doses, flags overdue ones and detects clashes (e.g. several infusions due at once with one nurse free).
  - Only a nurse `given`/`not_given` closes a dose. `patient_reported_taken` is stored separately.
  - **Never** suggest drugs or doses.
- **Explainer** (`engines/explain/`): English template sentences built from the rule traces (NEWS2 components, escalation reason, assignment reasons). No LLM.

## P4: Family privacy filter + outbound publisher

- Consent records per admission and relative. Revocation is immediate. Discharge or transfer revokes everything (invariant 4).
- Invite creation (409 without consent), one-time code generation (store only the hash), and the QR URL.
- Update drafts → nurse decision → **privacy filter** (build `family-update` from allow-listed fields only, then validate against the schema) → push.
- The **publisher** is a worker with **no listening port** that POSTs to family-gateway `/ingest/v1/*` (invariant 3).
- Invariant test: generate updates from a twin full of vitals, scores and drugs, and assert that nothing outside the allow-list reaches the payload (invariant 2).

## You give / you need

- **Give C:** the snapshot and WebSocket early (P1). Until then C mocks from `openapi.yaml`, so keep the server faithful to it.
- **Give A:** `call/state` (P2) and the outbound pushes (P4).
- **Need from A:** schema-valid events (P0), quality flags (P1), the ward layout and seed prescriptions (P3), family-gateway ingest (P4).

## Invariants you guard

1 (advisory only + audit), 2 (privacy filter), 4 (consent first), 5 (missing/stale labelled), 6 (idempotency), 8 (clinical parameters in config).
