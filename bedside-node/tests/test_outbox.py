"""Unit tests for NodeOutbox."""

from __future__ import annotations

import tempfile
from pathlib import Path

from borj_node.outbox import NodeOutbox


def test_outbox_enqueue_and_drain():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "outbox.db"
        outbox = NodeOutbox(db_path)

        assert outbox.pending_count() == 0

        payload = {
            "schemaVersion": 1,
            "eventId": "01K7ZQ8V3E4M5N6P7Q8R9S0T1Y",
            "ts": "2026-10-10T22:12:40Z",
            "ward": "W1",
            "bed": "B06",
            "callId": "C-B06-0001",
            "kind": "assist",
            "pressCount": 1,
        }
        outbox.enqueue("borj/W1/B06/call", payload)

        assert outbox.pending_count() == 1
        pending = outbox.get_pending()
        assert len(pending) == 1
        topic, item = pending[0]
        assert topic == "borj/W1/B06/call"
        assert item["eventId"] == "01K7ZQ8V3E4M5N6P7Q8R9S0T1Y"

        outbox.mark_delivered("01K7ZQ8V3E4M5N6P7Q8R9S0T1Y")
        assert outbox.pending_count() == 0


def test_outbox_persists_across_restarts():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "outbox.db"
        outbox1 = NodeOutbox(db_path)
        payload = {
            "schemaVersion": 1,
            "eventId": "01K7ZQ8V3E4M5N6P7Q8R9S0T1Y",
            "ts": "2026-10-10T22:12:40Z",
            "ward": "W1",
            "bed": "B06",
            "callId": "C-B06-0001",
            "kind": "assist",
            "pressCount": 1,
        }
        outbox1.enqueue("borj/W1/B06/call", payload)

        # Reopen with new instance
        outbox2 = NodeOutbox(db_path)
        assert outbox2.pending_count() == 1
        assert outbox2.get_pending()[0][1]["eventId"] == "01K7ZQ8V3E4M5N6P7Q8R9S0T1Y"
