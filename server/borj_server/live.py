"""Building ward views with NEWS2 attached, shared by the REST snapshot and the live stream."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .scoring import attach_news2, news2_inputs
from .timeutil import format_ts
from .twin.views import bed_view, snapshot_view, staff_view


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
    return snap


def build_beds(app: FastAPI, bed_ids: set[str] | None) -> list[dict[str, Any]]:
    """Current view of some beds (None = all), NEWS2 included."""
    ingestor = app.state.ingestor
    with ingestor.lock:
        now = ingestor.clock.now()
        beds = [b for b in ingestor.twin.beds.values() if bed_ids is None or b.bed in bed_ids]
        views = {"beds": [bed_view(b, now) for b in beds]}
        inputs = [i for i in news2_inputs(ingestor.twin, now) if bed_ids is None or i["bed"] in bed_ids]
        as_of = format_ts(now)
    inference = app.state.inference
    attach_news2(views, inference.news2_batch(as_of, inputs) if inference else None)
    return views["beds"]


def build_staff(app: FastAPI, staff_ids: set[str]) -> list[dict[str, Any]]:
    ingestor = app.state.ingestor
    with ingestor.lock:
        return [staff_view(ingestor.twin.staff[s]) for s in staff_ids if s in ingestor.twin.staff]
