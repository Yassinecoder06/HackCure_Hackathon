"""Apply one validated contract event to the twin.

Handlers are idempotent in effect and tolerant of out-of-order arrival: every update is
guarded by the event's own `ts`, so replaying or re-ordering the log gives the same twin.
Returns a short outcome string for logging and tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..timeutil import parse_ts
from .state import Administration, Admission, AlertAck, Bed, Call, Device, Prescription, Reading, WardTwin

log = logging.getLogger(__name__)

ADMIT_ACTIONS = {"admit", "transfer_in"}
LEAVE_ACTIONS = {"discharge", "transfer_out"}
PRESENCE_ON_WARD = {"shift_start": True, "returned": True, "break_end": True,
                    "called_away": False, "break_start": False, "shift_end": False}

# Default baseline acuity when the nurse did not set one at admission. Input to assignment (P3).
DEFAULT_ACUITY = 1


def _bed(twin: WardTwin, payload: dict[str, Any]) -> Bed | None:
    bed = twin.beds.get(payload["bed"])
    if bed is None:
        log.warning("event %s for unknown bed %s ignored", payload["eventId"], payload["bed"])
    return bed


def apply_binding(twin: WardTwin, payload: dict[str, Any]) -> str:
    bed = _bed(twin, payload)
    if bed is None:
        return "ignored:unknown_bed"
    ts = parse_ts(payload["ts"])
    action = payload["action"]

    if action in {"attach_device", "detach_device"}:
        device_id = payload.get("deviceId")
        if not device_id:
            return "ignored:no_device"
        if action == "detach_device":
            bed.devices.pop(device_id, None)
        else:
            bed.devices.setdefault(device_id, Device(device_id, "unknown", "ok", ts))
        return "applied"

    if bed.binding_ts is not None and ts < bed.binding_ts:
        return "ignored:older_than_current_binding"
    if action in LEAVE_ACTIONS and (bed.admission is None or bed.admission.admission_id != payload["admissionId"]):
        # E.g. a late discharge of the previous patient: it must not touch the current patient.
        return "ignored:not_current_admission"

    bed.binding_ts = ts
    # A new or departing patient must never inherit the previous patient's readings.
    bed.vitals.clear()
    if action in ADMIT_ACTIONS:
        bed.admission = Admission(
            admission_id=payload["admissionId"],
            patient_ref=payload.get("patientRef", payload["admissionId"]),
            acuity=payload.get("acuity", DEFAULT_ACUITY),
            admitted_at=ts,
        )
    else:
        bed.admission = None
        twin.assignments.pop(bed.bed, None)  # an empty bed needs no nurse
    return "applied"


def apply_vitals(twin: WardTwin, payload: dict[str, Any]) -> str:
    bed = _bed(twin, payload)
    if bed is None:
        return "ignored:unknown_bed"
    ts = parse_ts(payload["ts"])
    if bed.admission is None or ts < bed.admission.admitted_at:
        # Data must be tied to a patient by a binding (wristband scan) before it counts.
        return "ignored:no_admission_at_ts"

    quality = payload["quality"]
    flags = tuple(quality.get("flags", ()))
    updated = 0
    for param, value in payload["params"].items():
        current = bed.vitals.get(param)
        if current is not None and ts < current.ts:
            continue  # a newer reading already exists
        bed.vitals[param] = Reading(value, ts, payload["sourceType"], quality["valid"], quality["stale_after_s"], flags)
        updated += 1

    device_id = payload.get("deviceId")
    if device_id:
        device = bed.devices.get(device_id)
        if device is None:
            bed.devices[device_id] = Device(device_id, "unknown", "ok", ts)
        elif ts > device.last_seen:
            device.last_seen = ts
    return "applied" if updated else "ignored:older_than_current_readings"


def apply_device_status(twin: WardTwin, payload: dict[str, Any]) -> str:
    bed = _bed(twin, payload)
    if bed is None:
        return "ignored:unknown_bed"
    ts = parse_ts(payload["ts"])
    device = bed.devices.get(payload["deviceId"])
    if device is not None and ts < device.last_seen:
        return "ignored:older_than_current_status"
    bed.devices[payload["deviceId"]] = Device(payload["deviceId"], payload["deviceType"], payload["status"], ts)
    return "applied"


def apply_staff_presence(twin: WardTwin, payload: dict[str, Any]) -> str:
    member = twin.staff.get(payload["staffId"])
    if member is None:
        log.warning("presence for unknown staff %s ignored", payload["staffId"])
        return "ignored:unknown_staff"
    ts = parse_ts(payload["ts"])
    if member.presence_ts is not None and ts < member.presence_ts:
        return "ignored:older_than_current_presence"
    member.presence_ts = ts
    reason = payload["reason"]
    member.on_ward = payload["onWard"]
    if reason == "shift_start":
        member.on_shift = True
    elif reason == "shift_end":
        member.on_shift = False
    elif not member.on_shift and PRESENCE_ON_WARD.get(reason, False):
        member.on_shift = True
    return "applied"


def apply_call(twin: WardTwin, payload: dict[str, Any]) -> str:
    """A press from the bedside node: facts only. Whether it escalates is the call engine's decision."""
    if _bed(twin, payload) is None:
        return "ignored:unknown_bed"
    ts = parse_ts(payload["ts"])
    call = twin.calls.get(payload["callId"])
    if call is None:
        twin.calls[payload["callId"]] = Call(
            call_id=payload["callId"], bed=payload["bed"], kind=payload["kind"], pressed_at=ts,
            press_count=payload["pressCount"], delivered_late=bool(payload.get("deliveredLate")),
        )
        return "applied"
    call.press_count = max(call.press_count, payload["pressCount"])
    call.pressed_at = min(call.pressed_at, ts)
    call.delivered_late = call.delivered_late or bool(payload.get("deliveredLate"))
    return "applied"


