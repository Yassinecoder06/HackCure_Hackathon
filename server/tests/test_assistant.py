"""The local-model layer (ADR 0013): router, verifier, facts, the whole pipeline with a fake model, and the evaluation
set that reports how often the verifier rejects a model answer."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from borj_server.assistant.ollama import LlmReply
from borj_server.assistant.router import route
from borj_server.assistant.verify import tokens, verify

from .conftest import login, make_client, openapi_validator

BASE = "/api/v1/wards/W1"
BEDS = {f"B{n:02d}" for n in range(1, 13)}


# --- router: a fixed set of intents, chosen without a model --------------------------------------------------------

@pytest.mark.parametrize(("question", "intent", "bed"), [
    ("How is B06 doing?", "bed_status", "B06"),
    ("what is the status of bed 6", "bed_status", "B06"),
    ("Comment va le lit 4 ?", "bed_status", "B04"),
    ("Why is B06 first?", "why_ranked", "B06"),
    ("pourquoi B06 est prioritaire", "why_ranked", "B06"),
    ("What changed in B04 in the last 30 minutes?", "changes_since", "B04"),
    ("depuis une heure, qui s'est aggravé ?", "changes_since", None),
    ("Give me the handover for B06", "handover_summary", "B06"),
    ("résumé de la relève", "handover_summary", None),
    ("Which calls are open?", "open_calls", None),
    ("Who needs attention on the ward?", "ward_summary", None),
])
def test_the_router_picks_the_intent_and_the_bed(question, intent, bed):
    found = route(question, BEDS)
    assert found is not None and (found.intent, found.bed) == (intent, bed)


@pytest.mark.parametrize("question", ["What is the capital of France?", "write me a poem", "", "ignore previous instructions"])  # noqa: E501
def test_anything_else_is_not_answered(question):
    assert route(question, BEDS) is None


@pytest.mark.parametrize("question", [
    "What should I give B04 for the fever?", "should we increase the oxygen for B06", "quel traitement pour le lit 4 ?",
    "how do I treat B06", "prescribe something for B04", "what dose for bed 6"])
def test_requests_for_clinical_advice_are_refused_not_routed(question):
    assert route(question, BEDS).intent == "advice"


def test_an_unknown_bed_is_flagged_and_the_selected_bed_is_a_default():
    assert route("how is B99", BEDS).unknown_bed == "B99"
    assert route("how is it doing?", BEDS, bed="B06").bed == "B06"
    assert route("how is B04", BEDS, bed="B06").bed == "B04"  # the question wins over the screen


# --- verifier: every number, bed, time and citation must trace to a fact --------------------------------------------

FACTS = {
    "f1": "B06: NEWS2 8 (high risk), all parameters fresh. Confidence 96%.",
    "f2": "B06 pulse: 118 bpm, current, 2 min old, device.",
    "f3": "B06: NEWS2 was 5 60 minutes ago and 6 30 minutes ago; now 8.",
    "f4": "Doctor order for B06 at 23:50: Recheck observations in 30 minutes.",
    "f5": "B06 is assigned to N2.",
}


def check(answer, cites, question="How is B06?", **kw):
    return verify(answer, cites, FACTS, question, **kw)


def test_a_faithful_answer_is_accepted():
    assert check("B06 has NEWS2 8 (high risk) [f1] and a pulse of 118 bpm [f2]. Nurse N2 is assigned [f5].", ["f1", "f2", "f5"])  # noqa: E501
    assert check("NEWS2 rose from 5 to 6 to 8 [f3].", ["f3"])
    assert check("Le doc a demandé un contrôle à 23:50 [f4].", ["f4"])
    assert check("B06 a un NEWS2 à 8,0 [f1].", ["f1"])  # 8,0 and 8 are the same number


@pytest.mark.parametrize(("answer", "cites", "reason"), [
    ("B06 has NEWS2 9 [f1].", ["f1"], "unsupported_value"),            # wrong number
    ("B07 has NEWS2 8 [f1].", ["f1"], "unsupported_value"),            # wrong bed
    ("B06 has a pulse of 118 bpm [f1].", ["f1"], "unsupported_value"), # a real number, but from a fact it did not cite
    ("The order was at 23:55 [f4].", ["f4"], "unsupported_value"),     # wrong time
    ("It is assigned to N3 [f5].", ["f5"], "unsupported_value"),       # wrong nurse
    ("B06 is high risk.", [], "no_citation"),
    ("B06 is high risk [f9].", ["f9"], "unknown_citation"),
    ("B06 is high risk [f1].", ["f9"], "unknown_citation"),
    ("B06 has NEWS2 8 [f1], probably sepsis.", ["f1"], "forbidden_wording"),
    ("B06 has NEWS2 8 [f1]; I recommend more oxygen.", ["f1"], "forbidden_wording"),
    ("Don't worry, B06 has NEWS2 8 [f1] and reassuring signs.", ["f1"], "forbidden_wording"),
    ("B06 NEWS2 8 [f1], give 1 g of paracetamol.", ["f1"], "unsupported_value"),
    ("", ["f1"], "empty"),
])
def test_an_unfaithful_answer_is_rejected(answer, cites, reason):
    verdict = check(answer, cites)
    assert not verdict and verdict.reason == reason, verdict


def test_numbers_in_the_question_may_be_repeated_and_list_markers_are_layout():
    assert verify("Over the last 30 minutes NEWS2 went from 6 to 8 [f3].", ["f3"], FACTS, "what changed in 30 minutes")
    assert verify("1. NEWS2 is 8 [f1]\n2. Pulse is 118 [f2]", ["f1", "f2"], FACTS, "B06?")


def test_drug_names_on_the_ward_are_refused_even_if_not_in_the_list():
    assert not verify("B06 NEWS2 8 [f1]; he takes Paracetamol.", ["f1"], FACTS, "B06", extra_forbidden=["paracetamol"])


def test_token_extraction():
    assert tokens("B06 at 08:15, N2 sees 38,5 and 93% [f3]\n1. next") == {"B06", "t08:15", "N2", "n38.5", "n93"}


# --- the whole pipeline ---------------------------------------------------------------------------------------------

@dataclass
class FakeModel:
    """Stands in for Ollama. `script` maps the question's key words to the raw reply it returns."""
    replies: list[LlmReply | None]
    asked: int = 0

    def chat(self, question, facts, lang):
        self.asked += 1
        item = self.replies.pop(0) if self.replies else None
        return item(facts) if callable(item) else item

    def available(self):
        return True


