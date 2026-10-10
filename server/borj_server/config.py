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
    db_path: str = str(REPO_ROOT / "data" / "borj.sqlite")
    # "sim": use borj/{ward}/sim/clock as "now" when the simulator publishes it; "wall": real UTC.
    clock_mode: str = "sim"
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            ward=os.environ.get("BORJ_WARD", cls.ward),
            seed_path=Path(os.environ.get("BORJ_SEED_PATH", str(cls.seed_path))),
            db_path=os.environ.get("BORJ_DB_PATH", cls.db_path),
            clock_mode=os.environ.get("BORJ_CLOCK_MODE", cls.clock_mode),
            mqtt_enabled=_env_bool("BORJ_MQTT_ENABLED", cls.mqtt_enabled),
            mqtt_host=os.environ.get("MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(os.environ.get("MQTT_PORT", str(cls.mqtt_port))),
        )
