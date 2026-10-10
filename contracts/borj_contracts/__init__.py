"""Schema loading, topic routing and validation for the Borj contracts.

Shared by the simulator, gateway, server and tests so that everyone validates
against exactly the same files in contracts/schemas/.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .ulid import generate_ulid as generate_ulid

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
BASE_URI = "https://borj.local/schemas/"

# "staff" and "sim" are reserved words in the bed position of a topic.
RESERVED_BED_IDS = {"staff", "sim"}

_ID = r"[A-Za-z0-9_-]{1,40}"
_TOPIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"^borj/(?P<ward>{_ID})/sim/clock$"), "clock"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/assignment$"), "assignment"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/staff/(?P<staffId>{_ID})/ack$"), "ack"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/staff/(?P<staffId>{_ID})/presence$"), "staff-presence"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/vitals$"), "vitals"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/device/status$"), "device-status"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/call$"), "call"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/call/state$"), "call-state"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/med$"), "med"),
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/binding$"), "binding"),
    # Internal only: stored in the event log, never published on MQTT (contains drug names).
    (re.compile(rf"^borj/(?P<ward>{_ID})/(?P<bed>{_ID})/prescription$"), "prescription"),
]

# Subscribe pattern covering every contract topic.
SUBSCRIBE_ALL = "borj/#"


class ContractError(ValueError):
    """A message does not match the contract (unknown topic, schema error, id mismatch)."""


@dataclass(frozen=True)
class Route:
    schema: str
    ids: dict[str, str]


def schema_names() -> list[str]:
    return sorted(p.name.removesuffix(".schema.json") for p in SCHEMA_DIR.glob("*.schema.json"))


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for path in SCHEMA_DIR.glob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    return Registry().with_resources(resources)


@cache
def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


@cache
def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name), registry=_registry())


def validate(name: str, payload: dict[str, Any]) -> None:
    """Raise ContractError listing every schema violation."""
    errors = sorted(validator(name).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        msgs = "; ".join(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors)
        raise ContractError(f"{name}: {msgs}")


def route(topic: str) -> Route:
    """Map an MQTT topic to its schema name and the ids embedded in the topic."""
    for pattern, schema in _TOPIC_PATTERNS:
        m = pattern.match(topic)
        if m:
            ids = m.groupdict()
            if ids.get("bed") in RESERVED_BED_IDS:
                continue
            return Route(schema=schema, ids=ids)
    raise ContractError(f"unknown topic: {topic}")


def validate_message(topic: str, payload: dict[str, Any]) -> Route:
    """Validate payload against the topic's schema and check topic ids match payload ids."""
    r = route(topic)
    validate(r.schema, payload)
    for key, value in r.ids.items():
        if payload.get(key) != value:
            raise ContractError(f"{topic}: payload {key}={payload.get(key)!r} does not match topic")
    return r


def topic(kind: str, ward: str, bed: str | None = None, staff_id: str | None = None) -> str:
    """Build a contract topic. kind is a schema name."""
    if kind == "clock":
        return f"borj/{ward}/sim/clock"
    if kind == "assignment":
        return f"borj/{ward}/assignment"
    if kind in ("ack", "staff-presence"):
        if not staff_id:
            raise ContractError(f"{kind} needs a staff id")
        return f"borj/{ward}/staff/{staff_id}/{'ack' if kind == 'ack' else 'presence'}"
    suffix = {
        "vitals": "vitals",
        "device-status": "device/status",
        "call": "call",
        "call-state": "call/state",
        "med": "med",
        "binding": "binding",
        "prescription": "prescription",
    }[kind]
    if not bed or bed in RESERVED_BED_IDS:
        raise ContractError(f"invalid bed for {kind}: {bed!r}")
    return f"borj/{ward}/{bed}/{suffix}"


# --- Frame integrity (safety invariant 13): HMAC-SHA256 over canonical JSON -------------------


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """The bytes that get signed: the message without `integrity`, keys sorted, compact, UTF-8."""
    body = {k: v for k, v in payload.items() if k != "integrity"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign(payload: dict[str, Any], key: bytes, key_id: str) -> dict[str, Any]:
    """Return a copy of payload with an `integrity` field added."""
    digest = hmac.new(key, canonical_bytes(payload), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return {**payload, "integrity": {"alg": "HMAC-SHA256", "keyId": key_id, "sig": sig}}


def verify(payload: dict[str, Any], keys: dict[str, bytes]) -> bool:
    """True if `integrity` is present, its keyId is known, and the signature matches."""
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("alg") != "HMAC-SHA256":
        return False
    key = keys.get(integrity.get("keyId", ""))
    if key is None:
        return False
    expected = sign(payload, key, integrity["keyId"])["integrity"]["sig"]
    return hmac.compare_digest(expected, str(integrity.get("sig", "")))
