# simulator/ (owner: A)

Synthetic ward and scenario replayer. **Not implemented yet.** See [`docs/roles/A-edge.md`](../docs/roles/A-edge.md) for the spec and the first task.

- `scenarios/*.yaml`: scenario specs (written). `normal-night`, `deterioration`, `night-shift-peak` (the demo storyline).
- Reads the ward layout, device profiles and roster from [`seed/ward-W1.yaml`](../seed/ward-W1.yaml).
- Emits contract messages (validated with `borj_contracts`) and, from P1, raw device streams for the gateway.
- Seeded and reproducible, with controllable speed (`sim/clock` topic).

Scenario event types used by the specs: `deteriorate`, `set_manual`, `call` (`no_ack`, `repeat_of_previous`), `call_rate`, `admit`, `staff_leaves`, `device_offline`, `node_outage_call`.
