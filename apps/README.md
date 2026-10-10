# apps/ (owner: C)

**Not implemented yet.** See [`docs/roles/C-interfaces.md`](../docs/roles/C-interfaces.md) and [ADR 0002](../docs/decisions/0002-one-ward-app.md).

| App | Routes / purpose | Talks to |
|---|---|---|
| `ward/` | `/board`: big-screen station board with a 2D floor plan. `/staff`: phone view with alerts, 1-tap ack, fast entry, approvals, medication, what-if. `/doctor`: remote on-call doctor view | ward server ([`contracts/openapi.yaml`](../contracts/openapi.yaml)) |
| `family/` | Relatives' app: redeem invite, feed of approved updates | family-gateway only ([`contracts/family-gateway.openapi.yaml`](../contracts/family-gateway.openapi.yaml)) |
| `twin3d/` | 3D twin view (Blender-baked ward + React Three Fiber), display only, polish ([ADR 0012](../docs/decisions/0012-3d-twin.md)). Owner: B | ward server WebSocket |

Stack: TypeScript + React + Vite, installable web app, served over HTTPS. UI in English, with strings kept in one module per app.

HackCure UI rules: validate or reject in **3 steps at most**, show the **confidence and explanation** with every suggestion, label it **advisory**, work **offline** with a cached snapshot and queued actions.
