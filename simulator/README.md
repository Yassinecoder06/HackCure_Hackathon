# simulator/ (owner: A)

Synthetic ward telemetry generator and scenario simulator.

Implements **Role A, P0** specification in [`docs/roles/A-edge.md`](../docs/roles/A-edge.md).

---

## 1. Capabilities

- Package `borj_sim` (`python -m borj_sim`).
- Reads the ward layout, device profiles and staff roster from `seed/ward-W1.yaml`.
- Reads scenario definitions from `simulator/scenarios/`:
  - `normal-night.yaml`: Baseline quiet night shift.
  - `deterioration.yaml`: B06 fever, tachycardia, falling SpO2/BP, and confusion.
  - `night-shift-peak.yaml`: The full demo storyline (Section 2, HackCure demo script).
- Generates 100% contract-compliant events (`borj_contracts.validate_message()`):
  - `borj/{ward}/{bed}/binding`: Admissions and device attachments.
  - `borj/{ward}/{bed}/vitals`: Device measurements matching each bed's specific device profile (missing parameters are truly absent, never 0 or null).
  - `borj/{ward}/{bed}/device/status`: Periodic heartbeat and status alerts.
  - `borj/{ward}/{bed}/call`: Scripted and background Poisson calls with assist / comfort split.
  - `borj/{ward}/staff/{staffId}/ack`: Background nurse call acknowledgments and resolutions.
  - `borj/{ward}/staff/{staffId}/presence`: Shift start/end, breaks, and called away.
  - `borj/{ward}/sim/clock`: Synchronized simulation clock.
- **Seeded & Reproducible**: Fixed seeds produce identical ULIDs and message streams.
- **Controllable Time**: `--speed N` multiplier (e.g. 10x, 60x, or 0 for batch instant execution).

---

## 2. Usage

### Quick dry-run (prints JSON lines to stdout)
```bash
python -m borj_sim --scenario simulator/scenarios/deterioration.yaml --dry-run
```

### Run against local MQTT broker
```bash
python -m borj_sim --scenario simulator/scenarios/night-shift-peak.yaml --broker localhost:1883 --speed 10
```

### Run in Docker Compose
The simulator is configured as a service in `infra/docker-compose.yml`:
```bash
docker compose -f infra/docker-compose.yml up simulator
```

### Running Tests
```bash
pytest simulator/tests/
```
