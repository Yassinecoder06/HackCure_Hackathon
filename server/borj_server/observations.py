"""Manual observations: the 10-second bedside form becomes an ordinary `vitals` event.

The form sends only what the nurse actually entered. Nothing is filled in with defaults, so an
absent parameter stays absent and NEWS2 is labelled partial (safety invariant 5). The event goes
through the same ingest path as device vitals: validated against the contract, encrypted, stored,
applied to the twin and pushed on the live stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "observations.yaml"


@dataclass(frozen=True)
class ObservationsConfig:
    stale_after_s: int
    roles: tuple[str, ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> ObservationsConfig:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))["manual"]
        return cls(stale_after_s=int(d["stale_after_s"]), roles=tuple(d["roles"]))


def manual_vitals(event_id: str, ts: str, ward: str, bed: str, staff_id: str, params: dict[str, Any],
                  cfg: ObservationsConfig) -> dict[str, Any]:
    """A `vitals` payload with sourceType manual (contracts/schemas/vitals.schema.json)."""
    return {
        "schemaVersion": 1, "eventId": event_id, "ts": ts, "tsSource": "server", "ward": ward, "bed": bed,
        "source": "staff-app", "sourceType": "manual", "staffId": staff_id, "params": params,
        "quality": {"valid": True, "stale_after_s": cfg.stale_after_s},
    }
