from __future__ import annotations

import pytest
from borj_inference.news2 import PARAMS, News2Config, Reading, score

CFG = News2Config.load()


def fresh(value, age_s=0, stale_after_s=900):
    return Reading(value, "fresh", age_s, stale_after_s)


NORMAL = {
    "resp_rate": 16, "spo2": 97, "on_oxygen": False, "sys_bp": 120,
    "pulse": 70, "consciousness": "A", "temp_c": 37.0,
}


def full(**overrides):
    return {p: fresh(v) for p, v in {**NORMAL, **overrides}.items()}


def points_of(result, param):
    return next(c for c in result["components"] if c["param"] == param).get("points")


@pytest.mark.parametrize(("param", "value", "expected"), [
    ("resp_rate", 8, 3), ("resp_rate", 9, 1), ("resp_rate", 11, 1), ("resp_rate", 12, 0),
    ("resp_rate", 20, 0), ("resp_rate", 21, 2), ("resp_rate", 24, 2), ("resp_rate", 25, 3),
    ("spo2", 91, 3), ("spo2", 92, 2), ("spo2", 93, 2), ("spo2", 94, 1), ("spo2", 95, 1), ("spo2", 96, 0),
    ("on_oxygen", True, 2), ("on_oxygen", False, 0),
    ("sys_bp", 90, 3), ("sys_bp", 91, 2), ("sys_bp", 100, 2), ("sys_bp", 101, 1), ("sys_bp", 110, 1),
    ("sys_bp", 111, 0), ("sys_bp", 219, 0), ("sys_bp", 220, 3),
    ("pulse", 40, 3), ("pulse", 41, 1), ("pulse", 50, 1), ("pulse", 51, 0), ("pulse", 90, 0),
    ("pulse", 91, 1), ("pulse", 110, 1), ("pulse", 111, 2), ("pulse", 130, 2), ("pulse", 131, 3),
    ("consciousness", "A", 0), ("consciousness", "C", 3), ("consciousness", "V", 3),
    ("consciousness", "P", 3), ("consciousness", "U", 3),
    ("temp_c", 35.0, 3), ("temp_c", 35.1, 1), ("temp_c", 36.0, 1), ("temp_c", 36.1, 0),
    ("temp_c", 38.0, 0), ("temp_c", 38.1, 1), ("temp_c", 39.0, 1), ("temp_c", 39.1, 2),
])
def test_rcp_band_boundaries(param, value, expected):
    assert points_of(score(full(**{param: value}), CFG), param) == expected


@pytest.mark.parametrize(("spo2", "on_oxygen", "expected"), [
    (83, True, 3), (84, True, 2), (85, False, 2), (86, True, 1), (87, False, 1), (88, True, 0), (92, False, 0),
    (93, False, 0), (99, False, 0),
    (93, True, 1), (94, True, 1), (95, True, 2), (96, True, 2), (97, True, 3),
])
def test_spo2_scale_2(spo2, on_oxygen, expected):
    result = score(full(spo2=spo2, on_oxygen=on_oxygen), CFG, spo2_scale=2)
    assert points_of(result, "spo2") == expected


def test_spo2_scale_2_above_92_needs_oxygen_status():
    readings = full(spo2=95)
    del readings["on_oxygen"]
    result = score(readings, CFG, spo2_scale=2)
    assert points_of(result, "spo2") is None
    assert not result["complete"]
    assert "SpO2 scale 2 needs a fresh oxygen status" in result["label"]


def test_normal_patient_is_complete_low_and_fully_confident():
    result = score(full(), CFG)
    assert (result["total"], result["band"], result["complete"]) == (0, "low", True)
    assert result["confidence"]["value"] == 1.0
    assert result["label"] == "NEWS2 0"


@pytest.mark.parametrize(("overrides", "total", "band"), [
    ({"pulse": 95, "temp_c": 38.5}, 2, "low"),
    ({"consciousness": "C"}, 3, "low_medium"),           # single parameter scores 3
    ({"resp_rate": 22, "pulse": 115, "temp_c": 38.5}, 5, "medium"),
    ({"resp_rate": 22, "spo2": 93, "sys_bp": 104, "pulse": 112, "temp_c": 38.4}, 8, "high"),
])
def test_bands(overrides, total, band):
    result = score(full(**overrides), CFG)
    assert (result["total"], result["band"]) == (total, band)


def test_missing_and_stale_are_never_scored_and_labelled_partial():
    """Invariant 5: a stale reading must not count as a normal value."""
    readings = full(pulse=135)  # would score 3
    readings["pulse"] = Reading(135, "stale", 1200, 900)
    del readings["consciousness"]
    readings["temp_c"] = Reading(39.5, "invalid", 10, 900)
    result = score(readings, CFG)

    assert result["complete"] is False
    assert result["missing"] == ["consciousness", "temp_c"]
    assert result["stale"] == ["pulse"]
    assert points_of(result, "pulse") is None
    assert result["total"] == 0
    assert result["label"].startswith("Partial NEWS2, at least 0:")
    assert "pulse stale" in result["label"] and "temperature invalid" in result["label"]
    assert result["confidence"]["value"] == pytest.approx(4 / 7, abs=0.001)
    assert "4 of 7" in result["confidence"]["basis"]


def test_confidence_decays_with_age():
    new = score(full(), CFG)["confidence"]["value"]
    readings = {p: fresh(v, age_s=450, stale_after_s=900) for p, v in NORMAL.items()}
    half_way = score(readings, CFG)["confidence"]["value"]
    assert new == 1.0
    assert half_way == pytest.approx(0.75)


def test_no_readings_at_all():
    result = score({}, CFG)
    assert result["missing"] == list(PARAMS)
    assert result["confidence"]["value"] == 0.0
    assert result["complete"] is False


@pytest.mark.parametrize(("param", "bad"), [("consciousness", "X"), ("pulse", "fast"), ("on_oxygen", None)])
def test_unscorable_value_is_marked_invalid_not_a_crash(param, bad):
    result = score(full(**{param: bad}), CFG)
    component = next(c for c in result["components"] if c["param"] == param)
    assert component["status"] == "invalid"
    assert param in result["missing"]
    assert result["complete"] is False


def test_scale_2_never_assumes_on_air_from_a_bad_oxygen_value():
    result = score(full(spo2=95, on_oxygen=None), CFG, spo2_scale=2)
    assert points_of(result, "spo2") is None
    assert {"spo2", "on_oxygen"} <= set(result["missing"])
