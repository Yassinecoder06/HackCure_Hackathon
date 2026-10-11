"""Grounded, verified local LLM explainability layer (ADR 0013).

Grounds explanations on structured facts extracted from the live ward twin and event log.
Uses the local Gemma 4 quantized model (gemma4-ab-qat:e4b) via Ollama with temperature 0.0.
Every claim must cite [f1], [f2], etc. If verification fails or Ollama is unavailable,
falls back gracefully to deterministic templates (safety invariant 1).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from .explain import Explainer

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://10.42.0.1:11434"
DEFAULT_MODEL = "gemma4-ab-qat:e4b"


class GroundedExplainer:
    def __init__(
        self,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 12.0,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def build_bed_facts(
        self,
        bed_id: str,
        bed: dict[str, Any],
        admission: dict[str, Any] | None = None,
        alerts: list[dict[str, Any]] | None = None,
        nurse_id: str | None = None,
        nurse_name: str | None = None,
        priority_rank: int | None = None,
    ) -> list[str]:
        """Build numbered clinical facts from the digital twin (ADR 0013 step 2)."""
        facts: list[str] = []
        fid = 1

        # f1: Bed location & admission
        room = bed.get("room", f"Chamber {bed_id}")
        if admission:
            p_name = admission.get("patientName", "Patient")
            adm_id = admission.get("admissionId", "Unknown")
            age = admission.get("age")
            age_str = f", age {age}" if age else ""
            facts.append(f"[f{fid}] Bed {bed_id} ({room}) is occupied by {p_name} (Admission {adm_id}{age_str}).")
        else:
            facts.append(f"[f{fid}] Bed {bed_id} is located in {room}.")
        fid += 1

        # f2: NEWS2 score & risk band
        news2 = bed.get("news2")
        if news2 and isinstance(news2, dict):
            score = news2.get("total", 0)
            band = news2.get("band", "low")
            facts.append(f"[f{fid}] Current NEWS2 score is {score} ({band} risk band).")
            fid += 1

            # f3: Components
            components = news2.get("components", [])
            active_pts = [
                f"{c.get('param', '').replace('_', ' ').capitalize()}: {c.get('value')} (+{c.get('points', 0)} pts)"
                for c in components
                if c.get("value") is not None and c.get("points", 0) > 0
            ]
            if active_pts:
                facts.append(f"[f{fid}] Contributing physiological parameters: {', '.join(active_pts)}.")
                fid += 1

            # f4: Protocol directive
            resp = news2.get("response")
            if resp:
                facts.append(f"[f{fid}] NEWS2 protocol directive: {resp}.")
                fid += 1

            # Freshness / confidence
            conf = news2.get("confidence")
            if conf and isinstance(conf, dict):
                basis = conf.get("basis", "")
                if basis:
                    facts.append(f"[f{fid}] Data quality: {basis}.")
                    fid += 1

        # Active call state
        call = bed.get("call")
        if call and isinstance(call, dict) and call.get("state") not in ("resolved", None):
            kind = call.get("kind", "assist")
            state = call.get("state", "active")
            level = call.get("level", 0)
            pressed = call.get("pressedAt", "")
            facts.append(f"[f{fid}] Active {kind} call (state: {state}, escalation level {level}, pressed: {pressed}).")
            fid += 1

        # Active alerts
        if alerts:
            alert_descs = [a.get("headline", a.get("reason", "active alert")) for a in alerts]
            facts.append(f"[f{fid}] Active alerts: {'; '.join(alert_descs)}.")
            fid += 1

        # Primary nurse
        if nurse_id or nurse_name:
            nurse_desc = f"{nurse_name} ({nurse_id})" if nurse_name and nurse_id else (nurse_name or nurse_id)
            facts.append(f"[f{fid}] Assigned nursing care: {nurse_desc}.")
            fid += 1

        # Priority rank
        if priority_rank:
            facts.append(f"[f{fid}] Ward triage rank: #{priority_rank} priority.")
            fid += 1

        return facts

    def _call_ollama(self, prompt: str) -> str | None:
        """Query local Ollama instance with fallback to host/bridge IPs."""
        urls = [self.ollama_url]
        for candidate in ("http://10.42.0.1:11434", "http://172.20.0.1:11434", "http://localhost:11434"):
            if candidate not in urls:
                urls.append(candidate)

        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "top_p": 0.9},
        }).encode("utf-8")

        for url in urls:
            endpoint = f"{url}/api/generate"
            req = urllib.request.Request(
                endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    data = json.load(resp)
                    return data.get("response", "").strip()
            except Exception as exc:
                log.debug("Ollama request to %s failed: %s", endpoint, exc)
                continue
        return None

    def verify(self, response: str, facts: list[str]) -> tuple[bool, list[str]]:
        """Verify that claims cite fact tags and do not invent fact numbers (ADR 0013 step 4)."""
        citations: list[str] = []
        # Find all brackets like [f1] or [f1, f2, f3]
        bracketed = re.findall(r"\[(f\d+(?:[,\s]+f\d+)*)\]", response)
        for group in bracketed:
            parts = re.findall(r"f\d+", group)
            citations.extend([f"[{p}]" for p in parts])

        if not citations:
            return False, []

        max_fact = len(facts)
        valid_citations = []
        for c in citations:
            match = re.search(r"\d+", c)
            if match:
                idx = int(match.group(0))
                if 1 <= idx <= max_fact:
                    valid_citations.append(c)
                else:
                    log.warning("Verifier: hallucinated citation %s exceeds fact count %d", c, max_fact)
                    return False, []

        return True, list(dict.fromkeys(valid_citations))

    def explain_bed(
        self,
        bed_id: str,
        bed: dict[str, Any],
        admission: dict[str, Any] | None = None,
        alerts: list[dict[str, Any]] | None = None,
        nurse_id: str | None = None,
        nurse_name: str | None = None,
        question: str | None = None,
        lang: str = "en",
    ) -> dict[str, Any]:
        """Produce verified clinical explanation grounded on structured facts (ADR 0013)."""
        facts = self.build_bed_facts(bed_id, bed, admission, alerts, nurse_id, nurse_name)

        if not facts:
            return {
                "bed": bed_id,
                "summary": "No clinical facts available for this bed.",
                "model": self.model,
                "verified": True,
                "citations": [],
                "facts": [],
                "fallback": False,
                "disclaimer": "AI summary: check source data (ADR 0013)",
            }

        facts_text = "\n".join(facts)
        lang_instruction = (
            "Language: Respond strictly in French."
            if lang == "fr"
            else "Language: Respond strictly in English."
        )

        user_goal = (
            f"Question from clinician: {question}"
            if question
            else "Provide a concise 2-sentence clinical handover briefing for the nurse in charge."
        )

        prompt = f"""You are the Borj-PiCare Clinical Assistant running locally on the hospital ward.
