"""Medication timeline: schedule and remind from doctors' prescriptions (whitepaper 4.3, 5.2).

- Doses are generated deterministically from each prescription's daily times (ward local time),
  for admissions that are still in their bed. A dose id names the prescription and the due minute.
- Status: `given` / `not_given` come ONLY from a nurse's record. A patient's "I took my pills" is
  shown separately and never closes a dose. Otherwise `due`, then `overdue` after N minutes.
- Clashes: too many doses, or more than one infusion, due for the same nurse in the same window.
- The system never selects drugs or doses (safety invariant 1); drug labels stay on staff screens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .explain import Explainer
from .timeutil import format_ts
from .twin.state import Prescription, WardTwin

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "meds.yaml"


@dataclass(frozen=True)
class MedsConfig:
    ward_tz: timezone
    overdue_after: timedelta
    past: timedelta
    window: timedelta
    max_doses_per_nurse: int
    max_infusions_per_nurse: int
    overdue_priority: str

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> MedsConfig:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            ward_tz=timezone(timedelta(minutes=int(d["schedule"]["ward_utc_offset_min"]))),
            overdue_after=timedelta(minutes=int(d["schedule"]["overdue_after_min"])),
            past=timedelta(hours=float(d["schedule"]["timeline_past_hours"])),
            window=timedelta(minutes=int(d["clashes"]["window_min"])),
            max_doses_per_nurse=int(d["clashes"]["max_doses_per_nurse"]),
            max_infusions_per_nurse=int(d["clashes"]["max_infusions_per_nurse"]),
            overdue_priority=d["alerts"]["dose_overdue_priority"],
        )


def dose_id(prescription_id: str, due: datetime) -> str:
    return f"D-{prescription_id[:20]}-{due.strftime('%y%m%d%H%M')}"


def due_times(rx: Prescription, start: datetime, end: datetime, cfg: MedsConfig) -> list[datetime]:
    """UTC due times of a prescription between start and end."""
    first = max(date.fromisoformat(rx.start_date), start.astimezone(cfg.ward_tz).date() - timedelta(days=1))
    last = min(date.fromisoformat(rx.end_date) if rx.end_date else date.max,
               end.astimezone(cfg.ward_tz).date() + timedelta(days=1))
    times = []
    day = first
    while day <= last:
        for hhmm in rx.times:
            hour, minute = map(int, hhmm.split(":"))
            due = datetime(day.year, day.month, day.day, hour, minute, tzinfo=cfg.ward_tz).astimezone(UTC)
            if start <= due <= end:
                times.append(due)
        day += timedelta(days=1)
    return sorted(times)


def timeline(twin: WardTwin, now: datetime, cfg: MedsConfig, hours: float,
             ex: Explainer | None = None) -> dict[str, Any]:
    start, end = now - cfg.past, now + timedelta(hours=hours)
    doses = []
    infusion_ids = set()
    for rx in twin.prescriptions.values():
        bed = twin.beds.get(rx.bed)
        if bed is None or bed.admission is None or bed.admission.admission_id != rx.admission_id:
            continue  # discharged or moved: the bed no longer holds this admission
        for due in due_times(rx, start, end, cfg):
            did = dose_id(rx.prescription_id, due)
            record = twin.administrations.get(did)
            status = record.action if record else ("overdue" if now > due + cfg.overdue_after else "due")
            label = f"{rx.drug} {rx.dose} {rx.route}" + (" (infusion)" if rx.is_infusion else "")
            dose: dict[str, Any] = {
                "doseId": did, "admissionId": rx.admission_id, "bed": rx.bed, "due": format_ts(due),
                "status": status, "label": label,
            }
            if record:
                dose["administeredBy"] = record.staff_id
                dose["administeredAt"] = format_ts(record.ts)
            if did in twin.patient_reported:
                dose["patientReportedAt"] = format_ts(twin.patient_reported[did])
            if rx.is_infusion:
                infusion_ids.add(did)
            doses.append(dose)
    doses.sort(key=lambda d: (d["due"], d["bed"]))
    return {"doses": doses, "clashes": _clashes(doses, infusion_ids, twin, cfg, ex or Explainer("en", cfg.ward_tz))}


def _clashes(doses: list[dict[str, Any]], infusions: set[str], twin: WardTwin, cfg: MedsConfig,
             ex: Explainer) -> list[dict[str, Any]]:
    open_doses = [d for d in doses if d["status"] in ("due", "overdue")]
    clashes = []
    seen: set[tuple[str, ...]] = set()
    for i, anchor in enumerate(open_doses):
        anchor_due = datetime.fromisoformat(anchor["due"].replace("Z", "+00:00"))
        group = [d for d in open_doses[i:]
                 if datetime.fromisoformat(d["due"].replace("Z", "+00:00")) - anchor_due <= cfg.window]
        by_nurse: dict[str, list[dict[str, Any]]] = {}
        for d in group:
            by_nurse.setdefault(twin.assignments.get(d["bed"], "unassigned"), []).append(d)
        for nurse, mine in by_nurse.items():
            infusion_count = sum(1 for d in mine if d["doseId"] in infusions)
            too_many = len(mine) > cfg.max_doses_per_nurse
            too_many_infusions = infusion_count > cfg.max_infusions_per_nurse
            key = tuple(sorted(d["doseId"] for d in mine))
            if (too_many or too_many_infusions) and key not in seen:
                seen.add(key)
                who = ex.say("meds.unassigned") if nurse == "unassigned" else nurse
                beds = ", ".join(sorted({d["bed"] for d in mine}))
                window = int(cfg.window.total_seconds() // 60)
                reason = (ex.say("meds.clash.infusions", count=infusion_count, window=window, who=who, beds=beds)
                          if too_many_infusions else
                          ex.say("meds.clash.doses", count=len(mine), window=window, who=who, beds=beds))
                clashes.append({"at": anchor["due"], "doseIds": list(key), "reason": reason})
    return clashes
