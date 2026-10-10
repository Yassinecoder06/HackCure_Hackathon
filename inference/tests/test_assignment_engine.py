from __future__ import annotations

from borj_inference.assignment import AssignmentConfig, BedNeed, Nurse, suggest

CFG = AssignmentConfig.load()
NURSES = [Nurse("N1", frozenset({"iv"})), Nurse("N2", frozenset({"iv", "resp"})), Nurse("N3")]


def ward(**current):
    """Six beds in three rooms, 2 per nurse at the start (current={"B01": "N1", ...} overrides)."""
    layout = [("B01", "R1"), ("B02", "R1"), ("B03", "R2"), ("B04", "R2"), ("B05", "R3"), ("B06", "R3")]
    start = {"B01": "N1", "B02": "N1", "B03": "N2", "B04": "N2", "B05": "N3", "B06": "N3"} | current
    return [BedNeed(b, r, acuity=2, news2_total=1, news2_fresh=True, current_nurse=start[b]) for b, r in layout]


def test_balanced_ward_needs_no_change():
    result = suggest(NURSES, ward(), CFG)
    assert result["status"] == "optimal"
    assert result["changes"] == []
    assert result["confidence"]["value"] == 1.0


def test_nurse_called_away_beds_are_covered_and_rest_stays_put():
    nurses = [n for n in NURSES if n.staff_id != "N3"]
    result = suggest(nurses, ward(), CFG)
    moved = {c["bed"]: c for c in result["changes"]}
    assert set(moved) == {"B05", "B06"}  # only N3's beds move: continuity for everyone else
    assert all(c["fromStaffId"] == "N3" for c in moved.values())
    assert result["loadBefore"]["unassigned"] > 0 and "unassigned" not in result["loadAfter"]
    assert result["reasonItems"][0] == {"code": "assign.uncovered", "params": {"count": 2, "beds": "B05, B06"}}
    # Balance outweighs one extra room of walking: the two uncovered beds are split, 3 beds each.
    assert result["loadAfter"] == {"N1": 7.5, "N2": 7.5}


def test_deteriorating_patient_rebalances_load():
    beds = ward()
    beds[0] = BedNeed("B01", "R1", acuity=4, news2_total=9, news2_fresh=True, current_nurse="N1")
    beds[1] = BedNeed("B02", "R1", acuity=4, news2_total=7, news2_fresh=True, current_nurse="N1")
    result = suggest(NURSES, beds, CFG)
    after = result["loadAfter"]
    assert max(after.values()) < max(v for k, v in result["loadBefore"].items() if k != "unassigned")
    assert any(r["code"] == "assign.high_news2_moved" for r in result["reasonItems"])


def test_locked_beds_and_skills_are_hard_constraints():
    beds = ward()
    beds[0] = BedNeed("B01", "R1", acuity=4, news2_total=9, news2_fresh=True, current_nurse="N1", locked=True)
    beds[4] = BedNeed("B05", "R3", acuity=2, news2_total=1, news2_fresh=True, current_nurse="N3",
                      required_skills=frozenset({"resp"}))
    result = suggest(NURSES, beds, CFG)
    assert result["assignment"]["B01"] == "N1"
    assert result["assignment"]["B05"] == "N2"  # only N2 has the resp skill


def test_impossible_skill_is_reported_not_guessed():
    beds = ward()
    beds[0] = BedNeed("B01", "R1", acuity=2, required_skills=frozenset({"dialysis"}), current_nurse="N1")
    result = suggest(NURSES, beds, CFG)
    assert result["status"] == "infeasible" and result["changes"] == []
    assert result["reasonItems"][0] == {"code": "assign.missing_skill", "params": {"beds": "B01"}}
    assert result["confidence"]["value"] == 0.0


def test_unknown_news2_lowers_confidence():
    beds = [BedNeed(b.bed, b.room, b.acuity, None, False, b.current_nurse) for b in ward()]
    assert suggest(NURSES, beds, CFG)["confidence"]["value"] == 0.5


def test_same_inputs_same_answer():
    nurses = [n for n in NURSES if n.staff_id != "N2"]
    assert suggest(nurses, ward(), CFG) == suggest(nurses, ward(), CFG)
