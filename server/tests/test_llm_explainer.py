"""Tests for the grounded local LLM explainability layer (ADR 0013)."""

from __future__ import annotations

from unittest.mock import patch

from borj_server.llm_explainer import GroundedExplainer


def test_build_bed_facts():
    explainer = GroundedExplainer()
    bed = {
        "room": "Chamber 3",
        "news2": {
            "total": 6,
            "band": "medium",
            "components": [
                {"param": "resp_rate", "value": 22, "points": 2},
                {"param": "pulse", "value": 105, "points": 1},
            ],
            "response": "Urgent clinical review.",
            "confidence": {"basis": "7 of 7 fresh"},
        },
        "call": {"kind": "assist", "state": "sent", "level": 1, "pressedAt": "2026-10-11T07:40:00Z"},
    }
    admission = {"patientName": "Patient Test", "admissionId": "ADM-0001", "age": 68}
    facts = explainer.build_bed_facts("B06", bed, admission=admission, nurse_id="N1", nurse_name="Nurse Sarah")

    assert any("Bed B06" in f for f in facts)
    assert any("ADM-0001" in f for f in facts)
    assert any("NEWS2 score is 6" in f for f in facts)
    assert any("Resp rate" in f for f in facts)
    assert any("Nurse Sarah" in f for f in facts)
    assert all(f.startswith(f"[f{i}]") for i, f in enumerate(facts, start=1))


def test_verify_citations():
    explainer = GroundedExplainer()
    facts = ["[f1] Fact 1", "[f2] Fact 2", "[f3] Fact 3"]

    # Valid citations
    valid_resp = "Patient has high risk [f1] requiring prompt review [f2, f3]."
    is_valid, citations = explainer.verify(valid_resp, facts)
    assert is_valid
    assert "[f1]" in citations
    assert "[f2]" in citations
    assert "[f3]" in citations

    # No citations -> rejected
    no_cite = "Patient is doing fine without any references."
    is_valid, _ = explainer.verify(no_cite, facts)
    assert not is_valid

    # Hallucinated citation [f9] -> rejected
    hallucinated = "Patient has condition X [f9]."
    is_valid, _ = explainer.verify(hallucinated, facts)
    assert not is_valid


def test_fallback_on_llm_failure():
    explainer = GroundedExplainer(ollama_url="http://192.0.2.1:9999", timeout_s=0.1)
    bed = {
        "room": "Chamber 1",
        "news2": {"total": 4, "band": "low", "response": "Routine monitoring."},
    }
    result = explainer.explain_bed("B01", bed)
    assert result["bed"] == "B01"
    assert result["fallback"] is True
    assert result["model"] == "deterministic-template"
    assert "NEWS2 4" in result["summary"]


def test_explain_with_mocked_llm():
    explainer = GroundedExplainer()
    bed = {
        "room": "Chamber 2",
        "news2": {"total": 7, "band": "high", "response": "Emergency clinical response."},
    }
    mock_llm_response = "Bed B02 has a critical NEWS2 of 7 [f2], requiring an emergency clinical response [f3]."

    with patch.object(explainer, "_call_ollama", return_value=mock_llm_response):
        result = explainer.explain_bed("B02", bed)
        assert result["bed"] == "B02"
        assert result["fallback"] is False
        assert result["verified"] is True
        assert "[f2]" in result["citations"]
        assert result["model"] == "gemma4-ab-qat:e4b"
        assert "Gemma 4 QAT" in result["disclaimer"]
