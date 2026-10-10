"""Encryption at rest (ADR 0010, invariant 10): the database only ever holds ciphertext."""

from __future__ import annotations

import pytest
from borj_server.crypto import DataCipher, DataKeyError
from borj_server.store import EventStore, events
from cryptography.exceptions import InvalidTag
from sqlalchemy import select, update

from .conftest import example


def raw_rows(store: EventStore) -> list[tuple]:
    with store.engine.connect() as conn:
        return [tuple(r) for r in conn.execute(select(events)).all()]


def test_no_plaintext_patient_data_in_the_database():
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    payload = example("vitals.device")
    store.append("borj/W1/B04/vitals", "vitals", payload)

    raw = repr(raw_rows(store)).encode()
    for secret in (b"pulse", b"112", b"resp_rate", b"MON-B04", b"38.4", b"gateway-sim"):
        assert secret not in raw, f"{secret!r} stored in clear"
    assert [e.payload for e in store.events()] == [payload]  # but it reads back intact


def test_tampered_ciphertext_is_detected():
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    store.append("borj/W1/B04/vitals", "vitals", example("vitals.device"))
    with store.engine.begin() as conn:
        ct = conn.execute(select(events.c.ciphertext)).scalar_one()
        conn.execute(update(events).values(ciphertext=bytes([ct[0] ^ 1]) + ct[1:]))
    with pytest.raises(InvalidTag):
        list(store.events())


def test_ciphertext_moved_to_another_row_does_not_decrypt():
    """The event id is bound in as associated data."""
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    store.append("borj/W1/B04/vitals", "vitals", example("vitals.device"))
    store.append("borj/W1/B04/vitals", "vitals", example("vitals.manual"))
    with store.engine.begin() as conn:
        rows = conn.execute(select(events.c.seq, events.c.nonce, events.c.ciphertext)).all()
        conn.execute(update(events).where(events.c.seq == rows[1].seq)
                     .values(nonce=rows[0].nonce, ciphertext=rows[0].ciphertext))
    with pytest.raises(InvalidTag):
        list(store.events())


def test_key_rotation_keeps_old_records_readable(tmp_path):
    url = f"sqlite:///{(tmp_path / 'borj.sqlite').as_posix()}"
    old = EventStore(url, DataCipher({"k1": b"1" * 32}, "k1"))
    old.append("borj/W1/B04/vitals", "vitals", example("vitals.device"))
    old.close()

    rotated = EventStore(url, DataCipher({"k1": b"1" * 32, "k2": b"2" * 32}, "k2"))
    rotated.append("borj/W1/B04/vitals", "vitals", example("vitals.manual"))
    assert len(list(rotated.events())) == 2
    with rotated.engine.connect() as conn:
        assert sorted(conn.execute(select(events.c.key_id)).scalars()) == ["k1", "k2"]


def test_audit_detail_is_encrypted_and_reads_back():
    store = EventStore("sqlite://", DataCipher({"k1": b"K" * 32}, "k1"))
    store.audit("N1", "call.acknowledged", "C-B06-0001", {"note": "on my way to B06"})
    with store.engine.connect() as conn:
        raw = repr(conn.execute(select(events.metadata.tables["audit"])).all()).encode()
    assert b"on my way" not in raw
    assert store.audit_entries()[0]["detail"] == {"note": "on my way to B06"}


def test_bad_keys_are_refused(monkeypatch):
    with pytest.raises(DataKeyError):
        DataCipher({"k1": b"short"}, "k1")
    monkeypatch.delenv("BORJ_DATA_KEY", raising=False)
    with pytest.raises(DataKeyError):
        DataCipher.from_env()
