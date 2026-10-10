"""Live WebSocket stream: GET /api/v1/wards/{ward}/stream (contracts/openapi.yaml, StreamMessage).

Flow: an event is ingested (MQTT thread) -> the hub notes which bed/staff changed -> each
client's coroutine coalesces bursts, rebuilds those views with NEWS2 (in a worker thread, so the
event loop never blocks on the inference call) and sends them.

Latency (Track 2 "zero latency on triage", ADR 0008): every push records the time from the server
receiving the event to the message leaving on the socket; p50/p95 go out as `metrics` messages.
This is the server's share of the end-to-end budget; the apps add network and rendering time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .auth import AuthError
from .live import build_beds, build_calls, build_snapshot, build_staff

log = logging.getLogger(__name__)

POLICY_VIOLATION = 4401  # application close code: missing or invalid token
SUBPROTOCOL = "bearer"


def _token_from_subprotocols(websocket: WebSocket) -> str:
    """The client offers subprotocols ["bearer", "<token>"] (browsers cannot set an Authorization
    header on WebSockets). Unlike a ?token= query string, this never lands in access logs."""
    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    if len(offered) == 2 and offered[0] == SUBPROTOCOL:
        return offered[1]
    return ""


@dataclass
class Change:
    beds: set[str] = field(default_factory=set)
    staff: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    all_beds: bool = False
    clock: dict[str, Any] | None = None
    received: float = field(default_factory=time.monotonic)


class LatencyWindow:
    def __init__(self, window_s: float = 60.0) -> None:
        self.window_s = window_s
        self._samples: deque[tuple[float, float]] = deque()

    def add(self, ms: float) -> None:
        now = time.monotonic()
        self._samples.append((now, ms))
        while self._samples and now - self._samples[0][0] > self.window_s:
            self._samples.popleft()

    def summary(self) -> dict[str, Any]:
        values = sorted(ms for _, ms in self._samples)

        def pct(p: float) -> float:
            return round(values[min(len(values) - 1, int(p * len(values)))], 1) if values else 0.0

        return {"windowS": int(self.window_s), "triageLatencyMs": {"p50": pct(0.5), "p95": pct(0.95), "n": len(values)}}


class StreamHub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue[Change]] = set()
        self.latency = LatencyWindow()

    def on_ingest(self, schema: str, payload: dict[str, Any]) -> None:
        """Ingestor listener. Runs in the MQTT (or request) thread: only enqueue, never compute."""
        if self.loop is None or not self.queues:
            return
        if schema == "clock":
            change = Change(all_beds=True, clock={k: payload[k] for k in ("simTs", "speed", "running")})
        elif schema in ("call", "call-state"):
            change = Change(beds={payload["bed"]}, calls={payload["callId"]})
        elif schema == "ack" and payload["target"] == "alert":
            change = Change(all_beds=True)  # rare: refresh alerts everywhere rather than parse alert ids
        elif "bed" in payload:
            change = Change(beds={payload["bed"]})
        elif schema == "staff-presence":
            change = Change(staff={payload["staffId"]})
        elif schema == "assignment":
            moved = {c["bed"] for c in payload["changes"]}
            people = {c["toStaffId"] for c in payload["changes"]} | {
                c["fromStaffId"] for c in payload["changes"] if "fromStaffId" in c}
            change = Change(beds=moved, staff=people)
        else:
            return
        self._broadcast(change)

    def on_suggestion(self, suggestion: dict[str, Any]) -> None:
        if self.loop is not None and self.queues:
            self._broadcast(Change(suggestions=[dict(suggestion)]))

    def _broadcast(self, change: Change) -> None:
        for queue in list(self.queues):
            self.loop.call_soon_threadsafe(queue.put_nowait, change)


async def serve(websocket: WebSocket, app: FastAPI, ward: str, metrics_interval_s: float,
                refresh_interval_s: float) -> None:
    token = _token_from_subprotocols(websocket)
    try:
        who = app.state.auth.verify(token)
    except AuthError:
        await websocket.close(code=POLICY_VIOLATION)
        return
    if ward != app.state.ingestor.layout.ward:
        await websocket.close(code=POLICY_VIOLATION)
        return

    hub: StreamHub = app.state.hub
    queue: asyncio.Queue[Change] = asyncio.Queue()
    await websocket.accept(subprotocol=SUBPROTOCOL)
    app.state.ingestor.store.audit(who.staff_id, "stream.open", ward)
    hub.queues.add(queue)
    try:
        snapshot = await asyncio.to_thread(build_snapshot, app)
        await websocket.send_json({"type": "snapshot", "data": snapshot})
        known_alerts = {a["alertId"]: a for a in snapshot["alerts"]}
        tasks = [
            asyncio.create_task(_push_changes(websocket, app, queue, hub, known_alerts)),
            asyncio.create_task(_tick(queue, websocket, hub, metrics_interval_s, refresh_interval_s)),
            asyncio.create_task(_drain_client(websocket)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                log.error("stream task failed", exc_info=task.exception())
    finally:
        hub.queues.discard(queue)


async def _push_changes(websocket: WebSocket, app: FastAPI, queue: asyncio.Queue[Change], hub: StreamHub,
                        known_alerts: dict[str, dict[str, Any]]) -> None:
    while True:
        merged = await queue.get()
        while not queue.empty():  # coalesce a burst into one update per bed
            nxt = queue.get_nowait()
            merged.beds |= nxt.beds
            merged.staff |= nxt.staff
            merged.calls |= nxt.calls
            merged.suggestions += nxt.suggestions
            merged.all_beds |= nxt.all_beds
            merged.clock = nxt.clock or merged.clock
            merged.received = min(merged.received, nxt.received)
        if merged.clock:
            await websocket.send_json({"type": "clock", "data": merged.clock})
        for suggestion in merged.suggestions:
            await websocket.send_json({"type": "assignment_suggestion", "data": suggestion})
        if merged.calls:
            for call in await asyncio.to_thread(build_calls, app, merged.calls):
                await websocket.send_json({"type": "call", "data": call})
        if merged.all_beds or merged.beds:
            scope = None if merged.all_beds else merged.beds
            beds, alerts = await asyncio.to_thread(build_beds, app, scope)
            for bed in beds:
                await websocket.send_json({"type": "bed", "data": bed})
            await _send_alerts(websocket, known_alerts, alerts, scope)
        if merged.staff:
            for member in await asyncio.to_thread(build_staff, app, merged.staff):
                await websocket.send_json({"type": "staff", "data": member})
        if merged.beds and not merged.all_beds:
            hub.latency.add((time.monotonic() - merged.received) * 1000)


async def _send_alerts(websocket: WebSocket, known: dict[str, dict[str, Any]], current: list[dict[str, Any]],
                       scope: set[str] | None) -> None:
    """Send new or changed alerts, and `active: false` for alerts in scope whose condition has cleared."""
    current_ids = {a["alertId"] for a in current}
    for alert_id, alert in list(known.items()):
        if alert_id not in current_ids and (scope is None or alert.get("bed") in scope):
            await websocket.send_json({"type": "alert", "data": {**alert, "active": False}})
            del known[alert_id]
    for alert in current:
        if known.get(alert["alertId"]) != alert:
            await websocket.send_json({"type": "alert", "data": alert})
            known[alert["alertId"]] = alert


async def _tick(queue: asyncio.Queue[Change], websocket: WebSocket, hub: StreamHub, metrics_interval_s: float,
                refresh_interval_s: float) -> None:
    """Periodic metrics, and a periodic full refresh so readings age into 'stale' without new events."""
    last_refresh = time.monotonic()
    while True:
        await asyncio.sleep(metrics_interval_s)
        await websocket.send_json({"type": "metrics", "data": hub.latency.summary()})
        if time.monotonic() - last_refresh >= refresh_interval_s:
            queue.put_nowait(Change(all_beds=True))
            last_refresh = time.monotonic()


async def _drain_client(websocket: WebSocket) -> None:
    """The stream is server -> client; read only to notice the client going away."""
    while True:
        await websocket.receive_text()
