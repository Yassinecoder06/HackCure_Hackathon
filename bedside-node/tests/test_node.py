"""Unit tests for BedsideNode state machine and contract compliance."""

from __future__ import annotations

import borj_contracts as bc
from borj_node.node import BedsideNode


def test_button_press_generates_valid_contract_message():
    published = []

    node = BedsideNode(
        ward="W1",
        bed="B06",
        receipt_timeout_s=0.5,
        mock_gpio=True,
        audio_enabled=False,
    )
    # Intercept publish_call
    node.mqtt.is_connected = True
    node.mqtt.publish_call = lambda payload: published.append(payload) or True

    # Press assist
    node.buttons.trigger_assist()
    assert len(published) == 1
    call_msg = published[0]

    # Validate against contract schema!
    bc.validate_message("borj/W1/B06/call", call_msg)
    assert call_msg["kind"] == "assist"
    assert call_msg["pressCount"] == 1
    assert call_msg["bed"] == "B06"
    assert call_msg["ward"] == "W1"

    # Repeat press increments count and keeps callId
    node.current_state = "sent"
    node.buttons.trigger_assist()
    assert len(published) == 2
    repeat_msg = published[1]
    bc.validate_message("borj/W1/B06/call", repeat_msg)
    assert repeat_msg["callId"] == call_msg["callId"]
    assert repeat_msg["pressCount"] == 2

    # 3rd press triggers emergency (pressCount >= 3)
    node.buttons.trigger_assist()
    assert len(published) == 3
    emerg_msg = published[2]
    bc.validate_message("borj/W1/B06/call", emerg_msg)
    assert emerg_msg["callId"] == call_msg["callId"]
    assert emerg_msg["pressCount"] == 3
    assert node.leds._current_pattern == "emergency"

    # Nurse arrival at bedside: pressing comfort/presence button acknowledges active call
    ack_published = []
    node.mqtt.publish_ack = lambda cid, staff_id="N1": ack_published.append((cid, staff_id)) or True
    node.buttons.trigger_comfort()
    assert len(ack_published) == 1
    assert ack_published[0] == (call_msg["callId"], "N1")
    assert node.leds._current_pattern == "acknowledged"

    node.stop()


def test_call_state_transitions():
    node = BedsideNode(
        ward="W1",
        bed="B06",
        receipt_timeout_s=0.2,
        mock_gpio=True,
        audio_enabled=False,
    )
    node.mqtt.is_connected = True
    node.mqtt.publish_call = lambda p: True

    # 1. Button press
    node.buttons.trigger_assist()
    call_id = node.active_call_id
    assert call_id is not None

    # 2. Server answers with "sent"
    sent_state = {
        "schemaVersion": 1,
        "eventId": "01K7ZQ8V3E4M5N6P7Q8R9S0T1A",
        "ts": "2026-10-10T22:12:41Z",
        "tsSource": "server",
        "ward": "W1",
        "bed": "B06",
        "source": "server",
        "sourceType": "server",
        "callId": call_id,
        "kind": "assist",
        "state": "sent",
        "escalationLevel": 0,
    }
    bc.validate_message("borj/W1/B06/call/state", sent_state)
    node._on_call_state(sent_state)
    assert node.current_state == "sent"

    # 3. Staff acknowledges
    ack_state = dict(sent_state)
    ack_state["state"] = "acknowledged"
    ack_state["acknowledgedBy"] = "N1"
    bc.validate_message("borj/W1/B06/call/state", ack_state)
    node._on_call_state(ack_state)
    assert node.current_state == "acknowledged"

    # 4. Staff resolves
    res_state = dict(sent_state)
    res_state["state"] = "resolved"
    bc.validate_message("borj/W1/B06/call/state", res_state)
    node._on_call_state(res_state)
    assert node.current_state == "idle"
    assert node.active_call_id is None

    node.stop()


def test_timeout_triggers_not_sent():
    node = BedsideNode(
        ward="W1",
        bed="B06",
        receipt_timeout_s=0.1,  # fast timeout
        mock_gpio=True,
        audio_enabled=False,
    )
    node.mqtt.is_connected = True
    node.mqtt.publish_call = lambda p: True

    node.buttons.trigger_assist()
    assert node.current_state != "not_sent"

    node.stop()


def test_rotary_encoder_mock():
    from borj_node.encoder import RotaryEncoderController

    changed_vals = []
    encoder = RotaryEncoderController(
        pin_clk=23,
        pin_dt=24,
        max_steps=20,
        initial_percent=50,
        mock=True,
        on_change=lambda val: changed_vals.append(val),
    )
    assert encoder.current_percent == 50
    encoder.set_volume(80)
    assert encoder.current_percent == 80
    encoder.close()

