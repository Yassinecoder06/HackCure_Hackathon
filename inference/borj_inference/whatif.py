"""What-if simulation with SimPy (whitepaper 5.3). It compares scenarios; it does not predict outcomes.

Model: nurses and care assistants are limited resources (SimPy PriorityResource). Work arrives as
- bedside calls (Poisson; a share are comfort calls, which go to care assistants only if routing
  is switched on and one is on the ward),
- observation rounds per occupied bed, paced by the bed's NEWS2 band,
- medication doses (Poisson per bed),
- admission assessments (from disruptions).
Disruptions: staff_leaves / staff_joins (nurse or care assistant), admissions, call_surge,
route_comfort_to_assistants, patient_deteriorates.

Honest statistics (whitepaper 5.3): every scenario runs over many seeds; baseline and scenario
use the SAME seeds, and every random stream (call arrivals, call kinds, service times, ...) has its
own generator, so a disruption does not shift the random numbers of unrelated streams. Each
metric is reported as median and 5th-95th percentile. Rates and durations are illustrative until
calibrated with measured ward timings (config/whatif.yaml).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import simpy
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "whatif.yaml"
METRICS = ("wait_for_nurse_min", "longest_wait_min", "queue_length", "nurse_utilization", "overdue_meds",
           "patients_without_obs")
PRIORITY = {"call": 1, "admission": 1, "obs": 2, "med": 3}
BLOCK = -1  # a departing staff member's "task" outranks all work: they leave once their current task ends


@dataclass(frozen=True)
class WardState:
    nurses: int
    care_assistants: int = 0
    beds: tuple[tuple[str, str], ...] = ()  # (bed, NEWS2 band)
    route_comfort: bool = False


@dataclass(frozen=True)
class Disruption:
    type: str
    at_min: float = 0
    role: str = "nurse"
    count: int = 1
    bed: str | None = None
    calls_per_hour: float | None = None


class WhatIfConfig:
    def __init__(self, data: dict[str, Any]) -> None:
        self.calls_per_hour = float(data["calls"]["calls_per_hour"])
        self.comfort_share = float(data["calls"]["comfort_share"])
        self.call_service_min = float(data["calls"]["service_min"])
        self.obs_interval = {k: float(v) for k, v in data["observations"]["interval_min"].items()}
        self.obs_service_min = float(data["observations"]["service_min"])
        self.obs_grace_min = float(data["observations"]["overdue_grace_min"])
        self.doses_per_bed_per_hour = float(data["medications"]["doses_per_bed_per_hour"])
        self.med_service_min = float(data["medications"]["service_min"])
        self.med_overdue_min = float(data["medications"]["overdue_after_min"])
        self.admission_work_min = float(data["admissions"]["nurse_work_min"])
        self.new_patient_band = data["admissions"]["new_patient_band"]
        self.default_seeds = int(data["simulation"]["default_seeds"])
        self.default_horizon_min = int(data["simulation"]["default_horizon_min"])
        self.queue_sample_min = float(data["simulation"]["queue_sample_min"])

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> WhatIfConfig:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def assumptions(self) -> list[str]:
        return [
            f"Calls: {self.calls_per_hour:g}/h for the ward, {self.comfort_share:.0%} non-clinical, "
            f"{self.call_service_min:g} min each on average.",
            "Observation rounds every " + ", ".join(f"{v:g} min ({k})" for k, v in self.obs_interval.items())
            + f", {self.obs_service_min:g} min each.",
            f"Medication doses: {self.doses_per_bed_per_hour:g} per bed per hour, {self.med_service_min:g} min each.",
            f"Admission assessment: {self.admission_work_min:g} min of nurse time per new patient.",
            "Illustrative values, to be calibrated with timings measured in a shadow-mode pilot.",
            "Moving beds between the same nurses does not change capacity: only who is available does.",
        ]


@dataclass
class _Run:
    call_waits_nurse: list[float] = field(default_factory=list)
    call_waits_all: list[float] = field(default_factory=list)
    queue_samples: list[int] = field(default_factory=list)
    nurse_busy_min: float = 0.0
    overdue_meds: int = 0
    beds_without_obs: set[str] = field(default_factory=set)


def run_once(state: WardState, disruptions: list[Disruption], cfg: WhatIfConfig, seed: int,
             horizon_min: float) -> dict[str, float]:
    env = simpy.Environment()
    streams = {name: random.Random(f"{seed}:{name}") for name in
               ("arrivals", "kinds", "call_service", "obs_offset", "med_arrivals", "med_service")}
    joins = {r: sum(d.count for d in disruptions if d.type == "staff_joins" and d.role == r)
             for r in ("nurse", "care_assistant")}
    nurses = simpy.PriorityResource(env, capacity=max(1, state.nurses + joins["nurse"]))
    ca_capacity = state.care_assistants + joins["care_assistant"]
    assistants = simpy.PriorityResource(env, capacity=ca_capacity) if ca_capacity > 0 else None
    run = _Run()
    bands = {bed: band for bed, band in state.beds}
    route_from = 0.0 if state.route_comfort else min(
        (d.at_min for d in disruptions if d.type == "route_comfort_to_assistants"), default=float("inf"))
    surges = sorted((d.at_min, d.calls_per_hour) for d in disruptions if d.type == "call_surge" and d.calls_per_hour)
    available_nurse_min = float(nurses.capacity) * horizon_min

    def block(resource: simpy.PriorityResource, start: float, until: float | None) -> Any:
        yield env.timeout(start)
        with resource.request(priority=BLOCK) as req:
            yield req
            yield env.timeout((until if until is not None else horizon_min + 1) - env.now)

    for d in disruptions:  # joining staff are "not there yet" (blocked) until they arrive
        resource = nurses if d.role == "nurse" else assistants
        if resource is None:
            continue
        for _ in range(d.count):
            if d.type == "staff_leaves":
                env.process(block(resource, d.at_min, None))
                if resource is nurses:
                    available_nurse_min -= max(0.0, horizon_min - d.at_min)
            elif d.type == "staff_joins":
                env.process(block(resource, 0, d.at_min))
                if resource is nurses:
                    available_nurse_min -= min(d.at_min, horizon_min)

    def serve(resource: simpy.PriorityResource, kind: str, duration: float, on_start: Any = None) -> Any:
        arrived = env.now
        with resource.request(priority=PRIORITY[kind]) as req:
            yield req
            if on_start:
                on_start(env.now - arrived)
            start = env.now
            yield env.timeout(duration)
            if resource is nurses:
                run.nurse_busy_min += min(env.now, horizon_min) - min(start, horizon_min)

    pending_calls: dict[int, tuple[float, bool]] = {}

    def call(call_id: int, comfort: bool, duration: float) -> Any:
        to_assistant = comfort and assistants is not None and env.now >= route_from
        resource = assistants if to_assistant else nurses
        pending_calls[call_id] = (env.now, resource is nurses)

        def started(wait: float) -> None:
            pending_calls.pop(call_id, None)
            run.call_waits_all.append(wait)
            if resource is nurses:
                run.call_waits_nurse.append(wait)

        yield from serve(resource, "call", duration, started)

    def call_arrivals() -> Any:
        n = 0
        while True:
            rate = cfg.calls_per_hour
            for at, surge_rate in surges:
                if env.now >= at:
                    rate = surge_rate
            yield env.timeout(streams["arrivals"].expovariate(rate / 60.0))
            comfort = streams["kinds"].random() < cfg.comfort_share
            duration = streams["call_service"].expovariate(1.0 / cfg.call_service_min)
            env.process(call(n, comfort, duration))
            n += 1

    def observations(bed: str, start_delay: float) -> Any:
        due = start_delay
        while due < horizon_min:
            yield env.timeout(max(0.0, due - env.now))

            def started(wait: float, bed: str = bed) -> None:
                if wait > cfg.obs_grace_min:
                    run.beds_without_obs.add(bed)

            env.process(serve(nurses, "obs", cfg.obs_service_min, started))
            due += cfg.obs_interval[bands[bed]]

    def medications(bed: str) -> Any:
        rng = random.Random(f"{seed}:meds:{bed}")
        while True:
            yield env.timeout(rng.expovariate(cfg.doses_per_bed_per_hour / 60.0))

            def started(wait: float) -> None:
                if wait > cfg.med_overdue_min:
                    run.overdue_meds += 1

            env.process(serve(nurses, "med", cfg.med_service_min, started))

    def add_patient(bed: str, band: str, delay: float) -> None:
        bands[bed] = band
        env.process(observations(bed, delay))
        env.process(medications(bed))

    def admissions(d: Disruption) -> Any:
        yield env.timeout(d.at_min)
        for i in range(d.count):
            bed = f"NEW{int(d.at_min)}_{i}"
            env.process(serve(nurses, "admission", cfg.admission_work_min))
            add_patient(bed, cfg.new_patient_band, cfg.admission_work_min)

    def deteriorate(d: Disruption) -> Any:
        yield env.timeout(d.at_min)
        if d.bed in bands:
            bands[d.bed] = "high"

    def sample_queue() -> Any:
        while True:
            run.queue_samples.append(len(nurses.queue))
            yield env.timeout(cfg.queue_sample_min)

    env.process(call_arrivals())
    env.process(sample_queue())
    for bed, band in state.beds:
        add_patient(bed, band, streams["obs_offset"].uniform(0, cfg.obs_interval[band]))
    for d in disruptions:
        if d.type == "admissions":
            env.process(admissions(d))
        elif d.type == "patient_deteriorates":
            env.process(deteriorate(d))
    env.run(until=horizon_min)

    for arrived, by_nurse in pending_calls.values():  # still waiting at the end: censored waits count too
        run.call_waits_all.append(horizon_min - arrived)
        if by_nurse:
            run.call_waits_nurse.append(horizon_min - arrived)
    waits = run.call_waits_nurse
    return {
        "wait_for_nurse_min": sum(waits) / len(waits) if waits else 0.0,
        "longest_wait_min": max(run.call_waits_all, default=0.0),
        "queue_length": sum(run.queue_samples) / len(run.queue_samples) if run.queue_samples else 0.0,
        "nurse_utilization": min(1.0, run.nurse_busy_min / available_nurse_min) if available_nurse_min > 0 else 1.0,
        "overdue_meds": float(run.overdue_meds),
        "patients_without_obs": float(len(run.beds_without_obs)),
    }


def _dist(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def pct(p: float) -> float:
        return round(ordered[min(len(ordered) - 1, int(p * len(ordered)))], 2)

    return {"median": pct(0.5), "p5": pct(0.05), "p95": pct(0.95)}


def compare(state: WardState, disruptions: list[Disruption], cfg: WhatIfConfig, seeds: int,
            horizon_min: float) -> dict[str, Any]:
    baseline = [run_once(state, [], cfg, s, horizon_min) for s in range(seeds)]
    scenario = [run_once(state, disruptions, cfg, s, horizon_min) for s in range(seeds)]
    return {
        "seeds": seeds,
        "horizonMin": int(horizon_min),
        "baseline": {m: _dist([r[m] for r in baseline]) for m in METRICS},
        "scenario": {m: _dist([r[m] for r in scenario]) for m in METRICS},
        "assumptions": cfg.assumptions(),
    }
