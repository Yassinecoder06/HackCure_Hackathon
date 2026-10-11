# family-gateway/

The DMZ half of the **Family Care Link**. A relative opens the QR link from the ward, types the one-time code the nurse reads out, and sees only what a nurse approved: visiting hours, "dinner was served", a short note. Never vital signs, scores, drug names, doses, staff or locations (safety invariant 2).

Implements [`contracts/family-gateway.openapi.yaml`](../contracts/family-gateway.openapi.yaml). Decisions: [ADR 0008](../docs/decisions/0008-track-2.md), [ADR 0010](../docs/decisions/0010-security-baseline.md).

## How it fits

```
ward network                          dmz network                       internet
┌──────────────┐  outbound push   ┌───────────────┐   ┌────────────┐   ┌─────────────┐
│ server  ──►  │  TLS 1.3, :4443  │ family-proxy  │──►│ family-    │   │ relative's  │
│ family       │ ───────────────► │ (nginx)       │   │ gateway    │◄──│ phone, :8443│
│ publisher    │                  │ 443 public    │   │ (this)     │   │ TLS 1.3     │
└──────────────┘                  └───────────────┘   └────────────┘   └─────────────┘
```

- **Outbound only (invariant 3).** The ward's publisher connects *out* to the gateway. family-gateway sits on the `dmz` docker network alone, so it cannot even resolve `mosquitto`, `server` or `postgres`. The ingest port (4443) is not published; the public port serves relatives only and answers 404 for `/ingest`.
- **Two faces, one process.** `/ingest/v1/*` (bearer token of the ward publisher) and `/family/v1/*` (relatives). It also serves the built `apps/family` from the same origin, including `/r/<inviteId>`, the page the QR code opens.
- **Allow-list at the door (invariant 2).** Every pushed payload is validated against `contracts/schemas/family-{invite,update,revocation}.schema.json` (`additionalProperties: false`). Free text is checked again with the ward's own word list (`server/config/family.yaml`), because this service does not trust the ward to have done it.
- **Consent first (invariant 4).** An update for a link with no live invite is refused (409). A revocation kills the invite, every open session and, once nobody is left, deletes the stored updates. Expiry is judged on the ward's own clock (the newest timestamp the ward has sent), so a demo on a simulated clock behaves like production.
- **Strong, boring auth.** Invite = QR link + one-time code (6 digits; only a salted scrypt hash ever left the ward). The code works once, then it is a random session token (stored only as a hash). 5 failed attempts per client per 10 minutes give a 429; 10 failures on one invite from anywhere revoke the invite.
- **Audited.** Every redeem and feed read is recorded (time, link, session fingerprint, hashed client); the ward can read it with `GET /ingest/v1/views?linkId=`.
- **At rest.** Nurse-approved text is encrypted with AES-256-GCM (`FAMILY_DATA_KEY`). Transport is TLS 1.3 (nginx).

## Run

Part of the compose stack (`docker compose up --build`, see the root README). The relative's address is `https://<this machine>:8443`; put it in `BORJ_FAMILY_PUBLIC_URL` so the QR codes point to it.

Standalone, for development:

```bash
pip install -r family-gateway/requirements.txt
export FAMILY_PUBLISHER_TOKEN=dev-token FAMILY_DATA_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
export FAMILY_DB_PATH=data/family.sqlite FAMILY_STATIC_DIR=apps/family/dist
PYTHONPATH=contracts:family-gateway uvicorn borj_family_gateway.app:app_factory --factory --port 8100
pytest family-gateway/tests
```

| Variable | Meaning |
|---|---|
| `FAMILY_PUBLISHER_TOKEN` | bearer secret of the ward publisher (`infra/gen_secrets.py`) |
| `FAMILY_DATA_KEY` | base64 of 32 bytes, AES-256-GCM key for stored updates |
| `FAMILY_TRUST_PROXY` | `1` behind our nginx: the client address comes from `X-Real-IP` |
| `FAMILY_WARD_CONTACT` | phone number shown in the "not an emergency channel" notice (synthetic) |
| `FAMILY_SESSION_HOURS` | session length, default 12 |

## Code map

| File | Why it exists |
|---|---|
| `borj_family_gateway/app.py` | the routes, auth, rate limits, headers, static app |
| `borj_family_gateway/store.py` | SQLite tables, AES-GCM for update text, revocation, view audit, ward clock |
| `borj_family_gateway/security.py` | scrypt code check (same format as the ward), privacy filter, rate limiter |
| `tests/test_family_gateway.py` | allow-list, consent, one-time code, revocation, rate limits, encryption |
| `../server/tests/test_family_pipeline.py` | ward, publisher, gateway and relative in one test, plus revocation |
| `../tests/integration/family_smoke.py` | the same on the real compose stack, plus the network isolation checks |
