# Role B: Brain ("what the system knows and decides")

**Owns:**
- `server/`: business logic, twin, security, API, FHIR export, family privacy filter and publisher.
- `inference/`: NEWS2, assignment, what-if, explanations and confidence.
- The PostgreSQL schema.
- `apps/twin3d` (the 3D view).
- `contracts/openapi.yaml` and `contracts/fhir-mapping.md`.

Shared contract reviews with A and C.

Read first:
- [Whitepaper](../Borj_PiCare_Whitepaper_v2.pdf), sections 5 and 6.
- [HackCure specification](../HackCure_Cahier_des_Charges.pdf), sections 5 and 6.
- [ARCHITECTURE](../ARCHITECTURE.md).
- ADRs [0009](../decisions/0009-layers-and-postgres.md), [0010](../decisions/0010-security-baseline.md), [0011](../decisions/0011-interop-and-confidence.md) and [0012](../decisions/0012-3d-twin.md).
- [`contracts/`](../../contracts/).

---

## P0: server skeleton ✅ (PR #2)

- Event log keyed by `eventId`, where duplicates are no-ops (invariant 6).
- Live twin derived from the log (bindings, vitals, devices, presence), with event-time guards and a rebuild on out-of-order arrival.
- Freshness labels (fresh/stale/invalid) against the ward clock. Absent stays absent.
- MQTT ingest with contract validation, the demo clock, `/health`, `/snapshot`, an audit table.
- Dockerfile, compose service, CI end-to-end MQTT smoke test.

## P1: secure vertical slice

**Database and layers ([ADR 0009](../decisions/0009-layers-and-postgres.md))**
- [ ] Move the event log and audit log to **PostgreSQL**, with a `postgres` service in compose (coordinate with A). Keep the repository layer so unit tests can still use in-memory SQLite.
- [ ] **AES-256-GCM** encryption of event payloads and audit details before storage. The key comes from env/secret, with a key id stored for rotation. Write a test that the raw database contains no plaintext vitals.

**Inference service**
- [ ] `inference/` (FastAPI, internal network only, stateless).
- [ ] **NEWS2:**
  - Thresholds in `inference/config/news2.yaml`, following the RCP chart, each marked "TO BE CONFIRMED BY A CLINICIAN" (invariant 8).
  - Uses only fresh, valid parameters. Missing, stale or invalid ones are listed and the result is labelled partial (invariant 5).
  - SpO2 scale 2 only when a clinician sets it.
  - Bands: 0–4 low, a 3 in any single parameter is low-medium, 5–6 medium, 7+ high.
  - Points per component.
  - **Confidence** = the share of parameters fresh and valid, discounted by age ([ADR 0011](../decisions/0011-interop-and-confidence.md)).
- [ ] The server calls inference after each vitals update. If inference is down, the score shows "unavailable", never a guessed value.

**Security ([ADR 0010](../decisions/0010-security-baseline.md))**
- [ ] **Login:** staff id + PIN/password (argon2) → short-lived signed token, with roles from the seed. It replaces `X-Staff-Id`.
- [ ] **Access audit:** every read and write of patient data is logged (who, what, when).
- [ ] **Hash-chained audit log**, with a verification endpoint or CLI. Write a test that tampering is detected.
- [ ] **HMAC check** on incoming MQTT messages that carry `integrity`. Bad signatures are rejected and logged.

**API**
- [ ] WebSocket `stream`: an initial snapshot, then `bed`/`call`/`alert`/`clock`/`metrics` messages.
- [ ] `POST .../observations`: manual fast entry → a `vitals` event with `sourceType: manual`.

## P2: calls, escalation, latency

