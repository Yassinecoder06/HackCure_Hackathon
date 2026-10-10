"""REST routes. Only endpoints implemented so far; the rest of openapi.yaml lands phase by phase.

Every route that returns patient data requires a logged-in staff member and writes an audit
entry naming them (safety invariant 11).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..auth import AuthError, Principal, TooManyAttempts, require_role, require_staff
from ..scoring import attach_news2, news2_inputs
from ..timeutil import format_ts
from ..twin.views import snapshot_view, staff_view

router = APIRouter()
Staff = Annotated[Principal, Depends(require_staff)]


class LoginIn(BaseModel):
    staffId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    secret: str = Field(min_length=4, max_length=128)


def _check_ward(request: Request, ward: str) -> None:
    if ward != request.app.state.ingestor.layout.ward:
        raise HTTPException(404, {"error": "unknown_ward", "detail": ward})


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request) -> dict:
    store = request.app.state.ingestor.store
    try:
        token, expires = request.app.state.auth.login(body.staffId, body.secret)
    except TooManyAttempts as exc:
        store.audit(body.staffId, "auth.locked_out", body.staffId)
        raise HTTPException(429, {"error": "too_many_attempts", "detail": "try again later"}) from exc
    except AuthError as exc:
        store.audit(body.staffId, "auth.login_failed", body.staffId)
        raise HTTPException(401, {"error": "unauthorized", "detail": "invalid staff id or PIN"}) from exc
    store.audit(body.staffId, "auth.login", body.staffId)
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        staff = staff_view(ingestor.twin.staff[body.staffId])
    return {"token": token, "expiresAt": format_ts(expires), "staff": staff}


@router.get("/api/v1/wards/{ward}/snapshot")
def snapshot(ward: str, request: Request, who: Staff) -> dict:
    _check_ward(request, ward)
    ingestor = request.app.state.ingestor
    ingestor.store.audit(who.staff_id, "snapshot.read", ward)
    with ingestor.lock:
        clock = ingestor.clock
        now = clock.now()
        snap = snapshot_view(ingestor.twin, now, clock.effective_mode)
        inputs = news2_inputs(ingestor.twin, now)
    # Outside the lock: never hold up ingest while waiting on the inference layer.
    inference = request.app.state.inference
    attach_news2(snap, inference.news2_batch(snap["asOf"], inputs) if inference else None)
    return snap


@router.get("/api/v1/wards/{ward}/audit")
def audit_log(ward: str, request: Request, who: Staff, limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> list:
    _check_ward(request, ward)
    require_role(who, "charge_nurse")
    store = request.app.state.ingestor.store
    store.audit(who.staff_id, "audit.read", ward, {"limit": limit})
    return store.audit_entries(limit)


@router.get("/api/v1/wards/{ward}/audit/verify")
def audit_verify(ward: str, request: Request, who: Staff) -> dict:
    _check_ward(request, ward)
    require_role(who, "charge_nurse")
    store = request.app.state.ingestor.store
    result = store.verify_audit_chain()
    store.audit(who.staff_id, "audit.verify", ward, {"valid": result["valid"]})
    return result
