"""Building ward views shared by the REST API and the live stream: NEWS2 (in the viewer's language),
the NEWS2 trend, the priority ranking with its reasons, and the alerts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI

from .alerts import derive_alerts
from .explain import Explainer
from .meds import timeline
from .scoring import attach_news2, news2_inputs
from .timeutil import format_ts
from .twin.state import WardTwin
from .twin.views import bed_view, call_view, snapshot_view, staff_view

TREND_MINUTES = (60, 30)
SEVERITY = {"high": 3, "medium": 2, "low_medium": 1, "low": 0}


def _score_inputs(twin: WardTwin, now: datetime) -> list[dict[str, Any]]:
    """NEWS2 inputs now and at each trend point. Call under the ingest lock."""
    inputs = news2_inputs(twin, now)
    for minutes in TREND_MINUTES:
        inputs += news2_inputs(twin, now, as_of=now - timedelta(minutes=minutes), key_suffix=f"@{minutes}")
    return inputs


def _trend(bed_id: str, results: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not results:
        return []
    return [{"minutesAgo": m, "total": results[f"{bed_id}@{m}"]["total"],
             "complete": results[f"{bed_id}@{m}"]["complete"]}
            for m in TREND_MINUTES if f"{bed_id}@{m}" in results]


def _priority(beds: list[dict[str, Any]], twin: WardTwin, now: datetime, overdue: dict[str, int],
              ex: Explainer) -> None:
    """Rank admitted beds (most urgent first) and explain each rank in the viewer's language."""
    open_calls: dict[str, list] = {}
    for call in twin.calls.values():
        if call.state in ("sent", "escalated"):
            open_calls.setdefault(call.bed, []).append(call)

    def key(bed: dict[str, Any]) -> tuple:
        n = bed["news2"] or {}
        calls = open_calls.get(bed["bed"], [])
        return (-SEVERITY.get(n.get("band", "low"), 0), -max((c.escalation_level for c in calls), default=-1),
                -len(calls), -n.get("total", 0), -overdue.get(bed["bed"], 0), bed["bed"])

    admitted = sorted((b for b in beds if b["admission"]), key=key)
    for rank, bed in enumerate(admitted, start=1):
        reasons = []
        n = bed["news2"]
        if n:
            qualifier = "" if n["complete"] else ex.say("alert.news2.at_least")
            reasons.append(ex.say("priority.news2", qualifier=qualifier, total=n["total"], band=ex.band(n["band"])))
            oldest = next((t for t in bed.get("news2Trend", []) if t["total"] != n["total"]), None)
            if oldest:
                direction = "up" if n["total"] > oldest["total"] else "down"
                reasons.append(ex.say(f"priority.trend.{direction}", before=oldest["total"], after=n["total"],
                                      minutes=oldest["minutesAgo"]))
            if not n["complete"]:
                reasons.append(ex.say("priority.partial", params=ex.params(n["missing"] + n["stale"])))
        for call in sorted(open_calls.get(bed["bed"], []), key=lambda c: c.pressed_at):
            waited = max(0, int((now - call.pressed_at).total_seconds() // 60))
            reasons.append(ex.say("priority.call", kind=ex.kind(call.kind, capital=True), minutes=waited,
                                  level=call.escalation_level))
        if overdue.get(bed["bed"]):
            reasons.append(ex.say("priority.doses", count=overdue[bed["bed"]]))
        bed["priority"] = {"rank": rank, "of": len(admitted),
                           "reasons": reasons or [ex.say("priority.none")]}


def _overdue_by_bed(app: FastAPI, twin: WardTwin, now: datetime) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dose in timeline(twin, now, app.state.meds_config, hours=0)["doses"]:
        if dose["status"] == "overdue":
            counts[dose["bed"]] = counts.get(dose["bed"], 0) + 1
    return counts


def _beds_and_alerts(app: FastAPI, ex: Explainer, bed_ids: set[str] | None, snapshot: bool):
    ingestor = app.state.ingestor
    with ingestor.lock:
        twin = ingestor.twin
        now = ingestor.clock.now()
        snap = snapshot_view(twin, now, ingestor.clock.effective_mode) if snapshot else None
        views = snap["beds"] if snap else [bed_view(b, now, twin.assignments.get(b.bed)) for b in twin.beds.values()]
        inputs = _score_inputs(twin, now)
    # Outside the lock: never hold up ingest while waiting on the inference layer.
    inference = app.state.inference
    results = inference.news2_batch(format_ts(now), inputs) if inference else None
    current = {k: v for k, v in results.items() if "@" not in k} if results is not None else None
    attach_news2({"beds": views}, current)
    with ingestor.lock:
        for bed in views:
            if bed["news2"]:
                bed["news2"] = ex.news2(bed["news2"])
                bed["news2Trend"] = _trend(bed["bed"], results)
        _priority(views, ingestor.twin, now, _overdue_by_bed(app, ingestor.twin, now), ex)
        alerts = derive_alerts(ingestor.twin, {b["bed"]: b["news2"] for b in views}, now, app.state.call_config,
                               app.state.first_seen, bed_ids, meds_cfg=app.state.meds_config, ex=ex)
    if snap is not None:
        snap["alerts"] = alerts
        return snap, alerts
    return [b for b in views if bed_ids is None or b["bed"] in bed_ids], alerts


def default_explainer(app: FastAPI) -> Explainer:
    return Explainer(app.state.settings.default_lang, app.state.meds_config.ward_tz)


def build_snapshot(app: FastAPI, ex: Explainer | None = None) -> dict[str, Any]:
    snap, _ = _beds_and_alerts(app, ex or default_explainer(app), None, snapshot=True)
    return snap


def build_beds(app: FastAPI, bed_ids: set[str] | None,
               ex: Explainer | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Current view of some beds (None = all) with NEWS2, trend and priority, plus their alerts.
    NEWS2 is always computed for every bed, because the priority rank compares beds."""
    return _beds_and_alerts(app, ex or default_explainer(app), bed_ids, snapshot=False)


def build_calls(app: FastAPI, call_ids: set[str]) -> list[dict[str, Any]]:
    ingestor = app.state.ingestor
    with ingestor.lock:
        return [call_view(ingestor.twin.calls[c]) for c in call_ids if c in ingestor.twin.calls]


def build_staff(app: FastAPI, staff_ids: set[str]) -> list[dict[str, Any]]:
    ingestor = app.state.ingestor
    with ingestor.lock:
        return [staff_view(ingestor.twin.staff[s], ingestor.twin.assignments)
                for s in staff_ids if s in ingestor.twin.staff]


def news2_by_bed(app: FastAPI) -> dict[str, dict[str, Any] | None]:
    beds, _ = build_beds(app, None)
    return {b["bed"]: b["news2"] for b in beds}


def news2_total(app: FastAPI, bed_id: str) -> int | None:
    """Current NEWS2 total (a minimum if partial) for the call engine, or None if unavailable."""
    news2 = news2_by_bed(app).get(bed_id)
    return news2["total"] if news2 else None
