"""Store-and-forward outbox for the bedside node.

Persists call events locally in SQLite so that during network outages or broker
restarts, events are not lost. Once connectivity is restored, events are
replayed with `deliveredLate: True` and their original timestamps (invariants 5, 6, 10).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class NodeOutbox:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    call_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def enqueue(self, topic: str, payload: dict[str, Any]) -> None:
        event_id = payload["eventId"]
        call_id = payload["callId"]
        kind = payload["kind"]
        now_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload_str = json.dumps(payload)

        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO outbox_events
                (event_id, topic, payload, call_id, kind, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (event_id, topic, payload_str, call_id, kind, now_utc),
            )
            self._conn.commit()
            log.info("Queued event %s in local outbox (topic: %s)", event_id, topic)

    def get_pending(self) -> list[tuple[str, dict[str, Any]]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT topic, payload FROM outbox_events WHERE status = 'pending' ORDER BY created_at ASC"
            ).fetchall()
            results = []
            for r in rows:
                results.append((r["topic"], json.loads(r["payload"])))
            return results

    def mark_delivered(self, event_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE outbox_events SET status = 'delivered' WHERE event_id = ?",
                (event_id,),
            )
            self._conn.commit()
            log.debug("Marked event %s as delivered in outbox", event_id)

    def pending_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS cnt FROM outbox_events WHERE status = 'pending'").fetchone()
            return int(row["cnt"]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
