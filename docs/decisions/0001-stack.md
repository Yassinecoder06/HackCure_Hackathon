# 0001. Tech stack

Status: accepted (kickoff)

## Decision

| Concern | Choice |
|---|---|
| Backend, engines, simulator, gateway, bedside node | Python 3.12. FastAPI for HTTP. pytest. ruff for lint. |
| Assignment | Google OR-Tools (CP-SAT) |
| What-if | SimPy |
| Messaging | Mosquitto (MQTT 3.1.1/5), paho-mqtt client |
| Storage | **SQLite** (file in a docker volume), behind a thin repository layer |
| Apps | TypeScript, React, Vite. Installable web app (PWA). |
| Contracts | JSON Schema 2020-12 and OpenAPI 3.1 in `contracts/` |
| Run everything | `docker compose up` from `infra/` |

## Why SQLite instead of PostgreSQL

It means one fewer container and no migration tooling, and a single server process is the only writer. It also leaves fewer things to break in a live demo. Keep SQL portable, so switching to PostgreSQL later is a config change plus migrations.

## Consequences

- Python versions are pinned per component in `requirements.txt`. Node versions are pinned in `package.json` with a lockfile.
- Any change to this stack needs a new ADR.
