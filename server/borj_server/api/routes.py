"""REST routes. Only endpoints implemented so far; the rest of openapi.yaml lands phase by phase.

Every route that returns patient data requires a logged-in staff member and writes an audit
entry naming them (safety invariant 11).
"""

from __future__ import annotations

from typing import Annotated

import borj_contracts as bc
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field

from .. import stream
from ..auth import AuthError, Principal, TooManyAttempts, require_role, require_staff
from ..ids import new_ulid
from ..live import build_beds, build_snapshot, news2_by_bed
from ..timeutil import format_ts
from ..twin.views import call_view, staff_view

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
        staff = staff_view(ingestor.twin.staff[body.staffId], ingestor.twin.assignments)
    return {"token": token, "expiresAt": format_ts(expires), "staff": staff}


@router.get("/api/v1/wards/{ward}/snapshot")
def snapshot(ward: str, request: Request, who: Staff) -> dict:
    _check_ward(request, ward)
    request.app.state.ingestor.store.audit(who.staff_id, "snapshot.read", ward)
    return build_snapshot(request.app)


def _staff_ack(request: Request, who: Principal, target: str, target_id: str, action: str) -> None:
    """Record a staff action as an `ack` event: the authoritative record that a human acted."""
    ingestor = request.app.state.ingestor
    ward = ingestor.layout.ward
    payload = {
        "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(ingestor.event_now()), "ward": ward,
        "source": "staff-app", "sourceType": "staff_app", "staffId": who.staff_id,
        "target": target, "targetId": target_id, "action": action,
    }
    result = ingestor.handle(bc.topic("ack", ward, staff_id=who.staff_id), payload)
    if result.status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    ingestor.store.audit(who.staff_id, f"{target}.{action}", target_id)


def _call_or_404(request: Request, call_id: str):
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        call = ingestor.twin.calls.get(call_id)
    if call is None or call.state is None:
        raise HTTPException(404, {"error": "not_found", "detail": f"call {call_id}"})
    return call


@router.post("/api/v1/wards/{ward}/calls/{callId}/ack")
def ack_call(ward: str, callId: str, request: Request, who: Staff) -> dict:  # noqa: N803 (contract name)
    """One tap: someone is coming."""
    _check_ward(request, ward)
    call = _call_or_404(request, callId)
    if call.state == "resolved":
        raise HTTPException(409, {"error": "conflict", "detail": "call already resolved"})
    _staff_ack(request, who, "call", callId, "acknowledge")
    return call_view(_call_or_404(request, callId))


@router.post("/api/v1/wards/{ward}/calls/{callId}/resolve")
def resolve_call(ward: str, callId: str, request: Request, who: Staff) -> dict:  # noqa: N803
    _check_ward(request, ward)
    call = _call_or_404(request, callId)
    if call.state == "resolved":
        raise HTTPException(409, {"error": "conflict", "detail": "call already resolved"})
    _staff_ack(request, who, "call", callId, "resolve")
    return call_view(_call_or_404(request, callId))


@router.post("/api/v1/wards/{ward}/alerts/{alertId}/ack")
def ack_alert(ward: str, alertId: str, request: Request, who: Staff) -> dict:  # noqa: N803
    """Acknowledging silences a critical alarm; the alert stays listed while its condition lasts."""
    _check_ward(request, ward)
    _, alerts = build_beds(request.app, None)
    if not any(a["alertId"] == alertId for a in alerts):
        raise HTTPException(404, {"error": "not_found", "detail": f"no active alert {alertId}"})
    _staff_ack(request, who, "alert", alertId, "acknowledge")
    _, alerts = build_beds(request.app, None)
    return next(a for a in alerts if a["alertId"] == alertId)


class DisruptionIn(BaseModel):
    type: str = Field(pattern="^(staff_leaves|staff_joins|admissions|call_surge|route_comfort_to_assistants|"
                              "patient_deteriorates)$")
    atMin: int = Field(ge=0, le=720)
    staffId: str | None = None
    role: str | None = Field(default=None, pattern="^(nurse|care_assistant)$")
    count: int = Field(default=1, ge=1, le=20)
    bed: str | None = None
    callsPerHour: float | None = Field(default=None, ge=0, le=200)


