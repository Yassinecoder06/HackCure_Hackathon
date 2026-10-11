"""Transport security (safety invariants 10 and 13): broker ACLs, TLS 1.3 client setup, generated certificates."""

from __future__ import annotations

import base64
import importlib.util
import socket
import ssl
import threading
from pathlib import Path

import borj_contracts as bc
from borj_contracts import mqtt as bc_mqtt

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "infra" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def acl_rules() -> dict[str, list[tuple[str, str]]]:
    """{user: [(access, topic filter)]} from infra/mosquitto/acl.conf."""
    rules: dict[str, list[tuple[str, str]]] = {}
    user = None
    for line in (ROOT / "infra" / "mosquitto" / "acl.conf").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("user "):
            user = line.split(maxsplit=1)[1]
            rules[user] = []
        elif line.startswith("topic "):
            _, access, topic = line.split()
            rules[user].append((access, topic))
    return rules


def can_write(rules: list[tuple[str, str]], topic: str) -> bool:
    def match(filter_: str) -> bool:
        parts, want = filter_.split("/"), topic.split("/")
        for i, part in enumerate(parts):
            if part == "#":
                return True
            if i >= len(want) or (part != "+" and part != want[i]):
                return False
        return len(parts) == len(want)
    return any(access in ("write", "readwrite") and match(topic_filter) for access, topic_filter in rules)


def seed_beds() -> list[str]:
    return load_script("gen_secrets").bed_ids()


def test_every_bed_has_a_node_account_limited_to_its_own_bed():
    rules = acl_rules()
    beds = seed_beds()
    assert len(beds) >= 10
    for bed in beds:
        node = rules[f"node-{bed}"]
        assert can_write(node, f"borj/W1/{bed}/call")
        for other in beds:
            if other != bed:
                assert not can_write(node, f"borj/W1/{other}/call"), (bed, other)
        for forbidden in ("call/state", "prescription", "family", "order", "binding", "med"):
            assert not can_write(node, f"borj/W1/{bed}/{forbidden}")


def test_only_the_server_publishes_call_state_and_nobody_publishes_internal_topics():
    rules = acl_rules()
    for user, user_rules in rules.items():
        assert can_write(user_rules, "borj/W1/B04/call/state") == (user == "server"), user
        for internal in ("prescription", "family", "order"):
            assert not can_write(user_rules, f"borj/W1/B04/{internal}"), (user, internal)
        assert not can_write(user_rules, "borj/W1/assignment")


def test_every_acl_account_gets_a_password_from_gen_secrets():
    accounts = load_script("gen_secrets").mqtt_accounts()
    assert set(acl_rules()) == set(accounts)
    assert len(set(accounts.values())) == len(accounts)
    assert all(":" not in pw and "," not in pw for pw in accounts.values())  # the list format must stay parseable


class FakeClient:
    def __init__(self) -> None:
        self.credentials = None
        self.context = None

    def username_pw_set(self, user, password):
        self.credentials = (user, password)

    def tls_set_context(self, context):
        self.context = context


def test_configure_is_a_no_op_for_local_dev_and_strict_when_configured(tmp_path):
    plain = FakeClient()
    assert bc_mqtt.configure(plain, {}) is False and plain.credentials is None and plain.context is None

    certs = tmp_path
    gen = load_script("gen_certs")
    gen.CERTS = certs
    gen.make([], new_ca=True)
    client = FakeClient()
    assert bc_mqtt.configure(client, {"MQTT_USERNAME": "node-B04", "MQTT_PASSWORD": "pw",
                                      "MQTT_CA_CERT": str(certs / "ca.crt")}) is True
    assert client.credentials == ("node-B04", "pw")
    assert client.context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert client.context.verify_mode == ssl.CERT_REQUIRED and client.context.check_hostname


def test_generated_certificate_gives_a_verified_tls_13_handshake_and_refuses_tls_12(tmp_path):
    gen = load_script("gen_certs")
    gen.CERTS = tmp_path
    gen.make(["demo.example.org"], new_ca=True)

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ctx.load_cert_chain(tmp_path / "server.crt", tmp_path / "server.key")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    port = listener.getsockname()[1]
    versions: list[str | None] = []

    def serve() -> None:
        for _ in range(2):
            conn, _ = listener.accept()
            try:
                with server_ctx.wrap_socket(conn, server_side=True) as tls:
                    tls.recv(1)
                    versions.append(tls.version())
                    tls.sendall(b"y")  # the client waits for this, so it never closes mid-handshake
            except (ssl.SSLError, OSError):
                versions.append(None)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    def handshake(max_version: ssl.TLSVersion | None, hostname: str) -> str | None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cafile=str(tmp_path / "ca.crt"))
        if max_version:
            ctx.maximum_version = max_version
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw, \
                    ctx.wrap_socket(raw, server_hostname=hostname) as tls:
                tls.sendall(b"x")
                tls.recv(1)
                return tls.version()
        except (ssl.SSLError, OSError):
            return None

    assert handshake(None, "localhost") == "TLSv1.3"            # the CA signed it and localhost is a SAN
    assert handshake(ssl.TLSVersion.TLSv1_2, "localhost") is None  # TLS 1.2 only: refused
    thread.join(timeout=5)
    listener.close()
    assert versions == ["TLSv1.3", None], versions


def test_signing_key_comes_from_the_ring_by_key_id():
    b64 = lambda raw: base64.b64encode(raw).decode()  # noqa: E731
    ring = {"BORJ_DEVICE_KEYS": f"sim-k1:{b64(b'S' * 32)},node-B04:{b64(b'4' * 32)}"}
    key, key_id = bc_mqtt.signing_key("node-B04", ring)
    assert key_id == "node-B04" and key == bc.parse_keys(ring["BORJ_DEVICE_KEYS"])["node-B04"]
    assert bc_mqtt.signing_key("sim-k1", {}) == (None, "sim-k1")  # local dev: no ring, no signing
    assert bc_mqtt.signing_key("sim-k1", {**ring, "BORJ_SIGNING_KEY_ID": "node-B04"})[1] == "node-B04"


def test_env_example_holds_no_real_secrets():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        if "=" in line and key != "BORJ_DATA_KEY_ID" and any(
                word in key for word in ("PW", "PASSWORD", "KEY", "USERS", "TOKEN", "PINS")):
            assert line.split("=", 1)[1].split("#")[0].strip() in ("", "change-me-local-dev-only"), line
