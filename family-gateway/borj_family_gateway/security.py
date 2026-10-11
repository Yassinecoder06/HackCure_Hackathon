"""Small security helpers: invite codes, a privacy filter, rate limits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import yaml


def verify_code(code: str, encoded: str) -> bool:
    """Check a one-time code against the ward's 'scrypt$N$r$p$<salt>$<hash>' string (server/borj_server/family.py).
    Constant-time; a malformed string simply fails."""
    try:
        _, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        salt, expected = base64.urlsafe_b64decode(pad(salt_b64)), base64.urlsafe_b64decode(pad(digest_b64))
        actual = hashlib.scrypt(code.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


class PrivacyFilter:
    """Second line of defence for invariant 2. The ward already refuses clinical text; this service does not
    trust that, and refuses it again with the same word list (server/config/family.yaml, copied into the image)."""

    def __init__(self, terms: list[str], patterns: list[str]) -> None:
        self.terms = [t.lower() for t in terms]
        self.patterns = [re.compile(p) for p in patterns]

    @classmethod
    def load(cls, path: Path) -> PrivacyFilter:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))["privacy_filter"]
        return cls(cfg["blocked_terms"], cfg["blocked_patterns"])

    def hits(self, text: str) -> list[str]:
        lowered = text.lower()
        found = [t for t in self.terms if re.search(rf"(?<![\wÀ-ÿ]){re.escape(t)}(?![\wÀ-ÿ])", lowered)]
        return found + [m.group(0) for p in self.patterns for m in p.finditer(text)]


class RateLimiter:
    """At most `limit` events per `window_s` per key (a client address), in memory."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit, self.window_s = limit, window_s
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] > self.window_s:
            events.popleft()
        return events

    def blocked(self, key: str) -> bool:
        """True if the key is already at its limit (does not count an event)."""
        with self._lock:
            return len(self._trim(key, time.monotonic())) >= self.limit

    def hit(self, key: str) -> None:
        """Count one event."""
        with self._lock:
            now = time.monotonic()
            self._trim(key, now).append(now)

    def allow(self, key: str) -> bool:
        """Count one event; False if the key is over its limit."""
        with self._lock:
            now = time.monotonic()
            events = self._trim(key, now)
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True

    def retry_after(self, key: str) -> int:
        with self._lock:
            events = self._trim(key, time.monotonic())
            return max(1, int(self.window_s - (time.monotonic() - events[0]))) if events else 1
