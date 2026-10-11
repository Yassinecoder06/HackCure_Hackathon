"""MQTT client setup shared by every component: TLS 1.3, broker credentials and HMAC signing keys.

All of it comes from environment variables, so the same code runs against the plain local-dev broker
(nothing set) and the demo broker (TLS 1.3 on 8883, one account per component, ACLs):

    MQTT_CA_CERT      path to the CA certificate that signed the broker's certificate. Setting it turns TLS on.
    MQTT_USERNAME     broker account (server, sim, gw, node-B04 ...). infra/gen_secrets.py creates them.
    MQTT_PASSWORD
    BORJ_DEVICE_KEYS  HMAC key ring "keyId:<base64>,..." (see borj_contracts.parse_keys)
    BORJ_SIGNING_KEY_ID  which entry of the ring this component signs with (default given by the caller)

TLS 1.3 is the minimum, not a preference (HackCure spec, safety invariant 10): a broker that only speaks older
TLS is refused.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import Mapping
from typing import Any


def configure(client: Any, env: Mapping[str, str] | None = None) -> bool:
    """Apply credentials and TLS 1.3 from the environment to a paho client. Returns True if TLS is on."""
    env = os.environ if env is None else env
    username = env.get("MQTT_USERNAME")
    if username:
        client.username_pw_set(username, env.get("MQTT_PASSWORD", ""))
    ca = env.get("MQTT_CA_CERT")
    if not ca:
        return False
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # verifies the certificate and the host name
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(cafile=ca)
    client.tls_set_context(context)
    return True


def signing_key(default_key_id: str, env: Mapping[str, str] | None = None) -> tuple[bytes | None, str]:
    """(key, key id) this component signs with, or (None, id) when no key ring is configured (local dev)."""
    from . import parse_keys

    env = os.environ if env is None else env
    key_id = env.get("BORJ_SIGNING_KEY_ID") or default_key_id
    ring = parse_keys(env.get("BORJ_DEVICE_KEYS", ""))
    return ring.get(key_id), key_id
