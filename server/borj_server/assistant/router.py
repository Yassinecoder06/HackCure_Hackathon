"""Step 1 of ADR 0013: a deterministic intent router. A small fixed set of questions about the ward's current state is
supported; anything else gets "I can only answer questions about the ward's current state". We choose the facts, not
the model: small models are unreliable at choosing what to look up."""

from __future__ import annotations

import re
from dataclasses import dataclass

INTENTS = ("bed_status", "why_ranked", "changes_since", "handover_summary", "ward_summary", "open_calls")

BED_ID = re.compile(r"\bB\s?-?0?(\d{1,2})\b", re.IGNORECASE)
BED_WORD = re.compile(r"\b(?:bed|lit|chambre|room)\s*(?:n°|no\.?|number|numéro|num)?\s*0?(\d{1,2})\b", re.IGNORECASE)

# Keyword lists, English and French. Matching is on the lower-cased question.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "handover_summary": ("handover", "hand over", "hand-over", "relève", "releve", "transmission", "shift summary",
                         "résumé de la garde", "resume de la garde", "summarise", "summarize", "résume", "resume ",
                         "summary", "résumé"),
    "why_ranked": ("why", "pourquoi", "ranked", "rank ", "classé", "classe ", "first priority", "en premier", "priorité",
                   "priority", "prioritaire"),
    "changes_since": ("changed", "change ", "since", "depuis", "trend", "évolu", "evolu", "worse", "better",
                      "worsen", "improv", "aggrav", "amélior", "ameliorat", "deteriorat", "détérior"),
    "open_calls": ("calls", "call ", "appel", "bell", "sonnette", "pressed"),
    "ward_summary": ("ward summary", "summary of the ward", "overview", "state of the ward", "status of the ward",
                     "how is the ward", "on the ward", "who needs", "qui a besoin", "most urgent", "plus urgent",
                     "everyone", "résumé du service", "état du service", "tous les patients", "all beds", "all patients",
                     "tout le monde"),
}


# Questions that ask the system to decide or advise. They are refused, never sent to a model (safety invariant 1).
ADVICE = re.compile(
    r"\b(should (i|we)|what to (give|do)|give (him|her|them|the patient)|what (drug|medication|medicine|dose)|"
    r"which (drug|medication|medicine)|prescribe|treat|treatment|diagnos\w*|dosage|dose of|increase|decrease|"
    r"doit-on|dois-je|que donner|quel (médicament|traitement|dosage)|prescrire|traiter|traitement|diagnostic)\b",
    re.IGNORECASE)


@dataclass(frozen=True)
class Route:
    intent: str
    bed: str | None = None        # normalised to B06, or None
    unknown_bed: str | None = None  # a bed was named but does not exist on this ward
    minutes: int = 60             # for changes_since


def bed_in(question: str) -> str | None:
    for pattern in (BED_ID, BED_WORD):
        if m := pattern.search(question):
            return f"B{int(m.group(1)):02d}"
    return None


def route(question: str, known_beds: set[str], bed: str | None = None) -> Route | None:
    """The intent of a question, or None when it is not one we answer. `bed` is a bed the screen already has selected
    (used when the question itself names none)."""
    text = question.lower().strip()
    if not text:
        return None
    if ADVICE.search(text):
        return Route("advice")
    named = bed_in(question)
    target = named or bed
    unknown = target if target and target not in known_beds else None
    target = None if unknown else target

    def matches(intent: str) -> bool:
        return any(word in text for word in KEYWORDS[intent])

    minutes = 60
    if m := re.search(r"(\d{1,3})\s*(?:min|minute)", text):
        minutes = max(5, min(int(m.group(1)), 120))
    elif re.search(r"\b(\d)\s*(?:h|hr|hour|heure)", text):
        minutes = 60

    for intent in ("handover_summary", "why_ranked", "changes_since", "open_calls", "ward_summary"):
        if matches(intent):
            return Route(intent, target, unknown, minutes)
    if target or unknown:
        return Route("bed_status", target, unknown, minutes)
    return None
