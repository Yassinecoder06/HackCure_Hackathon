# 0004. Work split: family-gateway moves to Person A

Status: accepted (kickoff)

## Context

In the kickoff plan, Person C (interfaces) owned three apps, family-gateway, the demo script, the deck and the business model canvas, while Person A's simulator and gateway work is mostly front-loaded.

## Decision

- **A (edge and data)** also owns `family-gateway/`, a small FastAPI service in the DMZ, once the simulator and gateway are running.
- **B (brain)** owns the family privacy filter and the outbound publisher inside `server/`, because they sit on the ward side and need the twin.
- **C (interfaces)** owns `apps/ward`, `apps/family` and the demo script.
- The **deck and BMC are shared**. C leads, and everyone contributes their part.

See [`../roles/`](../roles/) for each role's task list.
