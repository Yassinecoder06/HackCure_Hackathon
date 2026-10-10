# gateway/ (owner: A)

Ward gateway. Runs on a laptop in the demo, or on the Raspberry Pi. **Not implemented yet.** See [`docs/roles/A-edge.md`](../docs/roles/A-edge.md), P1.

- `adapters/`: one adapter per device family behind a common read-only interface. Starts with a replay adapter for simulator streams.
- Validity and freshness flags (`sensor_off`, `artifact`, `implausible`, `stale_after_s`), with ranges in config.
- Device → bed binding from `binding` events.
- Store-and-forward outbox (SQLite) that keeps the original `eventId` and `ts` and adds the `late_delivery` flag.
- **Never writes to a device** (whitepaper 4.1).
