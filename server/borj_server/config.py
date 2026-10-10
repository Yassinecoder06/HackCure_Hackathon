"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ward: str = "W1"
    seed_path: Path = REPO_ROOT / "seed" / "ward-W1.yaml"
    # PostgreSQL in compose (postgresql+psycopg://...); SQLite for local dev and tests (ADR 0009).
    db_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'borj.sqlite').as_posix()}"
    # "sim": use borj/{ward}/sim/clock as "now" when the simulator publishes it; "wall": real UTC.
    clock_mode: str = "sim"
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    # Inference layer (ADR 0009). None = no inference service: NEWS2 shows as unavailable.
    inference_url: str | None = "http://localhost:8001"
    # Short: NEWS2 is on the triage path (latency budget < 1 s end to end).
    inference_timeout_s: float = 0.5
    # Login (ADR 0010). Base64 signing key and "STAFFID:PIN,..." demo PINs, both from infra/.env.
    token_key_b64: str | None = None
    staff_pins: str = ""
    token_ttl_s: int = 4 * 3600
    # Live stream: how often to send latency metrics, and to re-push all beds so readings age into "stale".
    stream_metrics_interval_s: float = 5.0
    stream_refresh_interval_s: float = 30.0
    calls_config_path: Path = REPO_ROOT / "server" / "config" / "calls.yaml"
    meds_config_path: Path = REPO_ROOT / "server" / "config" / "meds.yaml"
    family_config_path: Path = REPO_ROOT / "server" / "config" / "family.yaml"
    observations_config_path: Path = REPO_ROOT / "server" / "config" / "observations.yaml"
    escalation_tick_s: float = 1.0
    # Frame integrity (invariant 13). Key ring "keyId:<base64>,..." from infra/.env, and the mode:
    # off | verify (check signatures that are present) | require (also reject unsigned measurements).
    device_keys: str = ""
    integrity_mode: str = "verify"
    # Language of explanations when a request does not ask (?lang= or Accept-Language): en | fr.
    default_lang: str = "en"
    # Suggest a new assignment automatically when staff presence or admissions change.
    auto_suggest: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            ward=os.environ.get("BORJ_WARD", cls.ward),
            seed_path=Path(os.environ.get("BORJ_SEED_PATH", str(cls.seed_path))),
            db_url=os.environ.get("BORJ_DB_URL", cls.db_url),
            clock_mode=os.environ.get("BORJ_CLOCK_MODE", cls.clock_mode),
            mqtt_enabled=_env_bool("BORJ_MQTT_ENABLED", cls.mqtt_enabled),
            mqtt_host=os.environ.get("MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(os.environ.get("MQTT_PORT", str(cls.mqtt_port))),
            inference_url=os.environ.get("INFERENCE_URL", cls.inference_url) or None,
            inference_timeout_s=float(os.environ.get("INFERENCE_TIMEOUT_S", str(cls.inference_timeout_s))),
            token_key_b64=os.environ.get("BORJ_TOKEN_KEY") or None,
            staff_pins=os.environ.get("BORJ_STAFF_PINS", ""),
            token_ttl_s=int(os.environ.get("BORJ_TOKEN_TTL_S", str(cls.token_ttl_s))),
            calls_config_path=Path(os.environ.get("BORJ_CALLS_CONFIG", str(cls.calls_config_path))),
            default_lang=os.environ.get("BORJ_LANG", cls.default_lang),
            device_keys=os.environ.get("BORJ_DEVICE_KEYS", ""),
            integrity_mode=os.environ.get("BORJ_INTEGRITY_MODE", cls.integrity_mode),
        )
