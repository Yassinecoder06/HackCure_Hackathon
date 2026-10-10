"""Event log (the source of truth) and audit log, encrypted at rest.

- PostgreSQL in compose and the demo; SQLite only for unit tests and local dev (ADR 0009).
  One code path through SQLAlchemy Core.
- Every event payload and audit detail is sealed with AES-256-GCM before it reaches the
  database (ADR 0010, invariant 10). Only routing metadata stays in clear: event id, schema,
  topic, ward, timestamp. The topic names a bed, never a patient.
- The twin is derived state: it can always be rebuilt by replaying `events`.
- Inserting an eventId that already exists is a no-op (invariant 6).
- The audit log is hash-chained (invariant 11): each entry stores the hash of the previous one,
  computed over its metadata and its ciphertext, so editing, deleting or reordering any entry
  breaks verification, and verification needs no decryption key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import StaticPool

from .crypto import DataCipher, Sealed
from .timeutil import format_ts, parse_ts, utcnow

metadata = MetaData()

# BigInteger on PostgreSQL, but plain INTEGER on SQLite so it stays an autoincrement rowid alias.
_SeqType = BigInteger().with_variant(Integer(), "sqlite")

events = Table(
    "events",
    metadata,
    Column("seq", _SeqType, primary_key=True, autoincrement=True),
    Column("event_id", String(26), nullable=False, unique=True),
    Column("topic", String(200), nullable=False),
    Column("schema", String(40), nullable=False),
    Column("ward", String(40), nullable=False),
    # Normalised to microseconds so text order == time order.
    Column("ts", String(32), nullable=False, index=True),
    Column("received_at", String(32), nullable=False),
    Column("key_id", String(40), nullable=False),
    Column("nonce", LargeBinary, nullable=False),
    Column("ciphertext", LargeBinary, nullable=False),
)

audit = Table(
    "audit",
    metadata,
    Column("seq", _SeqType, primary_key=True, autoincrement=True),
    Column("audit_id", String(36), nullable=False, unique=True),
    Column("ts", String(32), nullable=False),
    Column("actor", String(64), nullable=False),
    Column("action", String(80), nullable=False),
    Column("target", String(200), nullable=False),
    Column("key_id", String(40), nullable=False),
    Column("nonce", LargeBinary, nullable=False),
    Column("ciphertext", LargeBinary, nullable=False),
    Column("prev_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
)

GENESIS_HASH = "0" * 64


def _audit_hash(prev_hash: str, audit_id: str, ts: str, actor: str, action: str, target: str,
                key_id: str, nonce: bytes, ciphertext: bytes) -> str:
    material = json.dumps(
        [prev_hash, audit_id, ts, actor, action, target, key_id,
         base64.b64encode(nonce).decode(), hashlib.sha256(ciphertext).hexdigest()],
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    topic: str
    schema: str
    payload: dict[str, Any]


def make_engine(db_url: str) -> Engine:
    url = make_url(db_url)
    if url.get_backend_name() == "sqlite":
        if url.database in (None, "", ":memory:"):
            # One shared connection, otherwise every connection sees a fresh empty in-memory DB.
            return create_engine(db_url, poolclass=StaticPool, connect_args={"check_same_thread": False})
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(db_url, connect_args={"check_same_thread": False})
    return create_engine(db_url, pool_pre_ping=True)


class EventStore:
    def __init__(self, db_url: str, cipher: DataCipher) -> None:
        self.engine = make_engine(db_url)
        self.cipher = cipher
        self._lock = threading.Lock()
        self._insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    # --- events -------------------------------------------------------------------------

    def append(self, topic: str, schema: str, payload: dict[str, Any]) -> bool:
        """Store an event. Returns False if its eventId was already stored (duplicate)."""
        event_id = payload["eventId"]
        sealed = self.cipher.seal(_to_bytes(payload), associated=event_id.encode())
        stmt = (
            self._insert(events)
            .values(
                event_id=event_id,
                topic=topic,
                schema=schema,
                ward=payload["ward"],
                ts=parse_ts(payload["ts"]).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                received_at=format_ts(utcnow()),
                key_id=sealed.key_id,
                nonce=sealed.nonce,
                ciphertext=sealed.ciphertext,
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
            # RETURNING tells us reliably whether a row was inserted: `rowcount` is not dependable
            # for INSERT on every driver (it is not on psycopg / PostgreSQL), and a wrong answer here
            # would make every new event look like a duplicate.
            .returning(events.c.seq)
        )
        with self._lock, self.engine.begin() as conn:
            return conn.execute(stmt).first() is not None

    def events(self) -> Iterator[StoredEvent]:
        """All events in event-time order (ties broken by arrival order), for replay."""
        query = select(events.c.seq, events.c.event_id, events.c.topic, events.c.schema, events.c.key_id,
                       events.c.nonce, events.c.ciphertext).order_by(events.c.ts, events.c.seq)
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(query).all()
        for seq, event_id, topic, schema, key_id, nonce, ct in rows:
            plaintext = self.cipher.open(Sealed(key_id, nonce, ct), associated=event_id.encode())
            yield StoredEvent(seq=seq, topic=topic, schema=schema, payload=json.loads(plaintext))

    def count(self) -> int:
        with self._lock, self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(events)).scalar_one()

    # --- audit log: every suggestion and every human decision (invariants 1, 11) ---------

    def audit(self, actor: str, action: str, target: str, detail: dict[str, Any] | None = None) -> str:
        """Append one entry to the chain. Single writer: the in-process lock serialises the chain."""
        audit_id = str(uuid.uuid4())
        ts = format_ts(utcnow())
        sealed = self.cipher.seal(_to_bytes(detail or {}), associated=audit_id.encode())
        with self._lock, self.engine.begin() as conn:
            last = conn.execute(select(audit.c.hash).order_by(audit.c.seq.desc()).limit(1)).scalar()
            prev_hash = last or GENESIS_HASH
            digest = _audit_hash(prev_hash, audit_id, ts, actor, action, target,
                                 sealed.key_id, sealed.nonce, sealed.ciphertext)
            conn.execute(audit.insert().values(
                audit_id=audit_id, ts=ts, actor=actor, action=action, target=target,
                key_id=sealed.key_id, nonce=sealed.nonce, ciphertext=sealed.ciphertext,
                prev_hash=prev_hash, hash=digest,
            ))
        return audit_id

    def verify_audit_chain(self) -> dict[str, Any]:
        """Recompute the chain from the start. Returns the AuditVerify shape from openapi.yaml."""
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(select(audit).order_by(audit.c.seq)).mappings().all()
        prev_hash = GENESIS_HASH
        for r in rows:
            expected = _audit_hash(prev_hash, r["audit_id"], r["ts"], r["actor"], r["action"], r["target"],
                                   r["key_id"], r["nonce"], r["ciphertext"])
            if r["prev_hash"] != prev_hash or r["hash"] != expected:
                return {"valid": False, "entries": len(rows), "firstBrokenAuditId": r["audit_id"]}
            prev_hash = r["hash"]
        return {"valid": True, "entries": len(rows)}

    def audit_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        query = select(audit).order_by(audit.c.seq.desc()).limit(limit)
        with self._lock, self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        return [
            {
                "auditId": r["audit_id"], "ts": r["ts"], "actor": r["actor"], "action": r["action"],
                "target": r["target"], "prevHash": r["prev_hash"], "hash": r["hash"],
                "detail": json.loads(self.cipher.open(Sealed(r["key_id"], r["nonce"], r["ciphertext"]),
                                                      associated=r["audit_id"].encode())),
            }
            for r in rows
        ]


def _to_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
