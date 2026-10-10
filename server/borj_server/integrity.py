"""Frame integrity at the MQTT boundary (safety invariant 13, ADR 0010).

Every message from the ward network may carry an `integrity` field: HMAC-SHA256 over the canonical
JSON, with the per-device key named by `keyId` (contracts/schemas/common.schema.json). The check
runs here, before ingest, so a forged or altered message never reaches the event log or the twin.

Modes (BORJ_INTEGRITY_MODE):
- off: no check (unit tests, local tinkering).
- verify: a signature that is present must be valid; unsigned messages are accepted and counted.
  The default while role A's signers are being wired.
- require: as verify, and measurement messages (MEASUREMENTS) must be signed. The demo mode.

A rejected message is logged and written to the hash-chained audit log (who: "mqtt"), so tampering
attempts are visible and non-repudiable. Events the server creates itself (REST actions, call/state)
do not pass through here: they come from an authenticated, audited staff action.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import borj_contracts as bc

from .ingest import Ingestor, IngestResult

log = logging.getLogger(__name__)

MODES = ("off", "verify", "require")
# Messages that carry measurements or bind data to a patient: a forged one could change a score or
# put readings on the wrong patient. These must be signed in "require" mode.
MEASUREMENTS = ("vitals", "device-status", "binding", "call")


class IntegrityGate:
    def __init__(self, keys: dict[str, bytes], mode: str = "verify") -> None:
        if mode not in MODES:
            raise ValueError(f"integrity mode must be one of {MODES}, not {mode!r}")
        self.keys = keys
        self.mode = mode
        self.stats = {"verified": 0, "unsigned": 0, "rejected": 0}

    def check(self, topic: str, payload: dict[str, Any]) -> str | None:
        """None if the message may be ingested, otherwise the reason it is rejected."""
        if self.mode == "off":
            return None
        try:
            schema = bc.route(topic).schema
        except bc.ContractError:
            return None  # not a contract topic: ingest rejects it with the contract error
        integrity = payload.get("integrity")
        if integrity is None:
            self.stats["unsigned"] += 1
            if self.mode == "require" and schema in MEASUREMENTS:
                return "unsigned"
            return None
        key_id = integrity.get("keyId") if isinstance(integrity, dict) else None
        if key_id not in self.keys:
            return "unknown_key"
        if not bc.verify(payload, self.keys):
            return "bad_signature"
        if not _in_scope(key_id, payload):
            return "key_not_for_this_bed"
        self.stats["verified"] += 1
        return None

    def handle_raw(self, ingestor: Ingestor, topic: str, raw: bytes) -> IngestResult:
        """Check, then ingest. Malformed JSON goes straight to ingest, which records it as invalid."""
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ingestor.handle_raw(topic, raw)
        if not isinstance(payload, dict):
            return ingestor.handle_raw(topic, raw)
        reason = self.check(topic, payload)
        if reason is None:
            return ingestor.handle(topic, payload)
        self.stats["rejected"] += 1
        key_id = payload["integrity"].get("keyId") if isinstance(payload.get("integrity"), dict) else None
        detail = {"reason": reason, "eventId": str(payload.get("eventId", ""))[:40], "keyId": key_id}
        log.warning("integrity: rejected message on %s (%s, key %s)", topic, reason, key_id)
        ingestor.store.audit("mqtt", "integrity.rejected", topic, detail)
        return IngestResult("integrity", reason)


def _in_scope(key_id: str, payload: dict[str, Any]) -> bool:
    """A bedside node's key (node-{bed}) only signs for its own bed; sim and gateway keys are ward-wide."""
    if key_id.startswith("node-"):
        return payload.get("bed") == key_id.removeprefix("node-")
    return True
