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


@pytest.mark.skip(reason="P1, B: stale/missing params excluded from NEWS2 and the score is labelled partial")
def test_5_missing_or_stale_is_labelled():
    pass


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


@pytest.mark.skip(reason="P1, B: every clinical threshold lives in server/config with a 'who validates' comment")
def test_8_clinical_parameters_are_config():
    pass
