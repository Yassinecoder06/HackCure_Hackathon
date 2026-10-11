"""Every user-facing sentence, in English and French, in one place (ADR 0011, HackCure section 6).

Explanations are templates over the rule that fired: deterministic, exact, and reviewable by a
clinician in one sitting. Style rule: say what the data shows, never what the patient has
("NEWS2 7: emergency clinical response", never a diagnosis).

The inference layer is language-neutral: it returns reason codes with parameters, and the server
renders them here. Times are shown in ward local time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

LANGS = ("en", "fr")

PARAMS = {
    "resp_rate": ("respiratory rate", "fréquence respiratoire"),
    "spo2": ("SpO2", "SpO2"),
    "spo2_scale": ("SpO2 scale", "échelle SpO2"),
    "on_oxygen": ("oxygen status", "oxygénothérapie"),
    "sys_bp": ("systolic BP", "pression artérielle systolique"),
    "pulse": ("pulse", "pouls"),
    "consciousness": ("consciousness (ACVPU)", "conscience (ACVPU)"),
    "temp_c": ("temperature", "température"),
}
BANDS = {
    "low": ("low risk", "risque faible"),
    "low_medium": ("a single parameter at 3", "un paramètre à 3"),
    "medium": ("medium risk", "risque moyen"),
    "high": ("high risk", "risque élevé"),
}
KINDS = {"assist": ("assist", "d'assistance"), "comfort": ("comfort", "de confort")}
SOLVER = {"optimal": ("optimal", "optimal"), "feasible": ("feasible", "réalisable"),
          "infeasible": ("infeasible", "sans solution")}

MESSAGES: dict[str, tuple[str, str]] = {
    # NEWS2 (response texts follow the RCP NEWS2 clinical response; to be confirmed by a clinician)
    "news2.response.low": ("Continue routine monitoring per ward protocol.",
                           "Poursuivre la surveillance habituelle selon le protocole du service."),
    "news2.response.low_medium": ("Urgent ward-based review.", "Évaluation urgente par l'équipe du service."),
    "news2.response.medium": ("Urgent clinical response (key threshold).", "Réponse clinique urgente (seuil clé)."),
    "news2.response.high": ("Emergency clinical response.", "Réponse clinique en urgence."),
    "news2.label.complete": ("NEWS2 {total}", "NEWS2 {total}"),
    "news2.label.partial": ("Partial NEWS2, at least {total}: {gaps}", "NEWS2 partiel, au moins {total} : {gaps}"),
    "news2.gap.missing": ("missing {params}", "manquant : {params}"),
    "news2.gap.stale": ("stale {params}", "périmé : {params}"),
    "news2.gap.invalid": ("invalid {params}", "invalide : {params}"),
    "news2.gap.scale2": ("SpO2 scale 2 needs a fresh oxygen status",
                         "l'échelle SpO2 2 exige un statut d'oxygène récent"),
    "news2.basis": ("{scored} of {n} parameters fresh and valid", "{scored} paramètres sur {n} récents et valides"),
    "news2.basis.unscored": ("; not scored: {params}", " ; non pris en compte : {params}"),
    # Alerts
    "alert.news2.headline": ("NEWS2 {qualifier}{total}: {response}", "NEWS2 {qualifier}{total} : {response}"),
    "alert.news2.at_least": ("at least ", "au moins "),
    "alert.news2.component": ("{param} {value} scores {points}", "{param} {value} : {points} point(s)"),
    "alert.stale": ("No fresh reading for: {params}. These values are not used.",
                    "Aucune mesure récente pour : {params}. Ces valeurs ne sont pas utilisées."),
    "alert.stale.basis": ("reading age compared with each sensor's freshness limit",
                          "âge des mesures comparé à la limite de fraîcheur de chaque capteur"),
    "alert.device": ("{device} reported '{status}' at {time}; its readings will go stale.",
                     "{device} a signalé « {status} » à {time} ; ses mesures vont devenir périmées."),
    "alert.device.basis": ("device status message", "message d'état de l'appareil"),
    "alert.dose": ("{label} for {bed} was due at {time} and has not been recorded by a nurse.",
                   "{label} pour {bed} était prévu à {time} et n'a pas été enregistré par un soignant."),
    "alert.dose.basis": ("doctor's prescription schedule and nurse records",
                         "horaires de la prescription médicale et enregistrements infirmiers"),
    "alert.call": ("{kind} call from {bed} escalated to level {level}: {reason}.",
                   "Appel {kind} de {bed} escaladé au niveau {level} : {reason}."),
    "alert.call.pressed": ("Pressed at {time}.", "Appel déclenché à {time}."),
    "alert.call.pressed_late": ("Pressed at {time} (delivered late after a link outage).",
                                "Appel déclenché à {time} (transmis en retard après une coupure de liaison)."),
    "alert.call.basis": ("deterministic rule on press time, presses and NEWS2",
                         "règle déterministe sur l'heure d'appel, les appuis et le NEWS2"),
    "reason.unacknowledged_timeout": ("not acknowledged in time", "non pris en charge à temps"),
    "reason.repeat_press": ("the patient pressed again", "le patient a rappelé"),
    "reason.high_news2": ("the patient's NEWS2 is high", "le NEWS2 du patient est élevé"),
    "reason.triple_tap_emergency": ("patient tapped call button 3 times (urgent emergency)",
                                    "le patient a appuyé 3 fois sur la sonnette (urgence immédiate)"),
    # Assignment suggestion reasons (codes come from the inference layer)
    "assign.uncovered": ("{count} bed(s) had no available nurse and are now covered: {beds}.",
                         "{count} lit(s) sans infirmier disponible, désormais couvert(s) : {beds}."),
    "assign.busiest": ("Busiest nurse's workload (acuity + NEWS2): {before} → {after}.",
                       "Charge de l'infirmier le plus occupé (acuité + NEWS2) : {before} → {after}."),
    "assign.continuity": ("Continuity of care: {kept} of {total} covered beds keep their nurse.",
                          "Continuité des soins : {kept} lits couverts sur {total} gardent leur infirmier."),
    "assign.high_news2_moved": ("{bed} (NEWS2 {news2}) goes to {nurse}, who then carries {load}.",
                                "{bed} (NEWS2 {news2}) est confié à {nurse}, dont la charge passe à {load}."),
    "assign.rooms": ("Rooms per nurse: at most {max}.", "Chambres par infirmier : au plus {max}."),
    "assign.no_beds": ("No occupied beds.", "Aucun lit occupé."),
    "assign.no_nurses": ("No nurse is on the ward: nothing can be assigned.",
                         "Aucun infirmier dans le service : aucune affectation possible."),
    "assign.missing_skill": ("No nurse on the ward has the skills needed for: {beds}.",
                             "Aucun infirmier présent n'a les compétences requises pour : {beds}."),
    "assign.infeasible": ("No assignment satisfies the constraints (locked beds, skills, bed cap).",
                          "Aucune affectation ne respecte les contraintes (lits verrouillés, compétences, plafond)."),
    "assign.basis": ("solver {status}; NEWS2 fresh for {fresh} of {total} occupied beds",
                     "solveur {status} ; NEWS2 récent pour {fresh} lits occupés sur {total}"),
    # What-if assumptions (codes come from the inference layer)
    "whatif.calls": ("Calls: {rate}/h for the ward, {share}% non-clinical, {minutes} min each on average.",
                     "Appels : {rate}/h pour le service, {share} % non cliniques, {minutes} min chacun en moyenne."),
    "whatif.obs": ("Observation rounds every {intervals}, {minutes} min each.",
                   "Tours de surveillance toutes les {intervals}, {minutes} min chacun."),
    "whatif.meds": ("Medication doses: {rate} per bed per hour, {minutes} min each.",
                    "Doses de médicaments : {rate} par lit et par heure, {minutes} min chacune."),
    "whatif.admission": ("Admission assessment: {minutes} min of nurse time per new patient.",
                         "Bilan d'admission : {minutes} min de temps infirmier par nouveau patient."),
    "whatif.illustrative": ("Illustrative values, to be calibrated with timings measured in a shadow-mode pilot.",
                            "Valeurs indicatives, à calibrer avec des durées mesurées lors d'un pilote en parallèle."),
    "whatif.capacity": ("Moving beds between the same nurses does not change capacity: only who is available does.",
                        "Répartir les lits autrement entre les mêmes infirmiers ne change pas la capacité : "
                        "seul le nombre de soignants disponibles compte."),
    "whatif.partial_news2": ("{count} bed(s) have no complete NEWS2: simulated with their minimum band (or low risk "
                             "if unavailable), so their workload may be underestimated.",
                             "{count} lit(s) sans NEWS2 complet : simulés avec leur niveau minimum (ou risque faible "
                             "s'il est indisponible), leur charge peut donc être sous-estimée."),
    # Medication clashes
    "meds.clash.doses": ("{count} doses due within {window} min for {who} ({beds})",
                         "{count} doses prévues en {window} min pour {who} ({beds})"),
    "meds.clash.infusions": ("{count} infusions due within {window} min for {who} ({beds})",
                             "{count} perfusions prévues en {window} min pour {who} ({beds})"),
    "meds.unassigned": ("unassigned beds", "les lits non affectés"),
    # Bed priority and NEWS2 trend
    "priority.rank": ("Rank {rank} of {of}", "Rang {rank} sur {of}"),
    "priority.news2": ("NEWS2 {qualifier}{total} ({band}).", "NEWS2 {qualifier}{total} ({band})."),
    "priority.trend.up": ("NEWS2 rose from {before} to {after} in the last {minutes} min.",
                          "Le NEWS2 est passé de {before} à {after} en {minutes} min."),
    "priority.trend.down": ("NEWS2 fell from {before} to {after} in the last {minutes} min.",
                            "Le NEWS2 a baissé de {before} à {after} en {minutes} min."),
    "priority.call": ("{kind} call waiting {minutes} min (level {level}).",
                      "Appel {kind} en attente depuis {minutes} min (niveau {level})."),
    "priority.doses": ("{count} dose(s) overdue.", "{count} dose(s) en retard."),
    "priority.partial": ("Score incomplete: check {params}.", "Score incomplet : vérifier {params}."),
    "priority.none": ("No active trigger.", "Aucun déclencheur actif."),
}


def pick_lang(*candidates: str | None, default: str = "en") -> str:
    """First supported language among e.g. ?lang=, then the Accept-Language header."""
    for candidate in candidates:
        if not candidate:
            continue
        for part in candidate.split(","):
            code = part.split(";")[0].strip().lower()[:2]
            if code in LANGS:
                return code
    return default


@dataclass(frozen=True)
class Explainer:
    lang: str = "en"
    tz: timezone = timezone(timedelta(hours=1))

    @property
    def _i(self) -> int:
        return LANGS.index(self.lang)

    def say(self, key: str, **params: Any) -> str:
        return MESSAGES[key][self._i].format(**params)

    def param(self, name: str) -> str:
        return PARAMS.get(name, (name, name))[self._i]

    def params(self, names: list[str]) -> str:
        return ", ".join(self.param(n) for n in names)

    def band(self, band: str) -> str:
        return BANDS[band][self._i]

    def kind(self, kind: str, capital: bool = False) -> str:
        text = KINDS[kind][self._i]
        return text.capitalize() if capital and self.lang == "en" else text

    def time(self, when: datetime | str) -> str:
        if isinstance(when, str):
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        return when.astimezone(self.tz).strftime("%H:%M")

    def number(self, value: float) -> str:
        text = f"{value:g}"
        return text.replace(".", ",") if self.lang == "fr" else text

    def items(self, items: list[dict[str, Any]]) -> list[str]:
        """Render reason/assumption items {code, params} coming from the inference layer."""
        out = []
        for item in items:
            p = dict(item.get("params", {}))
            if item["code"] == "assign.basis":
                p["status"] = SOLVER[p["status"]][self._i]
            if item["code"] == "whatif.obs":
                p["intervals"] = ", ".join(f"{self.number(m)} min ({self.band(b)})" for b, m in p["intervals"])
            for key in ("before", "after", "load", "rate", "minutes"):
                if isinstance(p.get(key), float):
                    p[key] = self.number(p[key])
            out.append(self.say(item["code"], **p))
        return out

    # --- NEWS2 ------------------------------------------------------------------------------

    def news2(self, result: dict[str, Any]) -> dict[str, Any]:
        """Re-render a NEWS2 result's label, response and confidence basis in this language."""
        invalid = [c["param"] for c in result["components"] if c["status"] == "invalid"]
        missing = [p for p in result["missing"] if p not in invalid]
        scale2 = any(c["param"] == "spo2" and c["status"] == "fresh" and "points" not in c
                     for c in result["components"])
        missing = [p for p in missing if not (scale2 and p == "spo2")]
        if result["complete"]:
            label = self.say("news2.label.complete", total=result["total"])
        else:
            gaps = []
            if missing:
                gaps.append(self.say("news2.gap.missing", params=self.params(missing)))
            if result["stale"]:
                gaps.append(self.say("news2.gap.stale", params=self.params(result["stale"])))
            if invalid:
                gaps.append(self.say("news2.gap.invalid", params=self.params(invalid)))
            if scale2:
                gaps.append(self.say("news2.gap.scale2"))
            label = self.say("news2.label.partial", total=result["total"], gaps="; ".join(gaps))
        scored = sum(1 for c in result["components"] if "points" in c)
        basis = self.say("news2.basis", scored=scored, n=len(result["components"]))
        unscored = result["missing"] + result["stale"]
        if unscored:
            basis += self.say("news2.basis.unscored", params=self.params(unscored))
        return {**result, "label": label, "response": self.say(f"news2.response.{result['band']}"),
                "confidence": {**result["confidence"], "basis": basis}}
