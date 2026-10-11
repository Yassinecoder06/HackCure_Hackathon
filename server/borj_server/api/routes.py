"""REST routes. Only endpoints implemented so far; the rest of openapi.yaml lands phase by phase.

Every route that returns patient data requires a logged-in staff member and writes an audit
entry naming them (safety invariant 11).
"""

from __future__ import annotations

import logging
from typing import Annotated

import borj_contracts as bc
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field

from .. import stream
from ..assignment import render as render_suggestion
from ..auth import AuthError, Principal, TooManyAttempts, require_role, require_staff
from ..explain import Explainer, pick_lang
from ..ids import new_ulid
from ..live import build_beds, build_snapshot, news2_by_bed
from ..meds import timeline
from ..observations import manual_vitals
from ..timeutil import format_ts
from ..twin.views import call_view, staff_view

log = logging.getLogger(__name__)
router = APIRouter()
Staff = Annotated[Principal, Depends(require_staff)]


class LoginIn(BaseModel):
    staffId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    secret: str = Field(min_length=4, max_length=128)


def explainer(request: Request) -> Explainer:
    """Language from ?lang=, then Accept-Language, then the server default."""
    lang = pick_lang(request.query_params.get("lang"), request.headers.get("accept-language"),
                     default=request.app.state.settings.default_lang)
    return Explainer(lang, request.app.state.meds_config.ward_tz)


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
    return build_snapshot(request.app, explainer(request))


