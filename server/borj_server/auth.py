"""Staff login and bearer tokens (ADR 0010: non-repudiation of access, invariant 11).

- Demo PINs for the synthetic staff come from BORJ_STAFF_PINS (generated into the git-ignored
  .env). They are hashed with argon2id at startup and the plain values are not kept.
- A successful login returns a short-lived HS256 token naming the staff member and role.
  Every request for patient data must carry one, so every access has a named actor in the audit log.
- Repeated failures lock the staff id out for a while (brute-force protection on short PINs).
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request

from .timeutil import utcnow

_ALG = "HS256"


class AuthError(Exception):
    pass


class TooManyAttempts(AuthError):
    pass


@dataclass(frozen=True)
class Principal:
    staff_id: str
    role: str


def parse_pins(raw: str) -> dict[str, str]:
    """'CN1:123456,N1:654321' -> {'CN1': '123456', 'N1': '654321'}"""
    pins = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        staff_id, _, pin = pair.partition(":")
        if staff_id and pin:
            pins[staff_id] = pin
    return pins


class Auth:
    def __init__(
        self,
        pins: dict[str, str],
        roles: dict[str, str],
        token_key: bytes,
        ttl_s: int,
        max_failures: int = 5,
        lockout_s: int = 300,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        if len(token_key) < 32:
            raise AuthError("token key must be at least 32 bytes")
        self._hasher = PasswordHasher()
        self._hashes = {sid: self._hasher.hash(pin) for sid, pin in pins.items() if sid in roles}
        self._roles = roles
        self._key = token_key
        self._ttl = timedelta(seconds=ttl_s)
        self._max_failures = max_failures
        self._lockout = timedelta(seconds=lockout_s)
        self._now = now
        self._failures: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def login(self, staff_id: str, secret: str) -> tuple[str, datetime]:
        now = self._now()
        with self._lock:
            window = self._failures[staff_id]
            while window and now - window[0] > self._lockout:
                window.popleft()
            if len(window) >= self._max_failures:
                raise TooManyAttempts(staff_id)
            stored = self._hashes.get(staff_id)
            try:
                if stored is None:
                    raise VerificationError("unknown staff id")
                self._hasher.verify(stored, secret)
            except VerificationError as exc:
                window.append(now)
                raise AuthError("invalid credentials") from exc
            window.clear()
        expires = now + self._ttl
        claims = {"sub": staff_id, "role": self._roles[staff_id], "iat": now, "exp": expires,
                  "jti": str(uuid.uuid4())}
        return jwt.encode(claims, self._key, algorithm=_ALG), expires

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._key, algorithms=[_ALG], options={"require": ["sub", "role", "exp"]})
        except jwt.PyJWTError as exc:
            raise AuthError("invalid or expired token") from exc
        if claims["sub"] not in self._roles:
            raise AuthError("unknown staff id")
        return Principal(claims["sub"], claims["role"])


def require_staff(request: Request) -> Principal:
    """FastAPI dependency: a valid bearer token, or 401."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, {"error": "unauthorized", "detail": "missing bearer token"})
    try:
        return request.app.state.auth.verify(token)
    except AuthError as exc:
        raise HTTPException(401, {"error": "unauthorized", "detail": str(exc)}) from exc


def require_role(principal: Principal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(403, {"error": "forbidden", "detail": f"requires role: {', '.join(roles)}"})

