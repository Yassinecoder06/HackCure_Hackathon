"""Ingest pipeline: validate -> dedupe/store -> apply to the twin.

Live processing must give the same twin as replaying the log. Handlers are guarded by
event time, but some outcomes depend on order (e.g. vitals that arrive before the late
binding that admits the patient). So when an event arrives out of order (older than the
newest event already applied), the twin is rebuilt from the log, which replays in event-time
order. Out-of-order arrival is rare (store-and-forward replays), and the log is small.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import borj_contracts as bc

from .clock import Clock
from .store import EventStore
from .timeutil import parse_ts
from .twin.handlers import apply
from .twin.layout import WardLayout
from .twin.state import WardTwin

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    status: str  # accepted | duplicate | invalid | clock | other_ward | integrity (rejected at the MQTT boundary)
    detail: str = ""


class Ingestor:
    def __init__(self, layout: WardLayout, store: EventStore, clock: Clock) -> None:
        self.layout = layout
        self.store = store
        self.clock = clock
        self.lock = threading.RLock()
        self.twin = WardTwin(layout)
        self._latest_ts: datetime | None = None
        self.stats = {"accepted": 0, "duplicate": 0, "invalid": 0, "rebuilds": 0}
        self.listeners: list[Callable[[str, dict[str, Any]], None]] = []

    def event_now(self) -> datetime:
        """Timestamp for events the server itself emits: never earlier than what it already applied.

        In demo mode the simulator clock only ticks once per simulated minute, so "clock now" can lag
        behind the event that triggered a decision; stamping with it would look out of order."""
        with self.lock:
            now = self.clock.now()
            return max(now, self._latest_ts) if self._latest_ts else now

    def rebuild(self) -> None:
        """Recompute the twin from the event log (event-time order)."""
        with self.lock:
            twin = WardTwin(self.layout)
            latest = None
            for event in self.store.events():
                apply(twin, event.schema, event.payload)
                latest = parse_ts(event.payload["ts"])
            self.twin = twin
            self._latest_ts = latest
            self.stats["rebuilds"] += 1

    def handle_raw(self, topic: str, raw: bytes) -> IngestResult:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._invalid(topic, f"not JSON: {exc}")
        if not isinstance(payload, dict):
            return self._invalid(topic, "payload is not an object")
        return self.handle(topic, payload)

    def handle(self, topic: str, payload: dict[str, Any]) -> IngestResult:
        try:
            route = bc.validate_message(topic, payload)
        except bc.ContractError as exc:
            return self._invalid(topic, str(exc))

        if payload["ward"] != self.layout.ward:
            return IngestResult("other_ward", payload["ward"])

        if route.schema == "clock":
            with self.lock:
                self.clock.update_from_message(payload)
            self._notify("clock", payload)
            return IngestResult("clock")

        with self.lock:
            if not self.store.append(topic, route.schema, payload):
                self.stats["duplicate"] += 1
                log.debug("duplicate event %s on %s ignored", payload["eventId"], topic)
                return IngestResult("duplicate", payload["eventId"])

            ts = parse_ts(payload["ts"])
            if self._latest_ts is not None and ts < self._latest_ts:
                self.rebuild()
                outcome = "rebuilt"
            else:
                outcome = apply(self.twin, route.schema, payload)
                self._latest_ts = ts
            self.stats["accepted"] += 1

        self._notify(route.schema, payload)
        return IngestResult("accepted", outcome)

    def _invalid(self, topic: str, reason: str) -> IngestResult:
        self.stats["invalid"] += 1
        log.warning("rejected message on %s: %s", topic, reason)
        return IngestResult("invalid", reason)

    def _notify(self, schema: str, payload: dict[str, Any]) -> None:
        for listener in self.listeners:
            try:
                listener(schema, payload)
            except Exception:  # a broken listener must never break ingest
                log.exception("ingest listener failed")
