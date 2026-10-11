"""Family Care Link, ward side (whitepaper 7; safety invariants 2, 3, 4; ADR 0010).

Consent first: nothing is drafted, approved or published for an admission without an active,
recorded consent for that kind of update, and revocation takes effect at once. Discharge or
transfer revokes the whole link automatically.

Privacy filter: when a nurse approves an update, the server builds the outgoing payload from
allow-listed fields only, validates it against contracts/schemas/family-update.schema.json (it fails
closed), and refuses free text that mentions clinical data (config/family.yaml plus the patient's
own drug names). The exact payload is stored in the event's `outbound` field; the family publisher
forwards only that, outbound, to family-gateway. Nothing in the ward accepts connections from it.

Invites: QR + one-time code. The code is shown once to the nurse; only a salted scrypt hash leaves
the ward. All of this is stored as internal `family` events (encrypted log, never MQTT).
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import borj_contracts as bc
import yaml

from .ids import new_ulid
from .ingest import Ingestor
from .timeutil import format_ts
from .twin.state import Consent, FamilyUpdate

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "family.yaml"
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
LEAVE_REASONS = {"discharge": "discharge", "transfer_out": "transfer"}


class FamilyError(Exception):
    def __init__(self, status: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status, self.error, self.detail = status, error, detail


@dataclass(frozen=True)
class FamilyConfig:
    valid_days: int
    public_url: str
    code_digits: int
    blocked_terms: tuple[str, ...]
    blocked_patterns: tuple[re.Pattern[str], ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> FamilyConfig:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            valid_days=int(d["invites"]["valid_days"]),
            public_url=os.environ.get("BORJ_FAMILY_PUBLIC_URL", d["invites"]["public_url"]).rstrip("/"),
            code_digits=int(d["invites"]["code_digits"]),
            blocked_terms=tuple(t.lower() for t in d["privacy_filter"]["blocked_terms"]),
            blocked_patterns=tuple(re.compile(p) for p in d["privacy_filter"]["blocked_patterns"]),
        )


def hash_code(code: str, salt: bytes | None = None) -> str:
    """'scrypt$N$r$p$<salt b64>$<hash b64>' - the only form of the one-time code that leaves the ward."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(code.encode(), salt=salt, **SCRYPT, dklen=32)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${b64(salt)}${b64(digest)}"


