# Role A: Edge, transport and deployment ("how reality gets in, safely")

**Owns:**
- `simulator/`, `gateway/`, `bedside-node/`.
- `infra/`: compose, the TLS broker, the Caddy proxy, the cloud VM.
- `seed/`, `family-gateway/`.
- `contracts/schemas/` and `contracts/mqtt-topics.md`.

Shared contract reviews with B and C.

**Good fit if you like:** Python, networking/MQTT, Docker, security plumbing, Raspberry Pi and hardware.

Read first:
- [Whitepaper](../Borj_PiCare_Whitepaper_v2.pdf), sections 4 and 7.3–7.4.
- [HackCure specification](../HackCure_Cahier_des_Charges.pdf), sections 5 and 9.
- [ARCHITECTURE](../ARCHITECTURE.md).
- [`contracts/mqtt-topics.md`](../../contracts/mqtt-topics.md).
- ADRs [0003](../decisions/0003-pi-bedside-node.md) and [0010](../decisions/0010-security-baseline.md).

---

## First task (P0): simulator v0 + compose

- [ ] `simulator/` as a Python package (`python -m borj_sim`) that reads a scenario from `simulator/scenarios/` and the ward from `seed/ward-W1.yaml`.
- [ ] It emits `binding`, `vitals` (device params per the bed's profile, so absent really is absent), `device/status`, `call` (Poisson, assist/comfort, repeat presses), background `ack`s, `staff/{id}/presence` and `sim/clock`.
- [ ] Every message passes `borj_contracts.validate_message(topic, payload)`.
- [ ] Seeded and reproducible, including deterministic ULIDs.
- [ ] `--speed N`, `--dry-run` (JSON lines to stdout), `--broker host:port`.
- [ ] Scripted events: `deteriorate`, `set_manual`, `call` (`no_ack`), `call_rate`, `admit`, `staff_leaves`, `device_offline`, `node_outage_call`.
- [ ] A `simulator` service in `docker-compose.yml`. The server service already exists (PR #2).
- [ ] Tests: every scenario only produces valid messages, with unique ids and no null/zero placeholders.

## P1: gateway + secure transport

- [ ] **Gateway adapters** (read-only): an adapter interface, and a replay adapter that reads a line-based device stream over TCP from the simulator, **with a per-frame checksum/CRC that the adapter verifies**.
- [ ] **Validity and freshness:** ranges in `gateway/config/quality.yaml` (commented "to be validated by biomedical/clinical staff"); `sensor_off`/`artifact`/`implausible` flags; `stale_after_s` per device type.
- [ ] **Bed binding**, and **store-and-forward** in a local SQLite outbox that keeps the original `eventId`/`ts` and adds `late_delivery`. Outbox payloads are encrypted with AES-256-GCM, like every patient payload at rest (invariant 10). Write a test that kills the broker mid-run.
- [ ] **TLS 1.3 broker** ([ADR 0010](../decisions/0010-security-baseline.md)): Mosquitto on 8883 with `tls_version tlsv1.3`, per-device credentials and ACLs (a device can only publish to its own bed's topics), and a local CA via mkcert. Plain 1883 only for unit tests.
- [ ] **HMAC-SHA256 signing** of every message in the envelope's `integrity` field (per-device keys in `.env`/secrets). Applies to the simulator, gateway and node.
- [ ] **Caddy** reverse proxy in compose: TLS 1.3 only, in front of the server (HTTPS + WSS) and the apps.

## P2: Pi bedside node + resilience drills

- [ ] `bedside-node/` (Python + `gpiozero`): an assist and a comfort button, LEDs driven by the retained `call/state`, and pre-recorded phrases on the speaker.
- [ ] Store-and-forward with `not_sent` behaviour (red blink, buzzer, "please use the emergency bell"), then replay with `deliveredLate: true`.
- [ ] Mock GPIO mode for laptops and CI. Wiring diagram in the README.
- [ ] **Optional real sensor (if the team agrees, see [ASSUMPTIONS](../ASSUMPTIONS.md)):** a MAX30102 (PPG: SpO2 and pulse) and a DS18B20 (temperature) on the Pi, publishing real `vitals` for one bed with frame-integrity checks.
- [ ] **Network-cut drill:** a script and checklist for cutting the Wi-Fi or internet live and showing that everything catches up afterwards.
- [ ] **Backup access point:** a travel router or phone hotspot configuration that the laptop, Pi and phones join, documented in `infra/README.md`.
- [ ] Tune `night-shift-peak.yaml` to the demo script (coordinate with C).

## P3: data for decisions

- [ ] Ward walking distances from the `seed/` positions, for assignment proximity.
- [ ] Seed prescriptions (synthetic, realistic) and simulator `med` events, including some `patient_reported_taken`.

## P4: family-gateway (DMZ)

Implement [`contracts/family-gateway.openapi.yaml`](../../contracts/family-gateway.openapi.yaml):
- [ ] Allow-list ingest; anything else is rejected (invariant 2).
- [ ] Immediate revocation (invariant 4).
- [ ] QR + one-time code redeem, rate limits, view audit.
- [ ] Serves `apps/family` over TLS.
- [ ] **Network isolation:** family-gateway sits only on the `dmz` network. Write a test that it cannot reach `mosquitto`, `server` or `postgres` (invariant 3).

## P5: deployment (HackCure deliverable L2)

- [ ] **Hosted demo:** a small cloud VM, a domain and a real TLS certificate (Caddy handles this automatically), deployed from `main`. This is the "active web URL".
- [ ] **Clean-machine test** of the local `docker compose up`.
- [ ] Server and hardware cost figures for the deployment dossier: VM, Pi gateway, nodes, backup power.

## You give / you need

- **Give B:** valid, signed events (P0–P1), quality flags (P1), the ward layout and seed prescriptions (P3), family-gateway ingest (P4).
- **Give C:** a running stack over HTTPS, a scenario timed to the demo script, the hosted URL.
- **Need from B:** `call/state` (P2), outbound family pushes (P4), the HMAC key format: **done**. `infra/.env` holds
  `BORJ_DEVICE_KEYS` (`keyId:<base64>,...`, parse with `borj_contracts.parse_keys`). Key ids: `sim-k1`, `gw-k1`,
  `node-{bed}` (a node's key is only accepted for its own bed). Once your signers load their entry, set
  `BORJ_INTEGRITY_MODE=require` in compose.

## Invariants you guard

3 (outbound only, network isolation), 5 (absent ≠ zero, stale flags), 6 (unique eventIds), 7 (synthetic data, no secrets), 10 (TLS in transit), 13 (frame integrity).