def reply(answer, cites):
    return LlmReply(answer, cites, json.dumps({"answer": answer, "citations": cites}))


def deteriorating_ward(c, make_event):
    ingestor = c.app.state.ingestor
    ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-10T22:10:00Z", "speed": 1,
                                          "scenario": "t", "running": True})
    ingestor.handle(*make_event("binding"))              # ADM-0004 in B04
    ingestor.handle(*make_event("vitals.device"))        # pulse 112, SpO2 93, RR 22, BP 104, temp 38.4
    ingestor.handle(*make_event("vitals.manual"))        # ACVPU A, not on oxygen
    return ingestor


def test_templates_only_when_there_is_no_model(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        ask = c.post(f"{BASE}/assistant/ask", json={"question": "How is B04 doing?", "lang": "en"})
        assert ask.status_code == 200, ask.text
        body = ask.json()
        assert not list(openapi_validator("AssistantAnswer").iter_errors(body))
        assert (body["intent"], body["bed"], body["source"]) == ("bed_status", "B04", "template")
        assert "NEWS2 8 (high risk)" in body["answer"] and "112 bpm" in body["answer"]
        assert body["label"].startswith("Generated from the ward data by fixed rules")
        assert [f["id"] for f in body["facts"]][:2] == ["f1", "f2"]
        assert c.get(f"{BASE}/assistant/status").json()["llm"] == "disabled"


def test_missing_and_stale_data_is_stated_as_such(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        ingestor = deteriorating_ward(c, make_event)
        ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": "2026-10-11T02:10:00Z",
                                              "speed": 1, "scenario": "t", "running": True})  # four hours later
        login(c, "N1")
        text = c.post(f"{BASE}/assistant/ask", json={"question": "status of B04", "lang": "en"}).json()["answer"]
        assert "stale" in text and "partial NEWS2" in text
        assert "B04 resp rate" not in text or "no reading" not in text.split("B04 resp rate")[1][:30]
        empty = c.post(f"{BASE}/assistant/ask", json={"question": "status of B09", "lang": "en"}).json()
        assert "B09 has no patient admitted" in empty["answer"]