def _staff_ack(request: Request, who: Principal, target: str, target_id: str, action: str,
               note: str | None = None) -> None:
    """Record a staff action as an `ack` event: the authoritative record that a human acted."""
    ingestor = request.app.state.ingestor
    ward = ingestor.layout.ward
    payload = {
        "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(ingestor.event_now()), "ward": ward,
        "source": "staff-app", "sourceType": "staff_app", "staffId": who.staff_id,
        "target": target, "targetId": target_id, "action": action,
        **({"note": note} if note else {}),
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
    _, alerts = build_beds(request.app, None, explainer(request))
    return next(a for a in alerts if a["alertId"] == alertId)


class PrescriptionIn(BaseModel):
    admissionId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    drug: str = Field(min_length=1, max_length=80)
    dose: str = Field(min_length=1, max_length=40)
    route: str = Field(pattern="^(oral|iv|im|sc|inhaled|topical|other)$")
    times: list[str] = Field(min_length=1)
    startDate: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    endDate: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    isInfusion: bool = False


class AdministrationIn(BaseModel):
    action: str = Field(pattern="^(given|not_given)$")
    presence: str = Field(pattern="^(badge_tap|wristband_scan|none)$")
    reason: str | None = Field(default=None, max_length=200)


class InstructionIn(BaseModel):
    text: str = Field(min_length=1, max_length=280)


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


class StaffPresenceIn(BaseModel):
    onWard: bool
    reason: str = Field(pattern="^(shift_start|shift_end|called_away|returned|break_start|break_end)$")
    expectedBackMin: int | None = Field(default=None, ge=0, le=720)


class DoctorOrderIn(BaseModel):
    bed: str = Field(pattern=r"^[A-Za-z0-9_-]{1,16}$")
    orderText: str = Field(min_length=1, max_length=500)


def _suggestion_call(fn, *args):
    from ..assignment import SuggestionError

    try:
        return fn(*args)
    except SuggestionError as exc:
        raise HTTPException(exc.status, {"error": exc.error, "detail": exc.detail}) from exc


@router.get("/api/v1/wards/{ward}/assignments/suggestions")
def list_suggestions(ward: str, request: Request, who: Staff, status: str | None = None) -> list:
    _check_ward(request, ward)
    ex = explainer(request)
    return [render_suggestion(s, ex) for s in request.app.state.assignment.list(status)]


@router.post("/api/v1/wards/{ward}/assignments/suggestions", status_code=201)
def create_suggestion(ward: str, request: Request, who: Staff) -> dict:
    """Ask the optimiser now. Never applies anything: the result is a pending suggestion."""
    _check_ward(request, ward)
    suggestion = _suggestion_call(request.app.state.assignment.suggest, f"requested by {who.staff_id}")
    return render_suggestion(suggestion, explainer(request))


@router.post("/api/v1/wards/{ward}/assignments/suggestions/{suggestionId}/decision")
def decide_suggestion(ward: str, suggestionId: str, body: DecisionIn, request: Request,  # noqa: N803
                      who: Staff) -> dict:
    """The only path that changes assignments: a charge nurse's decision (safety invariant 1)."""
    _check_ward(request, ward)
    require_role(who, "charge_nurse")
    decided = _suggestion_call(request.app.state.assignment.decide, suggestionId, body.decision, who.staff_id,
                               body.reason)
    return render_suggestion(decided, explainer(request))


class ObservationIn(BaseModel):
    """contracts/openapi.yaml ManualObservation: only what the nurse entered, never defaults."""
    model_config = {"extra": "forbid"}
    resp_rate: int | None = Field(default=None, ge=0, le=100)
    spo2: int | None = Field(default=None, ge=0, le=100)
    on_oxygen: bool | None = None
    sys_bp: int | None = Field(default=None, ge=0, le=300)
    pulse: int | None = Field(default=None, ge=0, le=300)
    consciousness: str | None = Field(default=None, pattern="^[ACVPU]$")
    temp_c: float | None = Field(default=None, ge=20, le=45)


@router.post("/api/v1/wards/{ward}/beds/{bed}/observations", status_code=201)
def record_observations(ward: str, bed: str, body: ObservationIn, request: Request, who: Staff) -> dict:
    """The 10-second form: a `vitals` event with sourceType manual and the nurse's staff id."""
    _check_ward(request, ward)
    cfg = request.app.state.observations_config
    require_role(who, *cfg.roles)
    params = body.model_dump(exclude_none=True)  # absent stays absent (safety invariant 5)
    if not params:
        raise HTTPException(422, {"error": "invalid", "detail": "enter at least one observation"})
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        known = ingestor.twin.beds.get(bed)
        admitted = known is not None and known.admission is not None
    if known is None:
        raise HTTPException(404, {"error": "not_found", "detail": f"no bed {bed}"})
    if not admitted:
        raise HTTPException(409, {"error": "conflict", "detail": f"no patient admitted in {bed}"})
    payload = manual_vitals(new_ulid(), format_ts(ingestor.event_now()), ward, bed, who.staff_id, params, cfg)
    result = ingestor.handle(bc.topic("vitals", ward, bed=bed), payload)
    if result.status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    ingestor.store.audit(who.staff_id, "vitals.manual_entry", bed, {"params": sorted(params)})
    return {"eventId": payload["eventId"]}


@router.post("/api/v1/wards/{ward}/prescriptions", status_code=201)
def create_prescription(ward: str, body: PrescriptionIn, request: Request, who: Staff) -> dict:
    """A doctor enters a prescription. The system schedules and reminds from it; it never chooses
    drugs or doses, and it never creates or changes a prescription itself (safety invariant 1)."""
    _check_ward(request, ward)
    require_role(who, "doctor")
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        bed = next((b.bed for b in ingestor.twin.beds.values()
                    if b.admission and b.admission.admission_id == body.admissionId), None)
    if bed is None:
        raise HTTPException(409, {"error": "conflict", "detail": f"admission {body.admissionId} is not in a bed"})
    payload = {
        "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(ingestor.event_now()), "ward": ward, "bed": bed,
        "source": "staff-app", "sourceType": "staff_app", "prescriptionId": f"RX-{new_ulid()[:12]}",
        "prescribedBy": who.staff_id, **body.model_dump(exclude_none=True),
    }
    # Stored in the encrypted event log only: never published on MQTT (it contains drug names).
    result = ingestor.handle(bc.topic("prescription", ward, bed=bed), payload)
    if result.status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    ingestor.store.audit(who.staff_id, "prescription.created", payload["prescriptionId"], {"bed": bed})
    with ingestor.lock:
        doses = [d for d in timeline(ingestor.twin, ingestor.clock.now(), request.app.state.meds_config, 24)["doses"]
                 if d["doseId"].startswith(f"D-{payload['prescriptionId'][:20]}-")]
    return {**body.model_dump(exclude_none=True), "prescriptionId": payload["prescriptionId"],
            "prescribedBy": who.staff_id, "doses": doses}


@router.get("/api/v1/wards/{ward}/meds/timeline")
def meds_timeline(ward: str, request: Request, who: Staff,
                  hours: Annotated[int, Query(ge=1, le=48)] = 8) -> dict:
    _check_ward(request, ward)
    ingestor = request.app.state.ingestor
    ingestor.store.audit(who.staff_id, "meds.read", ward, {"hours": hours})
    with ingestor.lock:
        return timeline(ingestor.twin, ingestor.clock.now(), request.app.state.meds_config, hours,
                        explainer(request))


@router.post("/api/v1/wards/{ward}/doses/{doseId}/administration")
def record_administration(ward: str, doseId: str, body: AdministrationIn, request: Request,  # noqa: N803
                          who: Staff) -> dict:
    """The nurse's tap is the administration record (whitepaper 4.3)."""
    _check_ward(request, ward)
    require_role(who, "nurse", "charge_nurse")
    if body.action == "not_given" and not body.reason:
        raise HTTPException(422, {"error": "invalid", "detail": "a reason is required for not_given"})
    ingestor = request.app.state.ingestor
    cfg = request.app.state.meds_config
    with ingestor.lock:
        doses = timeline(ingestor.twin, ingestor.clock.now(), cfg, 24)["doses"]
    dose = next((d for d in doses if d["doseId"] == doseId), None)
    if dose is None:
        raise HTTPException(404, {"error": "not_found", "detail": f"no scheduled dose {doseId}"})
    if dose["status"] in ("given", "not_given"):
        raise HTTPException(409, {"error": "conflict", "detail": f"dose already recorded as {dose['status']}"})
    payload = {
        "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(ingestor.event_now()), "ward": ward,
        "bed": dose["bed"], "source": "staff-app", "sourceType": "staff_app", "admissionId": dose["admissionId"],
        "doseId": doseId, "action": body.action, "recordedBy": "nurse", "staffId": who.staff_id,
        "presence": body.presence, **({"reason": body.reason} if body.reason else {}),
    }
    result = ingestor.handle(bc.topic("med", ward, bed=dose["bed"]), payload)
    if result.status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    ingestor.store.audit(who.staff_id, f"dose.{body.action}", doseId)
    with ingestor.lock:
        updated = timeline(ingestor.twin, ingestor.clock.now(), cfg, 24)["doses"]
    return next(d for d in updated if d["doseId"] == doseId)


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
    ex = explainer(request)
    result["assumptions"] = ex.items(result.pop("assumptionItems"))
    if uncertain:
        result["assumptions"].append(ex.say("whatif.partial_news2", count=uncertain))
    result["runId"] = f"W-{new_ulid()[:16]}"
    ingestor.store.audit(who.staff_id, "whatif.run", result["runId"],
                         {"disruptions": disruptions, "seeds": body.seeds, "horizonMin": body.horizonMin})
    return result


@router.post("/api/v1/wards/{ward}/alerts/{alertId}/instructions")
def instruct_alert(ward: str, alertId: str, body: InstructionIn, request: Request, who: Staff) -> dict:  # noqa: N803
    """The remote on-call doctor answers an escalation with a short instruction (telemedicine, ADR 0008).
    Works asynchronously: the doctor's app queues it while offline and sends it on reconnect."""
    _check_ward(request, ward)
    require_role(who, "doctor")
    _, alerts = build_beds(request.app, None)
    if not any(a["alertId"] == alertId for a in alerts):
        raise HTTPException(404, {"error": "not_found", "detail": f"no active alert {alertId}"})
    _staff_ack(request, who, "alert", alertId, "instruct", note=body.text)
    _, alerts = build_beds(request.app, None, explainer(request))
    return next(a for a in alerts if a["alertId"] == alertId)


@router.post("/api/v1/wards/{ward}/staff/{staffId}/presence", status_code=201)
def update_staff_presence(ward: str, staffId: str, body: StaffPresenceIn, request: Request, who: Staff) -> dict:  # noqa: N803
    """Availability only, not location tracking (contracts/openapi.yaml). Publishes staff-presence."""
    _check_ward(request, ward)
    if who.staff_id != staffId:
        require_role(who, "charge_nurse")  # you can mark yourself; only the charge nurse can mark others
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        if staffId not in ingestor.twin.staff:
            raise HTTPException(404, {"error": "not_found", "detail": f"unknown staff member {staffId}"})
    payload = {
        "schemaVersion": 1,
        "eventId": new_ulid(),
        "ts": format_ts(ingestor.event_now()),
        "ward": ward,
        "source": "staff-app",
        "sourceType": "staff_app",
        "staffId": staffId,
        "onWard": body.onWard,
        "reason": body.reason,
        **({"expectedBackMin": body.expectedBackMin} if body.expectedBackMin is not None else {}),
    }
    result = ingestor.handle(bc.topic("staff-presence", ward, staff_id=staffId), payload)
    if result.status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    ingestor.store.audit(
        who.staff_id, "staff.presence_updated", staffId, {"onWard": body.onWard, "reason": body.reason}
    )
    return {"eventId": payload["eventId"]}


def _order_view(order, twin) -> dict:
    doctor = twin.staff.get(order.doctor_id)
    return {"orderId": order.order_id, "bed": order.bed, "orderText": order.text, "doctorId": order.doctor_id,
            "doctorName": doctor.name if doctor else order.doctor_id, "createdAt": format_ts(order.ts)}


@router.get("/api/v1/wards/{ward}/doctor/orders")
def list_doctor_orders(ward: str, request: Request, who: Staff) -> list:
    _check_ward(request, ward)
    ingestor = request.app.state.ingestor
    ingestor.store.audit(who.staff_id, "doctor.orders_read", ward)  # a read of patient data (invariant 11)
    with ingestor.lock:
        newest_first = sorted(ingestor.twin.doctor_orders.values(), key=lambda o: o.ts, reverse=True)
        return [_order_view(o, ingestor.twin) for o in newest_first]


@router.post("/api/v1/wards/{ward}/doctor/orders", status_code=201)
def create_doctor_order(ward: str, body: DoctorOrderIn, request: Request, who: Staff) -> dict:
    """The remote doctor's order: a durable, encrypted `order` event. A message to the nurses only; it never
    changes a prescription, an assignment or a score (safety invariant 1)."""
    _check_ward(request, ward)
    require_role(who, "doctor")
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        known = ingestor.twin.beds.get(body.bed)
        admission = known.admission if known else None
    if known is None:
        raise HTTPException(404, {"error": "not_found", "detail": f"no bed {body.bed}"})
    if admission is None:
        raise HTTPException(409, {"error": "conflict", "detail": f"no patient admitted in {body.bed}"})
    payload = {
        "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(ingestor.event_now()), "ward": ward,
        "bed": body.bed, "source": "staff-app", "sourceType": "staff_app", "admissionId": admission.admission_id,
        "orderId": f"ORD-{new_ulid()}", "doctorId": who.staff_id, "orderText": body.orderText,
    }
    result = ingestor.handle(bc.topic("doctor-order", ward, bed=body.bed), payload)
    if result.status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    ingestor.store.audit(who.staff_id, "doctor.order_created", payload["orderId"], {"bed": body.bed})

    # If the bed has an active alert, the nurses also see the order on it (as the doctor's instruction).
    _, alerts = build_beds(request.app, None)
    for a in (a for a in alerts if a.get("bed") == body.bed):
        try:
            _staff_ack(request, who, "alert", a["alertId"], "instruct", note=body.orderText[:280])
        except HTTPException as exc:
            log.warning("order not attached to alert %s: %s", a["alertId"], exc.detail)
    with ingestor.lock:
        return _order_view(ingestor.twin.doctor_orders[payload["orderId"]], ingestor.twin)


@router.post("/api/v1/demo/trigger-peak")
def trigger_demo_peak(request: Request, who: Staff) -> dict:
    """Helper for the live demo: deteriorate B06 and press an assist call. Off unless BORJ_DEMO_ENDPOINTS=1,
    charge nurse only, and the audit log says it was a demo trigger, not a clinical entry."""
    if not request.app.state.settings.demo_endpoints:
        raise HTTPException(404, {"error": "not_found", "detail": "demo endpoints are disabled"})
    require_role(who, "charge_nurse")
    ingestor = request.app.state.ingestor
    ward = ingestor.layout.ward
    bed = "B06"
    with ingestor.lock:
        target = ingestor.twin.beds.get(bed)
        if target is None or target.admission is None:
            raise HTTPException(409, {"error": "conflict", "detail": f"no patient admitted in {bed}"})
    ingestor.store.audit(who.staff_id, "demo.trigger_peak", bed, {"synthetic": True})
    acute_vitals = {
        "temp_c": 39.2,
        "resp_rate": 26,
        "pulse": 118,
        "spo2": 91,
        "consciousness": "V",
        "on_oxygen": True,
    }
    cfg = request.app.state.observations_config
    payload = manual_vitals(new_ulid(), format_ts(ingestor.event_now()), ward, bed, who.staff_id, acute_vitals, cfg)
    if (result := ingestor.handle(bc.topic("vitals", ward, bed=bed), payload)).status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})

    call_payload = {
        "schemaVersion": 1,
        "eventId": new_ulid(),
        "ts": format_ts(ingestor.event_now()),
        "tsSource": "server",
        "ward": ward,
        "bed": bed,
        "source": f"node-{bed}",
        "sourceType": "bedside_node",
        "callId": f"C-{bed}-{new_ulid()[-6:]}",  # the random end of the ULID: the start is the same for hours
        "kind": "assist",
        "pressCount": 2,
    }
    if (result := ingestor.handle(bc.topic("call", ward, bed=bed), call_payload)).status != "accepted":
        raise HTTPException(422, {"error": "rejected", "detail": result.detail})
    return {"status": "ok", "message": "Deterioration and assist escalation simulated on Bed B06"}


