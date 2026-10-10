# apps/ (owner: C)

**Not implemented yet.** See [`docs/roles/C-interfaces.md`](../docs/roles/C-interfaces.md) and [ADR 0002](../docs/decisions/0002-one-ward-app.md).

| App | Routes / purpose | Talks to |
|---|---|---|
| `ward/` | `/board`: big-screen station board with a 2D floor plan. `/staff`: phone view with alerts, ack, fast entry, approvals, medication, what-if | ward server ([`contracts/openapi.yaml`](../contracts/openapi.yaml)) |
| `family/` | Relatives' app: redeem invite, feed of approved updates | family-gateway only ([`contracts/family-gateway.openapi.yaml`](../contracts/family-gateway.openapi.yaml)) |

Stack: TypeScript + React + Vite, installable web app. UI in English, with strings kept in one module per app.
