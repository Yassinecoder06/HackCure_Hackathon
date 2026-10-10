# server/ (owner: B)

FastAPI ward server. **Not implemented yet.** See [`docs/roles/B-brain.md`](../docs/roles/B-brain.md) for the spec and the first task.

Planned layout:

```
server/
  borj_server/
    main.py           # FastAPI app, MQTT subscriber, WebSocket
    twin/             # ward state store + idempotent event handlers
    engines/
      news2/          # deterministic NEWS2 with missing/stale handling + explanation
      calls/          # call state machine, routing, escalation timers
      assignment/     # OR-Tools suggestion (never auto-applied)
      whatif/         # SimPy, many seeds, median + p5-p95, Erlang-C oracle test
      meds/           # prescriptions -> doses, overdue, clashes (never chooses drugs)
      explain/        # template sentences from rule traces
      family/         # consent, privacy filter, outbound publisher
    api/              # routes matching contracts/openapi.yaml
  config/             # news2.yaml, calls.yaml, whatif.yaml (clinical params: TO BE CONFIRMED BY A CLINICIAN)
  tests/
```

API contract: [`contracts/openapi.yaml`](../contracts/openapi.yaml).
