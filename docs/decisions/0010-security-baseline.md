# 0010. Security baseline (HackCure section 5)

Status: accepted (2026-10-10)

The HackCure specification makes these **mandatory**, so they apply to the demo, not just to production.

| Requirement | Implementation |
|---|---|
| **Encryption in transit, TLS 1.3** | Mosquitto listener on 8883 with `tls_version tlsv1.3` and per-device credentials. Every HTTP service sits behind a **Caddy** reverse proxy that serves TLS 1.3 only. The local demo uses a local CA (mkcert); the hosted demo uses a real certificate. Plain 1883/HTTP is allowed only for unit tests and local development. |
| **Encryption at rest, AES-256** | Patient-related payloads (events, consent, prescriptions, audit details) are encrypted with **AES-256-GCM** before they reach PostgreSQL, using the Python `cryptography` library. The key comes from an env var or secret, never git, and a key id is stored for rotation. Backups and volumes contain only ciphertext. |
| **Pseudonymisation** | Synthetic ids only: `admissionId`, `patientRef` ("Patient 04"). No names or national ids anywhere. The family side gets an opaque `linkId`. |
| **Non-repudiation of access** | Real login (staff id + PIN/password hashed with argon2, short-lived signed tokens) replaces the `X-Staff-Id` demo stub. **Every read and write of patient data is logged** (who, what, when). The audit log is **hash-chained**: each entry stores the hash of the previous one, so any tampering is detectable. |
| **Integrity of measurement frames** | Each device or node signs its MQTT messages with **HMAC-SHA256** (per-device key) in the envelope's `integrity` field. The gateway and server reject bad signatures. Gateway adapters also check the device-level checksum or CRC. |
| **Leak prevention** | The family link stays outbound-only, allow-list only (safety invariants 2 and 3). Secrets live in `.env` (ignored) or Docker secrets. |

## Consequences

- New safety invariants 10 and 11 in `CLAUDE.md`.
- A: TLS broker, per-device credentials and HMAC signing in the simulator, gateway and node.
- B: encryption at rest, login, access audit, hash chain, HMAC verification.
- C: login screen, token handling, the app working over HTTPS.
