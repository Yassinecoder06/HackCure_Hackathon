"""Serialise the twin into the API shapes defined in contracts/openapi.yaml.

Freshness is computed here, against the ward clock, so that stale or invalid readings are
always labelled as such and never presented as normal values (safety invariant 5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..timeutil import format_ts
from .state import Bed, Reading, StaffMember, WardTwin


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


def bed_view(bed: Bed, now: datetime) -> dict[str, Any]:
    view: dict[str, Any] = {
        "bed": bed.bed,
        "room": bed.room,
        "admission": None,
        "news2": None,  # NEWS2 engine: P1
        "vitals": {param: reading_view(r, now) for param, r in sorted(bed.vitals.items())},
        "devices": [
            {"deviceId": d.device_id, "deviceType": d.device_type, "status": d.status,
             "lastSeen": format_ts(d.last_seen)}
            for d in sorted(bed.devices.values(), key=lambda d: d.device_id)
        ],
    }
    if bed.admission is not None:
        view["admission"] = {
            "admissionId": bed.admission.admission_id,
            "patientRef": bed.admission.patient_ref,
            "acuity": bed.admission.acuity,
            "admittedAt": format_ts(bed.admission.admitted_at),
        }
    return view


def staff_view(member: StaffMember) -> dict[str, Any]:
    return {
        "staffId": member.staff_id,
        "displayName": member.name,
        "role": member.role,
        "skills": list(member.skills),
        "onShift": member.on_shift,
        "onWard": member.on_ward,
        "assignedBeds": [],  # assignment engine: P3
    }


def snapshot_view(twin: WardTwin, now: datetime, clock_mode: str) -> dict[str, Any]:
    return {
        "ward": twin.ward,
        "asOf": format_ts(now),
        "clockMode": clock_mode,
        "beds": [bed_view(b, now) for b in twin.beds.values()],
        "staff": [staff_view(s) for s in twin.staff.values()],
        "calls": [],  # call engine: P2
        "alerts": [],  # NEWS2 / call alerts: P1-P2
    }
