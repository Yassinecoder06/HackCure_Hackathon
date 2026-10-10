"""REST routes. Only endpoints implemented so far; the rest of openapi.yaml lands phase by phase."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..scoring import attach_news2, news2_inputs
from ..twin.views import snapshot_view

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/v1/wards/{ward}/snapshot")
def snapshot(ward: str, request: Request) -> dict:
    ingestor = request.app.state.ingestor
    if ward != ingestor.layout.ward:
        raise HTTPException(status_code=404, detail={"error": "unknown_ward", "detail": ward})
    with ingestor.lock:
        clock = ingestor.clock
        now = clock.now()
        snap = snapshot_view(ingestor.twin, now, clock.effective_mode)
        inputs = news2_inputs(ingestor.twin, now)
    # Outside the lock: never hold up ingest while waiting on the inference layer.
    inference = request.app.state.inference
    attach_news2(snap, inference.news2_batch(snap["asOf"], inputs) if inference else None)
    return snap