def apply_call_state(twin: WardTwin, payload: dict[str, Any]) -> str:
    ts = parse_ts(payload["ts"])
    call = twin.calls.get(payload["callId"])
    if call is None:  # state without a stored press (should not happen): keep what the server decided
        call = twin.calls[payload["callId"]] = Call(
            call_id=payload["callId"], bed=payload["bed"], kind=payload["kind"],
            pressed_at=parse_ts(payload.get("pressedAt", payload["ts"])),
        )
    if call.state_ts is not None and ts < call.state_ts:
        return "ignored:older_than_current_state"
    call.state = payload["state"]
    call.state_ts = ts
    call.escalation_level = payload["escalationLevel"]
    call.escalation_reason = payload.get("escalationReason", call.escalation_reason)
    call.routed_to_role = payload.get("routedToRole", call.routed_to_role)
    if payload["state"] == "acknowledged":
        call.acknowledged_by = payload.get("acknowledgedBy")
        call.acknowledged_at = ts
    return "applied"


def apply_assignment(twin: WardTwin, payload: dict[str, Any]) -> str:
    """An approved suggestion: the only way assignments change (safety invariant 1)."""
    for change in payload["changes"]:
        if change["bed"] in twin.beds and change["toStaffId"] in twin.staff:
            twin.assignments[change["bed"]] = change["toStaffId"]
    return "applied"


def apply_prescription(twin: WardTwin, payload: dict[str, Any]) -> str:
    if _bed(twin, payload) is None:
        return "ignored:unknown_bed"
    twin.prescriptions[payload["prescriptionId"]] = Prescription(
        prescription_id=payload["prescriptionId"], admission_id=payload["admissionId"], bed=payload["bed"],
        drug=payload["drug"], dose=payload["dose"], route=payload["route"], times=tuple(payload["times"]),
        start_date=payload["startDate"], end_date=payload.get("endDate"),
        is_infusion=bool(payload.get("isInfusion")), prescribed_by=payload["prescribedBy"],
    )
    return "applied"


def apply_med(twin: WardTwin, payload: dict[str, Any]) -> str:
    """Only a nurse's record closes a dose; a patient's report is kept apart (whitepaper 4.3)."""
    ts = parse_ts(payload["ts"])
    if payload["recordedBy"] == "patient_reported":
        twin.patient_reported.setdefault(payload["doseId"], ts)
        return "applied"
    current = twin.administrations.get(payload["doseId"])
    if current is not None and ts < current.ts:
        return "ignored:older_than_current_record"
    twin.administrations[payload["doseId"]] = Administration(
        payload["action"], payload["staffId"], ts, payload.get("presence"), payload.get("reason"))
    return "applied"


def apply_ack(twin: WardTwin, payload: dict[str, Any]) -> str:
    """Acks on alerts are recorded here. Acks on calls are turned into call/state by the call engine."""
    if payload["target"] != "alert" or payload["action"] != "acknowledge":
        return "stored_only"
    twin.alert_acks.setdefault(payload["targetId"], AlertAck(payload["staffId"], parse_ts(payload["ts"])))
    return "applied"


HANDLERS: dict[str, Callable[[WardTwin, dict[str, Any]], str]] = {
    "binding": apply_binding,
    "vitals": apply_vitals,
    "device-status": apply_device_status,
    "staff-presence": apply_staff_presence,
    "call": apply_call,
    "call-state": apply_call_state,
    "ack": apply_ack,
    "assignment": apply_assignment,
    "prescription": apply_prescription,
    "med": apply_med,
}


def apply(twin: WardTwin, schema: str, payload: dict[str, Any]) -> str:
    handler = HANDLERS.get(schema)
    if handler is None:
        return "stored_only"
    return handler(twin, payload)