- [ ] A call state machine as in [`mqtt-topics.md`](../../contracts/mqtt-topics.md). Only the server publishes `call/state`.
- [ ] Routing: `assist` to nurses, `comfort` to care assistants.
- [ ] Escalation on: unacknowledged timeout (level 1 re-alert, level 2 charge nurse), repeated press, NEWS2 ≥ 5. Timers live in `server/config/calls.yaml`.
- [ ] Alerts follow the escalation ladder (low/medium/critical), each with a confidence and an explanation.
- [ ] Ack and resolve endpoints, which take **one tap**. All audited.
- [ ] **Latency metric:** end-to-end from the event `ts` to delivery on the WebSocket, published as `metrics` (p50/p95) for the board. Budget: under 1 s.
- [ ] Escalation to the **remote on-call doctor** (level 2+) through the same alert stream. The SMS fallback hook is a stub, behind config.
- [ ] Tests: escalation on the demo clock, repeated press, replay is a no-op, latency is measured.

## P3: decisions and telemedicine

- [ ] **Assignment** (inference, OR-Tools CP-SAT):
  - Inputs: acuity + NEWS2 workload, skills, proximity, continuity, locked assignments, breaks.
  - Output: a suggestion with reasons, workload before and after, and a confidence (solver status, data freshness).
  - **Never auto-applied**: only a charge nurse's decision changes assignments (invariant 1). Write a test for this.
- [ ] **What-if** (inference, SimPy):
  - Clone the twin, apply the disruptions, simulate ahead over N seeds, using the same seeds for baseline and scenario.
  - Report the median and p5–p95, plus the assumptions list.
  - **Erlang-C oracle test**: 26 calls/h at 8 min each gives 3 nurses → unbounded, 4 → 10.8 min, 5 → 1.9 min; routed 40% to care assistants gives 4.2 / 0.8 / 0.2 min.
- [ ] **Medications:** the doctor enters the prescription → the engine creates doses and flags overdue ones and clashes. Only a nurse's tap closes a dose; patient-reported entries are stored separately. Never choose drugs or doses.
- [ ] **Remote doctor instructions:** a short note on an alert, audited and shown to the nurse. It works asynchronously: queued and delivered when the doctor's phone reconnects.
- [ ] **FHIR R4 export (read-only)** following [`fhir-mapping.md`](../../contracts/fhir-mapping.md): `Patient`, `Encounter`, `Observation` (LOINC), `MedicationAdministration`. Access is audited.
- [ ] **Explainer:** template sentences from the rule traces.

## P4: family privacy filter + outbound publisher

- [ ] Consent records. Revocation is immediate, and discharge or transfer revokes everything (invariant 4).
- [ ] Invites (409 without consent), with only a hash of the one-time code stored.
- [ ] Draft → nurse decision → **privacy filter** (allow-list, then schema validation) → push.
- [ ] The publisher has **no listening port** (invariant 3).
- [ ] Invariant test: a twin full of vitals, scores and drugs leaks nothing outside the allow-list (invariant 2).

## P5: 3D twin (polish, [ADR 0012](../decisions/0012-3d-twin.md)) and delivery

- [ ] Blender (`bpy` scripts): generate the ward from `seed/ward-W1.yaml`, place CC0/CC-BY assets, PBR materials, **bake the lighting with Cycles/OptiX on the RTX 4060**, export a compressed `.glb`.
- [ ] `apps/twin3d` (React Three Fiber + drei + postprocessing):
  - HDRI lighting, N8AO, bloom, AgX tone mapping.
  - Live NEWS2 glow on the monitors, a "no signal" look for stale data, call lights, Mixamo nurses.
  - Adaptive quality, and a path-traced photo mode.
  - `CREDITS.md` listing the asset licences.
- [ ] A seed/reset script for demos, and performance checks.

## You give / you need

- **Give C:** snapshot, WebSocket and login (P1); calls (P2); decision and doctor endpoints (P3); family endpoints (P4). Keep `openapi.yaml` accurate, because C mocks it.
- **Give A:** `call/state` (P2), the outbound pushes (P4), the HMAC key list format.
- **Need from A:** a TLS broker and HMAC-signed events (P1), the ward layout and seed prescriptions (P3), family-gateway (P4).

## Invariants you guard

1 (advisory + audit), 2 (privacy filter), 4 (consent), 5 (missing/stale labelled), 6 (idempotency), 8 (clinical parameters in config), 10 (encryption), 11 (access audit / non-repudiation), 12 (confidence + explanation).
