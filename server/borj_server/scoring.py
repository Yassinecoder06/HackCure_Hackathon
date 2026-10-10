"""Bridge between the twin and the inference layer for NEWS2.

The server owns freshness (it knows the ward clock), so each reading goes to inference with
its status already decided. Inference never sees a stale value as if it were fresh.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .twin.state import WardTwin
from .twin.views import reading_status


def news2_inputs(twin: WardTwin, now: datetime) -> list[dict[str, Any]]:
    """One entry per admitted bed, in the inference /v1/news2/batch request shape."""
    beds = []
    for bed in twin.beds.values():
        if bed.admission is None:
            continue
        spo2_scale = 1
        params: dict[str, Any] = {}
        for param, reading in bed.vitals.items():
            if param == "spo2_scale":
                spo2_scale = reading.value  # a clinician's standing decision, not a measurement
                continue
            params[param] = {
                "value": reading.value,
                "status": reading_status(reading, now),
                "ageS": max(0, int((now - reading.ts).total_seconds())),
                "staleAfterS": reading.stale_after_s,
            }
        beds.append({"bed": bed.bed, "spo2Scale": spo2_scale, "params": params})
    return beds


def attach_news2(snapshot: dict[str, Any], results: dict[str, dict[str, Any]] | None) -> None:
    """Merge inference results into a snapshot. results=None means inference was unreachable."""
    for bed in snapshot["beds"]:
        if bed["admission"] is None or results is None:
            continue  # bed_view already set not_admitted / unavailable
        result = results.get(bed["bed"])
        if result is not None:
            bed["news2"] = result
            bed["news2Status"] = "ok"
