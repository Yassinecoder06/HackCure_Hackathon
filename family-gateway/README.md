# family-gateway/ (owner: A)

DMZ service for the Family Care Link. **Not implemented yet.** See [`docs/roles/A-edge.md`](../docs/roles/A-edge.md), P4.

- Implements [`contracts/family-gateway.openapi.yaml`](../contracts/family-gateway.openapi.yaml).
- Receives **outbound pushes from the ward** on `/ingest/v1/*` (allow-list schemas only) and serves relatives on `/family/v1/*`.
- Lives on the `dmz` docker network only. It cannot reach `mosquitto` or `server` (safety invariant 3).
- Holds no vitals, scores, drug names, doses or staff data, and has no way to obtain them.
