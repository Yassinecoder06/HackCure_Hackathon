"""Family Care Link on the real compose stack (safety invariants 2, 3 and 4), end to end:

    docker compose up -d --wait family-proxy family-publisher
    python tests/integration/family_smoke.py

A nurse records consent and creates an invite, drafts and approves a note; the outbound publisher pushes it to
family-gateway; a relative redeems the QR link + code over TLS 1.3 and reads it; a clinical note is refused;
withdrawing consent cuts the relative off. Then the isolation facts: the gateway cannot resolve or reach the ward's
services, the ward-only ingest port is not published, and /ingest is not served on the public face.
"""

from __future__ import annotations

import json
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CA = str(ROOT / "infra" / "certs" / "ca.crt")
API = "http://localhost:8000"
FAMILY = "https://localhost:8443"


def env() -> dict[str, str]:
    lines = (ROOT / ".env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


def call(method: str, url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | list | None]:
    request = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
    context = ssl.create_default_context(cafile=CA) if url.startswith("https") else None
    try:
        with urllib.request.urlopen(request, timeout=10, context=context) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, None


def expect(condition: bool, what: str) -> None:
    print(("ok   " if condition else "FAIL ") + what)
    if not condition:
        sys.exit(f"family smoke test failed: {what}")


def wait_for(fn, what: str, timeout_s: float = 60):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(1)
    sys.exit(f"timed out waiting for {what}")


def compose_exec(service: str, code: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", "exec", "-T", service, "python", "-c", code],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)


def main() -> None:
    pins = dict(pair.split(":", 1) for pair in env()["BORJ_STAFF_PINS"].split(","))
    status, login = call("POST", f"{API}/api/v1/auth/login", {"staffId": "N1", "secret": pins["N1"]})
    expect(status == 200, "a nurse logs in on the ward")
    nurse = login["token"]

    _, snapshot = call("GET", f"{API}/api/v1/wards/W1/snapshot", token=nurse)
    admission = next(b["admission"]["admissionId"] for b in snapshot["beds"] if b["admission"])
    base = f"{API}/api/v1/wards/W1/admissions/{admission}/family"

    status, _ = call("POST", f"{base}/invites", {"consentId": "CS-NONE"}, nurse)
    expect(status == 409, "no invite without a recorded consent")
    status, consent = call("POST", f"{base}/consents", {"relativeLabel": "Daughter", "givenBy": "patient",
                                                        "allowedKinds": ["nurse_note", "visiting_info"]}, nurse)
    expect(status == 201, "the nurse records the patient's consent")
    status, invite = call("POST", f"{base}/invites", {"consentId": consent["consentId"]}, nurse)
    expect(status == 201 and invite["qrUrl"].endswith(f"/r/{invite['inviteId']}"), "an invite with a QR link and code")

    status, refused = call("POST", f"{base}/updates", {"kind": "nurse_note", "text": "Her SpO2 is 93% today."}, nurse)
    expect(status == 422 and refused["error"] == "clinical_data_in_text", "a note with vital signs is refused")
    note = "A quiet evening; she ate most of her dinner."
    _, draft = call("POST", f"{base}/updates", {"kind": "nurse_note", "text": note}, nurse)
    status, _ = call("POST", f"{API}/api/v1/wards/W1/family/updates/{draft['updateId']}/decision",
                     {"decision": "approve"}, nurse)
    expect(status == 200, "the nurse approves the note")

    def redeemed():
        code, body = call("POST", f"{FAMILY}/family/v1/redeem",
                          {"inviteId": invite["inviteId"], "code": invite["oneTimeCode"]})
        return body if code == 200 else None

    session = wait_for(redeemed, "the invite to reach family-gateway (outbound publisher)")
    expect(True, "the relative redeems QR link + code over TLS 1.3")
    token = session["sessionToken"]

    def feed_with_note():
        code, body = call("GET", f"{FAMILY}/family/v1/feed", token=token)
        return body if code == 200 and any(u.get("text") == note for u in body["updates"]) else None

    feed = wait_for(feed_with_note, "the approved note to reach the relative")
    expect(set(feed) == {"notice", "wardContact", "allowedKinds", "updates"}, "the feed has only the contract's fields")
    expect(all(set(u) <= {"kind", "text", "publishedAt"} for u in feed["updates"]),
           "an update has only kind, text and time")
    expect("SpO2" not in json.dumps(feed), "no vital signs reach the relative")
    again = {"inviteId": invite["inviteId"], "code": invite["oneTimeCode"]}
    expect(call("POST", f"{FAMILY}/family/v1/redeem", again)[0] == 401, "the one-time code works once")

    expect(call("GET", f"{FAMILY}/ingest/v1/views?linkId=x")[0] == 404, "/ingest is not served on the public face")
    try:
        socket.create_connection(("localhost", 4443), timeout=3).close()
        published = True
    except OSError:
        published = False
    expect(not published, "the ward-only ingest port is not published")

    call("POST", f"{base}/consents/{consent['consentId']}/revoke", None, nurse)
    expect(wait_for(lambda: call("GET", f"{FAMILY}/family/v1/feed", token=token)[0] == 401, "revocation", 30),
           "withdrawing consent cuts the relative off")

    probe = "\n".join([
        "import socket",
        "for host in ['mosquitto', 'server', 'postgres', 'inference', 'nginx']:",
        "    try:",
        "        socket.gethostbyname(host)",
        "        print(host, 'RESOLVES')",
        "    except OSError:",
        "        print(host, 'unreachable')",
    ])
    result = compose_exec("family-gateway", probe)
    lines = [line for line in result.stdout.splitlines() if line.endswith(("RESOLVES", "unreachable"))]
    expect(len(lines) == 5 and all(line.endswith("unreachable") for line in lines),
           "family-gateway cannot even resolve mosquitto, server, postgres, inference or nginx")
    print("OK: Family Care Link works end to end and family-gateway is isolated from the ward")


if __name__ == "__main__":
    main()
