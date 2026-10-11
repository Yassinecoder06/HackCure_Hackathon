"""Step 2 of ADR 0013: the fact builder. Numbered facts, built deterministically from the live ward view (twin, NEWS2,
priority, calls, alerts, doctor orders), in the language of the user.

Live ward data is exact, structured and small, so we look it up instead of searching by similarity: a similarity search
could return the wrong bed or an old reading. Each fact is one plain sentence made by a template from structured
values. The model may only rephrase these; the verifier checks that every number, bed id and time it says is in a
fact it cites. Absent data is stated as absent or stale, never as a normal value (safety invariant 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..explain import Explainer

# (English, French). Written for nurses: short, factual, no judgement beyond the scores the system already shows.
M: dict[str, tuple[str, str]] = {
    "admitted": ("{bed}: {patient}, admitted at {time}, acuity {acuity}.",
                 "{bed} : {patient}, admis à {time}, acuité {acuity}."),
    "empty": ("{bed} has no patient admitted.", "{bed} n'a aucun patient admis."),
    "news2_complete": ("{bed}: NEWS2 {total} ({band}), all parameters fresh. Confidence {conf}%.",
                       "{bed} : NEWS2 {total} ({band}), tous les paramètres sont récents. Confiance {conf}%."),
    "news2_partial": ("{bed}: partial NEWS2, at least {total} ({band}); not scored: {params}. Confidence {conf}%.",
                      "{bed} : NEWS2 partiel, au moins {total} ({band}) ; non pris en compte : {params}. "
                      "Confiance {conf}%."),
    "news2_unavailable": ("{bed}: NEWS2 is unavailable (the scoring service cannot be reached).",
                          "{bed} : NEWS2 indisponible (le service de calcul est injoignable)."),
    "vital": ("{bed} {param}: {value}{unit}, {status}, {age} old, {source}.",
              "{bed} {param} : {value}{unit}, {status}, vieux de {age}, {source}."),
    "vital_missing": ("{bed} {param}: no reading.", "{bed} {param} : aucune mesure."),
    "trend": ("{bed}: NEWS2 was {before} 60 minutes ago and {middle} 30 minutes ago; now {total}.",
              "{bed} : NEWS2 était {before} il y a 60 minutes et {middle} il y a 30 minutes ; maintenant {total}."),
    "trend_unknown": ("{bed}: no NEWS2 history is available for the last hour.",
                      "{bed} : aucun historique NEWS2 disponible pour la dernière heure."),
    "priority": ("{bed} is number {rank} of {total} on the ward priority list. {reasons}",
                 "{bed} est n° {rank} sur {total} dans la liste de priorité du service. {reasons}"),
    "nurse": ("{bed} is assigned to {nurse}.", "{bed} est confié(e) à {nurse}."),
    "nobody": ("{bed} has no nurse assigned.", "{bed} n'a pas d'infirmier(ère) assigné(e)."),
    "call": ("{bed}: {kind} call, {state}{level}, pressed {count} time(s), {age} ago.",
             "{bed} : appel {kind}, {state}{level}, appuyé {count} fois, il y a {age}."),
    "alert": ("{bed}: active {priority} alert. {headline}", "{bed} : alerte {priority} active. {headline}"),
    "instruction": ("Doctor instruction on a {bed} alert at {time}: {text}",
                    "Instruction du médecin sur une alerte de {bed} à {time} : {text}"),
    "order": ("Doctor order for {bed} at {time}: {text}", "Ordre du médecin pour {bed} à {time} : {text}"),
    "ward_counts": ("{n} patients admitted: {high} at high NEWS2 risk, {medium} medium, {low} low.",
                    "{n} patients admis : {high} à risque NEWS2 élevé, {medium} moyen, {low} faible."),
    "ward_calls": ("{n} open calls, {escalated} escalated.", "{n} appels ouverts, dont {escalated} escaladé(s)."),
    "ward_alerts": ("{n} active alerts.", "{n} alertes actives."),
    "ward_staff": ("{n} staff on the ward: {names}.", "{n} soignants dans le service : {names}."),
    "ward_line": ("{rank}. {bed}: NEWS2 {total} ({band}){partial}.", "{rank}. {bed} : NEWS2 {total} ({band}){partial}."),
    "ward_nobody": ("No patient is admitted.", "Aucun patient n'est admis."),
}
PRIORITY_WORD = {"critical": ("critical", "critique"), "high": ("high", "haute"), "medium": ("medium", "moyenne"),
                 "low": ("low", "faible")}
STATUS = {"fresh": ("current", "récent"), "stale": ("stale", "périmé"), "invalid": ("invalid", "invalide")}
SOURCE = {"device": ("device", "appareil"), "manual": ("entered by hand", "saisi à la main")}
CALL_STATE = {
    "pressed": ("pressed, not yet sent", "appuyé, pas encore envoyé"), "sent": ("sent", "envoyé"),
    "not_sent": ("not delivered", "non délivré"), "acknowledged": ("acknowledged", "pris en charge"),
    "escalated": ("escalated", "escaladé"), "resolved": ("resolved", "terminé"),
}
UNITS = {"resp_rate": "/min", "spo2": "%", "sys_bp": " mmHg", "pulse": " bpm", "temp_c": " °C"}
SHOWN_PARAMS = ("resp_rate", "spo2", "on_oxygen", "sys_bp", "pulse", "consciousness", "temp_c")
YES_NO = {True: ("yes", "oui"), False: ("no", "non")}


@dataclass(frozen=True)
class Fact:
    id: str
    text: str
    bed: str | None = None


class FactSet:
    """An ordered list of numbered facts, [f1] [f2] ..."""

    def __init__(self) -> None:
        self.items: list[Fact] = []

    def add(self, text: str, bed: str | None = None) -> None:
        self.items.append(Fact(f"f{len(self.items) + 1}", text, bed))

    def as_dict(self) -> dict[str, str]:
        return {f.id: f.text for f in self.items}

    def __len__(self) -> int:
        return len(self.items)


class FactBuilder:
    def __init__(self, ex: Explainer) -> None:
        self.ex = ex
        self.i = 0 if ex.lang == "en" else 1

    # --- small helpers ------------------------------------------------------------------------

    def m(self, key: str, **values: Any) -> str:
        return M[key][self.i].format(**values)

    def age(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        if minutes < 1:
            return "moins d'une minute" if self.i else "under a minute"
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours} h {minutes} min" if minutes else f"{hours} h"
        return f"{minutes} min"

    def value(self, param: str, raw: Any) -> str:
        if isinstance(raw, bool):
            return YES_NO[raw][self.i]
        return self.ex.number(raw) if isinstance(raw, int | float) else str(raw)

    # --- one bed ------------------------------------------------------------------------------

    def bed_facts(self, facts: FactSet, view: dict[str, Any], calls: list[dict[str, Any]], alerts: list[dict[str, Any]],
                  orders: list[dict[str, Any]], vitals: bool = True) -> None:
        bed = view["bed"]
        admission = view.get("admission")
        if not admission:
            facts.add(self.m("empty", bed=bed), bed)
            return
        facts.add(self.m("admitted", bed=bed, patient=admission["patientRef"], time=self.ex.time(admission["admittedAt"]),
                         acuity=admission["acuity"]), bed)
        news2 = view.get("news2")
        if view.get("news2Status") != "ok" or not news2:
            facts.add(self.m("news2_unavailable", bed=bed), bed)
        else:
            conf = round(news2["confidence"]["value"] * 100)
            band = self.ex.band(news2["band"])
            if news2["complete"]:
                facts.add(self.m("news2_complete", bed=bed, total=news2["total"], band=band, conf=conf), bed)
            else:
                unscored = self.ex.params(news2["missing"] + news2["stale"]) or "-"
                facts.add(self.m("news2_partial", bed=bed, total=news2["total"], band=band, params=unscored,
                                 conf=conf), bed)
        if vitals:
            readings = view.get("vitals", {})
            for param in SHOWN_PARAMS:
                reading = readings.get(param)
                name = self.ex.param(param)
                if reading is None:
                    facts.add(self.m("vital_missing", bed=bed, param=name), bed)
                    continue
                facts.add(self.m("vital", bed=bed, param=name, value=self.value(param, reading["value"]),
                                 unit=UNITS.get(param, ""), status=STATUS[reading["status"]][self.i],
                                 age=self.age(reading["ageS"]), source=SOURCE[reading["sourceType"]][self.i]), bed)
        priority = view.get("priority")
        if priority:
            facts.add(self.m("priority", bed=bed, rank=priority["rank"], total=priority["of"],
                             reasons=" ".join(priority["reasons"])), bed)
        nurse = view.get("assignedNurse")
        facts.add(self.m("nurse", bed=bed, nurse=nurse) if nurse else self.m("nobody", bed=bed), bed)
        for call in (c for c in calls if c["bed"] == bed and c["state"] != "resolved"):
            lvl = call["escalationLevel"]
            level = (f" (niveau {lvl})" if self.i else f" (level {lvl})") if lvl else ""
            facts.add(self.m("call", bed=bed, kind=self.ex.kind(call["kind"]), state=CALL_STATE[call["state"]][self.i],
                             level=level, count=call["pressCount"],
                             age=self.age(self._since(call["pressedAt"], view))), bed)
        for alert in (a for a in alerts if a.get("bed") == bed and a.get("active", True)):
            facts.add(self.m("alert", bed=bed, priority=PRIORITY_WORD[alert["priority"]][self.i], headline=alert["explanation"][0]), bed)
            for note in alert.get("instructions", [])[-2:]:
                facts.add(self.m("instruction", bed=bed, time=self.ex.time(note["at"]), text=note["text"]), bed)
        for order in [o for o in orders if o["bed"] == bed][:2]:
            facts.add(self.m("order", bed=bed, time=self.ex.time(order["createdAt"]), text=order["orderText"]), bed)

    @staticmethod
    def _since(timestamp: str, view: dict[str, Any]) -> float:
        """Seconds between a call press and the view's own 'now' (the freshest reading time, else the press itself)."""
        from datetime import datetime

        def parse(ts: str) -> datetime:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))

        news2 = view.get("news2") or {}
        now = news2.get("computedAt")
        return max(0.0, (parse(now) - parse(timestamp)).total_seconds()) if now else 0.0

    def trend_facts(self, facts: FactSet, view: dict[str, Any]) -> None:
        bed, news2 = view["bed"], view.get("news2")
        trend = {t["minutesAgo"]: t["total"] for t in view.get("news2Trend", []) if t.get("total") is not None}
        if not news2 or 60 not in trend or 30 not in trend:
            facts.add(self.m("trend_unknown", bed=bed), bed)
        else:
            facts.add(self.m("trend", bed=bed, before=trend[60], middle=trend[30], total=news2["total"]), bed)

    # --- the ward -----------------------------------------------------------------------------

    def ward_facts(self, facts: FactSet, snap: dict[str, Any], lines: int = 12) -> None:
        admitted = [b for b in snap["beds"] if b.get("admission")]
        if not admitted:
            facts.add(self.m("ward_nobody"))
            return
        bands = {"high": 0, "medium": 0, "low": 0}
        for b in admitted:
            if b.get("news2"):
                bands[b["news2"]["band"]] += 1
        facts.add(self.m("ward_counts", n=len(admitted), high=bands["high"], medium=bands["medium"], low=bands["low"]))
        open_calls = [c for c in snap["calls"] if c["state"] != "resolved"]
        facts.add(self.m("ward_calls", n=len(open_calls),
                         escalated=sum(1 for c in open_calls if c["state"] == "escalated")))
        facts.add(self.m("ward_alerts", n=sum(1 for a in snap["alerts"] if a.get("active", True))))
        on_ward = [s["staffId"] for s in snap["staff"] if s.get("onWard")]
        facts.add(self.m("ward_staff", n=len(on_ward), names=", ".join(on_ward) or "-"))
        ranked = sorted(admitted, key=lambda b: b.get("priority", {}).get("rank", 99))
        for b in ranked[:lines]:
            n2 = b.get("news2")
            if n2:
                facts.add(self.m("ward_line", rank=b["priority"]["rank"], bed=b["bed"], total=n2["total"],
                                 band=self.ex.band(n2["band"]),
                                 partial=(" - " + ("partiel" if self.i else "partial")) if not n2["complete"] else ""),
                          b["bed"])
            else:
                facts.add(self.m("news2_unavailable", bed=b["bed"]), b["bed"])
