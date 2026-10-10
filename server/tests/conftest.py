from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import borj_contracts as bc
import pytest
from borj_server.clock import Clock
from borj_server.config import REPO_ROOT
from borj_server.crypto import DataCipher
from borj_server.ingest import Ingestor
from borj_server.store import EventStore
from borj_server.twin.layout import WardLayout

EXAMPLES = REPO_ROOT / "contracts" / "examples"
SEED = REPO_ROOT / "seed" / "ward-W1.yaml"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulids():
    for n in itertools.count(1):
        suffix = ""
        for _ in range(6):
            suffix = _CROCKFORD[n % 32] + suffix
            n //= 32
        yield "01K80000000000000000" + suffix


_ids = _ulids()


# Synthetic test-only credentials: they exist only in this test code, never in a real deployment.
TEST_TOKEN_KEY_B64 = "dGVzdC1vbmx5LXRva2VuLWtleS1ub3QtYS1zZWNyZXQtISE="  # 32+ bytes once decoded
TEST_PINS = {"CN1": "111111", "N1": "222222", "DR1": "333333"}


def make_client(tmp_path, with_inference: bool = False, **overrides):
    """Ward server TestClient. with_inference=True plugs in the real inference app in-process."""
    from borj_inference.main import create_app as create_inference_app
    from borj_server.config import Settings
    from borj_server.main import create_app
    from fastapi.testclient import TestClient

    settings = Settings(
        seed_path=SEED, db_url=f"sqlite:///{(tmp_path / 'borj.sqlite').as_posix()}", mqtt_enabled=False,
        inference_url=None, token_key_b64=TEST_TOKEN_KEY_B64,
        staff_pins=",".join(f"{k}:{v}" for k, v in TEST_PINS.items()),
        **overrides,
    )
    inference_http = TestClient(create_inference_app()) if with_inference else None
    return TestClient(create_app(settings, inference_http=inference_http, cipher=make_test_cipher()))


def login(client, staff_id: str = "CN1") -> dict:
    """Log in and make the client send the token on every following request."""
    resp = client.post("/api/v1/auth/login", json={"staffId": staff_id, "secret": TEST_PINS[staff_id]})
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['token']}"
    return resp.json()


def make_test_cipher() -> DataCipher:
    """A fixed, obviously synthetic key for tests only."""
    return DataCipher({"test": b"T" * 32}, "test")


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def layout() -> WardLayout:
    return WardLayout.load(SEED)


@pytest.fixture
def ingestor(layout: WardLayout) -> Ingestor:
    return Ingestor(layout, EventStore("sqlite://", make_test_cipher()), Clock("sim"))


@pytest.fixture
def make_event() -> Callable[..., tuple[str, dict[str, Any]]]:
    """Build (topic, payload) from a contract example with a fresh eventId and overrides."""

    def _make(name: str, **overrides: Any) -> tuple[str, dict[str, Any]]:
        payload = copy.deepcopy(example(name))
        payload["eventId"] = next(_ids)
        payload.update(overrides)
        schema = name.split(".")[0]
        if schema in ("ack", "staff-presence"):
            topic = bc.topic(schema, payload["ward"], staff_id=payload["staffId"])
        elif schema == "assignment":
            topic = bc.topic(schema, payload["ward"])
        else:
            topic = bc.topic(schema, payload["ward"], bed=payload["bed"])
        return topic, payload

    return _make


@pytest.fixture
def clock_at(ingestor: Ingestor) -> Callable[[str], None]:
    def _set(sim_ts: str) -> None:
        ingestor.handle(
            "borj/W1/sim/clock",
            {"schemaVersion": 1, "ward": "W1", "simTs": sim_ts, "speed": 10, "scenario": "test", "running": True},
        )

    return _set


def openapi_validator(component: str):
    """jsonschema validator for a component schema of contracts/openapi.yaml."""
    import yaml
    from jsonschema import Draft202012Validator

    doc = yaml.safe_load(Path(REPO_ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": f"#/components/schemas/{component}", "components": doc["components"]})
