"""Nurse assignment suggestions with OR-Tools CP-SAT (whitepaper 5.2, ADR 0011).

Hard constraints: every occupied bed gets exactly one nurse who is on the ward; a bed that needs a
skill only goes to a nurse who has it; locked beds keep their nurse; a nurse takes at most N beds.
Objective (weights in config/assignment.yaml), in decreasing weight:
  1. the busiest nurse's workload (acuity + NEWS2) as low as possible -> balance,
  2. as few beds as possible moved away from their current nurse -> continuity of care,
  3. as few rooms per nurse as possible -> less walking (rooms only: staff are never tracked).
The result is a SUGGESTION with reasons and a confidence index. This module never applies anything.
The solver runs single-threaded with a fixed seed, so the same inputs always give the same answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from ortools.sat.python import cp_model

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "assignment.yaml"
SCALE = 10  # workloads are solved as integers in tenths


@dataclass(frozen=True)
class Nurse:
    staff_id: str
    skills: frozenset[str] = frozenset()


@dataclass(frozen=True)
class BedNeed:
    bed: str
    room: str
    acuity: int
    news2_total: int | None = None
    news2_fresh: bool = False
    current_nurse: str | None = None
    locked: bool = False
    required_skills: frozenset[str] = field(default_factory=frozenset)


class AssignmentConfig:
    def __init__(self, data: dict[str, Any]) -> None:
        w, o = data["workload"], data["objective"]
        self.acuity_weight = float(w["acuity_weight"])
        self.news2_weight = float(w["news2_weight"])
        self.unknown_news2_points = int(w["unknown_news2_points"])
        self.max_beds_per_nurse = int(w["max_beds_per_nurse"])
        self.balance_weight = int(o["balance_weight"])
        self.change_weight = int(o["change_weight"])
        self.room_weight = int(o["room_weight"])
        self.time_limit_s = float(o["time_limit_s"])

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> AssignmentConfig:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def workload(self, bed: BedNeed) -> float:
        news2 = bed.news2_total if bed.news2_total is not None else self.unknown_news2_points
        return self.acuity_weight * bed.acuity + self.news2_weight * news2


def _loads(assignment: dict[str, str | None], beds: dict[str, BedNeed], cfg: AssignmentConfig,
           nurse_ids: list[str]) -> dict[str, float]:
    loads = {n: 0.0 for n in nurse_ids}
    for bed_id, nurse in assignment.items():
        key = nurse if nurse in loads else "unassigned"
        loads[key] = loads.get(key, 0.0) + cfg.workload(beds[bed_id])
    return {k: round(v, 1) for k, v in loads.items()}


def suggest(nurses: list[Nurse], beds: list[BedNeed], cfg: AssignmentConfig) -> dict[str, Any]:
    nurse_ids = [n.staff_id for n in nurses]
    by_bed = {b.bed: b for b in beds}
    before = {b.bed: b.current_nurse for b in beds}
    load_before = _loads(before, by_bed, cfg, nurse_ids)

    def result(status: str, assignment: dict[str, str], reasons: list[str], solver_factor: float) -> dict[str, Any]:
        changes = [
            {"bed": b, "toStaffId": n, **({"fromStaffId": before[b]} if before[b] else {})}
            for b, n in sorted(assignment.items()) if before[b] != n
        ]
        fresh = sum(1 for b in beds if b.news2_fresh)
        share = fresh / len(beds) if beds else 1.0
        return {
            "status": status,
            "assignment": assignment,
            "changes": changes,
            "loadBefore": load_before,
            "loadAfter": _loads(assignment, by_bed, cfg, nurse_ids) if assignment else load_before,
            "reasons": reasons,
            "confidence": {
                "value": round(solver_factor * (0.5 + 0.5 * share), 3),
                "basis": f"solver {status}; NEWS2 fresh for {fresh} of {len(beds)} occupied beds",
            },
        }

    if not beds:
        return result("optimal", {}, ["No occupied beds."], 1.0)
    if not nurses:
        return result("infeasible", {}, ["No nurse is on the ward: nothing can be assigned."], 0.0)

    model = cp_model.CpModel()
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    for n in nurses:
        for b in beds:
            if b.required_skills <= n.skills:
                x[n.staff_id, b.bed] = model.new_bool_var(f"x_{n.staff_id}_{b.bed}")

    uncovered_skill = [b.bed for b in beds if not any((n, b.bed) in x for n in nurse_ids)]
    if uncovered_skill:
        needed = ", ".join(uncovered_skill)
        return result("infeasible", {}, [f"No nurse on the ward has the skills needed for: {needed}."], 0.0)

    cap = max(cfg.max_beds_per_nurse, math.ceil(len(beds) / len(nurses)))
    weights = {b.bed: round(cfg.workload(b) * SCALE) for b in beds}
    for b in beds:
        model.add_exactly_one(x[n, b.bed] for n in nurse_ids if (n, b.bed) in x)
        if b.locked and b.current_nurse and (b.current_nurse, b.bed) in x:
            model.add(x[b.current_nurse, b.bed] == 1)
    max_load = model.new_int_var(0, sum(weights.values()), "max_load")
    rooms = sorted({b.room for b in beds})
    room_vars = []
    for n in nurse_ids:
        mine = [(x[n, b.bed], b) for b in beds if (n, b.bed) in x]
        model.add(sum(weights[b.bed] * v for v, b in mine) <= max_load)
        model.add(sum(v for v, _ in mine) <= cap)
        for room in rooms:
            covers = model.new_bool_var(f"room_{n}_{room}")
            for v, b in mine:
                if b.room == room:
                    model.add_implication(v, covers)
            room_vars.append(covers)
    moved = [1 - x[b.current_nurse, b.bed] if (b.current_nurse, b.bed) in x else 1
             for b in beds if b.current_nurse in nurse_ids]
    model.minimize(cfg.balance_weight * max_load + cfg.change_weight * SCALE * sum(moved)
                   + cfg.room_weight * SCALE * sum(room_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.time_limit_s
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 7
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result("infeasible", {}, ["No assignment satisfies the constraints (locked beds, skills, bed cap)."],
                      0.0)

    assignment = {b.bed: next(n for n in nurse_ids if (n, b.bed) in x and solver.value(x[n, b.bed])) for b in beds}
    status_name = "optimal" if status == cp_model.OPTIMAL else "feasible"
    return result(status_name, assignment, _reasons(beds, before, assignment, nurse_ids, cfg, by_bed),
                  1.0 if status == cp_model.OPTIMAL else 0.8)


def _reasons(beds: list[BedNeed], before: dict[str, str | None], after: dict[str, str], nurse_ids: list[str],
             cfg: AssignmentConfig, by_bed: dict[str, BedNeed]) -> list[str]:
    reasons = []
    uncovered = sorted(b.bed for b in beds if b.current_nurse not in nurse_ids)
    if uncovered:
        reasons.append(f"{len(uncovered)} bed(s) had no available nurse and are now covered: {', '.join(uncovered)}.")
    load_before = _loads(before, by_bed, cfg, nurse_ids)
    load_after = _loads(after, by_bed, cfg, nurse_ids)
    busiest_before = max((v for k, v in load_before.items() if k != "unassigned"), default=0.0)
    busiest_after = max(load_after.values(), default=0.0)
    reasons.append(f"Busiest nurse's workload (acuity + NEWS2): {busiest_before:.1f} -> {busiest_after:.1f}.")
    kept = sum(1 for b in beds if before[b.bed] == after[b.bed])
    with_nurse = sum(1 for b in beds if before[b.bed] in nurse_ids)
    if with_nurse:
        reasons.append(f"Continuity of care: {kept} of {with_nurse} covered beds keep their nurse.")
    for b in sorted(beds, key=lambda b: -cfg.workload(b)):
        if before[b.bed] != after[b.bed] and (b.news2_total or 0) >= 5:
            reasons.append(f"{b.bed} (NEWS2 {b.news2_total}) goes to {after[b.bed]}, "
                           f"who then carries {load_after[after[b.bed]]:.1f}.")
    rooms = {n: len({by_bed[b].room for b, m in after.items() if m == n}) for n in nurse_ids}
    reasons.append(f"Rooms per nurse: at most {max(rooms.values(), default=0)}.")
    return reasons