class LLMExplainIn(BaseModel):
    model_config = {"extra": "forbid"}
    question: str | None = None
    lang: str | None = None


@router.get("/api/v1/wards/{ward}/beds/{bed}/explain/llm")
def explain_bed_llm(ward: str, bed: str, request: Request, who: Staff, question: str | None = None,
                    lang: str | None = None) -> dict:
    """Grounded clinical explanation via local Gemma 4 QAT model (ADR 0013)."""
    _check_ward(request, ward)
    lang_code = lang or explainer(request).lang
    beds, alerts = build_beds(request.app, {bed}, explainer(request))
    if not beds:
        raise HTTPException(404, {"error": "not_found", "detail": f"unknown bed {bed}"})
    bed_data = beds[0]
    ingestor = request.app.state.ingestor
    with ingestor.lock:
        twin_bed = ingestor.twin.beds.get(bed)
        admission = None
        if twin_bed and twin_bed.admission:
            adm = twin_bed.admission
            admission = {"admissionId": adm.admission_id, "patientName": adm.patient_ref, "acuity": adm.acuity}
        nurse_id = ingestor.twin.assignments.get(bed)
        nurse = ingestor.twin.staff.get(nurse_id) if nurse_id else None
        nurse_name = nurse.name if nurse else None

    bed_alerts = [a for a in alerts if a.get("bed") == bed]
    explainer_service = getattr(request.app.state, "llm_explainer", None)
    if not explainer_service:
        from ..llm_explainer import GroundedExplainer
        explainer_service = GroundedExplainer(
            request.app.state.settings.ollama_url,
            request.app.state.settings.llm_model,
        )
    result = explainer_service.explain_bed(
        bed_id=bed,
        bed=bed_data,
        admission=admission,
        alerts=bed_alerts,
        nurse_id=nurse_id,
        nurse_name=nurse_name,
        question=question,
        lang=lang_code,
    )
    ingestor.store.audit(who.staff_id, "bed.explain_llm", bed,
                         {"question": question, "verified": result.get("verified")})
    return result


@router.post("/api/v1/wards/{ward}/beds/{bed}/explain/llm")
def explain_bed_llm_post(ward: str, bed: str, body: LLMExplainIn, request: Request, who: Staff) -> dict:
    return explain_bed_llm(ward, bed, request, who, question=body.question, lang=body.lang)


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
