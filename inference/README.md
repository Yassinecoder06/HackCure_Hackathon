# inference/ (owner: B)

The **inference layer** ([ADR 0009](../docs/decisions/0009-layers-and-postgres.md)): a stateless internal FastAPI
service, reachable only on the ward network. **Not implemented yet.** See [`docs/roles/B-brain.md`](../docs/roles/B-brain.md) (P1, P3).

| Engine | What it returns |
|---|---|
| `news2` | Score, band, points per component, missing/stale lists, **confidence** (data completeness and freshness) |
| `assignment` | OR-Tools suggestion with reasons, workload before/after, **confidence** (solver status, data freshness). Never applied by itself |
| `whatif` | SimPy results over N seeds: median and p5–p95 per metric, plus the assumptions list |
| `explain` | Template sentences from rule traces |

Deterministic by design: no black-box model (HackCure section 6). Clinical thresholds live in `inference/config/`,
each marked "TO BE CONFIRMED BY A CLINICIAN".
