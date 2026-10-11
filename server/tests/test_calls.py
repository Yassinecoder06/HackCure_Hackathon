"""Call engine: routing, escalation, acks (contracts/mqtt-topics.md, server/config/calls.yaml)."""

from __future__ import annotations

import pytest
from borj_server.alerts import FirstSeen, derive_alerts
from borj_server.calls import CallConfig, CallEngine
from borj_server.timeutil import parse_ts
from borj_server.twin.views import snapshot_view

CFG = CallConfig.load()  # ack after 120 s, escalate after 300 s, NEWS2 threshold 5
PRESSED = "2026-10-10T22:12:40Z"


@pytest.fixture
def engine(ingestor):
    news2 = {}
    published = []
    eng = CallEngine(ingestor, CFG, news2_total=lambda bed: news2.get(bed),
                     publish=lambda topic, payload: published.append((topic, payload)))
    ingestor.listeners.append(eng.on_event)
    eng.news2, eng.published = news2, published  # test handles
    return eng


def clock(ingestor, ts):
    ingestor.handle("borj/W1/sim/clock", {"schemaVersion": 1, "ward": "W1", "simTs": ts, "speed": 1,
                                          "scenario": "t", "running": True})


def press(ingestor, make_event, **overrides):
    return ingestor.handle(*make_event("call", **{"ts": PRESSED, **overrides}))


def ack(ingestor, make_event, action="acknowledge", staff="N1", call_id="C-B06-0001"):
    return ingestor.handle(*make_event("ack", staffId=staff, target="call", targetId=call_id, action=action,
                                       ts="2026-10-10T22:13:00Z"))


def call(ingestor, call_id="C-B06-0001"):
    return ingestor.twin.calls[call_id]


def test_assist_press_is_sent_to_nurses_and_published_retained(ingestor, make_event, engine):
    press(ingestor, make_event)
    c = call(ingestor)
    assert (c.state, c.escalation_level, c.routed_to_role) == ("sent", 0, "nurse")
    topic, payload = engine.published[-1]
    assert topic == "borj/W1/B06/call/state" and payload["state"] == "sent"


def test_comfort_press_goes_to_care_assistants(ingestor, make_event, engine):
    press(ingestor, make_event, kind="comfort", callId="C-B06-0002")
    assert call(ingestor, "C-B06-0002").routed_to_role == "care_assistant"


def test_ack_then_resolve(ingestor, make_event, engine):
    press(ingestor, make_event)
    ack(ingestor, make_event)
    assert (call(ingestor).state, call(ingestor).acknowledged_by) == ("acknowledged", "N1")
    ack(ingestor, make_event, action="resolve")
    assert call(ingestor).state == "resolved"
    assert snapshot_view(ingestor.twin, parse_ts(PRESSED), "sim")["calls"] == []


def test_unacknowledged_call_escalates_on_the_ward_clock(ingestor, make_event, engine):
    press(ingestor, make_event)
    clock(ingestor, "2026-10-10T22:14:39Z")
    assert call(ingestor).escalation_level == 0
    clock(ingestor, "2026-10-10T22:14:40Z")  # 120 s after the press
    c = call(ingestor)
    assert (c.state, c.escalation_level, c.escalation_reason) == ("escalated", 1, "unacknowledged_timeout")
    clock(ingestor, "2026-10-10T22:17:40Z")  # 300 s
    c = call(ingestor)
    assert (c.escalation_level, c.routed_to_role) == (2, "charge_nurse")
    assert CFG.escalated_to("assist", 2) == ["nurse", "charge_nurse", "doctor"]
    audit = [e["action"] for e in ingestor.store.audit_entries()]
    assert audit.count("call.escalated") == 2


def test_acknowledged_call_does_not_escalate(ingestor, make_event, engine):
    press(ingestor, make_event)
    ack(ingestor, make_event)
    clock(ingestor, "2026-10-10T22:30:00Z")
    assert (call(ingestor).state, call(ingestor).escalation_level) == ("acknowledged", 0)


def test_repeat_press_escalates_one_level_each_time(ingestor, make_event, engine):
    press(ingestor, make_event)
    press(ingestor, make_event, pressCount=2, ts="2026-10-10T22:13:10Z")
    assert (call(ingestor).escalation_level, call(ingestor).escalation_reason) == (1, "repeat_press")
    press(ingestor, make_event, pressCount=3, ts="2026-10-10T22:13:30Z")
    assert (call(ingestor).escalation_level, call(ingestor).escalation_reason) == (2, "triple_tap_emergency")


def test_triple_tap_immediate_emergency(ingestor, make_event, engine):
    # Patient taps 3 times immediately (pressCount >= 3 on initial delivery)
    press(ingestor, make_event, pressCount=3)
    c = call(ingestor)
    assert (c.escalation_level, c.escalation_reason, c.routed_to_role) == (2, "triple_tap_emergency", "charge_nurse")


def test_press_from_high_news2_patient_escalates_at_once_even_if_comfort(ingestor, make_event, engine):
    engine.news2["B06"] = 6
    press(ingestor, make_event, kind="comfort")
    c = call(ingestor)
    assert (c.state, c.escalation_level, c.escalation_reason, c.routed_to_role) == (
        "escalated", 1, "high_news2", "nurse")


def test_late_delivered_press_escalates_from_the_original_press_time(ingestor, make_event, engine):
    clock(ingestor, "2026-10-10T22:18:00Z")
    press(ingestor, make_event, deliveredLate=True)  # pressed 22:12:40, arrives after a link outage
    clock(ingestor, "2026-10-10T22:18:01Z")
    c = call(ingestor)
    assert c.delivered_late and c.escalation_level == 2


def test_duplicate_press_changes_nothing(ingestor, make_event, engine):
    """Invariant 6 for calls: a replayed press neither re-sends nor escalates."""
    topic, payload = make_event("call", ts=PRESSED)
    ingestor.handle(topic, payload)
    count = len(engine.published)
    assert ingestor.handle(topic, payload).status == "duplicate"
    assert len(engine.published) == count


def test_replay_rebuilds_call_states_without_rerunning_timers(ingestor, make_event, engine):
    press(ingestor, make_event)
    clock(ingestor, "2026-10-10T22:17:40Z")
    before = (call(ingestor).state, call(ingestor).escalation_level)
    published = len(engine.published)
    ingestor.rebuild()
    assert (call(ingestor).state, call(ingestor).escalation_level) == before
    assert len(engine.published) == published


def test_escalated_call_and_news2_alerts(ingestor, make_event, engine):
    ingestor.handle(*make_event("binding"))  # B04 admitted
    press(ingestor, make_event)
    clock(ingestor, "2026-10-10T22:17:40Z")
    news2 = {"B04": {"band": "high", "total": 8, "complete": True, "response": "Emergency.", "label": "NEWS2 8",
                     "components": [{"param": "pulse", "value": 124, "points": 2, "status": "fresh"}],
                     "confidence": {"value": 0.9, "basis": "7 of 7"}}}
    alerts = derive_alerts(ingestor.twin, news2, parse_ts("2026-10-10T22:17:40Z"), CFG, FirstSeen())
    by_type = {a["type"]: a for a in alerts}
    assert by_type["call_escalated"]["priority"] == "critical"
    assert by_type["call_escalated"]["escalatedTo"] == ["nurse", "charge_nurse", "doctor"]
    assert by_type["news2_high"]["priority"] == "critical"
    assert "Pulse 124 scores 2" in by_type["news2_high"]["explanation"]
    assert all(len(a["alertId"]) <= 40 for a in alerts)
