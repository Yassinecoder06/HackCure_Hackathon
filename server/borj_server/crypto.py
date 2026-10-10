"""AES-256-GCM encryption of patient payloads at rest (ADR 0010, safety invariant 10).

Every event payload and audit detail is encrypted before it reaches the database, so the
database files, volumes and backups only ever contain ciphertext. Each record stores the id of
the key that encrypted it (rotation) and a random 96-bit nonce. The row's own id is bound in as
associated data, so a ciphertext copied onto another row fails to decrypt.
"""

from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32  # AES-256


class DataKeyError(ValueError):
    """Missing or malformed data key."""


@dataclass(frozen=True)
class Sealed:
    key_id: str
    nonce: bytes
    ciphertext: bytes


class DataCipher:
    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        for key_id, key in keys.items():
            if len(key) != KEY_BYTES:
                raise DataKeyError(f"data key {key_id!r} must be {KEY_BYTES} bytes")
        if active_key_id not in keys:
            raise DataKeyError(f"active key {active_key_id!r} not provided")
        self._aead = {key_id: AESGCM(key) for key_id, key in keys.items()}
        self.active_key_id = active_key_id

    @classmethod
    def from_env(cls) -> DataCipher:
        """BORJ_DATA_KEY (base64 of 32 random bytes) and BORJ_DATA_KEY_ID, e.g. from infra/.env."""
        raw = os.environ.get("BORJ_DATA_KEY")
        if not raw:
            raise DataKeyError("BORJ_DATA_KEY is not set; run `python infra/gen_secrets.py` (see infra/README.md)")
        key_id = os.environ.get("BORJ_DATA_KEY_ID", "k1")
        return cls({key_id: base64.b64decode(raw)}, key_id)

    def seal(self, plaintext: bytes, associated: bytes) -> Sealed:
        nonce = secrets.token_bytes(12)
        ct = self._aead[self.active_key_id].encrypt(nonce, plaintext, associated)
        return Sealed(self.active_key_id, nonce, ct)

    def open(self, sealed: Sealed, associated: bytes) -> bytes:
        return self._aead[sealed.key_id].decrypt(sealed.nonce, sealed.ciphertext, associated)


def generate_key_b64() -> str:
    return base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")