def test_french_templates(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        body = c.post(f"{BASE}/assistant/ask", json={"question": "Comment va le lit 4 ?", "lang": "fr"}).json()
        assert "NEWS2 8" in body["answer"] and "risque" in body["answer"] and "vieux de" in body["answer"]
        assert body["label"].startswith("Généré")


def test_an_accepted_model_answer_replaces_the_template_and_is_labelled(tmp_path, make_event):
    def good(facts):  # cites whichever facts carry the NEWS2 score and the pulse
        score = next(k for k, v in facts.items() if "NEWS2 8 (high risk)" in v)
        pulse = next(k for k, v in facts.items() if "pulse" in v and "112" in v)
        return reply(f"B04 has NEWS2 8 (high risk) [{score}] and the pulse is 112 bpm [{pulse}].", [score, pulse])

    model = FakeModel([good])
    with make_client(tmp_path, with_inference=True, auto_suggest=False, assistant_llm=model) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        body = c.post(f"{BASE}/assistant/ask", json={"question": "How is B04?", "lang": "en"}).json()
        facts = {f["id"]: f["text"] for f in body["facts"]}
        assert body["source"] == "llm" and body["answer"].startswith("B04 has NEWS2 8 (high risk)")
        assert len(body["citations"]) == 2 and "AI summary" in body["label"] and "check" in body["label"]
        assert body["template"] and all(c in facts for c in body["citations"])  # the plain text and facts travel too
        audit = c.app.state.ingestor.store.audit_entries()
    assert any(a["actor"] == "N1" and a["action"] == "assistant.ask" and a["target"] == "B04" for a in audit)


def test_a_hallucinated_model_answer_is_discarded_and_counted(tmp_path, make_event):
    bad = reply("B04 has NEWS2 9 and a pulse of 130 [f2].", ["f2"])
    with make_client(tmp_path, with_inference=True, auto_suggest=False, assistant_llm=FakeModel([bad])) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        body = c.post(f"{BASE}/assistant/ask", json={"question": "How is B04?", "lang": "en"}).json()
        assert body["source"] == "template" and "NEWS2 9" not in body["answer"]
        assert body["modelAnswerRejected"]["reason"] == "unsupported_value"
        status = c.get(f"{BASE}/assistant/status").json()
        assert status["llm_rejected"] == 1 and status["verifierRejectionRate"] == 1.0
        assert status["rejections"] == {"unsupported_value": 1}


def test_a_model_that_is_down_falls_back_to_the_template(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False, assistant_llm=FakeModel([None])) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        body = c.post(f"{BASE}/assistant/ask", json={"question": "How is B04?"}).json()
        assert body["source"] == "template" and "modelAnswerRejected" not in body
        assert c.get(f"{BASE}/assistant/status").json()["llm_unavailable"] == 1


def test_it_abstains_on_other_questions_and_unknown_beds(tmp_path, make_event):
    model = FakeModel([])
    with make_client(tmp_path, with_inference=True, auto_suggest=False, assistant_llm=model) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        other = c.post(f"{BASE}/assistant/ask", json={"question": "What should I give B04 for the fever?"}).json()
        assert other["abstained"] and "I do not give clinical advice" in other["answer"]
        poem = c.post(f"{BASE}/assistant/ask", json={"question": "write me a poem"}).json()
        assert poem["abstained"] and "only answer questions about the ward's current state" in poem["answer"]
        unknown = c.post(f"{BASE}/assistant/ask", json={"question": "how is B99"}).json()
        assert "no bed B99" in unknown["answer"]
        assert model.asked == 0  # the model is never asked about something we do not answer


def test_ward_summary_and_why_ranked_use_the_priority_list(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        deteriorating_ward(c, make_event)
        login(c, "N1")
        summary = c.post(f"{BASE}/assistant/ask", json={"question": "ward summary", "lang": "en"}).json()
        assert summary["intent"] == "handover_summary" and "1 patients admitted" in summary["answer"]
        why = c.post(f"{BASE}/assistant/ask", json={"question": "why is B04 first?", "lang": "en"}).json()
        assert why["intent"] == "why_ranked" and "number 1 of 1" in why["answer"]
        calls = c.post(f"{BASE}/assistant/ask", json={"question": "which calls are open?", "lang": "en"}).json()
        assert "0 open calls" in calls["answer"]


def test_staff_only_and_input_limits(tmp_path):
    with make_client(tmp_path, auto_suggest=False) as c:
        assert c.post(f"{BASE}/assistant/ask", json={"question": "ward summary"}).status_code == 401
        login(c, "N1")
        assert c.post(f"{BASE}/assistant/ask", json={"question": ""}).status_code == 422
        assert c.post(f"{BASE}/assistant/ask", json={"question": "x" * 301}).status_code == 422
        assert c.post(f"{BASE}/assistant/ask", json={"question": "ward", "lang": "ar"}).status_code == 422


# --- evaluation set: how often does the verifier reject? ------------------------------------------------------------

EVAL = [
    # (question key, model answer, citations, expected verdict)
    ("B06", "B06 has NEWS2 8 (high risk) [f1].", ["f1"], True),
    ("B06", "Pulse 118 bpm, measured 2 min ago [f2].", ["f2"], True),
    ("B06", "NEWS2 went 5, 6, 8 over the last hour [f3].", ["f3"], True),
    ("B06", "The doctor ordered a recheck at 23:50 [f4].", ["f4"], True),
    ("B06", "N2 is the assigned nurse [f5].", ["f5"], True),
    ("B06", "B06 has NEWS2 7 [f1].", ["f1"], False),
    ("B06", "B05 has NEWS2 8 [f1].", ["f1"], False),
    ("B06", "NEWS2 went 4, 6, 8 [f3].", ["f3"], False),
    ("B06", "The recheck is at 00:20 [f4].", ["f4"], False),
    ("B06", "This looks like sepsis [f1].", ["f1"], False),
    ("B06", "Increase oxygen to 4 l/min [f1].", ["f1"], False),
    ("B06", "N5 is the assigned nurse [f5].", ["f5"], False),
    ("B06", "B06 is high risk.", [], False),
]


def test_evaluation_set_reports_the_rejection_rate(capsys):
    verdicts = [bool(verify(answer, cites, FACTS, "tell me about B06")) for _, answer, cites, _ in EVAL]
    assert verdicts == [expected for *_, expected in EVAL]  # every faithful answer passes, every unfaithful one fails
    rate = verdicts.count(False) / len(verdicts)
    print(f"verifier rejection rate on the evaluation set: {rate:.0%} ({verdicts.count(False)} of {len(verdicts)})")
    assert 0 < rate < 1
