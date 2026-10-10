"""Live WebSocket stream (contracts/openapi.yaml: StreamMessage)."""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import login, make_client, openapi_validator


def receive_until(ws, msg_type: str, limit: int = 50) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message["type"] == msg_type:
            return message
    raise AssertionError(f"no {msg_type} message")


def test_stream_requires_a_valid_token(tmp_path):
    with make_client(tmp_path) as c:
        with pytest.raises(WebSocketDisconnect) as exc, c.websocket_connect(
            "/api/v1/wards/W1/stream", subprotocols=["bearer", "not-a-token"]
        ):
            pass
        assert exc.value.code == 4401
        with pytest.raises(WebSocketDisconnect), c.websocket_connect("/api/v1/wards/W1/stream"):
            pass


def test_stream_sends_snapshot_then_bed_updates_with_news2(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, stream_metrics_interval_s=0.2) as c:
        token = login(c, "N1")["token"]
        ingestor = c.app.state.ingestor
        with c.websocket_connect("/api/v1/wards/W1/stream", subprotocols=["bearer", token]) as ws:
            assert ws.accepted_subprotocol == "bearer"
            first = ws.receive_json()
            assert first["type"] == "snapshot"
            assert not list(openapi_validator("WardSnapshot").iter_errors(first["data"]))

            ingestor.handle(*make_event("binding"))
            ingestor.handle(*make_event("vitals.device"))
            ingestor.handle(*make_event("vitals.manual"))
            ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:10:00Z",
                                                  "speed": 1, "scenario": "t", "running": True})
            bed = None
            for _ in range(50):
                message = ws.receive_json()
                assert not list(openapi_validator("StreamMessage").iter_errors(message))
                if message["type"] == "bed" and message["data"]["bed"] == "B04" and message["data"]["news2"]:
                    if message["data"]["news2"]["complete"]:
                        bed = message["data"]
                        break
            assert bed is not None
            assert not list(openapi_validator("Bed").iter_errors(bed))
            assert (bed["news2"]["total"], bed["news2"]["band"]) == (8, "high")

            metrics = receive_until(ws, "metrics")["data"]
            assert not list(openapi_validator("Metrics").iter_errors(metrics))
            assert metrics["triageLatencyMs"]["n"] >= 1

    entries = [(e["actor"], e["action"]) for e in c.app.state.ingestor.store.audit_entries()]
    assert ("N1", "stream.open") in entries