def verify_code(code: str, encoded: str) -> bool:
    """Reference check for family-gateway (A): same format, constant-time compare."""
    _, n, r, p, salt_b64, digest_b64 = encoded.split("$")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    salt, expected = base64.urlsafe_b64decode(pad(salt_b64)), base64.urlsafe_b64decode(pad(digest_b64))
    actual = hashlib.scrypt(code.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    return secrets.compare_digest(actual, expected)


def consent_view(c: Consent) -> dict[str, Any]:
    view = {"consentId": c.consent_id, "admissionId": c.admission_id, "relativeLabel": c.relative_label,
            "allowedKinds": list(c.allowed_kinds), "givenBy": c.given_by, "recordedAt": format_ts(c.recorded_at),
            "recordedBy": c.recorded_by, "active": c.active}
    if c.revoked_at:
        view["revokedAt"] = format_ts(c.revoked_at)
    return view


def update_view(u: FamilyUpdate) -> dict[str, Any]:
    view = {"updateId": u.update_id, "admissionId": u.admission_id, "kind": u.kind, "status": u.status,
            "createdAt": format_ts(u.created_at)}
    if u.text:
        view["text"] = u.text
    if u.decided_at:
        view["decidedAt"] = format_ts(u.decided_at)
    return view


class FamilyService:
    def __init__(self, ingestor: Ingestor, cfg: FamilyConfig) -> None:
        self.ingestor = ingestor
        self.cfg = cfg
        self._lock = threading.RLock()

    # --- privacy filter ---------------------------------------------------------------------

    def clinical_terms_in(self, text: str, admission_id: str) -> list[str]:
        """Words or numbers in nurse-written text that look like clinical data (refused, invariant 2)."""
        with self.ingestor.lock:
            drugs = {w.lower() for rx in self.ingestor.twin.prescriptions.values() if rx.admission_id == admission_id
                     for w in re.findall(r"[A-Za-zÀ-ÿ]{3,}", rx.drug)}
        lowered = text.lower()
        hits = [t for t in (*self.cfg.blocked_terms, *sorted(drugs))
                if re.search(rf"(?<![\wÀ-ÿ]){re.escape(t)}(?![\wÀ-ÿ])", lowered)]
        hits += [m.group(0) for p in self.cfg.blocked_patterns for m in p.finditer(text)]
        return hits

    def _check_text(self, text: str | None, admission_id: str) -> None:
        if text:
            hits = self.clinical_terms_in(text, admission_id)
            if hits:
                raise FamilyError(422, "clinical_data_in_text",
                                  "families never receive vital signs, scores, drug names or doses; "
                                  f"remove: {', '.join(dict.fromkeys(hits))}")

    # --- helpers ------------------------------------------------------------------------------

    def _bed_of(self, admission_id: str) -> str:
        with self.ingestor.lock:
            bed = next((b.bed for b in self.ingestor.twin.beds.values()
                        if b.admission and b.admission.admission_id == admission_id), None)
        if bed is None:
            raise FamilyError(409, "conflict", f"admission {admission_id} is not in a bed")
        return bed

    def _emit(self, bed: str, admission_id: str, event_type: str, source_type: str = "staff_app",
              **fields: Any) -> None:
        ward = self.ingestor.layout.ward
        payload = {"schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(self.ingestor.event_now()),
                   "ward": ward, "bed": bed, "source": "borj-server" if source_type == "server" else "staff-app",
                   "sourceType": source_type, "admissionId": admission_id, "type": event_type,
                   **{k: v for k, v in fields.items() if v is not None}}
        result = self.ingestor.handle(bc.topic("family-event", ward, bed=bed), payload)
        if result.status != "accepted":
            raise FamilyError(500, "not_recorded", f"{result.status}: {result.detail}")

    def _outbound(self, target: str, schema: str, payload: dict[str, Any]) -> dict[str, Any]:
        bc.validate(schema, payload)  # the allow-list: anything not in the schema is refused (fails closed)
        return {"target": target, "payload": payload}

    def _revocation(self, link_id: str, reason: str, invite_id: str | None = None) -> dict[str, Any]:
        payload = {"schemaVersion": 1, "revocationId": new_ulid(), "linkId": link_id, "reason": reason,
                   "effectiveAt": format_ts(self.ingestor.event_now())}
        if invite_id:
            payload["inviteId"] = invite_id
        return self._outbound("revocations", "family-revocation", payload)

    # --- consent ------------------------------------------------------------------------------

    def record_consent(self, admission_id: str, relative_label: str, allowed_kinds: list[str], given_by: str,
                       staff_id: str) -> dict[str, Any]:
        with self._lock:
            bed = self._bed_of(admission_id)
            with self.ingestor.lock:
                link_id = self.ingestor.twin.family_links.get(admission_id) or f"FL-{new_ulid()[-12:]}"
            consent_id = f"CS-{new_ulid()[-12:]}"
            self._emit(bed, admission_id, "consent_granted", consentId=consent_id, linkId=link_id,
                       relativeLabel=relative_label, allowedKinds=list(dict.fromkeys(allowed_kinds)),
                       givenBy=given_by, staffId=staff_id)
            return self.consent(consent_id)

    def consent(self, consent_id: str) -> dict[str, Any]:
        with self.ingestor.lock:
            c = self.ingestor.twin.consents.get(consent_id)
            if c is None:
                raise FamilyError(404, "not_found", f"consent {consent_id}")
            return consent_view(c)

    def consents(self, admission_id: str) -> list[dict[str, Any]]:
        with self.ingestor.lock:
            return [consent_view(c) for c in self.ingestor.twin.consents.values() if c.admission_id == admission_id]

    def revoke_consent(self, admission_id: str, consent_id: str, staff_id: str) -> dict[str, Any]:
        """Withdrawal takes effect at once: the twin stops publishing, and family-gateway is told."""
        with self._lock:
            with self.ingestor.lock:
                c = self.ingestor.twin.consents.get(consent_id)
                invite = next((i for i in self.ingestor.twin.invites.values()
                               if i.consent_id == consent_id and not i.revoked), None)
            if c is None or c.admission_id != admission_id:
                raise FamilyError(404, "not_found", f"consent {consent_id}")
            if not c.active:
                raise FamilyError(409, "conflict", "consent already revoked")
            outbound = self._revocation(c.link_id, "consent_withdrawn", invite.invite_id) if invite else None
            bed = self._bed_of(admission_id)
            self._emit(bed, admission_id, "consent_revoked", consentId=consent_id, linkId=c.link_id,
                       reason="consent_withdrawn", staffId=staff_id, outbound=outbound)
            return self.consent(consent_id)

    def on_event(self, schema: str, payload: dict[str, Any]) -> None:
        """Ingest listener: discharge or transfer revokes the whole family link (invariant 4)."""
        if schema != "binding" or payload["action"] not in LEAVE_REASONS:
            return
        with self.ingestor.lock:
            twin = self.ingestor.twin
            link_id = twin.family_links.get(payload["admissionId"])
            active = link_id and any(c.active for c in twin.consents.values() if c.link_id == link_id)
        if not active:
            return
        reason = LEAVE_REASONS[payload["action"]]
        self._emit(payload["bed"], payload["admissionId"], "link_revoked", source_type="server", linkId=link_id,
                   reason=reason, outbound=self._revocation(link_id, reason))

    # --- invites ------------------------------------------------------------------------------

    def create_invite(self, admission_id: str, consent_id: str, staff_id: str) -> dict[str, Any]:
        with self._lock:
            with self.ingestor.lock:
                twin = self.ingestor.twin
                c = twin.consents.get(consent_id)
                existing = any(i.consent_id == consent_id and not i.revoked for i in twin.invites.values())
            if c is None or c.admission_id != admission_id or not c.active:
                raise FamilyError(409, "no_consent", "an invite needs an active, recorded consent (invariant 4)")
            if existing:
                raise FamilyError(409, "conflict", "this relative already has an active invite")
            bed = self._bed_of(admission_id)
            code = f"{secrets.randbelow(10 ** self.cfg.code_digits):0{self.cfg.code_digits}d}"
            invite_id = new_ulid()
            expires = self.ingestor.event_now() + timedelta(days=self.cfg.valid_days)
            outbound = self._outbound("invites", "family-invite", {
                "schemaVersion": 1, "inviteId": invite_id, "linkId": c.link_id, "relativeLabel": c.relative_label,
                "allowedKinds": list(c.allowed_kinds), "consentRecordedAt": format_ts(c.recorded_at),
                "expiresAt": format_ts(expires), "codeHash": hash_code(code),
            })
            self._emit(bed, admission_id, "invite_created", consentId=consent_id, inviteId=invite_id,
                       linkId=c.link_id, staffId=staff_id, outbound=outbound)
            return {"inviteId": invite_id, "linkId": c.link_id, "qrUrl": f"{self.cfg.public_url}/r/{invite_id}",
                    "oneTimeCode": code, "expiresAt": format_ts(expires)}

    # --- updates ------------------------------------------------------------------------------

    def _consented_kind(self, admission_id: str, kind: str) -> str:
        with self.ingestor.lock:
            twin = self.ingestor.twin
            link_id = twin.family_links.get(admission_id)
            ok = any(c.active and kind in c.allowed_kinds for c in twin.consents.values()
                     if c.admission_id == admission_id)
        if not ok or link_id is None:
            raise FamilyError(409, "no_consent", f"no active consent covers '{kind}' updates (invariant 4)")
        return link_id

    def draft_update(self, admission_id: str, kind: str, text: str | None, staff_id: str) -> dict[str, Any]:
        with self._lock:
            if kind == "nurse_note" and not text:
                raise FamilyError(422, "invalid", "a nurse note needs text")
            self._consented_kind(admission_id, kind)
            self._check_text(text, admission_id)
            bed = self._bed_of(admission_id)
            update_id = new_ulid()
            self._emit(bed, admission_id, "update_drafted", updateId=update_id, kind=kind, text=text,
                       staffId=staff_id)
            return self.update(update_id)

    def update(self, update_id: str) -> dict[str, Any]:
        with self.ingestor.lock:
            u = self.ingestor.twin.family_updates.get(update_id)
            if u is None:
                raise FamilyError(404, "not_found", f"update {update_id}")
            return update_view(u)

    def updates(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.ingestor.lock:
            items = sorted(self.ingestor.twin.family_updates.values(), key=lambda u: u.created_at, reverse=True)
            return [update_view(u) for u in items if status is None or u.status == status]

    def decide_update(self, update_id: str, decision: str, staff_id: str, reason: str | None) -> dict[str, Any]:
        with self._lock:
            with self.ingestor.lock:
                u = self.ingestor.twin.family_updates.get(update_id)
            if u is None:
                raise FamilyError(404, "not_found", f"update {update_id}")
            if u.status != "pending_approval":
                raise FamilyError(409, "conflict", f"update is already {u.status}")
            bed = self._bed_of(u.admission_id)
            if decision == "reject":
                self._emit(bed, u.admission_id, "update_rejected", updateId=update_id, staffId=staff_id, note=reason)
                return self.update(update_id)
            link_id = self._consented_kind(u.admission_id, u.kind)  # consent may have been withdrawn since
            self._check_text(u.text, u.admission_id)
            now = format_ts(self.ingestor.event_now())
            payload: dict[str, Any] = {"schemaVersion": 1, "updateId": update_id, "linkId": link_id, "kind": u.kind,
                                       "publishedAt": now, "approval": {"approved": True, "approvedAt": now}}
            if u.text:
                payload["text"] = u.text
            self._emit(bed, u.admission_id, "update_approved", updateId=update_id, linkId=link_id, staffId=staff_id,
                       outbound=self._outbound("updates", "family-update", payload))
            return self.update(update_id)
