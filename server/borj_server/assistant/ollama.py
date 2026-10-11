"""Step 3 of ADR 0013: the local language model, through Ollama on this machine. No patient data leaves it.

The model is called with temperature 0 and a fixed seed, and its reply is constrained to a JSON object
{"answer": "...", "citations": ["f1", ...]} so the verifier can check it. If Ollama is not running, the model is not
installed, or it times out, `chat` returns None and the caller shows the deterministic text: nothing urgent depends on
this layer and the system works fully without it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "citations"],
}

SYSTEM = """You are a read-only assistant for nurses on a hospital ward. You answer ONLY from the numbered facts the user gives you.
Rules:
- Use only information that is in the facts. Never add a number, bed, time, name, cause, diagnosis, treatment or advice that is not in them.
- Cite the facts you used inline as [f1], [f2] and list their ids in "citations".
- If the facts do not answer the question, say that the data does not cover it.
- Do not reassure and do not recommend actions: describe the data. Data marked stale, missing or partial must be called stale, missing or partial.
- Be concise: at most 5 short sentences or a short list. Answer in {language}.
Reply with a JSON object: {{"answer": string, "citations": [string]}}."""

LANGUAGE = {"en": "English", "fr": "French"}


@dataclass(frozen=True)
class LlmReply:
    answer: str
    citations: list[str]
    raw: str


class OllamaClient:
    def __init__(self, url: str, model: str, timeout_s: float = 90, seed: int = 7, max_tokens: int = 400,
                 http: httpx.Client | None = None) -> None:
        self.model, self.seed, self.max_tokens = model, seed, max_tokens
        self.http = http or httpx.Client(base_url=url.rstrip("/"), timeout=timeout_s)

    def available(self) -> bool:
        """True if Ollama answers and has the configured model."""
        try:
            tags = self.http.get("/api/tags", timeout=2).json()
        except (httpx.HTTPError, ValueError):
            return False
        names = {m.get("name", "") for m in tags.get("models", [])}
        return self.model in names or f"{self.model}:latest" in names

    def chat(self, question: str, facts: dict[str, str], lang: str) -> LlmReply | None:
        listed = "\n".join(f"[{fact_id}] {text}" for fact_id, text in facts.items())
        body: dict[str, Any] = {
            "model": self.model, "stream": False, "format": REPLY_SCHEMA, "think": False,
            "options": {"temperature": 0, "seed": self.seed, "num_predict": self.max_tokens},
            "messages": [
                {"role": "system", "content": SYSTEM.format(language=LANGUAGE.get(lang, "English"))},
                {"role": "user", "content": f"Question: {question}\n\nFacts:\n{listed}"},
            ],
        }
        try:
            response = self.http.post("/api/chat", json=body)
            if response.status_code == 400 and "think" in response.text.lower():
                body.pop("think")  # a model without a thinking mode refuses the option
                response = self.http.post("/api/chat", json=body)
            response.raise_for_status()
            raw = response.json()["message"]["content"]
            data = json.loads(raw)
            return LlmReply(str(data["answer"]), [str(c) for c in data.get("citations", [])], raw)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            log.warning("local model unavailable or unusable: %s", exc)
            return None
