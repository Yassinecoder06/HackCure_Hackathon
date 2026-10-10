"""Building ward views with NEWS2 and alerts attached, shared by the REST API and the live stream."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .alerts import derive_alerts
from .scoring import attach_news2, news2_inputs
from .timeutil import format_ts
from .twin.views import bed_view, call_view, snapshot_view, staff_view


def _news2_by_bed(beds: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    return {b["bed"]: b["news2"] for b in beds}


def build_snapshot(app: FastAPI) -> dict[str, Any]:
    ingestor = app.state.ingestor
    with ingestor.lock:
        clock = ingestor.clock
        now = clock.now()
        snap = snapshot_view(ingestor.twin, now, clock.effective_mode)
        inputs = news2_inputs(ingestor.twin, now)
    # Outside the lock: never hold up ingest while waiting on the inference layer.
    inference = app.state.inference
    attach_news2(snap, inference.news2_batch(snap["asOf"], inputs) if inference else None)
    with ingestor.lock:
        snap["alerts"] = derive_alerts(ingestor.twin, _news2_by_bed(snap["beds"]), now, app.state.call_config,
                                       app.state.first_seen)
    return snap


def build_beds(app: FastAPI, bed_ids: set[str] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Current view of some beds (None = all) with NEWS2, plus the alerts that apply to them."""
    ingestor = app.state.ingestor
    with ingestor.lock:
        now = ingestor.clock.now()
        beds = [b for b in ingestor.twin.beds.values() if bed_ids is None or b.bed in bed_ids]
        views = {"beds": [bed_view(b, now, ingestor.twin.assignments.get(b.bed)) for b in beds]}
        inputs = [i for i in news2_inputs(ingestor.twin, now) if bed_ids is None or i["bed"] in bed_ids]
        as_of = format_ts(now)
    inference = app.state.inference
    attach_news2(views, inference.news2_batch(as_of, inputs) if inference else None)
    with ingestor.lock:
        alerts = derive_alerts(ingestor.twin, _news2_by_bed(views["beds"]), now, app.state.call_config,
                               app.state.first_seen, bed_ids)
    return views["beds"], alerts


def build_calls(app: FastAPI, call_ids: set[str]) -> list[dict[str, Any]]:
    ingestor = app.state.ingestor
    with ingestor.lock:
        return [call_view(ingestor.twin.calls[c]) for c in call_ids if c in ingestor.twin.calls]


def build_staff(app: FastAPI, staff_ids: set[str]) -> list[dict[str, Any]]:
    ingestor = app.state.ingestor
    with ingestor.lock:
        return [staff_view(ingestor.twin.staff[s], ingestor.twin.assignments)
                for s in staff_ids if s in ingestor.twin.staff]


def news2_by_bed(app: FastAPI) -> dict[str, dict[str, Any] | None]:
    beds, _ = build_beds(app, None)
    return _news2_by_bed(beds)


def news2_total(app: FastAPI, bed_id: str) -> int | None:
    """Current NEWS2 total (a minimum if partial) for the call engine, or None if unavailable."""
    beds, _ = build_beds(app, {bed_id})
    news2 = beds[0]["news2"] if beds else None
    return news2["total"] if news2 else None
