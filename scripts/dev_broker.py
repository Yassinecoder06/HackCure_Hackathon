"""Run the demo broker natively (no Docker): same mosquitto.conf, accounts, ACLs and certificates as the compose stack.

    python scripts/dev_broker.py          # TLS 1.3 on localhost:8883, runtime files in data/broker/

Needs Mosquitto installed (Windows: mosquitto.org/download, Linux: apt install mosquitto) and `infra/.env` and
`infra/certs/` from `python infra/gen_secrets.py` and `python infra/gen_certs.py`. It is the fallback when Docker is
not available; the compose stack stays the reference setup.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data" / "broker"


def find(tool: str) -> str:
    found = shutil.which(tool)
    if found:
        return found
    windows_dir = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "mosquitto"
    for base in (windows_dir, Path("/usr/sbin"), Path("/usr/bin")):
        for name in (tool, f"{tool}.exe"):
            if (base / name).exists():
                return str(base / name)
    sys.exit(f"{tool} not found: install Mosquitto (https://mosquitto.org/download/)")


def users() -> list[tuple[str, str]]:
    lines = (ROOT / "infra" / ".env").read_text(encoding="utf-8").splitlines()
    env = dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))
    return [tuple(pair.split(":", 1)) for pair in env["BORJ_MQTT_USERS"].split(",")]  # type: ignore[misc]


def main() -> None:
    certs = ROOT / "infra" / "certs"
    if not (certs / "server.crt").exists():
        sys.exit("no certificates: run `python infra/gen_certs.py` first")
    RUN.mkdir(parents=True, exist_ok=True)
    passwd = RUN / "passwd"
    passwd.write_text("", encoding="utf-8")
    for user, password in users():
        subprocess.run([find("mosquitto_passwd"), "-b", str(passwd), user, password], check=True)
    for name in ("ca.crt", "server.crt", "server.key"):
        shutil.copy(certs / name, RUN / name)
    shutil.copy(ROOT / "infra" / "mosquitto" / "acl.conf", RUN / "acl.conf")
    config = (ROOT / "infra" / "mosquitto" / "mosquitto.conf").read_text(encoding="utf-8")
    config = config.replace("/mosquitto/run", RUN.as_posix())
    # The loopback-only healthcheck listener moves aside: a Mosquitto Windows service often already owns 1883.
    config = config.replace("listener 1883 127.0.0.1", "listener 18830 127.0.0.1")
    (RUN / "mosquitto.conf").write_text(config, encoding="utf-8")
    print(f"broker: TLS 1.3 on 8883, accounts from infra/.env, runtime files in {RUN}")
    sys.exit(subprocess.call([find("mosquitto"), "-c", str(RUN / "mosquitto.conf")]))


if __name__ == "__main__":
    main()
