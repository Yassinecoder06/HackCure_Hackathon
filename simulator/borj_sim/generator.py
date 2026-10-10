"""Event generation engine for borj_sim.

Produces a deterministic, reproducible stream of contract-compliant ward events
(invariants 5, 6, 7, 13).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import borj_contracts as bc
from borj_contracts import generate_ulid

from .config import ScenarioConfig, WardConfig

log = logging.getLogger(__name__)


@dataclass
class BedSimulationState:
    bed: str
    admission_id: str | None = None
    patient_ref: str | None = None
    acuity: int = 1
    device_id: str | None = None
    device_type: str | None = None
    provides: list[str] = field(default_factory=list)
    device_online: bool = True
    offline_until_min: float = 0.0

    # Vitals current target
    current_vitals: dict[str, Any] = field(default_factory=dict)
    # Deterioration ramp
    deteriorate_from: dict[str, Any] = field(default_factory=dict)
    deteriorate_to: dict[str, Any] = field(default_factory=dict)
    deteriorate_start_min: float = 0.0
    deteriorate_end_min: float = 0.0


@dataclass
class ActiveCall:
    call_id: str
    bed: str
    kind: str
    press_count: int
    created_min: float
    no_ack: bool = False
    ack_scheduled_min: float | None = None
    resolve_scheduled_min: float | None = None
    acknowledged_by: str | None = None


class EventGenerator:
    def __init__(self, scenario: ScenarioConfig, ward: WardConfig) -> None:
        self.scenario = scenario
        self.ward = ward
        self.rng = random.Random(scenario.seed)

        # Parse start timestamp
        self.start_dt = datetime.fromisoformat(scenario.start.replace("Z", "+00:00")).astimezone(UTC)
        self.current_min = 0.0

        # Simulation state
        self.beds: dict[str, BedSimulationState] = {}
        self.calls: dict[str, ActiveCall] = {}
        self.current_call_rate = scenario.rates.calls_per_hour
        self.on_shift_staff = list(scenario.on_shift)

        self._init_beds()

    def _init_beds(self) -> None:
        for bed_id, profile_name in self.ward.beds.items():
            profiles = self.ward.device_profiles.get(profile_name, [])
            dev_id = f"MON-{bed_id}" if profiles else None
            dev_type = profiles[0]["type"] if profiles else None
            provides = profiles[0]["provides"] if profiles else []

            # Default baseline vitals
            baseline = {
                "resp_rate": 16,
                "spo2": 98,
                "spo2_scale": 1,
                "on_oxygen": False,
                "sys_bp": 120,
                "pulse": 72,
                "consciousness": "A",
                "temp_c": 36.8,
            }

            self.beds[bed_id] = BedSimulationState(
                bed=bed_id,
                device_id=dev_id,
                device_type=dev_type,
                provides=provides,
                current_vitals=baseline,
            )

    def current_ts(self) -> str:
        dt = self.start_dt + timedelta(minutes=self.current_min)
        return dt.isoformat().replace("+00:00", "Z")

    def make_envelope(self, topic: str, source: str, source_type: str, bed: str | None = None) -> dict[str, Any]:
        dt = self.start_dt + timedelta(minutes=self.current_min)
        t_ms = int(dt.timestamp() * 1000)
        env = {
            "schemaVersion": 1,
            "eventId": generate_ulid(t_ms=t_ms, rng=self.rng),
            "ts": self.current_ts(),
            "tsSource": "device_rtc" if source_type == "device" else "gateway",
            "ward": self.ward.ward,
            "source": source,
            "sourceType": source_type,
        }
        if bed:
            env["bed"] = bed
        return env

    def initial_events(self) -> list[tuple[str, dict[str, Any]]]:
        """Emits initial bindings, shift presence, and clock at minute 0."""
        events: list[tuple[str, dict[str, Any]]] = []

        # 1. Sim clock
        clock_msg = {
            "schemaVersion": 1,
            "ward": self.ward.ward,
            "simTs": self.current_ts(),
            "speed": 1.0,
            "scenario": self.scenario.name,
            "running": True,
        }
        events.append((bc.topic("clock", self.ward.ward), clock_msg))

        # 2. Staff presence
        for staff_id in self.scenario.on_shift:
            top = bc.topic("staff-presence", self.ward.ward, staff_id=staff_id)
            p_msg = {
                **self.make_envelope(top, "sim-gateway", "server"),
                "staffId": staff_id,
                "onWard": True,
                "reason": "shift_start",
            }
            events.append((top, p_msg))

        # 3. Patient admissions and device bindings
        for bed_id, state in self.beds.items():
            if bed_id in self.scenario.empty_beds:
                continue

            num_str = bed_id.replace("B", "")
            state.admission_id = f"ADM-{self.ward.ward}-{bed_id}"
            state.patient_ref = f"Patient {num_str}"
            state.acuity = 2

            # Patient admit binding
            t_bind = bc.topic("binding", self.ward.ward, bed=bed_id)
            admit_msg = {
                **self.make_envelope(t_bind, "sim-gateway", "server", bed=bed_id),
                "action": "admit",
                "admissionId": state.admission_id,
                "patientRef": state.patient_ref,
                "acuity": state.acuity,
                "method": "simulator",
            }
            events.append((t_bind, admit_msg))

            # Device attach binding
            if state.device_id:
                attach_msg = {
                    **self.make_envelope(t_bind, "sim-gateway", "server", bed=bed_id),
                    "action": "attach_device",
                    "admissionId": state.admission_id,
                    "deviceId": state.device_id,
                    "method": "simulator",
                }
                events.append((t_bind, attach_msg))

        # Validate all initial events
        for t, p in events:
            bc.validate_message(t, p)

        return events

    def generate_step(self, step_min: int = 1) -> list[tuple[str, dict[str, Any]]]:
        """Advances simulation by step_min and returns generated events."""
        events: list[tuple[str, dict[str, Any]]] = []
        target_min = self.current_min + step_min

        # Process any scripted events between current_min and target_min
        events.extend(self._process_scripted_events(target_min))

        self.current_min = target_min

        # 1. Update clock
        clock_msg = {
            "schemaVersion": 1,
            "ward": self.ward.ward,
            "simTs": self.current_ts(),
            "speed": 1.0,
            "scenario": self.scenario.name,
            "running": True,
        }
        events.append((bc.topic("clock", self.ward.ward), clock_msg))

        # 2. Device Vitals (every device_vitals_every_min)
        if int(self.current_min) % self.scenario.rates.device_vitals_every_min == 0:
            events.extend(self._generate_device_vitals())

        # 3. Manual Observations (every manual_obs_every_min)
        if int(self.current_min) % self.scenario.rates.manual_obs_every_min == 0:
            events.extend(self._generate_manual_obs())

        # 4. Device Heartbeat (every device_heartbeat_every_min)
        if int(self.current_min) % self.scenario.rates.device_heartbeat_every_min == 0:
            events.extend(self._generate_device_heartbeats())

        # 5. Background Poisson Calls
        events.extend(self._generate_background_calls(step_min))

        # 6. Scheduled background Acks / Resolves
        events.extend(self._process_scheduled_acks())

        # Validate every event
        for t, p in events:
            bc.validate_message(t, p)

        return events

    def _process_scripted_events(self, up_to_min: float) -> list[tuple[str, dict[str, Any]]]:
        events: list[tuple[str, dict[str, Any]]] = []
        for e in self.scenario.events:
            event_at = float(e.get("at", 0))
            if self.current_min < event_at <= up_to_min:
                etype = e.get("type")
                if etype == "deteriorate":
                    bed_id = e["bed"]
                    state = self.beds.get(bed_id)
                    if state:
                        state.deteriorate_from = dict(state.current_vitals)
                        state.deteriorate_to = dict(e["to"])
                        state.deteriorate_start_min = event_at
                        state.deteriorate_end_min = event_at + float(e.get("over_min", 60))
                        log.info("Deterioration started for %s: %s", bed_id, state.deteriorate_to)

                elif etype == "set_manual":
                    bed_id = e["bed"]
                    state = self.beds.get(bed_id)
                    if state and state.admission_id:
                        state.current_vitals.update(e.get("values", {}))
                        # Emit manual vitals event immediately
                        t_vit = bc.topic("vitals", self.ward.ward, bed=bed_id)
                        nurse_id = self.on_shift_staff[0] if self.on_shift_staff else "N1"
                        v_msg = {
                            **self.make_envelope(t_vit, f"app-{nurse_id}", "manual", bed=bed_id),
                            "staffId": nurse_id,
                            "params": dict(e.get("values", {})),
                            "quality": {"valid": True, "stale_after_s": 3600},
                        }
                        events.append((t_vit, v_msg))

                elif etype == "call_rate":
                    self.current_call_rate = float(e.get("calls_per_hour", 6.0))
                    log.info("Adjusted call rate to %.1f/h", self.current_call_rate)

                elif etype == "admit":
                    bed_id = e["bed"]
                    state = self.beds.get(bed_id)
                    if state:
                        state.admission_id = f"ADM-{self.ward.ward}-{bed_id}"
                        state.patient_ref = e.get("patient_ref", f"Patient {bed_id}")
                        state.acuity = int(e.get("acuity", 2))
                        t_bind = bc.topic("binding", self.ward.ward, bed=bed_id)
                        admit_msg = {
                            **self.make_envelope(t_bind, "sim-gateway", "server", bed=bed_id),
                            "action": "admit",
                            "admissionId": state.admission_id,
                            "patientRef": state.patient_ref,
                            "acuity": state.acuity,
                            "method": "simulator",
                        }
                        events.append((t_bind, admit_msg))

                elif etype == "staff_leaves":
                    staff_id = e["staff"]
                    if staff_id in self.on_shift_staff:
                        self.on_shift_staff.remove(staff_id)
                    t_pres = bc.topic("staff-presence", self.ward.ward, staff_id=staff_id)
                    pres_msg = {
                        **self.make_envelope(t_pres, f"app-{staff_id}", "staff_app"),
                        "staffId": staff_id,
                        "onWard": False,
                        "reason": "called_away",
                    }
                    events.append((t_pres, pres_msg))

                elif etype == "device_offline":
                    bed_id = e["bed"]
                    state = self.beds.get(bed_id)
                    if state and state.device_id:
                        for_min = float(e.get("for_min", 30))
                        state.device_online = False
                        state.offline_until_min = event_at + for_min
                        t_stat = bc.topic("device-status", self.ward.ward, bed=bed_id)
                        stat_msg = {
                            **self.make_envelope(t_stat, "sim-gateway", "device", bed=bed_id),
                            "deviceId": state.device_id,
                            "deviceType": state.device_type,
                            "status": "offline",
                            "detail": f"device offline for {int(for_min)} min",
                        }
                        events.append((t_stat, stat_msg))

                elif etype == "call":
                    bed_id = e["bed"]
                    kind = e.get("kind", "assist")
                    no_ack = bool(e.get("no_ack", False))
                    is_repeat = bool(e.get("repeat_of_previous", False))

                    active = self.calls.get(bed_id)
                    if is_repeat and active:
                        active.press_count += 1
                        call_id = active.call_id
                        press_count = active.press_count
                    else:
                        call_id = f"C-{bed_id}-{int(event_at * 100):06d}"
                        press_count = 1
                        self.calls[bed_id] = ActiveCall(
                            call_id=call_id,
                            bed=bed_id,
                            kind=kind,
                            press_count=press_count,
                            created_min=event_at,
                            no_ack=no_ack,
                        )

                    t_call = bc.topic("call", self.ward.ward, bed=bed_id)
                    call_msg = {
                        **self.make_envelope(t_call, f"node-{bed_id}", "bedside_node", bed=bed_id),
                        "callId": call_id,
                        "kind": kind,
                        "pressCount": press_count,
                    }
                    events.append((t_call, call_msg))

                elif etype == "node_outage_call":
                    bed_id = e["bed"]
                    kind = e.get("kind", "comfort")
                    delay_min = float(e.get("delay_min", 3))
                    call_id = f"C-{bed_id}-{int((event_at - delay_min) * 100):06d}"
                    t_call = bc.topic("call", self.ward.ward, bed=bed_id)
                    # Late delivery event with original timestamp
                    orig_dt = self.start_dt + timedelta(minutes=event_at - delay_min)
                    call_msg = {
                        **self.make_envelope(t_call, f"node-{bed_id}", "bedside_node", bed=bed_id),
                        "ts": orig_dt.isoformat().replace("+00:00", "Z"),
                        "callId": call_id,
                        "kind": kind,
                        "pressCount": 1,
                        "deliveredLate": True,
                    }
                    events.append((t_call, call_msg))

        return events

    def _generate_device_vitals(self) -> list[tuple[str, dict[str, Any]]]:
        events = []
        for bed_id, state in self.beds.items():
            if not state.admission_id or not state.device_id or not state.provides:
                continue

            # Check offline status
            if not state.device_online:
                if self.current_min >= state.offline_until_min:
                    state.device_online = True
                    log.info("Device on %s is back online", bed_id)
                else:
                    continue

            # Calculate vitals with ramp and natural drift
            params = {}
            for param in state.provides:
                val = self._compute_vital_value(state, param)
                params[param] = val

            # Check artifact
            is_artifact = self.rng.random() < self.scenario.rates.artifact_prob
            quality = {
                "valid": not is_artifact,
                "stale_after_s": 900,
            }
            if is_artifact:
                quality["flags"] = ["artifact"]

            t_vit = bc.topic("vitals", self.ward.ward, bed=bed_id)
            v_msg = {
                **self.make_envelope(t_vit, f"gateway-{bed_id}", "device", bed=bed_id),
                "deviceId": state.device_id,
                "params": params,
                "quality": quality,
            }
            events.append((t_vit, v_msg))
        return events

    def _compute_vital_value(self, state: BedSimulationState, param: str) -> Any:
        current = state.current_vitals.get(param)
        if current is None:
            return None

        # Check if deterioration ramp is running
        if state.deteriorate_to and state.deteriorate_start_min <= self.current_min:
            t_span = max(1.0, state.deteriorate_end_min - state.deteriorate_start_min)
            fraction = min(1.0, max(0.0, (self.current_min - state.deteriorate_start_min) / t_span))
            target = state.deteriorate_to.get(param, current)
            start_val = state.deteriorate_from.get(param, current)
            if isinstance(target, (int, float)) and isinstance(start_val, (int, float)):
                val = start_val + fraction * (target - start_val)
            else:
                val = target if fraction >= 1.0 else start_val
        else:
            val = current

        # Add small realistic drift
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if param in ("pulse", "resp_rate", "sys_bp"):
                drift = self.rng.randint(-1, 1)
                return max(0, int(val + drift))
            elif param == "spo2":
                drift = self.rng.randint(0, 1) if val < 95 else self.rng.randint(-1, 0)
                return max(0, min(100, int(val + drift)))
            elif param == "temp_c":
                drift = self.rng.choice([-0.05, 0.0, 0.05])
                return round(float(val + drift), 1)

        return val

    def _generate_manual_obs(self) -> list[tuple[str, dict[str, Any]]]:
        events = []
        nurses = [s for s in self.ward.staff if s.id in self.on_shift_staff and s.role == "nurse"]
        nurse_id = nurses[0].id if nurses else "N1"

        for bed_id, state in self.beds.items():
            if not state.admission_id:
                continue

            # Nurse records consciousness and on_oxygen (almost always manual)
            consciousness = state.current_vitals.get("consciousness", "A")
            on_oxygen = state.current_vitals.get("on_oxygen", False)

            params = {
                "consciousness": consciousness,
                "on_oxygen": on_oxygen,
            }
            # If bed has no monitor or monitor without RR, nurse also measures RR manually
            if "resp_rate" not in state.provides:
                params["resp_rate"] = self._compute_vital_value(state, "resp_rate") or 16

            t_vit = bc.topic("vitals", self.ward.ward, bed=bed_id)
            v_msg = {
                **self.make_envelope(t_vit, f"app-{nurse_id}", "manual", bed=bed_id),
                "staffId": nurse_id,
                "params": params,
                "quality": {"valid": True, "stale_after_s": 3600},
            }
            events.append((t_vit, v_msg))
        return events

    def _generate_device_heartbeats(self) -> list[tuple[str, dict[str, Any]]]:
        events = []
        for bed_id, state in self.beds.items():
            if state.device_id and state.device_online:
                t_stat = bc.topic("device-status", self.ward.ward, bed=bed_id)
                msg = {
                    **self.make_envelope(t_stat, "sim-gateway", "device", bed=bed_id),
                    "deviceId": state.device_id,
                    "deviceType": state.device_type,
                    "status": "ok",
                }
                events.append((t_stat, msg))
        return events

    def _generate_background_calls(self, step_min: int) -> list[tuple[str, dict[str, Any]]]:
        events = []
        prob_call = (self.current_call_rate / 60.0) * step_min
        if self.rng.random() < prob_call:
            # Pick an occupied bed
            occupied = [b for b, s in self.beds.items() if s.admission_id]
            if not occupied:
                return events

            bed_id = self.rng.choice(occupied)
            active = self.calls.get(bed_id)
            is_repeat = active is not None and self.rng.random() < self.scenario.rates.repeat_press_prob

            if is_repeat and active:
                active.press_count += 1
                call_id = active.call_id
                press_count = active.press_count
                kind = active.kind
            else:
                call_id = f"C-{bed_id}-{int(self.current_min * 100):06d}"
                kind = "comfort" if self.rng.random() < self.scenario.rates.comfort_share else "assist"
                press_count = 1

                active_call = ActiveCall(
                    call_id=call_id,
                    bed=bed_id,
                    kind=kind,
                    press_count=press_count,
                    created_min=self.current_min,
                )

                # Schedule background ack
                if self.rng.random() < self.scenario.rates.background_ack_prob:
                    delay = self.rng.randint(*self.scenario.rates.ack_delay_min)
                    resolve = delay + self.rng.randint(*self.scenario.rates.resolve_delay_min)
                    active_call.ack_scheduled_min = self.current_min + delay
                    active_call.resolve_scheduled_min = self.current_min + resolve
                    # Pick staff
                    nurses = [s.id for s in self.ward.staff if s.id in self.on_shift_staff and s.role == "nurse"]
                    active_call.acknowledged_by = self.rng.choice(nurses) if nurses else "N1"

                self.calls[bed_id] = active_call

            t_call = bc.topic("call", self.ward.ward, bed=bed_id)
            call_msg = {
                **self.make_envelope(t_call, f"node-{bed_id}", "bedside_node", bed=bed_id),
                "callId": call_id,
                "kind": kind,
                "pressCount": press_count,
            }
            events.append((t_call, call_msg))

        return events

    def _process_scheduled_acks(self) -> list[tuple[str, dict[str, Any]]]:
        events = []
        for bed_id, call in list(self.calls.items()):
            if call.no_ack:
                continue

            if call.ack_scheduled_min and self.current_min >= call.ack_scheduled_min:
                staff_id = call.acknowledged_by or "N1"
                t_ack = bc.topic("ack", self.ward.ward, staff_id=staff_id)
                ack_msg = {
                    **self.make_envelope(t_ack, f"app-{staff_id}", "staff_app"),
                    "staffId": staff_id,
                    "target": "call",
                    "targetId": call.call_id,
                    "action": "acknowledge",
                }
                events.append((t_ack, ack_msg))
                call.ack_scheduled_min = None  # don't ack twice

            if call.resolve_scheduled_min and self.current_min >= call.resolve_scheduled_min:
                staff_id = call.acknowledged_by or "N1"
                t_ack = bc.topic("ack", self.ward.ward, staff_id=staff_id)
                res_msg = {
                    **self.make_envelope(t_ack, f"app-{staff_id}", "staff_app"),
                    "staffId": staff_id,
                    "target": "call",
                    "targetId": call.call_id,
                    "action": "resolve",
                }
                events.append((t_ack, res_msg))
                del self.calls[bed_id]

        return events
