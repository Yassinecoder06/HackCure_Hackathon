from __future__ import annotations

from borj_server.timeutil import parse_ts
from borj_server.twin.views import snapshot_view

NOW = parse_ts("2026-10-10T22:10:00Z")


def admit_b04(ingestor, make_event, ts="2026-10-10T22:00:00Z"):
    return ingestor.handle(*make_event("binding", ts=ts))


def test_binding_then_vitals_updates_twin(ingestor, make_event):
    assert admit_b04(ingestor, make_event).status == "accepted"
    result = ingestor.handle(*make_event("vitals.device"))
    assert (result.status, result.detail) == ("accepted", "applied")

    bed = ingestor.twin.beds["B04"]
    assert bed.admission.admission_id == "ADM-0004"
    assert bed.vitals["pulse"].value == 112
    assert "MON-B04" in bed.devices


def test_absent_parameters_stay_absent(ingestor, make_event):
    """Invariant 5: the device sends no consciousness/on_oxygen, so the twin has none (not 0/None)."""
    admit_b04(ingestor, make_event)
    ingestor.handle(*make_event("vitals.device"))
    vitals = ingestor.twin.beds["B04"].vitals
    assert "consciousness" not in vitals
    assert "on_oxygen" not in vitals


def test_duplicate_event_changes_nothing(ingestor, make_event):
    """Invariant 6."""
    admit_b04(ingestor, make_event)
    topic, payload = make_event("vitals.device")
    assert ingestor.handle(topic, payload).status == "accepted"
    before = snapshot_view(ingestor.twin, NOW, "wall")

    again = ingestor.handle(topic, dict(payload, params={"pulse": 40}))  # same eventId, even if content differs
    assert again.status == "duplicate"
    assert snapshot_view(ingestor.twin, NOW, "wall") == before
    assert ingestor.store.count() == 2


def test_invalid_messages_are_rejected_and_not_stored(ingestor, make_event):
    topic, payload = make_event("vitals.device")
    assert ingestor.handle_raw(topic, b"{not json").status == "invalid"
    assert ingestor.handle(topic, dict(payload, params={"spo2": None})).status == "invalid"
    assert ingestor.handle("borj/W1/B05/vitals", payload).status == "invalid"  # topic/payload bed mismatch
    assert ingestor.handle("borj/W1/B04/nonsense", payload).status == "invalid"
    assert ingestor.store.count() == 0


def test_vitals_without_admission_are_not_attached(ingestor, make_event):
    result = ingestor.handle(*make_event("vitals.device"))
    assert result.detail == "ignored:no_admission_at_ts"
    assert ingestor.twin.beds["B04"].vitals == {}


def test_late_reading_does_not_overwrite_newer(ingestor, make_event):
    admit_b04(ingestor, make_event)
    ingestor.handle(*make_event("vitals.device", ts="2026-10-10T22:05:00Z", params={"pulse": 90}))
    ingestor.handle(*make_event("vitals.device", ts="2026-10-10T22:04:00Z", params={"pulse": 130}))
    reading = ingestor.twin.beds["B04"].vitals["pulse"]
    assert reading.value == 90
    assert reading.ts == parse_ts("2026-10-10T22:05:00Z")


def test_out_of_order_binding_rebuilds_so_live_equals_replay(ingestor, make_event):
    """Vitals that arrive before the (late) admission binding still end up attached."""
    ingestor.handle(*make_event("vitals.device", ts="2026-10-10T22:03:21Z"))
    assert ingestor.twin.beds["B04"].vitals == {}

    result = admit_b04(ingestor, make_event, ts="2026-10-10T22:00:00Z")
    assert result.detail == "rebuilt"
    assert ingestor.twin.beds["B04"].vitals["pulse"].value == 112


def test_discharge_and_readmit_never_inherit_old_readings(ingestor, make_event):
    admit_b04(ingestor, make_event)
    ingestor.handle(*make_event("vitals.device"))
    ingestor.handle(*make_event("binding", action="discharge", ts="2026-10-10T22:30:00Z"))
    bed = ingestor.twin.beds["B04"]
    assert bed.admission is None and bed.vitals == {}

    ingestor.handle(*make_event("binding", admissionId="ADM-0099", patientRef="Patient 99",
                                ts="2026-10-10T22:40:00Z"))
    assert bed.admission.admission_id == "ADM-0099"
    assert bed.vitals == {}


def test_rebuild_from_log_matches_live_twin(ingestor, make_event):
    admit_b04(ingestor, make_event)
    ingestor.handle(*make_event("vitals.device"))
    ingestor.handle(*make_event("vitals.manual"))
    ingestor.handle(*make_event("device-status"))
    ingestor.handle(*make_event("staff-presence"))
    ingestor.handle(*make_event("call"))  # stored only until P2
    live = snapshot_view(ingestor.twin, NOW, "wall")

    ingestor.rebuild()
    assert snapshot_view(ingestor.twin, NOW, "wall") == live


def test_staff_presence(ingestor, make_event):
    ingestor.handle(*make_event("staff-presence", onWard=True, reason="shift_start", ts="2026-10-10T22:00:00Z"))
    member = ingestor.twin.staff["N3"]
    assert (member.on_shift, member.on_ward) == (True, True)
    ingestor.handle(*make_event("staff-presence"))  # called away at 00:50
    assert (member.on_shift, member.on_ward) == (True, False)


def test_other_ward_and_clock_are_not_stored(ingestor, make_event, clock_at):
    assert ingestor.handle(*make_event("vitals.device", ward="W2")).status == "other_ward"
    clock_at("2026-10-10T22:15:00Z")
    assert ingestor.clock.effective_mode == "sim"
    assert ingestor.clock.now() == parse_ts("2026-10-10T22:15:00Z")
    assert ingestor.store.count() == 0
