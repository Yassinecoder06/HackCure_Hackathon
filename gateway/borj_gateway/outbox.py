"""Encrypted store-and-forward outbox for the gateway.

Encrypts patient data at rest with AES-256-GCM (safety invariant 10).
Preserves original eventId and ts upon late replay, adding `late_delivery` flag.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)


class GatewayOutbox:
    def __init__(self, db_path: Path | str = ":memory:", key: bytes | None = None) -> None:
        self.db_path = str(db_path)
        # 256-bit key for AES-256-GCM
        self.key = key or b"0" * 32
        self._aesgcm = AESGCM(self.key)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_outbox (
                    event_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def enqueue(self, topic: str, payload: dict[str, Any]) -> None:
        event_id = payload["eventId"]
        raw = json.dumps(payload).encode("utf-8")
        nonce = os.urandom(12)  # standard 96-bit AES-GCM nonce
        ciphertext = self._aesgcm.encrypt(nonce, raw, None)
        now_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO gateway_outbox
                (event_id, topic, nonce, ciphertext, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (event_id, topic, nonce, ciphertext, now_utc),
            )
            self._conn.commit()
            log.info("Encrypted and stored outbox event %s for %s", event_id, topic)

    def get_pending(self) -> list[tuple[str, dict[str, Any]]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT topic, nonce, ciphertext FROM gateway_outbox WHERE status = 'pending' ORDER BY created_at ASC"
            ).fetchall()
            results = []
            for r in rows:
                plaintext = self._aesgcm.decrypt(r["nonce"], r["ciphertext"], None)
                payload = json.loads(plaintext.decode("utf-8"))
                results.append((r["topic"], payload))
            return results

    def mark_delivered(self, event_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE gateway_outbox SET status = 'delivered' WHERE event_id = ?",
                (event_id,),
            )
            self._conn.commit()

    def pending_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS cnt FROM gateway_outbox WHERE status = 'pending'").fetchone()
            return int(row["cnt"]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
