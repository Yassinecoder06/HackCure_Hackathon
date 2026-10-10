"""Explanations in English and French from one wording module; NEWS2 trend and priority ranking."""

from __future__ import annotations

import string

import pytest
from borj_server.explain import LANGS, MESSAGES, Explainer, pick_lang

from .conftest import login, make_client, openapi_validator


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_every_message_has_both_languages_with_the_same_placeholders(key):
    english, french = MESSAGES[key]
    assert english and french and len(MESSAGES[key]) == len(LANGS)
    assert placeholders(english) == placeholders(french), key


def test_language_selection():
    assert pick_lang("fr") == "fr"
    assert pick_lang(None, "fr-TN,fr;q=0.9,en;q=0.8") == "fr"
    assert pick_lang(None, "ar-TN,ar;q=0.9") == "en"  # Arabic not available yet: default
    assert pick_lang("de", None, default="fr") == "fr"


def test_reason_codes_render_in_french():
    ex = Explainer("fr")
    rendered = ex.items([
        {"code": "assign.busiest", "params": {"before": 9.5, "after": 7.5}},
        {"code": "assign.basis", "params": {"status": "feasible", "fresh": 9, "total": 11}},
    ])
    assert rendered == ["Charge de l'infirmier le plus occupé (acuité + NEWS2) : 9,5 → 7,5.",
                        "solveur réalisable ; NEWS2 récent pour 9 lits occupés sur 11"]


def deteriorating_b04(c, make_event):
    """B04 admitted 21:00 with normal vitals, then deteriorating readings at 22:03 (NEWS2 8)."""
    ingestor = c.app.state.ingestor
    ingestor.handle(*make_event("binding", ts="2026-10-10T21:00:00Z"))
    ingestor.handle(*make_event("binding", bed="B05", admissionId="ADM-0005", ts="2026-10-10T21:00:00Z"))
    ingestor.handle(*make_event("vitals.device", ts="2026-10-10T21:05:00Z",
                                params={"resp_rate": 16, "spo2": 97, "sys_bp": 125, "pulse": 72, "temp_c": 37.0}))
    ingestor.handle(*make_event("vitals.device"))   # 22:03:21, NEWS2 components 2+2+1+2+1
    ingestor.handle(*make_event("vitals.manual"))   # 22:05, alert and on air
    ingestor.clock.update_from_message({"simTs": "2026-10-10T22:10:00Z"})
    return ingestor


def b04(body: dict) -> dict:
    return next(b for b in body["beds"] if b["bed"] == "B04")


def test_trend_and_priority_in_english(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        deteriorating_b04(c, make_event)
        login(c, "CN1")
        body = c.get("/api/v1/wards/W1/snapshot").json()
    assert not list(openapi_validator("WardSnapshot").iter_errors(body))
    bed = b04(body)
    assert bed["news2"]["total"] == 8
    assert {t["minutesAgo"]: t["total"] for t in bed["news2Trend"]} == {60: 0, 30: 0}
    assert bed["priority"]["rank"] == 1 and bed["priority"]["of"] == 2
    assert bed["priority"]["reasons"][:2] == ["NEWS2 8 (high risk).", "NEWS2 rose from 0 to 8 in the last 60 min."]


def test_whole_snapshot_in_french(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        ingestor = deteriorating_b04(c, make_event)
        ingestor.handle(*make_event("call", bed="B04", callId="C-B04-0001", ts="2026-10-10T22:04:00Z"))
        ingestor.clock.update_from_message({"simTs": "2026-10-10T22:10:00Z"})
        login(c, "CN1")
        by_query = c.get("/api/v1/wards/W1/snapshot?lang=fr").json()
        by_header = c.get("/api/v1/wards/W1/snapshot", headers={"Accept-Language": "fr-TN,fr;q=0.9"}).json()
    assert not list(openapi_validator("WardSnapshot").iter_errors(by_query))
    bed = b04(by_query)
    assert bed["news2"]["response"] == "Réponse clinique en urgence."
    assert bed["news2"]["confidence"]["basis"].startswith("7 paramètres sur 7 récents et valides")
    assert bed["priority"]["reasons"][1] == "Le NEWS2 est passé de 0 à 8 en 60 min."
    assert any(r.startswith("Appel d'assistance en attente depuis 6 min") for r in bed["priority"]["reasons"])
    alert = next(a for a in by_query["alerts"] if a["type"] == "news2_high")
    assert alert["explanation"][0] == "NEWS2 8 : Réponse clinique en urgence."
    assert "Pouls 112 : 2 point(s)" in alert["explanation"]
    assert b04(by_header)["news2"]["response"] == "Réponse clinique en urgence."


def test_partial_score_label_in_french(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        ingestor.handle(*make_event("vitals.device"))
        ingestor.clock.update_from_message({"simTs": "2026-10-10T22:10:00Z"})
        login(c, "N1")
        news2 = b04(c.get("/api/v1/wards/W1/snapshot?lang=fr").json())["news2"]
    assert news2["label"] == "NEWS2 partiel, au moins 8 : manquant : oxygénothérapie, conscience (ACVPU)"


def test_what_if_assumptions_in_french(tmp_path, make_event):
    with make_client(tmp_path, with_inference=True, auto_suggest=False) as c:
        deteriorating_b04(c, make_event)
        login(c, "CN1")
        result = c.post("/api/v1/wards/W1/whatif/runs?lang=fr",
                        json={"disruptions": [{"type": "call_surge", "atMin": 0, "callsPerHour": 20}],
                              "horizonMin": 60, "seeds": 10}).json()
    assert result["assumptions"][0] == "Appels : 12/h pour le service, 40 % non cliniques, 8 min chacun en moyenne."
    assert any(a.startswith("Valeurs indicatives") for a in result["assumptions"])
