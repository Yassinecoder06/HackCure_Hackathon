# contracts/ (shared: changes need all three owners)

The only thing all three roles depend on. Everything else is built against these files.

| File | What |
|---|---|
| [`mqtt-topics.md`](mqtt-topics.md) | Topics, publishers/subscribers, QoS, envelope rules, call state machine |
| [`schemas/`](schemas/) | JSON Schema 2020-12, one per message type (`common.schema.json` holds shared definitions) |
| [`examples/`](examples/) | One valid example per message. Used by tests, docs and app mocks |
| [`openapi.yaml`](openapi.yaml) | Ward server REST + WebSocket API (used by `apps/ward`) |
| [`family-gateway.openapi.yaml`](family-gateway.openapi.yaml) | DMZ API: ingest from the ward (outbound push) + relatives' app |
| [`borj_contracts/`](borj_contracts/) | Python helper: `validate_message(topic, payload)`, `route(topic)`, `topic(...)` |

Python usage (add `contracts` to `PYTHONPATH`, or `pip install -r requirements-dev.txt` and run from the repo root, since pytest is configured for it):

```python
from borj_contracts import validate_message, topic
validate_message(topic("vitals", "W1", bed="B04"), payload)  # raises ContractError
```

## Changing a contract

1. Open a PR that updates the schema, the docs here, the matching example, the simulator, and every consumer, together (or as linked PRs).
2. Keep `schemaVersion: 1` for additive optional fields. Bump it for breaking changes and support both versions during the transition.
3. Get an acknowledgement from all three owners, and tick the box in the PR template.
