# Borj-PiCare: Ward Control Tower

Health-tech hackathon project for a Tunisian public hospital ward.

Borj-PiCare turns bedside signals into a live **digital twin** of the ward: vitals from ward machines, patient calls and medication taps. On top of it, staff get **prioritised, explainable suggestions**: who to see first (NEWS2), who is free, and what happens if a nurse leaves (what-if simulation). It is **advisory only**, and a human always decides. A premium **Family Care Link** gives relatives consented, nurse-approved updates **without vitals**.

> **Status: project setup.** The architecture, contracts and team plan are in place. Feature code has not started yet.
> Everything runs on **synthetic data**. No real patients, devices or hospital systems.

## Start here

| If you want to... | Read |
|---|---|
| Understand the idea | [`docs/Borj_PiCare_Whitepaper_v2.pdf`](docs/Borj_PiCare_Whitepaper_v2.pdf) |
| See the architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Pick your role and first task** | [`docs/PLAN.md`](docs/PLAN.md) → [`docs/roles/`](docs/roles/) |
| Know the shared interfaces | [`contracts/`](contracts/) (MQTT topics, JSON Schemas, OpenAPI) |
| Know the hard rules | [`CLAUDE.md`](CLAUDE.md) (safety invariants + working rules) |
| See what was assumed | [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md), [`docs/decisions/`](docs/decisions/) |

## Repo layout

```
contracts/        shared: MQTT topics, JSON Schemas, OpenAPI, examples, validator   (all three)
seed/             synthetic ward layout and staff roster                              (A)
simulator/        synthetic ward + scenario replayer                                  (A)
gateway/          ward gateway: device adapters, quality flags, store-and-forward     (A)
bedside-node/     Raspberry Pi call node: buttons, LEDs, speaker                      (A)
family-gateway/   DMZ service for the Family Care Link                                (A)
infra/            docker-compose, Mosquitto config                                    (A)
server/           FastAPI: twin, NEWS2, calls, assignment, what-if, meds, audit       (B)
apps/ward/        station board (/board) + staff view (/staff)                        (C)
apps/family/      relatives' app (separate build)                                     (C)
tests/            cross-component and safety-invariant tests                          (all)
docs/             whitepaper, architecture, plan, roles, ADRs, demo script
```

## Running

Today, only the broker and the contract checks exist:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # .venv/bin/pip on Linux/macOS
.venv/Scripts/python -m pytest                        # validates all contracts
docker compose -f infra/docker-compose.yml up         # Mosquitto on localhost:1883
```

The target, once phase P0 is done:

```bash
git clone https://github.com/Yassinecoder06/HackCure_Hackathon.git
cd HackCure_Hackathon
docker compose -f infra/docker-compose.yml up
```
