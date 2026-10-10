"""Clinical and biomedical validity checker for gateway observations.

Implements validity and freshness checks per Whitepaper 4.1 and ADR 0010.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "quality.yaml"


@dataclass
class QualityResult:
    valid: bool
    stale_after_s: int
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "valid": self.valid,
            "stale_after_s": self.stale_after_s,
        }
        if self.flags:
            d["flags"] = self.flags
        return d


class QualityChecker:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or DEFAULT_CONFIG_PATH
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.params_cfg = raw.get("parameters", {})

    def check(self, params: dict[str, Any], flags: list[str] | None = None) -> QualityResult:
        all_flags = list(flags or [])
        stale_s_list = []

        for name, val in params.items():
            if val is None:
                continue

            cfg = self.params_cfg.get(name)
            if not cfg:
                continue

            stale_s_list.append(cfg.get("stale_after_s", 900))

            # Sensor-off check (e.g. pulse 0 or spo2 0)
            if name in ("spo2", "pulse", "resp_rate") and val == 0:
                if "sensor_off" not in all_flags:
                    all_flags.append("sensor_off")

            # Physical plausibility check
            min_val = cfg.get("min_plausible")
            max_val = cfg.get("max_plausible")
            if min_val is not None and val < min_val:
                if "implausible" not in all_flags:
                    all_flags.append("implausible")
            if max_val is not None and val > max_val:
                if "implausible" not in all_flags:
                    all_flags.append("implausible")

        stale_after = min(stale_s_list) if stale_s_list else 900
        is_valid = len(all_flags) == 0

        return QualityResult(
            valid=is_valid,
            stale_after_s=stale_after,
            flags=all_flags,
        )
