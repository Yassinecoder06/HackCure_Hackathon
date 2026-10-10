from __future__ import annotations

from borj_server.timeutil import parse_ts
from borj_server.twin.views import snapshot_view

from .conftest import openapi_validator


def b04_vitals(ingestor, now: str) -> dict:
    view = snapshot_view(ingestor.twin, parse_ts(now), "sim")
    return next(b for b in view["beds"] if b["bed"] == "B04")["vitals"]


def test_freshness_is_labelled_against_ward_clock(ingestor, make_event):
    """Invariant 5: a reading past stale_after_s is shown as stale, never as a normal value."""
    ingestor.handle(*make_event("binding"))
    ingestor.handle(*make_event("vitals.device"))  # 22:03:21, stale after 900 s

    fresh = b04_vitals(ingestor, "2026-10-10T22:10:00Z")["pulse"]
    assert (fresh["status"], fresh["ageS"]) == ("fresh", 399)

    stale = b04_vitals(ingestor, "2026-10-10T22:20:00Z")["pulse"]
    assert (stale["status"], stale["ageS"]) == ("stale", 999)


def test_invalid_reading_is_labelled_invalid(ingestor, make_event):
    ingestor.handle(*make_event("binding"))
    ingestor.handle(*make_event("vitals.device", quality={"valid": False, "stale_after_s": 900, "flags": ["artifact"]}))
    assert b04_vitals(ingestor, "2026-10-10T22:04:00Z")["pulse"]["status"] == "invalid"


def test_snapshot_matches_openapi_contract(ingestor, make_event):
    ingestor.handle(*make_event("binding"))
    ingestor.handle(*make_event("vitals.device"))
    ingestor.handle(*make_event("vitals.manual"))
    ingestor.handle(*make_event("device-status"))
    ingestor.handle(*make_event("staff-presence"))
    view = snapshot_view(ingestor.twin, parse_ts("2026-10-10T22:10:00Z"), "sim")

    errors = list(openapi_validator("WardSnapshot").iter_errors(view))
    assert not errors, [e.message for e in errors]
    assert len(view["beds"]) == 12
