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
        )
