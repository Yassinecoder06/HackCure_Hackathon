# Assumptions

Team answers and decisions, plus defaults where no answer was given. Change this file when an answer changes.

Inputs:
- The idea: [`Borj_PiCare_Whitepaper_v2.pdf`](Borj_PiCare_Whitepaper_v2.pdf).
- The competition rules: [`HackCure_Cahier_des_Charges.pdf`](HackCure_Cahier_des_Charges.pdf). When the two disagree, **the HackCure specification wins** for everything it requires (security, layers, deliverables, demo rules). The whitepaper wins on the product idea.

## Team answers and decisions

| Topic | Answer |
|---|---|
| Competition track | **Track 2, Web & Mobile** ([ADR 0008](decisions/0008-track-2.md)) |
| Deadline | No fixed deadline. Phases are done in order. |
| Demo format | **Live demo is mandatory.** HackCure accepts no pre-recorded video or static mockup as the MVP. A recording may exist only as a private safety net. |
| Hardware | One Raspberry Pi, push buttons, LEDs, a speaker. No ESP32. The dev PC has an NVIDIA RTX 4060 Laptop GPU. |
| Roles | **B is taken by @llamauser.** A and C are open: pick one in [`PLAN.md`](PLAN.md). |
| Languages | English for UI, code and docs (see "Open decisions"). |
| Equipment maintenance | **Out of scope.** Off-topic for Track 2. A device going offline still shows as stale data and a "device offline" alert, which is patient safety, not maintenance. |
| 3D twin | In, as polish after the core works: Blender bake + three.js ([ADR 0012](decisions/0012-3d-twin.md)). No Omniverse. |

## Open decisions (defaults apply until the team decides)

| Question | Default | Why it matters |
|---|---|---|
| Add a real **PPG + temperature sensor** (e.g. MAX30102 + DS18B20) to the Pi? | **Recommended, not yet decided** | Turns one bedside channel from simulated to real. It ticks HackCure's "biometric sensors" box and makes the live demo more convincing. It costs a few dinars. |
| UI language | English, with **French explanations available now** (server side: `?lang=fr`) | The specification and jury are francophone. Server-generated sentences are bilingual; the apps' own strings stay in one module per app, so a French UI is cheap. Arabic later. |

## Consequences of the answers

- The Pi plays the **bedside node** in the demo ([ADR 0003](decisions/0003-pi-bedside-node.md)). Production uses an ESP32 per bed.
- **No `firmware/` folder.** The node is Python on the Pi.
- **Phases have no dates.** Integration checkpoints happen at the end of each phase.

## Defaults and scope

- **Synthetic data only.** No real patients, staff or devices. Ward `W1` has 12 beds in 6 rooms ([`seed/ward-W1.yaml`](../seed/ward-W1.yaml)). The data must look medically realistic (HackCure L2).
- **Device protocols are simulated**, except an optional real sensor on the Pi.
- **Clinical parameters are illustrative.** The NEWS2 thresholds follow the RCP chart and must be confirmed by a clinician. Escalation timers and what-if rates are placeholders.
- **Security is real in the demo**: TLS 1.3, AES-256 at rest, real login, access audit ([ADR 0010](decisions/0010-security-baseline.md)). Hospital SSO is out of scope.
- **Storage is PostgreSQL**, with inference in its own service ([ADR 0009](decisions/0009-layers-and-postgres.md)).
- **Hosting:** a cloud VM for the "active web URL", plus a fully local Docker setup for the live demo. Neither is an INPDP-approved national host, so real deployment would need one.
- **Explanations are template-based** and confidence indices are deterministic ([ADR 0011](decisions/0011-interop-and-confidence.md)). An optional local LLM may later phrase handover summaries and answer ward questions, grounded on selected facts and checked by a verifier, never on alerts ([ADR 0013](decisions/0013-local-llm-grounded.md)).
- **FHIR:** read-only R4 export only. No writing into a real hospital information system.

## Contract additions beyond the kickoff plan

From the whitepaper:
- Call `kind` (`assist` or `comfort`). Comfort calls route to care assistants first. Calls auto-escalate on a repeated press or when NEWS2 is 5 or more.
- `binding` topic (bed to admission to devices). Medication events carry `recordedBy`.
- `staff/{id}/presence` topic, `call/state` (published by the server only), `sim/clock` (demo only).
- What-if reports the median and p5–p95 over many seeds, with the same seeds for baseline and scenario.
- Family: QR code plus one-time code, rate limits, "not an emergency channel" notice.

From the HackCure specification:
- An optional HMAC `integrity` field on every MQTT envelope.
- Real login (bearer tokens) instead of the `X-Staff-Id` stub.
- A `confidence` field on NEWS2 results, alerts and assignment suggestions.
- A read-only FHIR R4 export.
- Remote-doctor instructions on alerts.
- A latency metric on the stream.
