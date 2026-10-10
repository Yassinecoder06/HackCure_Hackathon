"""REST routes. Only endpoints implemented so far; the rest of openapi.yaml lands phase by phase."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
        return snapshot_view(ingestor.twin, clock.now(), clock.effective_mode)
