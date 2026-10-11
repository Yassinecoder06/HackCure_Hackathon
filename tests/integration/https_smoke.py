"""HTTPS front door checks (safety invariant 10): TLS 1.3 only, plain HTTP only redirects, the API is behind it.

    docker compose up -d --wait nginx
    python tests/integration/https_smoke.py            # https://localhost, CA from infra/certs/ca.crt
"""

from __future__ import annotations

import http.client
import os
import socket
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST = os.environ.get("HTTPS_HOST", "localhost")
CA = str(ROOT / "infra" / "certs" / "ca.crt")


def context(max_version: ssl.TLSVersion | None = None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile=CA)
    if max_version is not None:
        ctx.maximum_version = max_version
    return ctx


def expect(condition: bool, what: str) -> None:
    print(("ok   " if condition else "FAIL ") + what)
    if not condition:
        sys.exit(f"HTTPS check failed: {what}")


def https_get(path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPSConnection(HOST, 443, context=context(), timeout=10)
    conn.request("GET", path)
    return conn.getresponse()


def main() -> None:
    with socket.create_connection((HOST, 443), timeout=10) as raw, \
            context().wrap_socket(raw, server_hostname=HOST) as tls:
        expect(tls.version() == "TLSv1.3", "the certificate verifies and the connection is TLS 1.3")
    try:
        with socket.create_connection((HOST, 443), timeout=10) as raw, \
                context(ssl.TLSVersion.TLSv1_2).wrap_socket(raw, server_hostname=HOST):
            refused = False
    except (ssl.SSLError, OSError):
        refused = True
    expect(refused, "a client limited to TLS 1.2 is refused")

    plain = http.client.HTTPConnection(HOST, 80, timeout=10)
    plain.request("GET", "/")
    response = plain.getresponse()
    expect(response.status == 301 and response.getheader("Location", "").startswith("https://"),
           "plain HTTP only redirects to HTTPS")

    health = https_get("/health")
    expect(health.status == 200, "the API health endpoint answers through the proxy")
    expect("max-age" in (health.getheader("Strict-Transport-Security") or ""), "HSTS is sent")
    expect(https_get("/api/v1/wards/W1/snapshot").status == 401, "patient data needs a login, even over HTTPS")
    page = https_get("/")
    expect(page.status == 200 and b"<html" in page.read().lower(), "the ward app is served")
    print("OK: HTTPS front door is TLS 1.3 only, redirects HTTP and protects the API")


if __name__ == "__main__":
    main()
