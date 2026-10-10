# Demo script (owner: C)

Follows the **HackCure live-demo protocol** (specification section 9). To be refined until P5, and kept in sync with `simulator/scenarios/night-shift-peak.yaml` (A).

**Rules:**
- **Live only.** No pre-recorded video or static mockup is accepted as the MVP.
- Run on the **local Docker setup**, with the laptop, the Pi and the phones on the **backup access point**. The hosted URL is shown, but never relied on.

## Step 1: Clinical case (≈ 1 min)

A night shift on an internal-medicine ward of a regional hospital. A charge nurse and three nurses cover twelve patients, the paper charts are three hours old, and the internet is unreliable. At 3 am two emergency admissions arrive while the patient in bed 6 develops a fever and becomes confused. Who do they see first? Who covers which room?

## Step 2: Live MVP (≈ 3–4 min)

1. **The board.** The ward's 2D floor plan, NEWS2 per bed with its confidence, stale-data warnings, and the measured triage latency in the corner.
2. **Deterioration.** B06's NEWS2 climbs. Click the bed: the points per parameter, the explanation, and a confidence below 1 because consciousness hasn't been entered yet. A nurse adds it in the fast-entry form, and the score becomes complete.
3. **The call.** Press the **real button on the Pi**. The LED turns amber, and a nurse's phone rings in under a second (show the latency). Nobody acknowledges → it escalates to the charge nurse, then to the **remote on-call doctor's** phone, who replies with an instruction.
4. **Cut the network, live.** Switch off the access point's internet, or the Wi-Fi at the bed:
   - the ward keeps working;
   - the Pi shows `not_sent` and tells the patient to use the emergency bell;
   - when the connection comes back, everything catches up (`deliveredLate`).
5. **Rebalance.** N3 is called away → an assignment suggestion with reasons and a confidence → the charge nurse approves in 3 taps. "Advisory: you decide."
6. **What-if.** "What if we routed comfort calls to the care assistant?" → the wait time with a p5–p95 band, from the running simulator.
7. **Family Care Link.** The consent step, then the family app shows a nurse-approved note, and visibly **no vitals or scores** even though B06 is critical.

## Step 3: Technical defence (Q&A)

Each person answers for their part. Prepare short answers for:

| Likely question | Owner |
|---|---|
| Why MQTT, why these components? | A |
| What happens when the network, broker, server or inference service fails? | A + B |
| How does it scale to more wards or hospitals? | B |
| How is data protected (TLS 1.3, AES-256, pseudonymisation, audit, consent)? | B |
| Is the AI a black box? How confident is it? (Deterministic NEWS2, confidence = data quality, human validates) | B |
| How does it integrate with the hospital information system (SIH)? (FHIR R4 export) | B |
| Real or simulated? (Honest slide: simulated device protocols, one real button and optional sensor) | C |
| Who pays, and what does it cost? | C |
| What is the legal path (INPDP, Law 2004-63, DPM/ANMPS)? | C |
| Can you explain this code? (Everyone, for their own component) | all |
