"""What-if simulator. First validated against queueing theory (whitepaper 5.3, Figure 2 table)."""

from __future__ import annotations

import copy

import pytest
from borj_inference.whatif import METRICS, Disruption, WardState, WhatIfConfig, compare, run_once

CFG = WhatIfConfig.load()
BEDS = tuple((f"B{i:02d}", "low") for i in range(1, 12))


def calls_only(calls_per_hour: float) -> WhatIfConfig:
    cfg = copy.copy(CFG)
    cfg.calls_per_hour, cfg.comfort_share, cfg.call_service_min = calls_per_hour, 0.4, 8.0
    return cfg


def mean_nurse_wait(nurses: int, route_comfort: bool, seeds: int = 40, horizon_min: float = 6000) -> float:
    """At 87% load (4 nurses, no routing) queue waits converge slowly: 40 seeds of 100 h give a standard
    error of about 0.5 min on 10.8, so the 15% tolerance is about 3 standard errors."""
    cfg = calls_only(26)
    state = WardState(nurses=nurses, care_assistants=50 if route_comfort else 0, beds=(), route_comfort=route_comfort)
    waits = [run_once(state, [], cfg, seed, horizon_min)["wait_for_nurse_min"] for seed in range(seeds)]
    return sum(waits) / len(waits)


@pytest.mark.parametrize(("nurses", "route_comfort", "erlang_c_min", "tolerance"), [
    (4, False, 10.8, 0.15),   # all calls to nurses
    (5, False, 1.9, 0.20),
    (3, True, 4.2, 0.15),     # 40% of calls routed to care assistants
    (4, True, 0.8, 0.25),
])
def test_reproduces_the_erlang_c_table(nurses, route_comfort, erlang_c_min, tolerance):
    """Peak demand 26 calls/h, 8 min each (Poisson arrivals, exponential service): the simulator's mean
    wait must match the analytic Erlang-C values from the whitepaper before we trust its scenarios."""
    simulated = mean_nurse_wait(nurses, route_comfort)
    assert simulated == pytest.approx(erlang_c_min, rel=tolerance)


def test_three_nurses_without_routing_is_unstable():
    """Erlang-C says 'unbounded' (load 3.47 Erlang > 3 nurses): waits keep growing with the horizon."""
    short = mean_nurse_wait(3, False, seeds=4, horizon_min=600)
    long = mean_nurse_wait(3, False, seeds=4, horizon_min=3000)
    assert long > 2 * short > 20


def test_same_seeds_same_results():
    state = WardState(nurses=3, care_assistants=1, beds=BEDS)
    disruptions = [Disruption("staff_leaves", at_min=60)]
    assert compare(state, disruptions, CFG, 10, 240) == compare(state, disruptions, CFG, 10, 240)


def test_nurse_called_away_makes_things_worse():
    state = WardState(nurses=3, care_assistants=1, beds=BEDS)
    result = compare(state, [Disruption("staff_leaves", at_min=30)], CFG, 60, 240)
    assert set(result["baseline"]) == set(METRICS)
    assert result["scenario"]["wait_for_nurse_min"]["median"] > result["baseline"]["wait_for_nurse_min"]["median"]
    assert result["scenario"]["nurse_utilization"]["median"] > result["baseline"]["nurse_utilization"]["median"]
    for metric in METRICS:
        dist = result["scenario"][metric]
        assert dist["p5"] <= dist["median"] <= dist["p95"]


def test_routing_comfort_calls_to_assistants_helps_nurses():
    state = WardState(nurses=3, care_assistants=1, beds=BEDS)
    surge = Disruption("call_surge", at_min=0, calls_per_hour=26)
    worse = compare(state, [surge], CFG, 60, 240)["scenario"]["wait_for_nurse_min"]["median"]
    better = compare(state, [surge, Disruption("route_comfort_to_assistants")], CFG, 60, 240)
    assert better["scenario"]["wait_for_nurse_min"]["median"] < worse


def test_admissions_and_deterioration_add_work():
    state = WardState(nurses=3, care_assistants=1, beds=BEDS)
    base = compare(state, [], CFG, 40, 240)["baseline"]["nurse_utilization"]["median"]
    busy = compare(state, [Disruption("admissions", at_min=30, count=2),
                           Disruption("patient_deteriorates", at_min=0, bed="B06")], CFG, 40, 240)
    assert busy["scenario"]["nurse_utilization"]["median"] > base
    assert any("calibrated" in a for a in busy["assumptions"])