Goal: {user_goal}
{lang_instruction}

SAFETY RULES (MANDATORY):
1. Rely EXCLUSIVELY on the numbered facts [f1], [f2], etc.
2. Do NOT invent medications, diagnoses, or values not explicitly stated in the facts.
3. Every sentence MUST cite its supporting fact tag like [f1] or [f2].
4. Be concise (2 to 3 sentences maximum), direct, and objective.

Facts:
{facts_text}
"""

        raw_output = self._call_ollama(prompt)

        if raw_output:
            is_valid, citations = self.verify(raw_output, facts)
            if is_valid:
                return {
                    "bed": bed_id,
                    "summary": raw_output,
                    "model": self.model,
                    "verified": True,
                    "citations": citations,
                    "facts": facts,
                    "fallback": False,
                    "disclaimer": "AI summary: check source data (Local Gemma 4 QAT • ADR 0013)",
                }
            log.warning("Verifier rejected LLM output for bed %s; falling back to templates", bed_id)

        # Fallback to deterministic template (Explainer)
        ex = Explainer(lang=lang)
        news2 = bed.get("news2", {})
        band = news2.get("band", "low")
        total = news2.get("total", 0)
        resp_text = news2.get("response", "")
        fallback_summary = (
            f"Lit {bed_id} : NEWS2 {total} ({ex.band(band)}). {resp_text} [f1]"
            if lang == "fr"
            else f"Bed {bed_id}: NEWS2 {total} ({ex.band(band)}). {resp_text} [f1]"
        )

        return {
            "bed": bed_id,
            "summary": fallback_summary,
            "model": "deterministic-template",
            "verified": True,
            "citations": ["[f1]"],
            "facts": facts,
            "fallback": True,
            "disclaimer": "Deterministic clinical template (Local LLM unavailable or unverified)",
        }
