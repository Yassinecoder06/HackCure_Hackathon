# Role C: Interfaces and story ("what people see and believe")

**Owns:**
- `apps/ward/` (station board, staff view, remote doctor view) and `apps/family/`.
- `docs/demo-script.md` and `docs/deployment-dossier.md` (deliverable L3).
- Leads the pitch deck and BMC; everyone contributes.

Shared contract reviews with A and B.

**Good fit if you like:** TypeScript/React, UX for people under stress, storytelling and pitching.

Read first:
- [Whitepaper](../Borj_PiCare_Whitepaper_v2.pdf), sections 2, 6, 7 and 12.
- [HackCure specification](../HackCure_Cahier_des_Charges.pdf), all 3 pages: the jury scores against it.
- [ARCHITECTURE](../ARCHITECTURE.md).
- [`contracts/openapi.yaml`](../../contracts/openapi.yaml).
- ADRs [0002](../decisions/0002-one-ward-app.md), [0005](../decisions/0005-in-app-alerts-first.md), [0008](../decisions/0008-track-2.md) and [0011](../decisions/0011-interop-and-confidence.md).

**Hard UI rules (from the specification):**
- Validating or rejecting an alert or an order takes **3 steps at most**.
- Every suggestion is labelled **advisory: a clinician decides**, and shows its **confidence** and **explanation**.
- Navigation stays uncluttered, to lower the cognitive load.
- Mobile-first.

---

## First task (P0): app scaffolds against a mock API

- [ ] `apps/ward`: Vite + React + TS, with the routes `/board`, `/staff` and `/doctor`. `apps/family`: a separate Vite + React + TS app.
- [ ] Pin the Node version (`.nvmrc`) and commit the lockfile.
- [ ] API types generated from `contracts/openapi.yaml` (e.g. `openapi-typescript`).
- [ ] A mock API (MSW or Prism) with a fake WebSocket replaying `bed`/`call`/`alert`/`metrics` messages, behind `VITE_USE_MOCK=1`.
- [ ] All UI strings in one module per app (English now; French later is cheap).
- [ ] A CI job running `npm ci && npm run build && npm run lint` for both apps.
- [ ] `apps/family` must not import anything from the ward API client (invariants 2 and 3). Enforce it with a lint rule or test.

## P1: login, board v1, fast entry

- [ ] **Login screen** (staff id + PIN) → bearer token. Show who is logged in, and a session timeout.
- [ ] **Board (`/board`):**
  - A 2D floor plan from `seed/ward-W1.yaml`.
  - Each bed shows the NEWS2 band colour, the score, a **"partial" badge listing missing or stale parameters**, the **confidence**, and the data age.
  - Stale data is greyed out or striped, never shown as normal (invariant 5).
  - A priority list. Click a bed to see the components and the explanation.
  - **Measured latency** shown in a corner.
- [ ] **Fast-entry form:** pre-filled from device values, adds ACVPU, on oxygen, and resp rate if missing. Target 10 seconds.

## P2: staff view + offline

- [ ] An alert list following the escalation ladder: a silent badge, a notification with sound, or a persistent full-screen alarm until acknowledged.
- [ ] **Acknowledge in 1 tap.**
- [ ] Call states (`sent`, `acknowledged`, `escalated`, `not_sent`/`deliveredLate`), matching the board and the Pi node.
- [ ] **Offline mode:**
  - A service worker caches the app and the last snapshot.
  - The UI shows "offline since hh:mm", with the data marked stale.
  - Acks are queued and sent on reconnect.
  - Critical alerts that couldn't be acknowledged are flagged.
- [ ] Sound and vibration over the WebSocket while open (Web Push is a stretch goal).

## P3: decisions UI + remote doctor

- [ ] **Assignment approval** (charge nurse): the changes, reasons, workload before/after and confidence. Approve or reject in **3 steps or fewer**.
- [ ] **What-if panel:** pick disruptions → run → compare baseline, scenario and suggestion with **median and p5–p95 bands**, and the assumptions list on screen.
- [ ] **Medication timeline:** doses due and overdue, clashes, the nurse's given/not-given tap, patient-reported entries shown separately.
- [ ] **Doctor view (`/doctor`)**, mobile and remote: escalations with the NEWS2 trend, reasons and confidence, plus acknowledge and a short instruction note. It must work on a poor connection: small payloads, queued sends.

## P4: Family Care Link UI

- [ ] Ward app: record consent, create an invite (QR + one-time code shown once), draft updates, the approval queue, revoke.
- [ ] `apps/family`:
  - Redeem (QR + code), then a feed of approved updates.
  - An always-visible **"Not an emergency channel"** notice with the ward phone number.
  - Mobile-first, light enough for rural mobile networks.
  - No vitals, scores, drug names, staff names or times-since-visit.

## P5: story and deliverables

- [ ] [`docs/demo-script.md`](../demo-script.md), following the HackCure protocol: clinical case → live demo (including the **live network cut**) → technical defence. Synced with A's scenario.
- [ ] [`docs/deployment-dossier.md`](../deployment-dossier.md) (**L3**): field feasibility, regulatory compliance (INPDP / Law 2004-63, GDPR, DPM/ANMPS), who pays, access barriers, cost estimates, **roadmap at 3 and 6 months**.
- [ ] Deck:
  - problem → live demo → an honest real-vs-simulated slide;
  - security and privacy by design;
  - FHIR interoperability;
  - business model and costs;
  - risks;
  - roadmap.
- [ ] **Technical-defence rehearsal:** each person answers for their component (choices, scalability, resilience, data governance).
- [ ] Rehearse twice on a clean machine with the backup access point. A recording is only a private safety net; **video is not accepted as the MVP**.

## You give / you need

- **Give everyone:** the demo storyline early (P1), so A tunes the scenario and B prioritises what's on screen.
- **Need from B:** snapshot, WebSocket and login (P1), calls and metrics (P2), decision and doctor endpoints (P3), family endpoints (P4).
- **Need from A:** the stack over HTTPS, family-gateway (P4), the hosted URL (P5).

## Invariants you guard

1 (the UI makes clear a human decides), 2 (the family UI cannot show forbidden data), 5 (stale/missing never displayed as normal), 12 (confidence + explanation shown, ≤ 3 steps).
