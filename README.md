# Borj-PiCare: Ward Control Tower

**HackCure · Track 2 (Web & Mobile).** A care-coordination platform for hospital wards, including regional and district hospitals where the network is unreliable.

Borj-PiCare turns bedside signals into a live **digital twin** of the ward: vitals from ward machines, patient calls and medication taps. On top of it, staff get **prioritised, explainable suggestions**:
- who to see first (NEWS2, with its reasons and a confidence index);
- who is free, and how to rebalance the night (assignment suggestions);
- what happens if a nurse leaves (what-if simulation).

Critical alerts reach the nurse's phone, then the charge nurse, then a **remote on-call doctor**. The triage path never leaves the ward network, so it keeps working with no internet. A premium **Family Care Link** gives relatives consented, nurse-approved updates **without vitals**.

**Advisory only:** a clinician validates or rejects every suggestion, in 3 steps at most, and every action is audited.

> **Status:** P0. Architecture, contracts and team plan are done; the server skeleton is in review ([PR #2](https://github.com/Yassinecoder06/HackCure_Hackathon/pull/2)).
> Everything runs on **synthetic data**. No real patients, devices or hospital systems.

## Start here

| If you want to... | Read |
|---|---|
| Understand the idea | [`docs/Borj_PiCare_Whitepaper_v2.pdf`](docs/Borj_PiCare_Whitepaper_v2.pdf) |
| Know what the competition requires | [`docs/HackCure_Cahier_des_Charges.pdf`](docs/HackCure_Cahier_des_Charges.pdf) |
| See the architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Pick your role and first task** | [`docs/PLAN.md`](docs/PLAN.md) → [`docs/roles/`](docs/roles/) |
| Know the shared interfaces | [`contracts/`](contracts/) (MQTT topics, JSON Schemas, OpenAPI, FHIR mapping) |
| Know the hard rules | [`CLAUDE.md`](CLAUDE.md) (13 safety invariants + working rules) |
| See what was decided and assumed | [`docs/decisions/`](docs/decisions/), [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) |

## How it meets the HackCure requirements

| Requirement | Approach |
|---|---|
| Security and privacy by design | TLS 1.3 in transit, AES-256-GCM at rest, pseudonymous ids, login + hash-chained access audit, HMAC-signed measurements ([ADR 0010](docs/decisions/0010-security-baseline.md)) |
| Separate layers | Frontend apps · business-logic server · inference service · PostgreSQL ([ADR 0009](docs/decisions/0009-layers-and-postgres.md)) |
| Degraded network | The ward runs locally with no internet; store-and-forward at the gateway, nodes and apps; a live network-cut demo |
| Zero latency on triage | Local triage path, under 1 s from button to phone, measured on the board |
| Interoperability | JSON contracts + read-only FHIR R4 export with LOINC codes ([ADR 0011](docs/decisions/0011-interop-and-confidence.md)) |
| Explainable decision support | Deterministic engines with a confidence index and explanation on every output; human validates or rejects |

## Repo layout

```
contracts/        shared: MQTT topics, JSON Schemas, OpenAPI, FHIR mapping, validator   (all three)
seed/             synthetic ward layout, devices and staff roster                         (A)
simulator/        synthetic ward + scenario replayer                                      (A)
gateway/          ward gateway: read-only adapters, quality flags, HMAC, store-and-forward (A)
bedside-node/     Raspberry Pi call node: buttons, LEDs, speaker                          (A)
family-gateway/   DMZ service for the Family Care Link                                    (A)
infra/            docker-compose, TLS broker, Caddy proxy, deployment                     (A)
server/           business logic: twin, calls, consent, audit, API, FHIR export           (B)
inference/        NEWS2, assignment (OR-Tools), what-if (SimPy), confidence               (B)
apps/ward/        station board (/board), staff view (/staff), doctor view (/doctor)      (C)
apps/family/      relatives' app (separate build)                                         (C)
apps/twin3d/      3D twin view (Blender + three.js), polish                               (B)
tests/            cross-component, safety-invariant and integration tests                 (all)
docs/             whitepaper, HackCure spec, architecture, plan, roles, ADRs, dossier
```

## Install and run (local)

**Prerequisites:**
- Git.
- Python 3.12.
- Docker Desktop (or Docker Engine) with Compose v2.
- Node.js 20+, once the apps exist.

```bash
git clone https://github.com/Yassinecoder06/HackCure_Hackathon.git
cd HackCure_Hackathon

# Python tooling and contract/invariant tests
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # .venv/bin/pip on Linux/macOS
.venv/Scripts/python -m pytest

# Local secrets (PostgreSQL password, AES-256 data key) into .env, never committed
python infra/gen_secrets.py

# The demo stack: Mosquitto, PostgreSQL, inference, server (more services are added phase by phase)
docker compose up --build
# Log in with a demo PIN printed by gen_secrets.py (also in .env), then use the token:
#   curl -X POST localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"staffId":"CN1","secret":"<PIN>"}'
#   curl -H "Authorization: Bearer <token>" localhost:8000/api/v1/wards/W1/snapshot
```

Each component's README lists its own dependencies and run commands. Copy `.env.example` to `.env` for local settings, and never commit `.env`.

**Target for the demo:** one `docker compose up` on a clean laptop starts the broker (TLS), PostgreSQL, the server, inference, the simulator, the gateway, the apps and the family gateway, all behind Caddy over HTTPS. A hosted copy provides the active web URL (deliverable L2).

## Deliverables (HackCure)

| | Deliverable | Where |
|---|---|---|
| L1 | Public repo, clear history, exhaustive README | This repo |
| L2 | Working MVP with realistic synthetic data, active web URL | Local Docker setup + hosted URL (P5) |
| L3 | Deployment dossier: feasibility, regulatory compliance, roadmap at 3 and 6 months | [`docs/deployment-dossier.md`](docs/deployment-dossier.md) |
