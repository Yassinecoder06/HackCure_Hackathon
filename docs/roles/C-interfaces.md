# Role C: Interfaces and story ("what people see and believe")

**Owns:** `apps/ward/` (station board + staff view), `apps/family/`, `docs/demo-script.md`. Leads the pitch deck and BMC (everyone contributes). Shared contract reviews with A and B.

**Good fit if you like:** TypeScript/React, UI/UX design, storytelling and pitching.

Read first: [whitepaper](../Borj_PiCare_Whitepaper_v2.pdf) sections 2, 6, 7 and 12 (pitch plan), [ARCHITECTURE](../ARCHITECTURE.md), [`contracts/openapi.yaml`](../../contracts/openapi.yaml), [ADR 0002](../decisions/0002-one-ward-app.md), [ADR 0005](../decisions/0005-in-app-alerts-first.md).

---

## First task (P0): app scaffolds against a mock API

Acceptance criteria:
- [ ] `apps/ward`: Vite + React + TypeScript with the routes `/board` and `/staff`. `apps/family`: a separate Vite + React + TS app.
- [ ] Pin the Node version (`.nvmrc`) and commit the lockfile.
- [ ] API types generated from `contracts/openapi.yaml` (e.g. `openapi-typescript`), not hand-written.
- [ ] Mock API from the OpenAPI examples (e.g. MSW or Prism) with a fake WebSocket that replays a few `bed`/`call`/`alert` messages. A `VITE_USE_MOCK=1` switch.
- [ ] All UI strings in one module per app (English now, translatable later).
- [ ] CI job: `npm ci && npm run build && npm run lint` for both apps.
- [ ] `apps/family` must **not** import anything from the ward API client (invariants 2 and 3). Add a lint rule or test for this.

## P1: Station board v1 + fast entry

- **Board (`/board`)**: a 2D floor plan from `seed/ward-W1.yaml` (rooms and positions), see [ADR 0006](../decisions/0006-no-3d-twin.md).
  - Each bed shows the patient label, the NEWS2 total and band colour, a **"partial" badge listing missing/stale parameters**, and the data age.
  - Stale data is shown greyed out or striped, **never as a normal value** (invariant 5).
  - A priority list sorted by NEWS2 band and score. Click a bed to see the score components and the explanation sentences.
  - Large-screen friendly, readable from 3 metres.
- **Fast-entry form (`/staff`)**: pick a bed (wristband QR scan later), pre-filled with device values, plus consciousness ACVPU, on oxygen, and resp rate if missing. Target 10 seconds. Only entered fields are sent.

## P2: Staff view

- An alert list with the escalation ladder: low = silent badge, medium = notification with sound, critical = a persistent full-screen alarm until acknowledged.
- Calls with their states (`sent`, `acknowledged`, `escalated`, `not_sent`/`deliveredLate` shown clearly), and ack/resolve buttons.
- Sound and vibration over the WebSocket while the app is open. Web Push is a stretch goal ([ADR 0005](../decisions/0005-in-app-alerts-first.md)).
- A login stub: pick a synthetic staff member, which sets `X-Staff-Id`.
- The board shows the same call states as the phone and the bedside node.

## P3: Decisions UI

- **Assignment approval** (charge nurse): the suggested changes, reasons and load before/after, with Approve / Reject (and a reason). Show "advisory: you decide".
- **What-if panel**: choose disruptions (nurse called away, N admissions, call surge, route comfort calls to assistants) and run. Compare baseline vs scenario (vs suggestion) with **median and p5–p95 bands**, and show the assumptions list on screen.
- **Medication timeline**: doses due/overdue and clashes, a nurse "given/not given" tap, and patient-reported entries shown separately.

## P4: Family Care Link UI

- In the ward app: record consent (patient or legal representative, which items), create an invite (show the QR code and the one-time code once), draft updates (templates + short note), the nurse approval queue, and revoke.
- `apps/family`: redeem (QR + code), then a feed of approved updates.
  - An always-visible **"Not an emergency channel"** notice with the ward phone number.
  - **No vitals, scores, drug names, staff names or times-since-visit**: there is nothing to render because the API does not have them.
  - Mobile-first, plain language.

## P5: Story

- `docs/demo-script.md`: a minute-by-minute script synced with A's `night-shift-peak` scenario. It covers deterioration → escalation → assignment approval → what-if → the family filter.
- Deck: problem, demo, an honest **real vs simulated** slide, the device integration plan, legal/consent posture (INPDP, Law 2004-63), the premium model (facility add-on / family-paid / hybrid), risks and the roadmap.
- Record the backup screen video. Rehearse twice on a clean machine.

## You give / you need

- **Give everyone:** the demo storyline early (P1), so A tunes the scenario and B prioritises what is on screen.
- **Need from B:** the snapshot + WebSocket (P1), calls (P2), the decision endpoints (P3), the family endpoints (P4). Use the mock until each lands.
- **Need from A:** a running compose stack, and family-gateway (P4).

## Invariants you guard

2 (the family UI cannot show forbidden data), 5 (stale/missing never displayed as normal), 1 (the UI makes clear a human decides).
