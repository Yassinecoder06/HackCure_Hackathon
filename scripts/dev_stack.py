"""Run the whole ward stack natively, without Docker: broker (TLS 1.3), inference, server and simulator.

    python scripts/dev_stack.py                       # everything, scenario night-shift-peak at speed 10
    python scripts/dev_stack.py --no-simulator        # broker + inference + server only
    python scripts/dev_stack.py --scenario deterioration --speed 30 --require-signatures

Prerequisites (once): `pip install -r requirements-dev.txt -r server/requirements.txt -r inference/requirements.txt
-r simulator/requirements.txt`, Mosquitto installed, `python infra/gen_secrets.py` and `python infra/gen_certs.py`.
It is the fallback when Docker is not available; the compose stack stays the reference setup. Uses SQLite in data/.
Ctrl-C stops everything.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    lines = (ROOT / "infra" / ".env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


def wait_http(url: str, what: str, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            print(f"  {what}: up")
            return
        except OSError:
            time.sleep(0.5)
    sys.exit(f"{what} did not start within {timeout_s:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-simulator", action="store_true")
    parser.add_argument("--api-port", default="8000", help="server port (default 8000)")
    parser.add_argument("--scenario", default="night-shift-peak")
    parser.add_argument("--speed", default="10")
    parser.add_argument("--require-signatures", action="store_true", help="reject unsigned measurements (demo mode)")
    parser.add_argument("--db", default=str(ROOT / "data" / "borj.sqlite"), help="SQLite file (fresh file = reset)")
    args = parser.parse_args()

    secrets = load_env()
    py = sys.executable
    paths = os.pathsep.join(str(ROOT / d) for d in ("contracts", "server", "inference", "simulator"))
    base = {**os.environ, "PYTHONPATH": paths}
    ca = str(ROOT / "infra" / "certs" / "ca.crt")
    mqtt = {"MQTT_HOST": "localhost", "MQTT_PORT": "8883", "MQTT_CA_CERT": ca}
    server_env = {
        **base, **mqtt, "MQTT_USERNAME": "server", "MQTT_PASSWORD": secrets["MQTT_PW_SERVER"],
        "BORJ_DB_URL": f"sqlite:///{Path(args.db).as_posix()}", "BORJ_CLOCK_MODE": "sim",
        "INFERENCE_URL": "http://localhost:8001", "BORJ_DEMO_ENDPOINTS": "1",
        "BORJ_INTEGRITY_MODE": "require" if args.require_signatures else "verify",
        **{k: secrets[k] for k in ("BORJ_DATA_KEY", "BORJ_DATA_KEY_ID", "BORJ_TOKEN_KEY", "BORJ_STAFF_PINS",
                                    "BORJ_DEVICE_KEYS")},
    }
    sim_env = {**base, **mqtt, "MQTT_USERNAME": "sim", "MQTT_PASSWORD": secrets["MQTT_PW_SIM"],
               "BORJ_DEVICE_KEYS": secrets["BORJ_DEVICE_KEYS"]}
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)

    procs: list[subprocess.Popen] = []

    def start(name: str, cmd: list[str], env: dict[str, str]) -> None:
        print(f"starting {name}")
        procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env))

    def stop(*_: object) -> None:
        for proc in reversed(procs):
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    start("broker", [py, "scripts/dev_broker.py"], base)
    time.sleep(2)
    start("inference", [py, "-m", "uvicorn", "borj_inference.main:app", "--port", "8001"], base)
    wait_http("http://localhost:8001/health", "inference")
    start("server", [py, "-m", "uvicorn", "borj_server.main:app", "--port", args.api_port], server_env)
    wait_http(f"http://localhost:{args.api_port}/health", "server")
    if not args.no_simulator:
        start("simulator", [py, "-m", "borj_sim", "--scenario", f"simulator/scenarios/{args.scenario}.yaml",
                            "--speed", args.speed], sim_env)
    print(f"stack is up: API http://localhost:{args.api_port} (docs at /docs). Ctrl-C to stop.")
    while True:
        for proc in procs:
            if proc.poll() is not None:
                print(f"a process exited with code {proc.returncode}; stopping")
                stop()
        time.sleep(1)


if __name__ == "__main__":
    main()
