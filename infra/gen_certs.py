"""Create a local certificate authority and the server certificate for the demo (TLS 1.3, safety invariant 10).

    python infra/gen_certs.py                      # creates infra/certs/ if missing
    python infra/gen_certs.py --san 192.168.1.20   # also valid for this host name or IP (the demo laptop's address)
    python infra/gen_certs.py --force              # new CA and certificate: clients must trust the new ca.crt
(--san re-issues the server certificate under the existing CA, so nothing has to be re-trusted.)

One certificate serves the MQTT broker (8883) and the HTTPS front door (443). It is valid for localhost, the
compose service names, the usual hotspot gateway address (10.42.0.1) and any --san you add, so the Raspberry Pi nodes
and phones on the backup access point can verify it. Clients trust `infra/certs/ca.crt`:
- Python clients: MQTT_CA_CERT=infra/certs/ca.crt (the compose services get it mounted).
- Browsers: import ca.crt once as a trusted root, or accept the warning for the demo. (The hosted demo URL uses a
  public certificate from Caddy, see docs/deployment.md.)

infra/certs/ is git-ignored: the private keys never leave this machine (safety invariant 7).
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERTS = Path(__file__).resolve().parent / "certs"
DEFAULT_NAMES = ["localhost", "mosquitto", "nginx", "borj.local"]
DEFAULT_IPS = ["127.0.0.1", "::1", "10.42.0.1"]  # 10.42.0.1: NetworkManager hotspot default (the Pi guide uses it)


def local_addresses() -> list[str]:
    """This machine's own addresses, so the broker certificate also matches the LAN IP the nodes use."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            found.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in found if "%" not in a)


def subject_alt_names(extra: list[str]) -> list[x509.GeneralName]:
    names = list(DEFAULT_NAMES)
    ips = list(DEFAULT_IPS) + local_addresses()
    for item in extra:
        try:
            ipaddress.ip_address(item)
            ips.append(item)
        except ValueError:
            names.append(item)
    sans: list[x509.GeneralName] = [x509.DNSName(n) for n in dict.fromkeys(names)]
    sans += [x509.IPAddress(ipaddress.ip_address(i)) for i in dict.fromkeys(ips)]
    return sans


def write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(0o644)  # the broker container's own user must be able to read the bind-mounted key


def make(extra: list[str], new_ca: bool) -> None:
    CERTS.mkdir(exist_ok=True)
    now = datetime.now(UTC) - timedelta(minutes=5)

    if (CERTS / "ca.key").exists() and (CERTS / "ca.crt").exists() and not new_ca:
        # Re-issue the server certificate under the CA clients already trust (e.g. to add the laptop's address).
        ca_key = serialization.load_pem_private_key((CERTS / "ca.key").read_bytes(), None)
        ca_name = x509.load_pem_x509_certificate((CERTS / "ca.crt").read_bytes()).subject
        ca = None
    else:
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                                "Borj-PiCare demo CA (synthetic, not for production)")])
        ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now)
              .not_valid_after(now + timedelta(days=825))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                           content_commitment=False, key_encipherment=False, data_encipherment=False,
                                           key_agreement=False, encipher_only=False, decipher_only=False),
                             critical=True)
              .sign(ca_key, hashes.SHA256()))

    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "borj-server")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(subject_alt_names(extra)), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))

    if ca is not None:
        (CERTS / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        write_key(CERTS / "ca.key", ca_key)  # kept so --san can re-issue under the same CA; never mounted anywhere
    (CERTS / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    write_key(CERTS / "server.key", key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--san", action="append", default=[], help="extra host name or IP the certificate must match")
    parser.add_argument("--force", action="store_true", help="replace the CA and certificate")
    args = parser.parse_args()
    if (CERTS / "server.crt").exists() and not args.force and not args.san:
        print(f"{CERTS}: already exists (use --force to replace, or --san HOST to add an address)")
        return
    make(args.san, new_ca=args.force or not (CERTS / "ca.key").exists())
    print(f"{CERTS}: wrote server.crt and server.key (EC P-256, valid 825 days); trust ca.crt")


if __name__ == "__main__":
    main()
