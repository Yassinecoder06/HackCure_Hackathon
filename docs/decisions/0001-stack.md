# 0001. Tech stack

Status: accepted (kickoff). **Storage superseded by [0009](0009-layers-and-postgres.md): PostgreSQL in its own container, plus a separate inference service.**

## Decision

| Concern | Choice |
|---|---|
| Backend, engines, simulator, gateway, bedside node | Python 3.12. FastAPI for HTTP. pytest. ruff for lint. |
| Assignment | Google OR-Tools (CP-SAT) |
| What-if | SimPy |
| Messaging | Mosquitto (MQTT 3.1.1/5), paho-mqtt client |
| Storage | ~~SQLite~~ → **PostgreSQL** (see 0009). SQLite only for in-memory unit tests |
| Apps | TypeScript, React, Vite. Installable web app (PWA). |
| Contracts | JSON Schema 2020-12 and OpenAPI 3.1 in `contracts/` |
| Run everything | `docker compose up` from `infra/` |
| TLS / reverse proxy | Caddy, TLS 1.3 only (see [0010](0010-security-baseline.md)) |
| Encryption at rest | `cryptography` (AES-256-GCM) |

## Why SQLite at first (historical)

SQLite was picked for simplicity. The HackCure specification then required a separate database layer, so 0009 moved to PostgreSQL.

## Consequences

- Python versions are pinned per component in `requirements.txt`. Node versions are pinned in `package.json` with a lockfile.
- Any change to this stack needs a new ADR.
