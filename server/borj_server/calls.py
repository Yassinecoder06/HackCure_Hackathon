"""Call engine: routing and escalation of bedside calls (contracts/mqtt-topics.md, whitepaper 4.2).

The engine reacts to presses, staff acks and clock ticks. Every decision it makes becomes a
server-published `call/state` event that goes through the normal ingest path, so it is stored in
the event log and a replay rebuilds exactly the same call states without re-running any timer.

Rules (all parameters in server/config/calls.yaml):
- assist calls go to nurses, comfort calls to care assistants first (still visible to nurses);
- unacknowledged after ack_timeout_s -> level 1, after escalate_timeout_s -> level 2 (charge nurse,
  plus the on-call doctor for assist calls), measured from the patient's original press;
- a repeated press escalates one level; a press from a patient with NEWS2 >= threshold escalates
  at once and is routed to a nurse even if it was a comfort call.
The patient button is a non-authoritative signal: only a staff ack/resolve changes those states.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import borj_contracts as bc
import yaml

from .ids import new_ulid
from .ingest import Ingestor
from .timeutil import format_ts
from .twin.state import Call

log = logging.getLogger(__name__)

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "calls.yaml"
OPEN_UNACKED = {"sent", "escalated"}


@dataclass(frozen=True)
class CallConfig:
    ack_timeout_s: int
    escalate_timeout_s: int
    routing: dict[str, list[str]]
    doctor_from_level: int
    escalate_press_at_total: int
    news2_band_priority: dict[str, str]
    call_level_priority: dict[int, str]
    stale_data_priority: str
    device_offline_priority: str

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> CallConfig:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            ack_timeout_s=int(data["timers"]["ack_timeout_s"]),
            escalate_timeout_s=int(data["timers"]["escalate_timeout_s"]),
            routing={k: list(v) for k, v in data["routing"].items() if k in ("assist", "comfort")},
            doctor_from_level=int(data["routing"]["doctor_from_level"]),
            escalate_press_at_total=int(data["news2_escalation"]["escalate_press_at_total"]),
            news2_band_priority=dict(data["alerts"]["news2_band_priority"]),
            call_level_priority={int(k): v for k, v in data["alerts"]["call_level_priority"].items()},
            stale_data_priority=data["alerts"]["stale_data_priority"],
            device_offline_priority=data["alerts"]["device_offline_priority"],
        )

    def role_for(self, kind: str, level: int) -> str:
        return self.routing[kind][min(level, len(self.routing[kind]) - 1)]

    def escalated_to(self, kind: str, level: int) -> list[str]:
        roles = list(dict.fromkeys(self.role_for(kind, lv) for lv in range(level + 1)))
        if kind == "assist" and level >= self.doctor_from_level:
            roles.append("doctor")
        return roles


class CallEngine:
    def __init__(
        self,
        ingestor: Ingestor,
        cfg: CallConfig,
        news2_total: Callable[[str], int | None],
        publish: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.ingestor = ingestor
        self.cfg = cfg
        self.news2_total = news2_total
        self.publish = publish
        self._lock = threading.RLock()  # serialises decisions; re-entrant because emitting re-enters on_event
        self._handled_presses: dict[str, int] = {}

    # --- ingest listener -------------------------------------------------------------------

    def on_event(self, schema: str, payload: dict[str, Any]) -> None:
        if schema == "call":
            self.on_press(payload)
        elif schema == "ack" and payload["target"] == "call":
            self.on_ack(payload)
        elif schema == "clock":
            self.tick()

    def on_press(self, payload: dict[str, Any]) -> None:
        with self._lock:
            call = self._call(payload["callId"])
            if call is None or not call.open:
                return
            if call.state is None:
                self._emit(call, "sent", 0, None, self.cfg.role_for(call.kind, 0))
                self._handled_presses[call.call_id] = call.press_count
                total = self.news2_total(call.bed)
                if total is not None and total >= self.cfg.escalate_press_at_total:
                    self._emit(call, "escalated", 1, "high_news2", self.cfg.role_for("assist", 1))
                return
            if payload["pressCount"] > self._handled_presses.get(call.call_id, 1):
                self._handled_presses[call.call_id] = payload["pressCount"]
                level = min(call.escalation_level + 1, 2)
                self._emit(call, "escalated", level, "repeat_press", self.cfg.role_for(call.kind, level))

    def on_ack(self, payload: dict[str, Any]) -> None:
        with self._lock:
            call = self._call(payload["targetId"])
            if call is None or not call.open or call.state is None:
                return
            if payload["action"] == "acknowledge" and call.state in OPEN_UNACKED:
                self._emit(call, "acknowledged", call.escalation_level, call.escalation_reason,
                           call.routed_to_role, acknowledged_by=payload["staffId"])
            elif payload["action"] == "resolve":
                self._emit(call, "resolved", call.escalation_level, call.escalation_reason,
                           call.routed_to_role, acknowledged_by=call.acknowledged_by or payload["staffId"])

    def tick(self) -> None:
        """Time-based escalation. Safe to call often: it only emits when a level must rise."""
        with self._lock:
            with self.ingestor.lock:
                now = self.ingestor.clock.now()
                due = [c for c in self.ingestor.twin.calls.values() if c.state in OPEN_UNACKED]
            for call in due:
                waited = (now - call.pressed_at).total_seconds()
                target = 2 if waited >= self.cfg.escalate_timeout_s else 1 if waited >= self.cfg.ack_timeout_s else 0
                if target > call.escalation_level:
                    self._emit(call, "escalated", target, "unacknowledged_timeout",
                               self.cfg.role_for(call.kind, target), now=now)

    # --- helpers ---------------------------------------------------------------------------

    def _call(self, call_id: str) -> Call | None:
        with self.ingestor.lock:
            return self.ingestor.twin.calls.get(call_id)

    def _emit(self, call: Call, state: str, level: int, reason: str | None, role: str | None,
              acknowledged_by: str | None = None, now: datetime | None = None) -> None:
        ts = max(now, self.ingestor.event_now()) if now else self.ingestor.event_now()
        payload: dict[str, Any] = {
            "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(ts), "ward": self.ingestor.layout.ward,
            "bed": call.bed, "source": "borj-server", "sourceType": "server", "callId": call.call_id,
            "kind": call.kind, "state": state, "escalationLevel": level, "pressedAt": format_ts(call.pressed_at),
        }
        if reason:
            payload["escalationReason"] = reason
        if role:
            payload["routedToRole"] = role
        if acknowledged_by:
            payload["acknowledgedBy"] = acknowledged_by
        topic = bc.topic("call-state", payload["ward"], bed=call.bed)
        result = self.ingestor.handle(topic, payload)
        if result.status != "accepted":
            log.error("call/state for %s not accepted: %s %s", call.call_id, result.status, result.detail)
            return
        if state == "escalated":
            self.ingestor.store.audit("system", "call.escalated", call.call_id,
                                      {"level": level, "reason": reason, "to": self.cfg.escalated_to(call.kind, level)})
            if "doctor" in self.cfg.escalated_to(call.kind, level):
                log.info("call %s escalated to the on-call doctor (SMS fallback: stub)", call.call_id)
        if self.publish is not None:
            self.publish(topic, payload)  # retained, so a rebooting bedside node gets its LED state back
