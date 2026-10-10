# Assumptions

Answers from the team at kickoff (2026-10-10), plus defaults where no answer was given. Change this file when an answer changes.

## Team answers

| Question | Answer |
|---|---|
| Deadline / demo format | **No fixed deadline.** Phases are ordered by priority, not dated. The demo format is decided later (live demo with a recorded backup is the plan). |
| Hardware | **One Raspberry Pi, push buttons, LEDs and a speaker.** No ESP32 and no real vitals monitor. |
| Team skills and hours | Not given yet. Roles are **A / B / C placeholders**: each person picks a role from [`roles/`](roles/). |
| Languages | **English** for UI, code and docs. |
| GitHub | Commits are pushed with the `llamauser` account. The repo owner (`Yassinecoder06`) holds admin rights (branch protection). |

## Consequences

- **Hardware is no longer "Could".** The Pi plays the **bedside node** (buttons, LEDs, speaker) for the live showpiece, and can also run the gateway. The whitepaper's production design (ESP32 per bed, Pi per ward) is unchanged. See [ADR 0003](decisions/0003-pi-bedside-node.md).
- **No `firmware/` folder.** The node is Python on the Pi (`bedside-node/`).
- **English-only UI.** The whitepaper mentions French and Tunisian Arabic, so UI strings stay in one place per app so that a translation layer can be added later without a rewrite. Arabic right-to-left support is deferred. Audio phrases are recorded in English for the demo.
- **No dates.** Integration checkpoints happen at the end of each phase instead of on a calendar.

## Defaults and scope

- **Synthetic data only.** No real patients, staff or devices. Ward `W1` has 12 beds in 6 rooms ([`seed/ward-W1.yaml`](../seed/ward-W1.yaml)).
- **Device protocols are simulated.** The gateway replays simulator streams through the same adapter interface a real device would use.
- **Clinical parameters are illustrative.** The NEWS2 thresholds follow the RCP chart and must be confirmed by a clinician. Escalation timers and what-if rates are placeholders.
- **Auth is a stub** (`X-Staff-Id` header). Hospital SSO is out of scope.
- **Storage is SQLite** ([ADR 0001](decisions/0001-stack.md)).
- **Family-gateway hosting** is a plain container in the demo, not an approved national host.
- **Equipment reminders** (whitepaper 5.2) are **out of scope for now**.
- **Optional local LLM explainer**: out of scope. Explanations are template-based.
- **3D / Omniverse**: not used ([ADR 0006](decisions/0006-no-3d-twin.md)). The board uses a 2D floor plan.

## Contract additions beyond the kickoff plan (from the whitepaper)

These were added because the whitepaper requires them. The whitepaper wins over the kickoff plan.

- Call `kind`: `assist` or `comfort`. Comfort calls route to care assistants first. Calls auto-escalate on a repeated press or when NEWS2 is 5 or more (whitepaper 4.2).
- `binding` topic: bed to admission to devices, confirmed by a wristband scan (4.1). Family invites are tied to the admission.
- Medication events carry `recordedBy`. A patient-reported event never closes a dose (4.3).
- `staff/{id}/presence` topic: shift start/end and "called away", needed for the "nurse leaves" scenario.
- `call/state` topic published only by the server, so bedside LEDs show delivery state (4.2).
- `sim/clock` topic: demo-only accelerated clock.
- What-if reports the median and the 5th to 95th percentile over many seeds, with baseline and scenario on the same seeds (5.3).
- Family: QR code plus one-time code, rate limits, "not an emergency channel" notice (7.3, 7.4).
