"""Frame integrity gate (invariant 13): key ring parsing, MQTT wiring, key generation."""

from __future__ import annotations

import base64
import importlib.util
import json
from types import SimpleNamespace

import borj_contracts as bc
import pytest
from borj_server.config import REPO_ROOT
from borj_server.integrity import IntegrityGate
from borj_server.mqtt import MqttListener


def test_parse_keys():
    raw = f" sim-k1:{base64.b64encode(b'S' * 32).decode()}, node-B04:{base64.b64encode(b'4' * 32).decode()},,"
    assert bc.parse_keys(raw) == {"sim-k1": b"S" * 32, "node-B04": b"4" * 32}
    assert bc.parse_keys("") == {}


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        IntegrityGate({}, "lenient")


def test_mqtt_listener_checks_before_ingest(ingestor, make_event):
    gate = IntegrityGate({"sim-k1": b"S" * 32}, "require")
    listener = MqttListener(ingestor, "localhost", 1883, gate=gate)
    topic, payload = make_event("vitals.device")
    listener._on_message(None, None, SimpleNamespace(topic=topic, payload=json.dumps(payload).encode()))
    assert gate.stats["rejected"] == 1 and not list(ingestor.store.events())
    signed = bc.sign(payload, b"S" * 32, "sim-k1")
    listener._on_message(None, None, SimpleNamespace(topic=topic, payload=json.dumps(signed).encode()))
    assert gate.stats["verified"] == 1 and [e.payload["eventId"] for e in ingestor.store.events()] == [
        payload["eventId"]]


def test_gen_secrets_makes_one_key_per_signer():
    spec = importlib.util.spec_from_file_location("gen_secrets", REPO_ROOT / "infra" / "gen_secrets.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    keys = bc.parse_keys(gen.device_keys())
    assert {"sim-k1", "gw-k1", "node-B01", "node-B10"} <= set(keys)
    assert all(len(k) == 32 for k in keys.values()) and len(set(keys.values())) == len(keys)
