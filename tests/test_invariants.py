"""One test per safety invariant (CLAUDE.md).

Tests that need components which do not exist yet are skipped with the phase and role
that will turn them on. Remove the skip when the component lands; never skip a test that
used to pass.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skip(reason="P3, B: no code path applies an assignment/prescription without a logged human decision")
def test_1_advisory_only():
    pass


@pytest.mark.skip(reason="P4, B: privacy filter output from a twin full of vitals/scores/drugs passes only allow-list")
def test_2_family_never_sees_forbidden_fields():
    pass


@pytest.mark.skip(reason="P4, A: family-gateway on dmz network cannot resolve or reach mosquitto/server")
def test_3_outbound_only():
    pass


@pytest.mark.skip(reason="P4, B: no invite/update without consent; revocation immediate; discharge expires invites")
def test_4_consent_first():
    pass


def test_5_missing_or_stale_is_labelled():
    """A stale reading that would score 3 is excluded, listed, and the score is labelled partial."""
    from borj_inference.news2 import News2Config, Reading, score

    readings = {
        "resp_rate": Reading(16, "fresh", 60, 900),
        "pulse": Reading(140, "stale", 1800, 900),  # would score 3 if it were (wrongly) used
        "temp_c": Reading(37.0, "invalid", 60, 900),
    }
    result = score(readings, News2Config.load())
    assert result["total"] == 0
    assert result["complete"] is False
    assert result["stale"] == ["pulse"]
    assert {"temp_c", "consciousness", "spo2", "on_oxygen", "sys_bp"} <= set(result["missing"])
    assert result["label"].startswith("Partial NEWS2")
    assert result["confidence"]["value"] < 1


def test_6_idempotency():
    """Replaying every contract example twice leaves the event log and the twin unchanged."""
    import json

    import borj_contracts as bc
    from borj_server.clock import Clock
    from borj_server.ingest import Ingestor
    from borj_server.store import EventStore
    from borj_server.timeutil import parse_ts
    from borj_server.twin.layout import WardLayout
    from borj_server.twin.views import snapshot_view

    ingestor = Ingestor(WardLayout.load(ROOT / "seed" / "ward-W1.yaml"), EventStore(":memory:"), Clock("wall"))
    messages = []
    for path in sorted((ROOT / "contracts" / "examples").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "eventId" not in payload:
            continue  # clock and family payloads are not ward events
        schema = path.name.split(".")[0]
        if schema in ("ack", "staff-presence"):
            topic = bc.topic(schema, payload["ward"], staff_id=payload["staffId"])
        else:
            topic = bc.topic(schema, payload["ward"], bed=payload["bed"])
        messages.append((topic, payload))

    for topic, payload in messages:
        ingestor.handle(topic, payload)
    now = parse_ts("2026-10-11T01:00:00Z")
    count, twin = ingestor.store.count(), snapshot_view(ingestor.twin, now, "wall")

    for topic, payload in messages:
        assert ingestor.handle(topic, payload).status == "duplicate"
    assert ingestor.store.count() == count
    assert snapshot_view(ingestor.twin, now, "wall") == twin


def test_7_no_env_files_committed():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    leaked = [f for f in tracked if Path(f).name.startswith(".env") and Path(f).name != ".env.example"]
    assert not leaked, f".env files must not be committed: {leaked}"


def test_8_clinical_parameters_are_config():
    """Every clinical config block names who must validate it, and the engine reads thresholds from it."""
    import yaml

    for path in sorted(ROOT.glob("*/config/*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        blocks = list(cfg.get("parameters", {}).values()) + [v for k, v in cfg.items() if k != "parameters"]
        missing = [b for b in blocks if isinstance(b, dict) and not b.get("validated_by")]
        assert not missing, f"{path}: blocks without validated_by"

    engine = (ROOT / "inference" / "borj_inference" / "news2.py").read_text(encoding="utf-8")
    for threshold in ("upto: 91", "<= 91", "< 92", ">= 131"):
        assert threshold not in engine, "NEWS2 thresholds must come from config, not code"


@pytest.mark.skip(reason="P1, A+B: TLS 1.3 broker/proxy; AES-256-GCM at rest (no plaintext vitals in the DB)")
def test_10_encrypted_in_transit_and_at_rest():
    pass


@pytest.mark.skip(reason="P1, B: every patient-data access audited; audit hash chain detects tampering")
def test_11_non_repudiation():
    pass


@pytest.mark.skip(reason="P1-P3, B: every score/alert/suggestion carries confidence + explanation")
def test_12_explainable_and_advisory():
    pass


@pytest.mark.skip(reason="P1, A+B: messages with a bad or missing HMAC are rejected in demo mode")
def test_13_frame_integrity():
    pass
