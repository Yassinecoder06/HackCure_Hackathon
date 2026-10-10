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
from .state import Admission, Bed, Device, Reading, WardTwin

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
    elif action in LEAVE_ACTIONS:
        if bed.admission is not None and bed.admission.admission_id == payload["admissionId"]:
            bed.admission = None
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


HANDLERS: dict[str, Callable[[WardTwin, dict[str, Any]], str]] = {
    "binding": apply_binding,
    "vitals": apply_vitals,
    "device-status": apply_device_status,
    "staff-presence": apply_staff_presence,
    # call, call-state, ack, med: stored now, handled by the call engine (P2) and meds engine (P3).
}


def apply(twin: WardTwin, schema: str, payload: dict[str, Any]) -> str:
    handler = HANDLERS.get(schema)
    if handler is None:
        return "stored_only"
    return handler(twin, payload)
