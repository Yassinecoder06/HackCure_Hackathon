# Role A: Edge and data ("how reality gets in")

**Owns:** `simulator/`, `gateway/`, `bedside-node/`, `infra/`, `seed/`, `family-gateway/`, `contracts/schemas/` and `contracts/mqtt-topics.md`. Shared contract reviews with B and C.

**Good fit if you like:** Python, networking/MQTT, Docker, Raspberry Pi and hardware, test data.

Read first: [whitepaper](../Borj_PiCare_Whitepaper_v2.pdf) sections 4 and 7.3–7.4, [ARCHITECTURE](../ARCHITECTURE.md), [`contracts/mqtt-topics.md`](../../contracts/mqtt-topics.md), [ADR 0003](../decisions/0003-pi-bedside-node.md).

---

## First task (P0): simulator v0 + compose

Build `simulator/` as a Python package (`python -m borj_sim`) that reads a scenario from `simulator/scenarios/` and the ward from `seed/ward-W1.yaml`.

Acceptance criteria:
- [ ] Emits `binding` (admit each occupied bed), `vitals` (device params per the bed's device profile, so absent params really are absent), `device/status` heartbeats, `call` presses (Poisson, assist/comfort share, repeat presses), background `ack`s, `staff/{id}/presence`, and `sim/clock`.
- [ ] Every message validates with `borj_contracts.validate_message(topic, payload)`.
- [ ] Seeded and reproducible: the same seed gives identical output, including `eventId`s (deterministic ULIDs).
- [ ] `--speed N` (sim seconds per wall second, 0 = as fast as possible), `--dry-run` (JSON lines to stdout), `--broker host:port`.
- [ ] Scripted events from the scenario files: `deteriorate`, `set_manual`, `call` (with `no_ack`), `call_rate`, `admit`, `staff_leaves`, `device_offline`, `node_outage_call`.
- [ ] `infra/docker-compose.yml` runs `mosquitto` + `simulator`. `docker compose up` shows events (e.g. `mosquitto_sub -t 'borj/#' -v`).
- [ ] Tests in `simulator/tests/`: every scenario in dry-run mode yields only schema-valid messages, unique eventIds, and no `null`/zero placeholders.
- [ ] CI runs those tests.

In v0 the simulator may publish `vitals` directly. In P1 it switches to emitting device streams that the gateway parses.

## P1: Gateway (vertical slice)

- **Adapter interface** in `gateway/adapters/`: `connect()`, `read() -> RawReading`, `close()`. Adapters are **read-only** and never write to a device.
- **Replay adapter**: reads a line-based device stream over TCP from the simulator. This simulator-to-gateway format is internal to A and does not need to go in `contracts/`. Mimic what a monitor's serial/HL7 output looks like.
- **Validity and freshness**: plausibility ranges in a config file (`gateway/config/quality.yaml`, commented "to be validated by biomedical/clinical staff"), flags `sensor_off` / `artifact` / `implausible`, and `stale_after_s` per device type.
- **Bed binding**: device → bed map, updated by `binding` attach/detach events.
- **Store-and-forward**: a SQLite outbox. If the broker is down, queue the events and replay them with their original `ts` and `eventId`, adding `late_delivery`. Write a test that kills the broker mid-run.
- Acceptance: the simulator in device-stream mode → gateway → MQTT gives schema-valid `vitals` with correct flags. B's server shows them.

## P2: Pi bedside node + peak scenario

- `bedside-node/` uses Python and `gpiozero`: an assist button, a comfort button, LEDs and the speaker.
- It publishes `call` (repeat press = same `callId`, `pressCount` + 1) and subscribes to the retained `borj/{ward}/{bed}/call/state`.
- LED states:
  - `pressed`: short beep and pulse.
  - `sent`: steady amber.
  - `acknowledged`: green pulse.
  - No `call/state` within N seconds: `not_sent`, which means fast red blink, buzzer and the recorded phrase "please use the emergency bell". Queue the press locally and replay it with `deliveredLate: true`.
- Mock GPIO mode (`MockFactory`) so the node runs on a laptop and in CI.
- Audio: a small fixed set of pre-recorded English phrases. Drug names are never spoken. Volume limit.
- Wiring diagram and setup in `bedside-node/README.md`.
- Tune `night-shift-peak.yaml` so the storyline is visible at demo speed (coordinate with C's demo script).

## P3: Data for decisions

- Ward layout distances (from `seed/` positions) for B's assignment proximity.
- Seed prescriptions (synthetic) in `seed/`, so B can build the medication timeline, and simulator `med` events (nurse taps, plus some `patient_reported_taken`).

## P4: family-gateway (DMZ)

Implement [`contracts/family-gateway.openapi.yaml`](../../contracts/family-gateway.openapi.yaml) as FastAPI with SQLite:
- [ ] `/ingest/v1/*` validates against the allow-list schemas and rejects anything else (invariant 2). A bearer token from env.
- [ ] Revocation takes effect immediately: kill sessions and delete stored updates (invariant 4).
- [ ] Redeem with QR + one-time code (hash compare), sessions, rate limits (429), and an audit log of every view.
- [ ] Serves the `apps/family` build.
- [ ] **Network isolation**: in compose, family-gateway sits only on the `dmz` network. Add a test that it cannot resolve or reach `mosquitto` or `server` (invariant 3).

## P5

- Clean-machine install test of `docker compose up`.
- `docs/integration-survey.md`: a per-device-model template (port, protocol, read-only?, parameters, vendor/biomed approval, binding method) for the real-world story.

## You give / you need

- **Give B:** valid events on MQTT early (P0), gateway quality flags (P1), the family-gateway ingest API (P4).
- **Give C:** a running stack to point the apps at, and a scenario timed to the demo script.
- **Need from B:** `call/state` publishing (P2), the outbound family publisher (P4).

## Invariants you guard

3 (outbound only: network isolation), 5 (absent, not zero; stale flags), 6 (unique eventIds, replay-safe), 7 (synthetic data only, no secrets).
