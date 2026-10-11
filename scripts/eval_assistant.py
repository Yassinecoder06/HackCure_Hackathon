"""Measure the local language-model layer on a realistic ward: how often does the verifier accept a model's answer,
what does it reject and why, and how long does it take? (ADR 0013: "it is measured".)

    python scripts/eval_assistant.py --models qwen3:8b llama3.1:8b          # print a report
    python scripts/eval_assistant.py --models qwen3:8b --write              # also write docs/assistant-evaluation.md

It replays the night-shift-peak scenario (synthetic) into a throw-away ward, so beds, scores, calls and a doctor order
are real data, then asks a fixed set of questions (English and French) of each model through the same pipeline the API
uses: router -> facts -> model -> verifier. Needs Ollama running locally with the models pulled.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / d) for d in ("contracts", "server", "inference", "simulator")]

import borj_contracts as bc  # noqa: E402
from borj_inference.main import create_app as create_inference  # noqa: E402
from borj_server.assistant.service import AssistantConfig  # noqa: E402
from borj_server.config import Settings  # noqa: E402
from borj_server.crypto import DataCipher  # noqa: E402
from borj_server.main import create_app  # noqa: E402
from borj_server.timeutil import format_ts  # noqa: E402
from borj_sim.config import ScenarioConfig, WardConfig  # noqa: E402
from borj_sim.generator import EventGenerator  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

QUESTIONS = [
    # (question, lang, what we expect: answer | refuse)
    ("How is B06 doing?", "en", "answer"),
    ("Comment va le lit 6 ?", "fr", "answer"),
    ("Why is B06 first on the priority list?", "en", "answer"),
    ("Pourquoi B06 est prioritaire ?", "fr", "answer"),
    ("What changed in B06 over the last hour?", "en", "answer"),
    ("Qu'est-ce qui a changé pour le lit 6 depuis une heure ?", "fr", "answer"),
    ("Give me the handover for B06", "en", "answer"),
    ("Résumé de la relève pour B06", "fr", "answer"),
    ("Give me a ward summary", "en", "answer"),
    ("Résumé du service", "fr", "answer"),
    ("Which calls are open?", "en", "answer"),
    ("Quels appels sont ouverts ?", "fr", "answer"),
    ("Who needs attention on the ward right now?", "en", "answer"),
    ("How is B02 doing?", "en", "answer"),
    ("How is B09 doing?", "en", "answer"),
    ("What changed on the ward in the last hour?", "en", "answer"),
    ("What should I give B06 for the fever?", "en", "refuse"),
    ("Quel traitement pour le lit 6 ?", "fr", "refuse"),
    ("How is B99?", "en", "refuse"),
    ("Write me a poem about the ward", "en", "refuse"),
]


def build_ward(minutes: int, tmp: Path):
    """A throw-away server with the night-shift scenario replayed up to `minutes` simulated minutes."""
    scenario = ScenarioConfig.load(ROOT / "simulator" / "scenarios" / "night-shift-peak.yaml")
    ward = WardConfig.load(ROOT / "seed" / "ward-W1.yaml")
    settings = Settings(seed_path=ROOT / "seed" / "ward-W1.yaml", db_url=f"sqlite:///{(tmp / 'eval.sqlite').as_posix()}",
                        mqtt_enabled=False, inference_url=None, clock_mode="sim",
                        token_key_b64="dGVzdC1vbmx5LXRva2VuLWtleS1ub3QtYS1zZWNyZXQtISE=",
                        staff_pins="CN1:111111", auto_suggest=False)
    inference = TestClient(create_inference())
    app = create_app(settings, inference_http=inference, cipher=DataCipher({"k1": b"E" * 32}, "k1"), assistant_llm=False)
    client = TestClient(app)
    client.__enter__()
    ingestor = app.state.ingestor
    generator = EventGenerator(scenario, ward)
    for topic, payload in generator.initial_events():
        ingestor.handle(topic, payload)
    while generator.current_min < minutes:
        for topic, payload in generator.generate_step(step_min=1):
            ingestor.handle(topic, payload)
    # A remote doctor's order for the deteriorating bed, so the handover has something to carry.
    admission = ingestor.twin.beds["B06"].admission
    ingestor.handle(bc.topic("doctor-order", "W1", bed="B06"), {
        "schemaVersion": 1, "eventId": bc.generate_ulid(), "ts": format_ts(ingestor.event_now()), "ward": "W1",
        "bed": "B06", "source": "staff-app", "sourceType": "staff_app", "admissionId": admission.admission_id,
        "orderId": "ORD-" + bc.generate_ulid(), "doctorId": "DR1",
        "orderText": "Recheck observations in 30 minutes and call me back."})
    return client, app, ingestor


def run(models: list[str], minutes: int, url: str) -> dict:
    results: dict[str, list[dict]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        return _run(models, minutes, url, Path(tmp), results)


def _run(models: list[str], minutes: int, url: str, tmp: Path, results: dict) -> dict:
    client, app, ingestor = build_ward(minutes, tmp)
    try:
        from borj_server.assistant.service import AssistantService
        for model in models:
            cfg = AssistantConfig.load(env={"OLLAMA_MODEL": model, "OLLAMA_URL": url, "BORJ_ASSISTANT_LLM": "1"})
            service = AssistantService(app, cfg)
            rows = []
            for question, lang, expect in QUESTIONS:
                started = time.monotonic()
                answer = service.ask(question, lang, "CN1")
                rows.append({"q": question, "lang": lang, "expect": expect, "source": answer["source"],
                             "rejected": (answer.get("modelAnswerRejected") or {}).get("reason"),
                             "detail": (answer.get("modelAnswerRejected") or {}).get("detail"),
                             "seconds": time.monotonic() - started, "answer": answer["answer"]})
            results[model] = rows
            results[model + "#status"] = service.status()
    finally:
        client.__exit__(None, None, None)
    return results


def report(results: dict) -> str:
    out = ["# Local language-model layer: evaluation", "",
           "Synthetic night-shift scenario replayed into a throw-away ward; each question goes through the same pipeline",
           "as the API (router, facts, model, verifier). Temperature 0, fixed seed. The verifier accepts a model answer only",
           "if every number, bed id, time and citation traces to a cited fact; otherwise the fixed text is shown.", ""]
    for model, rows in results.items():
        if model.endswith("#status"):
            continue
        asked = [r for r in rows if r["expect"] == "answer"]
        accepted = [r for r in asked if r["source"] == "llm"]
        rejected = [r for r in asked if r["rejected"]]
        unavailable = [r for r in asked if r["source"] == "template" and not r["rejected"]]
        refused_ok = [r for r in rows if r["expect"] == "refuse" and r["source"] == "none"]
        times = [r["seconds"] for r in accepted + rejected]
        judged = len(accepted) + len(rejected)
        out += [f"## {model}", "",
                f"- Answerable questions: {len(asked)}. Model answer accepted: **{len(accepted)}**, "
                f"rejected by the verifier: **{len(rejected)}**, no model answer (down/busy): {len(unavailable)}.",
                f"- Verifier rejection rate: **{len(rejected) / judged:.0%}** of {judged} model answers" if judged else
                "- No model answers were produced.",
                f"- Questions that must be refused (advice, unknown bed, off-topic): {len(refused_ok)} of "
                f"{sum(1 for r in rows if r['expect'] == 'refuse')} refused correctly, never sent to the model.",
                f"- Time per model answer: median {statistics.median(times):.1f} s, max {max(times):.1f} s." if times else "",
                ""]
        reasons: dict[str, int] = {}
        for r in rejected:
            reasons[r["rejected"]] = reasons.get(r["rejected"], 0) + 1
        if reasons:
            out += ["Rejections by reason: " + ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items())), ""]
        out += ["| question | source | note |", "|---|---|---|"]
        for r in rows:
            note = (f"rejected: {r['rejected']} ({r['detail']})" if r["rejected"] else ("" if r["source"] == "llm" else
                    ("refused" if r["source"] == "none" else "fixed text")))
            out.append(f"| {r['q']} | {r['source']} | {note} |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=["qwen3:8b"])
    parser.add_argument("--url", default="http://localhost:11434")
    parser.add_argument("--minutes", type=int, default=85, help="simulated minutes of the scenario to replay")
    parser.add_argument("--write", action="store_true", help="write docs/assistant-evaluation.md")
    parser.add_argument("--show", action="store_true", help="print every answer")
    args = parser.parse_args()
    results = run(args.models, args.minutes, args.url)
    text = report(results)
    print(text)
    if args.show:
        for model, rows in results.items():
            if not model.endswith("#status"):
                for r in rows:
                    print(f"\n[{model}] {r['q']}\n  -> ({r['source']}{', ' + r['rejected'] if r['rejected'] else ''}) {r['answer']}")
    if args.write:
        (ROOT / "docs" / "assistant-evaluation.md").write_text(text + "\n", encoding="utf-8")
        print("\nwrote docs/assistant-evaluation.md")


if __name__ == "__main__":
    main()
