"""SQLite store of everything family-gateway knows. It never holds vitals, scores, drugs, doses, staff or locations
(the allow-list schemas leave no room for them). Nurse-written update text is encrypted at rest (AES-256-GCM)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    invite_id TEXT PRIMARY KEY, link_id TEXT NOT NULL, relative_label TEXT NOT NULL, allowed_kinds TEXT NOT NULL,
    code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, link_id TEXT NOT NULL, invite_id TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS updates (
    update_id TEXT PRIMARY KEY, link_id TEXT NOT NULL, kind TEXT NOT NULL, nonce BLOB, ciphertext BLOB,
    published_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revocations (
    revocation_id TEXT PRIMARY KEY, link_id TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS views (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, link_id TEXT NOT NULL, session TEXT NOT NULL,
    client TEXT NOT NULL, what TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clock (id INTEGER PRIMARY KEY CHECK (id = 1), ward_time TEXT);
"""


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, path: Path | str, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("FAMILY_DATA_KEY must be 32 bytes (AES-256)")
        self._aes = AESGCM(key)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)

    # --- ward time ----------------------------------------------------------------------------
    # Expiry is judged on the ward's own clock (the newest timestamp the ward has sent), so a demo running on a
    # simulated clock behaves like production. Before the ward has sent anything, the caller falls back to wall time.

    def ward_time(self) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT ward_time FROM clock WHERE id = 1").fetchone()
        return row["ward_time"] if row else None

    def advance_ward_time(self, ts: str) -> None:
        with self._lock:
            current = self.ward_time()
            if current is None or ts > current:  # ISO 8601 UTC strings sort chronologically
                self._db.execute(
                    "INSERT INTO clock (id, ward_time) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET "
                    "ward_time = excluded.ward_time", (ts,))
                self._db.commit()

    # --- invites and sessions -----------------------------------------------------------------

    def add_invite(self, p: dict[str, Any]) -> bool:
        with self._lock:
            if self._db.execute("SELECT 1 FROM invites WHERE invite_id = ?", (p["inviteId"],)).fetchone():
                return False  # idempotent: the same invite pushed twice changes nothing
            self._db.execute(
                "INSERT INTO invites (invite_id, link_id, relative_label, allowed_kinds, code_hash, expires_at, status)"
                " VALUES (?, ?, ?, ?, ?, ?, 'active')",
                (p["inviteId"], p["linkId"], p["relativeLabel"], json.dumps(p["allowedKinds"]), p["codeHash"],
                 p["expiresAt"]))
            self._db.commit()
            return True

    def invite(self, invite_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute("SELECT * FROM invites WHERE invite_id = ?", (invite_id,)).fetchone()

    def usable_invites(self, now: str) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(
                "SELECT * FROM invites WHERE status = 'active' AND expires_at > ?", (now,)).fetchall()

    def link_has_live_invite(self, link_id: str, now: str) -> bool:
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM invites WHERE link_id = ? AND status != 'revoked' AND expires_at > ?",
                (link_id, now)).fetchone() is not None

    def count_failure(self, invite_id: str, lock_after: int) -> None:
        with self._lock:
            self._db.execute("UPDATE invites SET failed_attempts = failed_attempts + 1 WHERE invite_id = ?",
                             (invite_id,))
            self._db.execute("UPDATE invites SET status = 'revoked' WHERE invite_id = ? AND failed_attempts >= ?",
                             (invite_id, lock_after))
            self._db.commit()

    def redeem(self, invite_id: str, token: str, session_expires_at: str, link_id: str) -> None:
        with self._lock:
            # The one-time code is used up now; the session carries on from here.
            self._db.execute("UPDATE invites SET status = 'redeemed' WHERE invite_id = ?", (invite_id,))
            self._db.execute("INSERT INTO sessions (token_hash, link_id, invite_id, expires_at) VALUES (?, ?, ?, ?)",
                             (digest(token), link_id, invite_id, session_expires_at))
            self._db.commit()

    def session(self, token: str, now: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(
                "SELECT s.*, i.allowed_kinds, i.status AS invite_status, i.expires_at AS invite_expires_at "
                "FROM sessions s JOIN invites i ON i.invite_id = s.invite_id "
                "WHERE s.token_hash = ? AND s.expires_at > ?", (digest(token), now)).fetchone()

    # --- updates ------------------------------------------------------------------------------

    def add_update(self, p: dict[str, Any]) -> bool:
        with self._lock:
            if self._db.execute("SELECT 1 FROM updates WHERE update_id = ?", (p["updateId"],)).fetchone():
                return False
            nonce = ciphertext = None
            if "text" in p:
                nonce = os.urandom(12)
                ciphertext = self._aes.encrypt(nonce, p["text"].encode(), p["updateId"].encode())
            self._db.execute(
                "INSERT INTO updates (update_id, link_id, kind, nonce, ciphertext, published_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (p["updateId"], p["linkId"], p["kind"], nonce, ciphertext, p["publishedAt"]))
            self._db.commit()
            return True

    def updates_for(self, link_id: str, kinds: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM updates WHERE link_id = ? ORDER BY published_at DESC, update_id DESC",
                (link_id,)).fetchall()
        out = []
        for row in rows:
            if row["kind"] not in kinds:
                continue
            item = {"kind": row["kind"], "publishedAt": row["published_at"]}
            if row["ciphertext"] is not None:
                item["text"] = self._aes.decrypt(row["nonce"], row["ciphertext"], row["update_id"].encode()).decode()
            out.append(item)
        return out

    # --- revocation ---------------------------------------------------------------------------

    def revoke(self, revocation_id: str, link_id: str, invite_id: str | None, at: str) -> bool:
        """Immediate: the invite(s) die, their sessions die, and once nobody is left the updates are deleted."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM revocations WHERE revocation_id = ?", (revocation_id,)).fetchone():
                return False
            if invite_id:
                self._db.execute("UPDATE invites SET status = 'revoked' WHERE invite_id = ? AND link_id = ?",
                                 (invite_id, link_id))
                self._db.execute("DELETE FROM sessions WHERE invite_id = ? AND link_id = ?", (invite_id, link_id))
            else:
                self._db.execute("UPDATE invites SET status = 'revoked' WHERE link_id = ?", (link_id,))
                self._db.execute("DELETE FROM sessions WHERE link_id = ?", (link_id,))
            if not self._db.execute("SELECT 1 FROM invites WHERE link_id = ? AND status != 'revoked'",
                                    (link_id,)).fetchone():
                self._db.execute("DELETE FROM updates WHERE link_id = ?", (link_id,))
            self._db.execute("INSERT INTO revocations (revocation_id, link_id, applied_at) VALUES (?, ?, ?)",
                             (revocation_id, link_id, at))
            self._db.commit()
            return True

    # --- view audit ---------------------------------------------------------------------------

    def log_view(self, ts: str, link_id: str, session_token_hash: str, client: str, what: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO views (ts, link_id, session, client, what) VALUES (?, ?, ?, ?, ?)",
                             (ts, link_id, session_token_hash[:10], digest(client)[:12], what))
            self._db.commit()

    def views(self, link_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, session, client, what FROM views WHERE link_id = ? ORDER BY id DESC LIMIT ?",
                (link_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def raw_dump(self) -> bytes:
        """Everything stored, as bytes (a test uses it to show nurse text is not in the file in clear)."""
        with self._lock:
            return "\n".join(self._db.iterdump()).encode()
