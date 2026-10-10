"""Unit and integration tests for borj_sim scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import borj_contracts as bc
import pytest
from borj_sim.config import ScenarioConfig, WardConfig
from borj_sim.runner import SimulationRunner

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = ROOT / "simulator" / "scenarios"
WARD_FILE = ROOT / "seed" / "ward-W1.yaml"


@pytest.mark.parametrize(
    "scenario_name",
    ["deterioration.yaml", "normal-night.yaml", "night-shift-peak.yaml"],
)
def test_scenario_produces_valid_contract_messages(scenario_name):
    scenario_path = SCENARIOS_DIR / scenario_name
    scenario = ScenarioConfig.load(scenario_path)
    ward = WardConfig.load(WARD_FILE)

    seen_event_ids = set()
    messages = []

    def record_event(topic, payload):
        # Validate against contracts
        bc.validate_message(topic, payload)

        if "eventId" in payload:
            eid = payload["eventId"]
            assert eid not in seen_event_ids, f"Duplicate eventId detected: {eid}"
            seen_event_ids.add(eid)

        # Invariant 5: absent is absent, never null
        if "params" in payload:
            for k, v in payload["params"].items():
                assert v is not None, f"Parameter {k} must not be None"

        messages.append((topic, payload))

    runner = SimulationRunner(
        scenario=scenario,
        ward=ward,
        speed=0,  # run instantaneously
        dry_run=True,
        on_event=record_event,
    )

    # Run for 30 minutes of simulation time
    count = runner.run(max_minutes=30)
    assert count > 0
    assert len(messages) == count


def test_deterministic_seeding():
    """Identical scenario seeds must produce identical message streams."""
    scenario_path = SCENARIOS_DIR / "deterioration.yaml"
    ward = WardConfig.load(WARD_FILE)

    def run_sim():
        scenario = ScenarioConfig.load(scenario_path)
        events = []
        runner = SimulationRunner(
            scenario=scenario,
            ward=ward,
            speed=0,
            dry_run=True,
            on_event=lambda t, p: events.append((t, json.dumps(p, sort_keys=True))),
        )
        runner.run(max_minutes=15)
        return events

    run1 = run_sim()
    run2 = run_sim()

    assert len(run1) == len(run2)
    assert run1 == run2, "Different outputs from identical seed"


def test_deterioration_scenario_events():
    """Verify B06 actually deteriorates and manual obs are emitted."""
    scenario_path = SCENARIOS_DIR / "deterioration.yaml"
    scenario = ScenarioConfig.load(scenario_path)
    ward = WardConfig.load(WARD_FILE)

    b06_vitals = []

    def record_event(topic, payload):
        if topic == "borj/W1/B06/vitals":
            b06_vitals.append(payload)

    runner = SimulationRunner(
        scenario=scenario,
        ward=ward,
        speed=0,
        dry_run=True,
        on_event=record_event,
    )
    # Deterioration starts at 15m and manual entry at 95m
    runner.run(max_minutes=100)

    # Check that B06 had vitals observations
    assert len(b06_vitals) > 10

    # Initial vs late pulse / temp
    assert b06_vitals[0]["params"].get("pulse", 72) < 90
    late_pulse = [v["params"].get("pulse") for v in b06_vitals[-5:] if "pulse" in v["params"]]
    assert any(p > 100 for p in late_pulse), f"Pulse should have deteriorated above 100: {late_pulse}"

    # Manual observation with consciousness C
    manual_entries = [v for v in b06_vitals if v["sourceType"] == "manual"]
    assert any(m["params"].get("consciousness") == "C" for m in manual_entries)


def test_mock_medical_monitor():
    from borj_sim.mock_monitor import MockMedicalMonitor

    monitor = MockMedicalMonitor(ward="W1", bed="B06", profile="deteriorate")
    vitals = monitor.publish_vitals()
    bc.validate_message("borj/W1/B06/vitals", vitals)
    assert vitals["bed"] == "B06"
    assert vitals["ward"] == "W1"
    assert "pulse" in vitals["params"]
    assert "spo2" in vitals["params"]
    assert "sys_bp" in vitals["params"]
    assert "temp_c" in vitals["params"]
    assert "resp_rate" in vitals["params"]

