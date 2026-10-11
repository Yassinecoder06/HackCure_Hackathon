"""The verifier: the last gate before anything a language model wrote reaches a nurse (ADR 0013).

A model answer is accepted only if everything checkable in it is traceable to the numbered facts it cites:
- every citation points at a fact that exists, and there is at least one;
- every number, bed id, clock time and staff id in the answer appears in a cited fact (or in the question);
- it contains no diagnosis, treatment, dosing or reassurance wording (the system is advisory and never gives clinical
  advice; safety invariants 1 and 12).
Anything else is rejected and the caller shows the deterministic template text instead. This is deterministic code with
no model in it, so it can be tested and measured (the rejection rate is the hallucination rate we report).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
BED = re.compile(r"\bB\s?-?(\d{1,2})\b", re.IGNORECASE)
STAFF = re.compile(r"\b(?:CN|CA|DR|N)\d{1,2}\b")
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
CITE = re.compile(r"\[\s*f(\d+)\s*\]", re.IGNORECASE)
LIST_MARK = re.compile(r"(?m)^\s*(?:[-*•]\s+|\d{1,2}[.)]\s+)")

# Words a clinical decision-support tool must not produce on its own. Whole words, case-insensitive, EN and FR.
# TO BE VALIDATED BY A CLINICIAN: extend, never shrink. The names of the drugs prescribed on the ward are added at run
# time (`extra_forbidden`): the facts never contain a drug, so a drug name in an answer can only be invented.
FORBIDDEN = (
    "diagnose", "diagnosis", "diagnosed", "diagnostic", "diagnostique", "diagnostiquer", "treat", "treated", "treatment",
    "traitement", "traiter", "prescribe", "prescribed", "prescription", "prescrire", "administer", "administered",
    "administrer", "dose", "dosage", "dosing", "antibiotic", "antibiotics", "antibiotique", "antibiotiques", "sepsis",
    "pneumonia", "pneumonie", "infection", "infarct", "stroke", "avc", "reassure", "reassuring", "reassurance",
    "rassurant", "rassurante", "rassurer", "no need to worry", "pas d'inquiétude", "ne vous inquiétez pas",
    "should receive", "should be given", "devrait recevoir", "il faut donner", "i recommend", "je recommande",
    "recommend", "recommandé", "recommande", "likely", "probably", "probablement", "caused by", "causé par",
    "because of an", "due to an", "en raison d'une",
)
_FORBIDDEN = re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in FORBIDDEN) + r")(?![\w])", re.IGNORECASE)


def normalize_number(text: str) -> str:
    value = float(text.replace(",", "."))
    return f"{value:g}"


def tokens(text: str) -> set[str]:
    """The checkable things in a text: bed ids (B06), clock times (08:15), staff ids (N2) and numbers (38.5)."""
    found: set[str] = set()
    for m in TIME.finditer(text):
        found.add(f"t{int(m.group(1)):02d}:{m.group(2)}")
    rest = TIME.sub(" ", text)
    for m in BED.finditer(rest):
        found.add(f"B{int(m.group(1)):02d}")
    rest = BED.sub(" ", rest)
    for m in STAFF.finditer(rest):
        found.add(m.group(0).upper())
    rest = STAFF.sub(" ", rest)
    rest = CITE.sub(" ", rest)
    rest = LIST_MARK.sub(" ", rest)  # "1." or "-" bullets are layout, not claims
    for m in NUMBER.finditer(rest):
        found.add("n" + normalize_number(m.group(0)))
    return found


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""  # a short machine-readable code when not ok
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


def verify(answer: str, citations: list[str], facts: dict[str, str], question: str = "",
           extra_forbidden: Iterable[str] = ()) -> Verdict:
    """facts maps a fact id ('f1') to the fact's text."""
    if not answer.strip():
        return Verdict(False, "empty")
    cited = [c.lower() for c in citations]
    inline = [f"f{n}" for n in CITE.findall(answer)]
    all_cites = list(dict.fromkeys([*cited, *inline]))
    if not all_cites:
        return Verdict(False, "no_citation", "an answer must cite at least one fact")
    unknown = [c for c in all_cites if c not in facts]
    if unknown:
        return Verdict(False, "unknown_citation", ", ".join(unknown))
    if (bad := _FORBIDDEN.search(answer)) is not None:
        return Verdict(False, "forbidden_wording", bad.group(0))
    for name in extra_forbidden:
        if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", answer, re.IGNORECASE):
            return Verdict(False, "drug_name", name)

    allowed: set[str] = set(tokens(question))
    for fact_id in all_cites:
        allowed |= tokens(facts[fact_id])
    unsupported = sorted(tokens(answer) - allowed)
    if unsupported:
        return Verdict(False, "unsupported_value", ", ".join(t.lstrip("nt") if t[0] in "nt" else t for t in unsupported))
    return Verdict(True)
