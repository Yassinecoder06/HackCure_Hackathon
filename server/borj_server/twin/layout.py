"""Static ward layout and roster from seed/ward-W1.yaml (synthetic)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class StaffSeed:
    staff_id: str
    name: str
    role: str
    skills: tuple[str, ...]


@dataclass(frozen=True)
class WardLayout:
    ward: str
    bed_rooms: dict[str, str]  # bed id -> room id, in seed order
    room_positions: dict[str, tuple[float, float]]
    station: tuple[float, float]
    staff: tuple[StaffSeed, ...]

    @classmethod
    def load(cls, path: Path) -> WardLayout:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        bed_rooms: dict[str, str] = {}
        positions: dict[str, tuple[float, float]] = {}
        for room in data["rooms"]:
            positions[room["id"]] = (float(room["x"]), float(room["y"]))
            for bed in room["beds"]:
                bed_rooms[bed] = room["id"]
        staff = tuple(
            StaffSeed(s["id"], s["name"], s["role"], tuple(s.get("skills", []))) for s in data["staff"]
        )
        station = (float(data["station"]["x"]), float(data["station"]["y"]))
        return cls(data["ward"], dict(sorted(bed_rooms.items())), positions, station, staff)
