# CLAUDE.md: rules for Claude Code in this repo

Borj-PiCare: a care-coordination platform for hospital wards, built for **HackCure, Track 2 (Web & Mobile)**. **Advisory only**: a clinician always validates or rejects.

Sources of truth:
- The idea: `docs/Borj_PiCare_Whitepaper_v2.pdf`.
- The competition requirements: `docs/HackCure_Cahier_des_Charges.pdf`. It wins on security, layers, deliverables and demo rules.
- The team plan: `docs/PLAN.md`, with role sheets in `docs/roles/`.

## Before editing

1. Read this file, `docs/ARCHITECTURE.md`, and the contract you touch (`contracts/mqtt-topics.md`, `contracts/schemas/*.json`, `contracts/openapi.yaml`, `contracts/family-gateway.openapi.yaml`, `contracts/fhir-mapping.md`).
2. Work only in the folders of the role you are helping (see `docs/PLAN.md` and `.github/CODEOWNERS`). If you must edit another person's folder or `contracts/`, say so explicitly in the PR description.
3. Do not implement items marked "Won't (now)" in `docs/PLAN.md`.

## Safety invariants (hard rules, enforced by tests in `tests/`)

1. **Advisory only.** No code path may apply an assignment, change a prescription, or choose a drug or dose without a human action recorded in the audit log.
2. **The Family Care Link never exposes** vital signs, NEWS2 or any risk score, drug names or doses, auto-generated reassurance, staff identities, locations or response times, or other patients' information. `contracts/schemas/family-update.schema.json` is an allow-list, and tests must fail if any other field reaches `family-gateway`.
3. **Family publishing is outbound-only.** The ward network accepts no inbound connection from the internet or from family components. family-gateway lives on a separate network and cannot reach the broker, the server or the database.
4. **Consent first.** No family update or invite exists without a recorded consent. Revocation takes effect immediately, and invites expire at discharge or transfer.
5. **Missing or stale data is shown as missing or stale**, never as a normal value. Scores computed from incomplete input are labelled partial. Absent parameters are absent, never `0`/`null`/`""`.
6. **Idempotency.** Replaying the same `eventId` twice changes nothing.
7. **No real patient data** in the repo, tests or demo: synthetic only, pseudonymous ids only. No secrets in git (`.env` is ignored, `.env.example` is committed).
8. **Clinical parameters are config, not code**, each with a comment saying who must validate it.
9. **Legal posture.** Real deployment needs INPDP authorization (Law 2004-63, plus GDPR where it applies), an approved hosting location, and patient written consent for any family view. Vitals for relatives are not part of this build.
10. **Encrypted in transit and at rest.** TLS 1.3 for MQTT (8883) and HTTP (via Caddy) in the demo. Patient payloads are encrypted with AES-256-GCM before they reach the database. Plain text is allowed only in unit tests and local development.
11. **Non-repudiation.** Every read and write of patient data, every suggestion and every human decision is logged with who, what and when, in a hash-chained audit log. No anonymous access to patient data.
12. **Explainable and advisory.** Every algorithmic output (score, alert, suggestion, what-if) carries a **confidence index** and an **explanation** (the triggering parameters or rules). The UI labels it advisory, and validating or rejecting it takes **3 steps at most**.
13. **Frame integrity.** Measurement messages carry an HMAC-SHA256 `integrity` signature (per-device key) in the demo; invalid signatures are rejected and logged.

## Working rules

- `main` is always demo-able. Use short-lived branches `a/...`, `b/...`, `c/...`, and merge via a PR with one approving review.
- **Contract change** = update the schema, `mqtt-topics.md`/OpenAPI/FHIR mapping, the example in `contracts/examples/`, the simulator, and the affected consumers in the same PR (or linked PRs). Tick the "all three acknowledged" box in the PR template.
- Every PR: tests added or updated, no failing invariant tests, a screenshot for UI changes.
- CI on every PR: lint, unit tests, contract validation (schemas, examples, OpenAPI), invariant tests, the compose smoke test, and app builds (once apps exist).
- Record non-obvious decisions as ADRs in `docs/decisions/NNNN-short-title.md`.
- Pin dependency versions. Synthetic data lives in `seed/` and `simulator/scenarios/`.
- **Explainability of our own code.** HackCure requires every team member to explain the data pipelines, libraries and internal behaviour of their stack. Keep code simple, keep each component's README explaining the "why", and never merge code its owner cannot explain.
- **Attribution.** Commits and PRs are made under the team member's own GitHub account. Do not add AI attribution lines (no `Co-Authored-By` for an AI, no "Generated with" footers).
- Keep each component's README current with install steps and dependencies (HackCure deliverable L1).

## Conventions

- Python 3.12, FastAPI, pytest, ruff (config in `pyproject.toml`). TypeScript + React + Vite for apps.
- Validate MQTT payloads with `contracts/borj_contracts` (`validate_message(topic, payload)`). Do not copy the schemas.
- Envelope fields are camelCase (`eventId`, `ts`, `sourceType`). Clinical parameters are snake_case (`resp_rate`, `spo2`, `temp_c`), matching NEWS2 naming.
- Timestamps are UTC ISO 8601 with a trailing `Z`. Event ids are ULIDs.
- UI language is English (French is an open option). Keep strings in one module per app so they can be translated later.

## Commands

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Windows; use .venv/bin on Linux/macOS
.venv/Scripts/python -m pytest          # contract + invariant tests
.venv/Scripts/ruff check .
docker compose -f infra/docker-compose.yml up
```
