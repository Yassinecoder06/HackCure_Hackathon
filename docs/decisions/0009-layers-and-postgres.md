# 0009. Separate layers: frontend, business logic, inference, database (PostgreSQL)

Status: accepted (2026-10-10). Supersedes the SQLite choice in [0001](0001-stack.md).

## Context

The HackCure specification (section 5) requires a **strict separation of the frontend, business logic, inference and database layers**. In our first design, the decision engines ran inside the server process, and SQLite was a file inside it.

## Decision

| Layer | Service | Contents |
|---|---|---|
| Frontend | `apps/ward`, `apps/family`, `apps/twin3d` | UI only, no business rules |
| Business logic | `server/` (FastAPI) | Ingest, twin, call state machine, consent, audit, REST/WebSocket API, privacy filter |
| Inference | `inference/` (FastAPI, internal only) | NEWS2 scoring, assignment (OR-Tools), what-if (SimPy), explanations and confidence indices. Stateless: it receives the inputs, returns results and a rule trace |
| Database | `postgres` container | Event log, audit log, consent records, prescriptions. Patient payloads encrypted with AES-256-GCM (see [0010](0010-security-baseline.md)) |

- The server calls the inference service over HTTP on the internal ward network.
- **The triage path must stay within the latency budget** ([0008](0008-track-2.md)). NEWS2 is cheap, so the call is local and fast. If the inference service is down, the board shows "score unavailable" (stale, never a guessed value) and calls and escalation keep working.
- Unit tests may still use SQLite in memory through the same repository layer, but compose and the demo use PostgreSQL.

## Consequences

- One more container (`postgres`) and one more service (`inference`). B owns both.
- The P0 server skeleton (SQLite) is migrated in P1.
- This gives a clear answer to the jury's "scalability" question: the inference service scales horizontally, and the database is a standard managed-able PostgreSQL.