class WhatIfIn(BaseModel):
    disruptions: list[DisruptionIn]
    horizonMin: int = Field(default=240, ge=30, le=720)
    seeds: int = Field(default=200, ge=10, le=2000)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str | None = Field(default=None, max_length=200)


def _suggestion_call(fn, *args):
    from ..assignment import SuggestionError

    try:
        return fn(*args)
    except SuggestionError as exc:
        raise HTTPException(exc.status, {"error": exc.error, "detail": exc.detail}) from exc


@router.get("/api/v1/wards/{ward}/assignments/suggestions")
def list_suggestions(ward: str, request: Request, who: Staff, status: str | None = None) -> list:
    _check_ward(request, ward)
    return request.app.state.assignment.list(status)


@router.post("/api/v1/wards/{ward}/assignments/suggestions", status_code=201)
def create_suggestion(ward: str, request: Request, who: Staff) -> dict:
    """Ask the optimiser now. Never applies anything: the result is a pending suggestion."""
    _check_ward(request, ward)
    return _suggestion_call(request.app.state.assignment.suggest, f"requested by {who.staff_id}")


@router.post("/api/v1/wards/{ward}/assignments/suggestions/{suggestionId}/decision")
def decide_suggestion(ward: str, suggestionId: str, body: DecisionIn, request: Request,  # noqa: N803
                      who: Staff) -> dict:
    """The only path that changes assignments: a charge nurse's decision (safety invariant 1)."""
    _check_ward(request, ward)
    require_role(who, "charge_nurse")
    return _suggestion_call(request.app.state.assignment.decide, suggestionId, body.decision, who.staff_id,
                            body.reason)


@router.post("/api/v1/wards/{ward}/whatif/runs")
def whatif_run(ward: str, body: WhatIfIn, request: Request, who: Staff) -> dict:
    """Simulate a copy of the current ward with disruptions; never touches live state."""
    _check_ward(request, ward)
    app = request.app
    news2 = news2_by_bed(app)
    ingestor = app.state.ingestor
    with ingestor.lock:
        twin = ingestor.twin
        on_ward = [s for s in twin.staff.values() if s.on_ward]
        roles = {s.staff_id: s.role for s in twin.staff.values()}
        beds = [(b.bed, (news2.get(b.bed) or {}).get("band", "low")) for b in twin.beds.values() if b.admission]
        uncertain = sum(1 for b in twin.beds.values()
                        if b.admission and not (news2.get(b.bed) or {}).get("complete"))
    disruptions = []
    for d in body.disruptions:
        role = d.role or (roles.get(d.staffId) if d.staffId else None) or "nurse"
        if role not in ("nurse", "care_assistant"):
            raise HTTPException(422, {"error": "invalid", "detail": f"{d.staffId} is not a nurse or care assistant"})
        disruptions.append({"type": d.type, "atMin": d.atMin, "role": role, "count": d.count, "bed": d.bed,
                            "callsPerHour": d.callsPerHour})
    payload = {
        "ward": {"nurses": sum(1 for s in on_ward if s.role == "nurse"),
                 "careAssistants": sum(1 for s in on_ward if s.role == "care_assistant"), "beds": beds},
        "disruptions": disruptions, "horizonMin": body.horizonMin, "seeds": body.seeds,
    }
    inference = app.state.inference
    result = inference.whatif(payload) if inference else None
    if result is None:
        raise HTTPException(503, {"error": "inference_unavailable", "detail": "inference layer unreachable"})
    if uncertain:
        result["assumptions"].append(f"{uncertain} bed(s) have no complete NEWS2: simulated with their minimum "
                                     "band (or low risk if unavailable), so their workload may be underestimated.")
    result["runId"] = f"W-{new_ulid()[:16]}"
    ingestor.store.audit(who.staff_id, "whatif.run", result["runId"],
                         {"disruptions": disruptions, "seeds": body.seeds, "horizonMin": body.horizonMin})
    return result


@router.websocket("/api/v1/wards/{ward}/stream")
async def live_stream(websocket: WebSocket, ward: str) -> None:
    """Token offered as subprotocols ["bearer", "<token>"] (see stream.py)."""
    settings = websocket.app.state.settings
    await stream.serve(websocket, websocket.app, ward, settings.stream_metrics_interval_s,
                       settings.stream_refresh_interval_s)


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
