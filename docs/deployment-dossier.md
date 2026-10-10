# Deployment dossier (HackCure deliverable L3)

Owner: C (lead). Everyone contributes their section. This is a skeleton to complete by P5. The figures are placeholders until they are researched, and every number must state its source or assumption.

## 1. Field feasibility

- **Target site:** an internal-medicine or step-down ward in a Tunisian public hospital (regional or district hospital first).
- **What must be true** (from whitepaper section 10, "Hypotheses to validate"):
  - Charge nurses find the board useful daily.
  - The device ports allow read-only capture.
  - The taps add little time compared with paper.
  - Families use the link.
  - INPDP authorization is obtainable within a pilot timeline.
- **Device integration survey:** per device model, record the port, protocol, read-only access, parameters, and vendor/biomedical approval (A provides the template).
- **Network reality:** the ward runs on a local network with no internet dependency, and the remote doctor and family link tolerate poor connections.
- **Staff workload:** entry faster than paper, one-tap acks, validation in 3 steps or fewer.

## 2. Regulatory compliance

| Topic | Position |
|---|---|
| Health data (Tunisia) | Law 2004-63: health data processing is prohibited by default. We need **INPDP authorization**, informed consent, pseudonymisation and approved national hosting before any real data. |
| GDPR | Applies only if EU residents' data is processed. The same principles are followed by design. |
| Medical device status | The rules for standalone software are unclear in Tunisia, so we ask the **DPM / ANMPS** early. The prototype is non-certified, read-only on devices, and advisory. |
| Security | TLS 1.3, AES-256 at rest, access audit, hash-chained logs ([ADR 0010](decisions/0010-security-baseline.md)). |
| Family link | Written patient consent, an allow-list, nurse approval, outbound-only publishing. |

## 3. Business model (who pays, barriers, costs)

- **Payers** (whitepaper section 7.6, business model canvas):
  - Public wards: ministry programmes and grants.
  - Private clinics: a per-bed subscription.
  - Family Care Link: a facility add-on or paid by families.
  - Paid what-if studies for hospital managers.
- **Access barriers:** slow public procurement, the regulatory path, staff adoption, device vendor terms.
- **Cost estimates (to complete):**

| Item | Unit cost (TND) | Per ward | Source / assumption |
|---|---|---|---|
| Ward gateway (Raspberry Pi + case + UPS) | _tbd_ | 1 | |
| Bedside node (ESP32, buttons, LEDs, enclosure) | _tbd_ | 12 | |
| Server or hosting (VM, monthly) | _tbd_ | — | |
| Approved national hosting for the family link (monthly) | _tbd_ | — | |
| Installation, training and support (per ward) | _tbd_ | — | |

## 4. Post-hackathon roadmap

| Horizon | Goals |
|---|---|
| **3 months** | Ward interviews and observation at one partner hospital. Device integration survey on the target ward. Clinician validation of the NEWS2 thresholds and wording. Privacy review and the INPDP authorization file prepared. A shadow-mode pilot plan agreed with the hospital. |
| **6 months** | **Shadow pilot** on one ward: the system runs alongside current practice with no clinical action taken. Measure the time per task, alert latency, and calls from relatives. Calibrate the what-if model with the measured timings. Family Care Link pilot in one private clinic. Funding application (programme or grant). |
| Later | Live advisory use, more wards, national health-identifier and FHIR integration with the hospital information system. |
