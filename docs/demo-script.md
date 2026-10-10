# Demo script (owner: C)

To be written in P1 and refined until P5. Sync it with `simulator/scenarios/night-shift-peak.yaml` (A).

Starting outline (from whitepaper section 12, pitch plan):

1. **The night shift.** A charge nurse, a few nurses, many patients. Two admissions arrive while a patient worsens.
2. **The solution.** Machine data and bedside nodes feed the ward board, which shows NEWS2 priority with reasons and stale-data warnings.
3. **Live.** B06 deteriorates. An assist call goes unacknowledged and escalates (the Pi node LED shows it). N3 is called away, and the system suggests a re-assignment that the charge nurse approves. The what-if panel shows the wait-time effect. Every number comes from the running simulator.
4. **Family Care Link.** The consent step, then the limited family view, with a live demonstration that vitals are filtered out.
5. **Trust and business.** Advisory only, synthetic data, the honest real-vs-simulated slide, the premium model, the pilot plan.
