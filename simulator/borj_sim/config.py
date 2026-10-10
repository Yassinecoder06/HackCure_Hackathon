"""Scenario and Ward configuration loaders for borj_sim."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeviceProfile:
    type: str
    provides: list[str]


@dataclass
class StaffMember:
    id: str
    name: str
    role: str
    skills: list[str] = field(default_factory=list)


@dataclass
class WardConfig:
    ward: str
    name: str
    station: dict[str, float]
    rooms: list[dict[str, Any]]
    device_profiles: dict[str, list[dict[str, Any]]]
    beds: dict[str, str]  # bed_id -> profile_name
    staff: list[StaffMember]

    @classmethod
    def load(cls, path: Path) -> WardConfig:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        staff = [
            StaffMember(
                id=s["id"],
                name=s["name"],
                role=s["role"],
                skills=s.get("skills", []),
            )
            for s in data.get("staff", [])
        ]
        return cls(
            ward=data["ward"],
            name=data["name"],
            station=data["station"],
            rooms=data["rooms"],
            device_profiles=data["device_profiles"],
            beds=data["beds"],
            staff=staff,
        )


@dataclass
class ScenarioRates:
    device_vitals_every_min: int = 5
    manual_obs_every_min: int = 60
    device_heartbeat_every_min: int = 15
    calls_per_hour: float = 6.0
    comfort_share: float = 0.4
    repeat_press_prob: float = 0.05
    artifact_prob: float = 0.0
    background_ack_prob: float = 0.9
    ack_delay_min: tuple[int, int] = (1, 4)
    resolve_delay_min: tuple[int, int] = (3, 8)


@dataclass
class ScenarioConfig:
    name: str
    description: str
    ward_file: str
    start: str  # ISO timestamp
    duration_min: int
    seed: int
    on_shift: list[str]
    empty_beds: list[str]
    rates: ScenarioRates
    events: list[dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> ScenarioConfig:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        rates_raw = data.get("rates", {})
        bg_ack = rates_raw.get("background_ack", {})

        rates = ScenarioRates(
            device_vitals_every_min=rates_raw.get("device_vitals_every_min", 5),
            manual_obs_every_min=rates_raw.get("manual_obs_every_min", 60),
            device_heartbeat_every_min=rates_raw.get("device_heartbeat_every_min", 15),
            calls_per_hour=float(rates_raw.get("calls_per_hour", 6.0)),
            comfort_share=float(rates_raw.get("comfort_share", 0.4)),
            repeat_press_prob=float(rates_raw.get("repeat_press_prob", 0.05)),
            artifact_prob=float(rates_raw.get("artifact_prob", 0.0)),
            background_ack_prob=float(bg_ack.get("prob", 0.9)),
            ack_delay_min=tuple(bg_ack.get("delay_min", [1, 4])),
            resolve_delay_min=tuple(bg_ack.get("resolve_after_min", [3, 8])),
        )

        return cls(
            name=data["name"],
            description=data.get("description", "").strip(),
            ward_file=data["ward_file"],
            start=data["start"],
            duration_min=data["duration_min"],
            seed=data.get("seed", 42),
            on_shift=data.get("on_shift", []),
            empty_beds=data.get("empty_beds", []),
            rates=rates,
            events=data.get("events", []),
        )
