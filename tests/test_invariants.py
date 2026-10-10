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


@pytest.mark.skip(reason="P0, B: ingesting the same eventId twice leaves the twin unchanged")
def test_6_idempotency():
    pass


def test_7_no_env_files_committed():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    leaked = [f for f in tracked if Path(f).name.startswith(".env") and Path(f).name != ".env.example"]
    assert not leaked, f".env files must not be committed: {leaked}"


@pytest.mark.skip(reason="P1, B: every clinical threshold lives in server/config with a 'who validates' comment")
def test_8_clinical_parameters_are_config():
    pass


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
