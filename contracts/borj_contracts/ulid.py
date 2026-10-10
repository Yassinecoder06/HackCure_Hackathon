"""ULID (Universally Unique Lexicographically Sortable Identifier) generator.

Generates 26-character Crockford Base32 strings matching `^[0-9A-HJKMNP-TV-Z]{26}$`.
Supports deterministic generation when provided with a random.Random instance.
"""

from __future__ import annotations

import os
import random
import time

CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid(
    t_ms: int | None = None,
    rng: random.Random | None = None,
) -> str:
    """Generate a 26-character Crockford Base32 ULID.

    48 bits timestamp (milliseconds) + 80 bits randomness.
    """
    if t_ms is None:
        t_ms = int(time.time() * 1000)

    # 48 bits timestamp
    t_ms &= 0xFFFFFFFFFFFF

    # 80 bits entropy
    if rng is not None:
        entropy = rng.getrandbits(80)
    else:
        entropy = int.from_bytes(os.urandom(10), "big")

    val = (t_ms << 80) | entropy
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD_BASE32[val & 0x1F])
        val >>= 5
    return "".join(reversed(chars))
