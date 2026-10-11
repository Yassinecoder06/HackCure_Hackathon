"""Broker security checks against a running Borj broker (safety invariants 10 and 13, HackCure spec section 5).

    python tests/integration/broker_security_smoke.py            # broker on localhost:8883, secrets from .env

Proves, on the real broker: TLS 1.3 only, no anonymous access, no wrong password, and the topic rules in
infra/mosquitto/acl.conf (a bedside node can only call from its own bed; nobody but the server publishes call/state;
the internal topics are closed to everyone).
"""

from __future__ import annotations

import os
import ssl
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "contracts"))
HOST = os.environ.get("BROKER_HOST", "localhost")
PORT = int(os.environ.get("BROKER_PORT", "8883"))
CA = str(ROOT / "infra" / "certs" / "ca.crt")


def env() -> dict[str, str]:
    lines = (ROOT / ".env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


ACCOUNTS = dict(pair.split(":", 1) for pair in env()["BORJ_MQTT_USERS"].split(","))


def tls_context(max_version: ssl.TLSVersion | None = None) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=CA)
    if max_version is not None:
        context.maximum_version = max_version
    return context


def connect(user: str | None, password: str | None, tls: bool = True, context: ssl.SSLContext | None = None,
            wait_s: float = 4.0) -> tuple[mqtt.Client, bool]:
    """(client, accepted). accepted is False if the broker refused or never answered."""
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=f"sec-{user}-{time.time_ns()}")
    if user is not None:
        client.username_pw_set(user, password)
    if tls:
        client.tls_set_context(context or tls_context())
    result: dict[str, bool] = {}
    client.on_connect = lambda c, u, f, rc, p: result.setdefault("ok", not rc.is_failure)
    client.connect(HOST, PORT, keepalive=10)
    client.loop_start()
    deadline = time.monotonic() + wait_s
    while "ok" not in result and time.monotonic() < deadline:
        time.sleep(0.05)
    return client, result.get("ok", False)


def close(client: mqtt.Client) -> None:
    client.loop_stop()
    client.disconnect()


def expect(condition: bool, what: str) -> None:
    print(("ok   " if condition else "FAIL ") + what)
    if not condition:
        raise SystemExit(f"broker security check failed: {what}")


def main() -> None:
    sim_pw = ACCOUNTS["sim"]
    good, accepted = connect("sim", sim_pw)
    expect(accepted, "a component with its own account connects over TLS 1.3")
    close(good)

    client, accepted = connect("sim", "not-the-password")
    expect(not accepted, "a wrong password is refused")
    close(client)
    client, accepted = connect(None, None)
    expect(not accepted, "anonymous access is refused")
    close(client)
    client, accepted = connect("sim", sim_pw, tls=False)
    expect(not accepted, "plain MQTT on the TLS port is refused")
    close(client)
    try:
        client, accepted = connect("sim", sim_pw, context=tls_context(ssl.TLSVersion.TLSv1_2))
        close(client)
    except (ssl.SSLError, OSError):
        accepted = False
    expect(not accepted, "a client limited to TLS 1.2 is refused (TLS 1.3 only)")

    # Topic rules: what the server (which reads everything) actually receives from other accounts.
    seen: list[str] = []
    server, accepted = connect("server", ACCOUNTS["server"])
    expect(accepted, "the server account connects")
    server.on_message = lambda c, u, m: seen.append(m.topic)
    server.subscribe("borj/#", qos=1)
    time.sleep(0.5)

    def publish_as(user: str, topic: str) -> None:
        client, ok = connect(user, ACCOUNTS[user])
        expect(ok, f"{user} connects")
        client.publish(topic, b"{}", qos=1).wait_for_publish(3)
        close(client)

    probes = [
        ("node-B04", "borj/W1/B04/call", True),                 # its own bed
        ("node-B04", "borj/W1/B05/call", False),                # another bed
        ("node-B04", "borj/W1/B04/call/state", False),          # only the server decides call state
        ("node-B04", "borj/W1/B04/vitals", False),              # a call button is not a monitor
        ("sim", "borj/W1/B04/call/state", False),
        ("sim", "borj/W1/B04/prescription", False),             # internal topics: closed to everyone
        ("gw", "borj/W1/B04/family", False),
        ("gw", "borj/W1/B04/vitals", True),
        ("server", "borj/W1/B04/call/state", True),
        ("server", "borj/W1/B04/order", False),
    ]
    for user, topic, allowed in probes:
        seen.clear()
        publish_as(user, topic)
        time.sleep(0.4)
        expect((topic in seen) == allowed, f"{user} {'may' if allowed else 'may not'} publish {topic}")
    close(server)
    print("OK: broker is TLS 1.3 only, authenticated, and enforces the topic rules")


if __name__ == "__main__":
    main()
