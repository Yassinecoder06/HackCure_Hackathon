"""Live ward twin: the current state derived from the event log.

Rules this module enforces:
- A parameter never received is absent from `vitals` (never 0/None) (invariant 5).
- Readings older than the current one never overwrite it (late, out-of-order events).
- Readings from before the current admission never attach to the new patient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .layout import WardLayout


@dataclass
class Reading:
    value: Any
    ts: datetime
    source_type: str  # device | manual
    valid: bool
    stale_after_s: int
    flags: tuple[str, ...] = ()


@dataclass
class Admission:
    admission_id: str
    patient_ref: str
    acuity: int
    admitted_at: datetime


@dataclass
class Device:
    device_id: str
    device_type: str
    status: str
    last_seen: datetime


@dataclass
class Bed:
    bed: str
    room: str
    admission: Admission | None = None
    binding_ts: datetime | None = None
    vitals: dict[str, Reading] = field(default_factory=dict)
    # Every reading of the current admission (param, reading), for trends and "as of" views.
    history: list[tuple[str, Reading]] = field(default_factory=list)
    devices: dict[str, Device] = field(default_factory=dict)


@dataclass
class StaffMember:
    staff_id: str
    name: str
    role: str
    skills: tuple[str, ...]
    on_shift: bool = False
    on_ward: bool = False
    presence_ts: datetime | None = None


@dataclass
class Call:
    """A bedside call. Press facts come from the node; state comes only from server call/state events."""

    call_id: str
    bed: str
    kind: str
    pressed_at: datetime
    press_count: int = 1
    delivered_late: bool = False
    state: str | None = None  # None until the server has published a call/state for it
    state_ts: datetime | None = None
    escalation_level: int = 0
    escalation_reason: str | None = None
    routed_to_role: str | None = None
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None

    @property
    def open(self) -> bool:
        return self.state != "resolved"


@dataclass
class Prescription:
    """Entered by a doctor. The system never creates or changes one (safety invariant 1)."""

    prescription_id: str
    admission_id: str
    bed: str
    drug: str
    dose: str
    route: str
    times: tuple[str, ...]
    start_date: str
    end_date: str | None
    is_infusion: bool
    prescribed_by: str


@dataclass
class Administration:
    """A nurse's record: the only thing that closes a dose."""

    action: str  # given | not_given
    staff_id: str
    ts: datetime
    presence: str | None = None
    reason: str | None = None


@dataclass
class AlertAck:
    staff_id: str
    ts: datetime


class WardTwin:
    def __init__(self, layout: WardLayout) -> None:
        self.ward = layout.ward
        self.layout = layout
        self.beds: dict[str, Bed] = {bed: Bed(bed=bed, room=room) for bed, room in layout.bed_rooms.items()}
        self.staff: dict[str, StaffMember] = {
            s.staff_id: StaffMember(s.staff_id, s.name, s.role, s.skills) for s in layout.staff
        }
        self.calls: dict[str, Call] = {}
        # bed -> nurse. Changes ONLY through approved `assignment` events (safety invariant 1).
        self.assignments: dict[str, str] = {}
        self.alert_acks: dict[str, AlertAck] = {}
        # alertId -> remote doctor instructions [(text, staffId, ts)], shown to the nurses on the alert
        self.alert_instructions: dict[str, list[tuple[str, str, datetime]]] = {}
        self.prescriptions: dict[str, Prescription] = {}
        self.administrations: dict[str, Administration] = {}  # doseId -> nurse record
        self.patient_reported: dict[str, datetime] = {}        # doseId -> "I took my pills" (never closes a dose)
