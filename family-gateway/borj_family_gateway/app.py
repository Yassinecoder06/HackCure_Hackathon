"""family-gateway: the DMZ half of the Family Care Link (contracts/family-gateway.openapi.yaml).

Two faces, one process:
- /ingest/v1/*  the ward pushes approved payloads here. The ward always initiates; this service has no way to reach
  the ward network (it sits on the dmz docker network only: safety invariant 3). Payloads must validate against the
  allow-list schemas (invariant 2), free text is checked once more, and updates need a live invite (invariant 4).
- /family/v1/*  relatives' phones. QR invite + one-time code, then a session token. Rate-limited and audited.

It holds no vitals, scores, drug names, doses, staff identities or locations, and has no way to obtain them.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import borj_contracts as bc
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .security import PrivacyFilter, RateLimiter, verify_code
from .store import Store, digest

DUMMY_HASH = "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
KINDS = ["visiting_info", "meal_served", "medication_round_completed", "nurse_note", "ward_contact"]
NOTICE = {
    "en": "This is not an emergency channel and it is not a medical report. In an emergency, call the ward on {phone}.",
    "fr": ("Ceci n'est pas un canal d'urgence ni un compte rendu médical. "
           "En cas d'urgence, appelez le service au {phone}."),
}


def wall_now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Settings:
    publisher_token: str
    data_key: bytes
    db_path: str = "/data/family.sqlite"
    # One word list for both ends: the ward's own file (the Docker image copies it to /app/config/privacy.yaml).
    privacy_config: Path = Path(__file__).resolve().parents[2] / "server" / "config" / "family.yaml"
    static_dir: Path | None = None
    trust_proxy: bool = False            # read the client address from X-Real-IP (set by our own nginx)
    ward_contact: str = "+216 70 000 000"  # synthetic
    session_hours: float = 12
    redeem_attempts: int = 5             # failed redeem attempts per client ...
    redeem_window_s: float = 600         # ... per this many seconds
    lock_invite_after: int = 10          # failed attempts on one invite, from anywhere, and it is revoked
    feed_per_minute: int = 120
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        static = env.get("FAMILY_STATIC_DIR")
        return cls(
            publisher_token=env["FAMILY_PUBLISHER_TOKEN"],
            data_key=base64.b64decode(env["FAMILY_DATA_KEY"]),
            db_path=env.get("FAMILY_DB_PATH", cls.db_path),
            privacy_config=Path(env.get("FAMILY_PRIVACY_CONFIG", str(cls.privacy_config))),
            static_dir=Path(static) if static else None,
            trust_proxy=env.get("FAMILY_TRUST_PROXY", "0") == "1",
            ward_contact=env.get("FAMILY_WARD_CONTACT", cls.ward_contact),
            session_hours=float(env.get("FAMILY_SESSION_HOURS", cls.session_hours)),
        )


class RedeemIn(BaseModel):
    inviteId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,40}$")
    code: str = Field(min_length=4, max_length=12)


def create_app(settings: Settings) -> FastAPI:
    store = Store(settings.db_path, settings.data_key)
    privacy = PrivacyFilter.load(settings.privacy_config)
    redeem_failures = RateLimiter(settings.redeem_attempts, settings.redeem_window_s)
    feed_limit = RateLimiter(settings.feed_per_minute, 60)
    app = FastAPI(title="Borj family-gateway", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)

    def ward_now() -> str:
        return store.ward_time() or iso(wall_now())

    def client_of(request: Request) -> str:
        if settings.trust_proxy and request.headers.get("x-real-ip"):
            return request.headers["x-real-ip"]
        return request.client.host if request.client else "unknown"

    def publisher(authorization: str | None = Header(default=None)) -> None:
        sent = authorization.removeprefix("Bearer ").strip() if authorization else ""
        if not hmac.compare_digest(sent.encode(), settings.publisher_token.encode()):
            raise HTTPException(401, "bad publisher token")

    def validated(schema: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            bc.validate(schema, payload)  # allow-list: additionalProperties false, so nothing else gets in
        except bc.ContractError as exc:
            raise HTTPException(422, f"not on the allow-list: {exc}") from exc
        return payload

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
        })
        if request.url.path.startswith(("/family/", "/ingest/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # --- ward -> gateway (outbound pushes from the ward) --------------------------------------

    @app.post("/ingest/v1/invites", status_code=202, dependencies=[Depends(publisher)])
    def ingest_invite(payload: dict[str, Any]) -> dict:
        invite = validated("family-invite", payload)
        store.advance_ward_time(invite["consentRecordedAt"])
        return {"stored": store.add_invite(invite)}

    @app.post("/ingest/v1/updates", status_code=202, dependencies=[Depends(publisher)])
    def ingest_update(payload: dict[str, Any]) -> dict:
        update = validated("family-update", payload)
        if "text" in update and (hits := privacy.hits(update["text"])):
            raise HTTPException(422, f"clinical data in text: {', '.join(dict.fromkeys(hits))}")
        store.advance_ward_time(update["publishedAt"])
        if not store.link_has_live_invite(update["linkId"], ward_now()):
            raise HTTPException(409, "no active invite for this link (consent first)")
        return {"stored": store.add_update(update)}

    @app.post("/ingest/v1/revocations", status_code=202, dependencies=[Depends(publisher)])
    def ingest_revocation(payload: dict[str, Any]) -> dict:
        rev = validated("family-revocation", payload)
        store.advance_ward_time(rev["effectiveAt"])
        return {"applied": store.revoke(rev["revocationId"], rev["linkId"], rev.get("inviteId"), rev["effectiveAt"])}

    @app.get("/ingest/v1/views", dependencies=[Depends(publisher)])
    def views(linkId: str) -> list:  # noqa: N803
        """Who looked, when: lets the ward answer 'has the family seen it?' without exposing anything else."""
        return store.views(linkId)

    # --- relatives ----------------------------------------------------------------------------

    @app.post("/family/v1/redeem")
    def redeem(body: RedeemIn, request: Request) -> dict:
        client = client_of(request)
        if redeem_failures.blocked(client):
            wait = str(redeem_failures.retry_after(client))
            raise HTTPException(429, "too many attempts", headers={"Retry-After": wait})
        now = ward_now()
        if body.inviteId:
            row = store.invite(body.inviteId)
            candidates = [row] if row is not None and row["status"] == "active" and row["expires_at"] > now else []
            if not candidates:  # same work as a real check, so a wrong id is not faster than a wrong code
                verify_code(body.code, DUMMY_HASH)
        else:
            candidates = store.usable_invites(now)
        match = next((row for row in candidates if verify_code(body.code, row["code_hash"])), None)
        if match is None:
            redeem_failures.hit(client)
            if body.inviteId:
                store.count_failure(body.inviteId, settings.lock_invite_after)
            raise HTTPException(401, "invalid or expired invite")
        token = secrets.token_urlsafe(32)
        session_end = wall_now() + timedelta(hours=settings.session_hours)
        store.redeem(match["invite_id"], token, iso(session_end), match["link_id"])
        store.log_view(iso(wall_now()), match["link_id"], digest(token), client, "redeem")
        return {"sessionToken": token, "expiresAt": iso(session_end)}

    @app.get("/family/v1/feed")
    def feed(request: Request, authorization: str | None = Header(default=None),
             accept_language: str | None = Header(default=None)) -> dict:
        token = authorization.removeprefix("Bearer ").strip() if authorization else ""
        client = client_of(request)
        if not feed_limit.allow(digest(token) if token else client):
            raise HTTPException(429, "too many requests", headers={"Retry-After": "30"})
        session = store.session(token, iso(wall_now())) if token else None
        if session is None or session["invite_status"] == "revoked" or session["invite_expires_at"] <= ward_now():
            raise HTTPException(401, "no session, revoked or expired")
        kinds = [k for k in KINDS if k in json.loads(session["allowed_kinds"])]
        store.log_view(iso(wall_now()), session["link_id"], session["token_hash"], client, "feed")
        lang = "fr" if (accept_language or "").lower().startswith("fr") else "en"
        return {"notice": NOTICE[lang].format(phone=settings.ward_contact), "wardContact": settings.ward_contact,
                "allowedKinds": kinds, "updates": store.updates_for(session["link_id"], kinds)}

    # --- the family app (static), same origin as the API --------------------------------------

    if settings.static_dir and settings.static_dir.is_dir():
        root = settings.static_dir.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("family/", "ingest/")):
                return JSONResponse({"detail": "not found"}, status_code=404)
            target = (root / path).resolve()
            if path and target.is_file() and root in target.parents:
                return FileResponse(target)
            return FileResponse(root / "index.html")  # /r/<inviteId> (the QR link) and every client-side route

    app.state.store = store
    app.state.settings = settings
    return app


def app_factory() -> FastAPI:  # pragma: no cover - uvicorn --factory entry point
    return create_app(Settings.from_env())
