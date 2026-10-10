"""SQLite event log (the source of truth) and audit log.

The twin is derived state: it can always be rebuilt by replaying `events`.
Inserting an eventId that already exists is a no-op (safety invariant 6).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .timeutil import format_ts, parse_ts, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,
    topic       TEXT NOT NULL,
    schema      TEXT NOT NULL,
    ward        TEXT NOT NULL,
    ts          TEXT NOT NULL,  -- normalised to microseconds so text order == time order
    received_at TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);

CREATE TABLE IF NOT EXISTS audit (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    target  TEXT NOT NULL,
    detail  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    topic: str
    schema: str
    payload: dict[str, Any]


class EventStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def append(self, topic: str, schema: str, payload: dict[str, Any]) -> bool:
        """Store an event. Returns False if its eventId was already stored (duplicate)."""
        with self._lock:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO events (event_id, topic, schema, ward, ts, received_at, payload)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["eventId"],
                    topic,
                    schema,
                    payload["ward"],
                    parse_ts(payload["ts"]).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    format_ts(utcnow()),
                    json.dumps(payload, separators=(",", ":")),
                ),
            )
            self._db.commit()
            return cur.rowcount == 1

    def events(self) -> Iterator[StoredEvent]:
        """All events in event-time order (ties broken by arrival order), for replay."""
        with self._lock:
            rows = self._db.execute("SELECT seq, topic, schema, payload FROM events ORDER BY ts, seq").fetchall()
        for seq, topic, schema, payload in rows:
            yield StoredEvent(seq=seq, topic=topic, schema=schema, payload=json.loads(payload))

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # --- audit log: every suggestion and every human decision (safety invariant 1) ---

    def audit(self, actor: str, action: str, target: str, detail: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO audit (ts, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                (format_ts(utcnow()), actor, action, target, json.dumps(detail or {})),
            )
            self._db.commit()

    def audit_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, ts, actor, action, target, detail FROM audit ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"auditId": str(seq), "ts": ts, "actor": actor, "action": action, "target": target,
             "detail": json.loads(detail)}
            for seq, ts, actor, action, target, detail in rows
        ]
