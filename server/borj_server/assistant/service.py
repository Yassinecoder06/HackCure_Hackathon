"""The assistant: question -> route -> facts -> (model -> verifier) -> answer, labelled and audited (ADR 0013).

The deterministic text is always built first. The model's wording replaces it only if the verifier accepts it; every
other path (no model, model down, busy, rejected) shows the deterministic text. Whatever is shown, the facts are
returned with it so a nurse can check the source, and the request is written to the hash-chained audit log
(safety invariant 11).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from ..explain import Explainer
from ..live import build_snapshot
from ..timeutil import format_ts
from .facts import FactBuilder, FactSet
from .ollama import OllamaClient
from .router import Route, route
from .verify import verify

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "assistant.yaml"

LABEL = {
    "llm": ("AI summary of the ward data. Advisory: check the source facts.",
            "Résumé par IA des données du service. À titre indicatif : vérifiez les faits sources."),
    "template": ("Generated from the ward data by fixed rules. Advisory.",
                 "Généré à partir des données du service par des règles fixes. À titre indicatif."),
    "none": ("", ""),
}
ABSTAIN = {
    "unsupported": ("I can only answer questions about the ward's current state: a bed's status, why a bed is ranked, "
                    "what changed, open calls, a ward summary or a handover.",
                    "Je ne réponds qu'aux questions sur l'état actuel du service : l'état d'un lit, pourquoi un lit est "
                    "classé ainsi, ce qui a changé, les appels ouverts, un résumé du service ou une relève."),
    "unknown_bed": ("There is no bed {bed} on this ward.", "Il n'y a pas de lit {bed} dans ce service."),
    "advice": ("I describe the ward's data. I do not give clinical advice, diagnoses or treatment recommendations: "
               "that is for the clinician.",
               "Je décris les données du service. Je ne donne ni conseil clinique, ni diagnostic, ni recommandation de "
               "traitement : cela revient au clinicien."),
    "no_data": ("The data does not cover that question.", "Les données ne couvrent pas cette question."),
}


@dataclass(frozen=True)
class AssistantConfig:
    enabled: bool
    url: str
    model: str
    timeout_s: float
    seed: int
    max_tokens: int
    max_concurrent: int
    max_question: int

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG, env: dict[str, str] | None = None) -> AssistantConfig:
        import os

        env = os.environ if env is None else env
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        llm = d["llm"]
        enabled = str(env.get("BORJ_ASSISTANT_LLM", llm["enabled"])).lower() in ("1", "true", "yes", "on")
        return cls(enabled=enabled, url=env.get("OLLAMA_URL", llm["url"]), model=env.get("OLLAMA_MODEL", llm["model"]),
                   timeout_s=float(llm["timeout_s"]), seed=int(llm["seed"]), max_tokens=int(llm["max_tokens"]),
                   max_concurrent=int(llm["max_concurrent"]), max_question=int(d["questions"]["max_length"]))


class AssistantService:
    def __init__(self, app: FastAPI, cfg: AssistantConfig, llm: Any | None = None) -> None:
        self.app, self.cfg = app, cfg
        # `llm` is anything with chat(question, facts, lang) -> LlmReply | None (tests plug in a fake).
        if llm is False:
            self.llm = None  # explicitly no model
        elif llm is not None:
            self.llm = llm
        else:
            self.llm = OllamaClient(cfg.url, cfg.model, cfg.timeout_s, cfg.seed, cfg.max_tokens) if cfg.enabled else None
        self._slots = threading.BoundedSemaphore(cfg.max_concurrent)
        self.stats = {"asked": 0, "abstained": 0, "template": 0, "llm_accepted": 0, "llm_rejected": 0,
                      "llm_unavailable": 0, "llm_busy": 0}
        self.rejections: dict[str, int] = {}

    # --- status -------------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        if self.llm is None:
            state = "disabled"
        else:
            probe = getattr(self.llm, "available", None)
            state = "available" if (probe is None or probe()) else "unavailable"
        judged = self.stats["llm_accepted"] + self.stats["llm_rejected"]
        return {"llm": state, "model": self.cfg.model if self.llm is not None else None, **self.stats,
                "verifierRejectionRate": round(self.stats["llm_rejected"] / judged, 3) if judged else None,
                "rejections": dict(self.rejections)}

    # --- the pipeline -------------------------------------------------------------------------

    def ask(self, question: str, lang: str, who: str, bed: str | None = None) -> dict[str, Any]:
        ingestor = self.app.state.ingestor
        ex = Explainer(lang, self.app.state.meds_config.ward_tz)
        i = 0 if lang == "en" else 1
        self.stats["asked"] += 1
        question = " ".join(question.split())[: self.cfg.max_question]
        with ingestor.lock:
            known = set(ingestor.twin.beds)
        found = route(question, known, bed)
        if found is None or found.unknown_bed or found.intent == "advice":
            self.stats["abstained"] += 1
            if found is None:
                text = ABSTAIN["unsupported"][i]
            elif found.intent == "advice":
                text = ABSTAIN["advice"][i]
            else:
                text = ABSTAIN["unknown_bed"][i].format(bed=found.unknown_bed)
            return self._finish(who, question, lang, found, [], text, "none", None, None)

        facts = self._facts(found, ex)
        template = " ".join(f.text for f in facts.items)
        if not len(facts):
            self.stats["abstained"] += 1
            return self._finish(who, question, lang, found, [], ABSTAIN["no_data"][i], "none", None, None)

        answer, source, rejected, citations = template, "template", None, [f.id for f in facts.items]
        if self.llm is not None:
            reply = self._try_model(question, facts, lang)
            if reply == "busy":
                self.stats["llm_busy"] += 1
            elif reply is None:
                self.stats["llm_unavailable"] += 1
            else:
                verdict = verify(reply.answer, reply.citations, facts.as_dict(), question, self._drug_names())
                if verdict:
                    self.stats["llm_accepted"] += 1
                    answer, source = reply.answer, "llm"
                    citations = list(dict.fromkeys(c.lower() for c in reply.citations))
                else:
                    self.stats["llm_rejected"] += 1
                    self.rejections[verdict.reason] = self.rejections.get(verdict.reason, 0) + 1
                    rejected = {"reason": verdict.reason, "detail": verdict.detail}
        if source == "template":
            self.stats["template"] += 1
        return self._finish(who, question, lang, found, facts.items, answer, source, rejected, template,
                            citations=citations)

    def _try_model(self, question: str, facts: FactSet, lang: str):
        if not self._slots.acquire(blocking=False):
            return "busy"
        try:
            return self.llm.chat(question, facts.as_dict(), lang)
        finally:
            self._slots.release()

    def _drug_names(self) -> list[str]:
        ingestor = self.app.state.ingestor
        with ingestor.lock:
            drugs = {w.lower() for rx in ingestor.twin.prescriptions.values()
                     for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", rx.drug)}
        return sorted(drugs)

    # --- facts per intent ---------------------------------------------------------------------

    def _facts(self, found: Route, ex: Explainer) -> FactSet:
        ingestor = self.app.state.ingestor
        snap = build_snapshot(self.app, ex)
        with ingestor.lock:
            twin = ingestor.twin
            orders = [{"bed": o.bed, "orderText": o.text, "createdAt": format_ts(o.ts)}
                      for o in sorted(twin.doctor_orders.values(), key=lambda o: o.ts, reverse=True)]
        builder, facts = FactBuilder(ex), FactSet()
        beds = {b["bed"]: b for b in snap["beds"]}
        calls, alerts = snap["calls"], snap["alerts"]
        intent, bed = found.intent, found.bed

        if intent in ("bed_status", "why_ranked", "changes_since", "handover_summary") and bed is None:
            if intent == "bed_status":
                intent = "ward_summary"
            elif intent == "why_ranked":
                top = next((b for b in sorted(snap["beds"], key=lambda b: b.get("priority", {}).get("rank", 99))
                            if b.get("admission")), None)
                bed = top["bed"] if top else None
                if bed is None:
                    return facts
            else:
                intent = "ward_" + intent  # a ward-level changes / handover

        if intent == "bed_status":
            builder.bed_facts(facts, beds[bed], calls, alerts, orders)
            builder.trend_facts(facts, beds[bed])
        elif intent == "why_ranked":
            builder.bed_facts(facts, beds[bed], calls, alerts, orders, vitals=False)
            builder.trend_facts(facts, beds[bed])
        elif intent == "changes_since":
            builder.trend_facts(facts, beds[bed])
        elif intent == "handover_summary":
            builder.bed_facts(facts, beds[bed], calls, alerts, orders)
            builder.trend_facts(facts, beds[bed])
        elif intent == "ward_changes_since":
            for b in sorted((b for b in snap["beds"] if b.get("admission")),
                            key=lambda b: b.get("priority", {}).get("rank", 99))[:12]:
                builder.trend_facts(facts, b)
        elif intent == "open_calls":
            builder.ward_facts(facts, snap, lines=0)
            for b in snap["beds"]:
                if b.get("admission") and any(c["bed"] == b["bed"] and c["state"] != "resolved" for c in calls):
                    builder.bed_facts(facts, b, calls, [], [], vitals=False)
        else:  # ward_summary, ward_handover_summary
            builder.ward_facts(facts, snap)
            if intent == "ward_handover_summary":
                for b in sorted((b for b in snap["beds"] if b.get("admission") and b.get("news2")
                                 and b["news2"]["band"] != "low"),
                                key=lambda b: b["priority"]["rank"])[:5]:
                    builder.trend_facts(facts, b)
                for order in orders[:3]:
                    facts.add(builder.m("order", bed=order["bed"], time=ex.time(order["createdAt"]),
                                        text=order["orderText"]), order["bed"])
        return facts

    # --- result and audit ---------------------------------------------------------------------

    def _finish(self, who: str, question: str, lang: str, found: Route | None, facts, answer: str, source: str,
                rejected: dict[str, str] | None, template: str | None, citations: list[str] | None = None):
        ingestor = self.app.state.ingestor
        result = {
            "intent": found.intent if found else None, "bed": found.bed if found else None, "answer": answer,
            "source": source, "label": LABEL[source][0 if lang == "en" else 1], "abstained": source == "none",
            "citations": citations or [], "facts": [{"id": f.id, "text": f.text} for f in facts],
            "model": self.cfg.model if source == "llm" else None, "lang": lang,
            "generatedAt": format_ts(ingestor.event_now()),
        }
        if template is not None and source == "llm":
            result["template"] = template
        if rejected:
            result["modelAnswerRejected"] = rejected
        ingestor.store.audit(who, "assistant.ask", result["bed"] or "ward", {
            "question": question, "intent": result["intent"], "source": source, "answer": answer,
            "citations": result["citations"], "rejected": rejected})
        return result
