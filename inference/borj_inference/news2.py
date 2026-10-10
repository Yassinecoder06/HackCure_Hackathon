"""Deterministic NEWS2 scoring with explicit handling of missing and stale data.

Every threshold comes from config/news2.yaml (safety invariant 8). Rules:
- Only fresh, valid parameters are scored. Missing, stale or invalid ones are listed and the
  result is labelled PARTIAL: its total is a minimum, because unscored parameters could add
  points (safety invariant 5).
- The result explains itself: points per parameter, plus a confidence index that measures
  input quality, not certainty about the patient (HackCure section 6, invariant 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PARAMS = ("resp_rate", "spo2", "on_oxygen", "sys_bp", "pulse", "consciousness", "temp_c")
LABELS = {
    "resp_rate": "respiratory rate",
    "spo2": "SpO2",
    "on_oxygen": "oxygen status",
    "sys_bp": "systolic BP",
    "pulse": "pulse",
    "consciousness": "consciousness (ACVPU)",
    "temp_c": "temperature",
}
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "news2.yaml"


@dataclass(frozen=True)
class Reading:
    """One parameter as the server sees it: value plus freshness status at scoring time."""

    value: Any
    status: str  # fresh | stale | invalid
    age_s: int
    stale_after_s: int


class News2Config:
    def __init__(self, data: dict[str, Any]) -> None:
        self.params = data["parameters"]
        self.response = data["response"]
        self.weight_at_stale = float(data["confidence"]["weight_at_stale_threshold"])

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> News2Config:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))


def _band_points(bands: list[dict[str, Any]], value: float) -> int:
    for band in bands:
        if band["upto"] is None or value <= band["upto"]:
            return int(band["points"])
    raise ValueError(f"no band covers {value}")


def _points(cfg: News2Config, param: str, value: Any, spo2_scale: int, on_oxygen: bool | None) -> int | None:
    """Points for one fresh parameter, or None if it cannot be scored without another input."""
    c = cfg.params[param]
    if param == "on_oxygen":
        return int(c["points_if_true"] if value else c["points_if_false"])
    if param == "consciousness":
        return int(c["points"][value])
    if param == "spo2":
        if spo2_scale == 1:
            return _band_points(c["scale_1"], value)
        if value <= c["scale_2"][-1]["upto"]:
            return _band_points(c["scale_2"], value)
        if on_oxygen is None:
            return None  # scale 2 above 92% depends on oxygen use, which is unknown
        return _band_points(c["scale_2_from_93_on_oxygen" if on_oxygen else "scale_2_from_93_on_air"], value)
    return _band_points(c["bands"], value)


def _age_weight(cfg: News2Config, reading: Reading) -> float:
    fraction = min(max(reading.age_s, 0) / max(reading.stale_after_s, 1), 1.0)
    return 1.0 - (1.0 - cfg.weight_at_stale) * fraction


def score(readings: dict[str, Reading], cfg: News2Config, spo2_scale: int = 1) -> dict[str, Any]:
    """Score one bed. Returns the News2Result shape from contracts/openapi.yaml (minus computedAt)."""
    fresh = {p: r for p, r in readings.items() if p in PARAMS and r.status == "fresh"}
    on_oxygen = bool(fresh["on_oxygen"].value) if "on_oxygen" in fresh else None

    components: list[dict[str, Any]] = []
    missing: list[str] = []
    stale: list[str] = []
    notes: list[str] = []
    weights: list[float] = []
    total = 0
    any3 = False

    for param in PARAMS:
        reading = readings.get(param)
        if reading is None:
            components.append({"param": param, "status": "missing"})
            missing.append(param)
            weights.append(0.0)
            continue
        component: dict[str, Any] = {"param": param, "value": reading.value, "status": reading.status}
        if reading.status != "fresh":
            (stale if reading.status == "stale" else missing).append(param)
            weights.append(0.0)
            components.append(component)
            continue
        points = _points(cfg, param, reading.value, spo2_scale, on_oxygen)
        if points is None:
            missing.append(param)
            notes.append("SpO2 scale 2 needs a fresh oxygen status")
            weights.append(0.0)
        else:
            component["points"] = points
            total += points
            any3 = any3 or points == 3
            weights.append(_age_weight(cfg, reading))
        components.append(component)

    complete = not missing and not stale
    high, medium = cfg.response["high_from_total"], cfg.response["medium_from_total"]
    band = "high" if total >= high else "medium" if total >= medium else "low_medium" if any3 else "low"

    if complete:
        label = f"NEWS2 {total}"
    else:
        gaps = [f"{LABELS[p]} {'invalid' if readings.get(p) and readings[p].status == 'invalid' else 'missing'}"
                for p in missing] + [f"{LABELS[p]} stale" for p in stale]
        label = f"Partial NEWS2, at least {total}: " + ", ".join(gaps + notes)

    scored = sum(1 for c in components if "points" in c)
    basis = f"{scored} of {len(PARAMS)} parameters fresh and valid"
    if missing or stale:
        basis += "; not scored: " + ", ".join(LABELS[p] for p in missing + stale)

    return {
        "total": total,
        "complete": complete,
        "band": band,
        "anySingleParam3": any3,
        "response": cfg.response["texts"][band],
        "components": components,
        "missing": missing,
        "stale": stale,
        "label": label,
        "spo2Scale": spo2_scale,
        "confidence": {"value": round(sum(weights) / len(PARAMS), 3), "basis": basis},
    }
