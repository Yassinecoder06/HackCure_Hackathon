# gateway/ (owner: A)

Ward Device Gateway. Runs on a ward laptop or on the Raspberry Pi.

Implements **Role A, P1** specification in [`docs/roles/A-edge.md`](../docs/roles/A-edge.md).

---

## 1. Capabilities

- **Device Adapters (Read-Only)**: `DeviceAdapter` interface. Never writes to medical machines (whitepaper 4.1). Includes `ReplayAdapter` with CRC32 checksum verification for frame integrity.
- **Validity & Freshness**: Evaluates vital signs against `gateway/config/quality.yaml`, applying `sensor_off`, `artifact`, and `implausible` flags.
- **Dynamic Bed Binding**: Subscribes to `borj/{ward}/+/binding` events to maintain live device-to-bed and bed-to-admission mappings.
- **Store-and-Forward Outbox**: Local SQLite storage where patient payloads are encrypted at rest with **AES-256-GCM** (safety invariant 10). Replays pending observations with `late_delivery` flag when link returns.
- **HMAC-SHA256 Signing**: Every outgoing message carries an HMAC-SHA256 signature in its `integrity` envelope (safety invariant 13).

---

## 2. Running Tests

```bash
pytest gateway/tests/
```
