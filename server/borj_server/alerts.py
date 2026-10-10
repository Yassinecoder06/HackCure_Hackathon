"""Alerts derived from the twin (escalation ladder: low = silent badge, medium = notification,
critical = persistent until acknowledged). Every alert carries a confidence index and explanation
sentences built from the triggering rule (HackCure section 6, invariant 12).

Alerts are a pure function of the current twin and NEWS2 results. An alert's id names its
condition (e.g. the bed, admission and NEWS2 band), so an acknowledgement sticks while the condition
lasts, and a worse condition (a higher band, a higher call level) raises a new, unacknowledged alert.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from .calls import CallConfig
from .explain import Explainer
from .meds import MedsConfig, timeline
from .timeutil import format_ts
from .twin.state import WardTwin
from .twin.views import reading_status

DETERMINISTIC = 1.0


def alert_id(prefix: str, *condition: str) -> str:
    """Short, URL-safe id that names the condition (fits the contract's 40-character id limit)."""
    return f"{prefix}-{hashlib.sha256('|'.join(condition).encode()).hexdigest()[:16]}"


class FirstSeen:
    """Remembers when each alert condition was first observed (for createdAt)."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def __call__(self, alert_id: str, now: datetime) -> str:
        return self._seen.setdefault(alert_id, format_ts(now))


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def derive_alerts(twin: WardTwin, news2: dict[str, dict[str, Any] | None], now: datetime, cfg: CallConfig,
                  first_seen: FirstSeen, bed_ids: set[str] | None = None,
                  meds_cfg: MedsConfig | None = None, ex: Explainer | None = None) -> list[dict[str, Any]]:
    ex = ex or Explainer("en", meds_cfg.ward_tz if meds_cfg else Explainer().tz)
    alerts: list[dict[str, Any]] = []

    def add(alert_id: str, bed: str, kind: str, priority: str, explanation: list[str], confidence: dict[str, Any],
            escalated_to: list[str] | None = None) -> None:
        alert: dict[str, Any] = {
            "alertId": alert_id, "bed": bed, "type": kind, "priority": priority, "createdAt": first_seen(alert_id, now),
            "explanation": explanation, "confidence": confidence, "active": True,
        }
        if escalated_to:
            alert["escalatedTo"] = escalated_to
        ack = twin.alert_acks.get(alert_id)
        if ack is not None:
            alert["acknowledgedBy"] = ack.staff_id
        notes = twin.alert_instructions.get(alert_id)
        if notes:
            alert["instructions"] = [{"text": text, "by": by, "at": format_ts(at)} for text, by, at in notes]
        alerts.append(alert)

    for bed in twin.beds.values():
        if bed_ids is not None and bed.bed not in bed_ids:
            continue
        if bed.admission is not None:
            adm = bed.admission.admission_id
            result = news2.get(bed.bed)
            if result is not None and result["band"] in cfg.news2_band_priority:
                kind = "news2_single_param_3" if result["band"] == "low_medium" else "news2_high"
                scored = [c for c in result["components"] if c.get("points")]
                qualifier = "" if result["complete"] else ex.say("alert.news2.at_least")
                explanation = [ex.say("alert.news2.headline", qualifier=qualifier, total=result["total"],
                                      response=ex.say(f"news2.response.{result['band']}"))]
                explanation += [ex.say("alert.news2.component", param=_capital(ex.param(c["param"])),
                                       value=c["value"], points=c["points"])
                                for c in sorted(scored, key=lambda c: -c["points"])]
                if not result["complete"]:
                    explanation.append(ex.news2(result)["label"])
                add(alert_id("news2", bed.bed, adm, result["band"]), bed.bed, kind,
                    cfg.news2_band_priority[result["band"]], explanation, result["confidence"])

            stale = sorted(p for p, r in bed.vitals.items() if reading_status(r, now) == "stale")
            if stale:
                add(alert_id("stale", bed.bed, adm), bed.bed, "stale_data", cfg.stale_data_priority,
                    [ex.say("alert.stale", params=ex.params(stale))],
                    {"value": DETERMINISTIC, "basis": ex.say("alert.stale.basis")})

        for device in bed.devices.values():
            if device.status in ("offline", "error"):
                add(alert_id("device", device.device_id, device.status, format_ts(device.last_seen)), bed.bed,
                    "device_offline", cfg.device_offline_priority,
                    [ex.say("alert.device", device=device.device_id, status=device.status,
                            time=ex.time(device.last_seen))],
                    {"value": DETERMINISTIC, "basis": ex.say("alert.device.basis")})

    if meds_cfg is not None:
        for dose in timeline(twin, now, meds_cfg, hours=0)["doses"]:
            if dose["status"] == "overdue" and (bed_ids is None or dose["bed"] in bed_ids):
                add(alert_id("dose", dose["doseId"]), dose["bed"], "dose_overdue", meds_cfg.overdue_priority,
                    [ex.say("alert.dose", label=dose["label"], bed=dose["bed"], time=ex.time(dose["due"]))],
                    {"value": DETERMINISTIC, "basis": ex.say("alert.dose.basis")})

    for call in twin.calls.values():
        if bed_ids is not None and call.bed not in bed_ids:
            continue
        if call.state == "escalated" and call.escalation_level >= 1:
            reason = ex.say(f"reason.{call.escalation_reason or 'unacknowledged_timeout'}")
            pressed = "alert.call.pressed_late" if call.delivered_late else "alert.call.pressed"
            add(alert_id("call", call.call_id, str(call.escalation_level)), call.bed, "call_escalated",
                cfg.call_level_priority.get(call.escalation_level, "critical"),
                [ex.say("alert.call", kind=ex.kind(call.kind, capital=True), bed=call.bed,
                        level=call.escalation_level, reason=reason),
                 ex.say(pressed, time=ex.time(call.pressed_at))],
                {"value": DETERMINISTIC, "basis": ex.say("alert.call.basis")},
                escalated_to=cfg.escalated_to(call.kind, call.escalation_level))
    return alerts
