"""Serialise the twin into the API shapes defined in contracts/openapi.yaml.

Freshness is computed here, against the ward clock, so that stale or invalid readings are
always labelled as such and never presented as normal values (safety invariant 5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..timeutil import format_ts
from .state import Bed, Call, Reading, StaffMember, WardTwin


def reading_status(reading: Reading, now: datetime) -> str:
    if not reading.valid:
        return "invalid"
    age_s = (now - reading.ts).total_seconds()
    return "stale" if age_s > reading.stale_after_s else "fresh"


def reading_view(reading: Reading, now: datetime) -> dict[str, Any]:
    return {
        "value": reading.value,
        "ts": format_ts(reading.ts),
        "ageS": max(0, int((now - reading.ts).total_seconds())),
        "status": reading_status(reading, now),
        "sourceType": reading.source_type,
    }


def bed_view(bed: Bed, now: datetime, assigned_nurse: str | None = None) -> dict[str, Any]:
    view: dict[str, Any] = {
        "bed": bed.bed,
        "room": bed.room,
        "admission": None,
        "news2": None,  # filled from the inference layer by scoring.attach_news2
        "news2Status": "not_admitted" if bed.admission is None else "unavailable",
        "vitals": {param: reading_view(r, now) for param, r in sorted(bed.vitals.items())},
        "devices": [
            {"deviceId": d.device_id, "deviceType": d.device_type, "status": d.status,
             "lastSeen": format_ts(d.last_seen)}
            for d in sorted(bed.devices.values(), key=lambda d: d.device_id)
        ],
    }
    if assigned_nurse:
        view["assignedNurse"] = assigned_nurse
    if bed.admission is not None:
        view["admission"] = {
            "admissionId": bed.admission.admission_id,
            "patientRef": bed.admission.patient_ref,
            "acuity": bed.admission.acuity,
            "admittedAt": format_ts(bed.admission.admitted_at),
        }
    return view


def staff_view(member: StaffMember, assignments: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "staffId": member.staff_id,
        "displayName": member.name,
        "role": member.role,
        "skills": list(member.skills),
        "onShift": member.on_shift,
        "onWard": member.on_ward,
        "assignedBeds": sorted(b for b, n in (assignments or {}).items() if n == member.staff_id),
    }


def call_view(call: Call) -> dict[str, Any]:
    view: dict[str, Any] = {
        "callId": call.call_id,
        "bed": call.bed,
        "kind": call.kind,
        "state": call.state or "pressed",
        "escalationLevel": call.escalation_level,
        "routedToRole": call.routed_to_role or ("nurse" if call.kind == "assist" else "care_assistant"),
        "pressCount": call.press_count,
        "deliveredLate": call.delivered_late,
        "pressedAt": format_ts(call.pressed_at),
    }
    if call.escalation_reason:
        view["escalationReason"] = call.escalation_reason
    if call.acknowledged_by:
        view["acknowledgedBy"] = call.acknowledged_by
    if call.acknowledged_at:
        view["acknowledgedAt"] = format_ts(call.acknowledged_at)
    return view


def snapshot_view(twin: WardTwin, now: datetime, clock_mode: str) -> dict[str, Any]:
    return {
        "ward": twin.ward,
        "asOf": format_ts(now),
        "clockMode": clock_mode,
        "beds": [bed_view(b, now, twin.assignments.get(b.bed)) for b in twin.beds.values()],
        "staff": [staff_view(s, twin.assignments) for s in twin.staff.values()],
        "calls": [call_view(c) for c in twin.calls.values() if c.open],
        "alerts": [],  # derived after NEWS2 is attached (live.py, alerts.py)
    }
