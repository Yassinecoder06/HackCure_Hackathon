"""Unit and invariant tests for the Ward Gateway."""

from __future__ import annotations

import tempfile
from pathlib import Path

import borj_contracts as bc
import pytest
from borj_gateway import (
    FrameCrcError,
    GatewayOutbox,
    QualityChecker,
    WardGateway,
    format_device_frame,
    parse_device_frame,
)


def test_frame_crc_verification():
    # 1. Valid frame
    valid_line = format_device_frame(1, "MON-B04", {"pulse": 78, "spo2": 97})
    reading = parse_device_frame(valid_line)
    assert reading.device_id == "MON-B04"
    assert reading.params == {"pulse": 78, "spo2": 97}

    # 2. Corrupted frame
    corrupted_line = valid_line.replace("78", "99")
    with pytest.raises(FrameCrcError):
        parse_device_frame(corrupted_line)

    # 3. Invalid CRC format
    bad_crc_line = valid_line[:-5] + "ZZZZ\n"
    with pytest.raises(FrameCrcError):
        parse_device_frame(bad_crc_line)


def test_quality_and_plausibility_checks():
    checker = QualityChecker()

    # Normal reading
    res_normal = checker.check({"pulse": 72, "spo2": 98, "resp_rate": 16})
    assert res_normal.valid is True
    assert res_normal.flags == []

    # Sensor-off (pulse: 0)
    res_off = checker.check({"pulse": 0, "spo2": 98})
    assert res_off.valid is False
    assert "sensor_off" in res_off.flags

    # Implausible (pulse: 290, resp_rate: 90)
    res_implausible = checker.check({"pulse": 290, "resp_rate": 90})
    assert res_implausible.valid is False
    assert "implausible" in res_implausible.flags


def test_outbox_encrypted_at_rest():
    """Invariant 10: patient payload encrypted with AES-256-GCM before reaching SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "gw_outbox.db"
        key = b"G" * 32
        outbox = GatewayOutbox(db_path=db_path, key=key)

        payload = {
            "schemaVersion": 1,
            "eventId": "01K7ZQ8V3E4M5N6P7Q8R9S0T1Y",
            "ts": "2026-10-10T22:12:40Z",
            "tsSource": "gateway",
            "ward": "W1",
            "bed": "B06",
            "source": "gateway-ward",
            "sourceType": "device",
            "deviceId": "MON-B06",
            "params": {"spo2": 94, "pulse": 115},
            "quality": {"valid": True, "stale_after_s": 900},
        }
        outbox.enqueue("borj/W1/B06/vitals", payload)
        assert outbox.pending_count() == 1

        # Check raw database file content: must NOT contain plaintext vitals!
        raw_db_bytes = db_path.read_bytes()
        assert b"MON-B06" not in raw_db_bytes
        assert b"115" not in raw_db_bytes
        assert b"spo2" not in raw_db_bytes

        # Decrypt through outbox
        pending = outbox.get_pending()
        assert len(pending) == 1
        topic, dec_payload = pending[0]
        assert topic == "borj/W1/B06/vitals"
        assert dec_payload["params"] == {"spo2": 94, "pulse": 115}

        outbox.close()


def test_gateway_process_reading_with_hmac():
    """Invariant 13: outgoing vitals signed with HMAC-SHA256."""
    hmac_key = b"test-secret-key-32-bytes-long!!!"
    gateway = WardGateway(
        ward="W1",
        signing_key=hmac_key,
        signing_key_id="GW-TEST",
    )

    # Bind device MON-B06 to B06
    gateway.bindings.apply_binding_event({
        "bed": "B06",
        "action": "attach_device",
        "deviceId": "MON-B06",
    })

    # Process reading while offline (buffers to outbox)
    vitals = gateway.process_reading(
        device_id="MON-B06",
        params={"spo2": 96, "pulse": 82},
    )

    assert vitals is not None
    assert vitals["bed"] == "B06"
    assert vitals["deviceId"] == "MON-B06"

    # Contract validation
    bc.validate_message("borj/W1/B06/vitals", vitals)

    # Verify HMAC signature
    assert bc.verify(vitals, {"GW-TEST": hmac_key})
