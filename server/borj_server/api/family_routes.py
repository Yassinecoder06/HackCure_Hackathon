"""Family Care Link endpoints, ward side (contracts/openapi.yaml, tag family). Nurses only; audited."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import Principal, require_role, require_staff
from ..family import FamilyError

router = APIRouter(prefix="/api/v1/wards/{ward}")
Staff = Annotated[Principal, Depends(require_staff)]
KINDS = "^(visiting_info|meal_served|medication_round_completed|nurse_note|ward_contact)$"


class ConsentIn(BaseModel):
    relativeLabel: str = Field(min_length=1, max_length=40)
    allowedKinds: list[Annotated[str, Field(pattern=KINDS)]] = Field(min_length=1)
    givenBy: str = Field(pattern="^(patient|legal_representative)$")


class InviteIn(BaseModel):
    consentId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")


class DraftIn(BaseModel):
    kind: str = Field(pattern=KINDS)
    text: str | None = Field(default=None, max_length=280)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str | None = Field(default=None, max_length=200)


def _call(request: Request, who: Principal, ward: str, action: str, target: str, fn, *args) -> Any:
    if ward != request.app.state.ingestor.layout.ward:
        raise HTTPException(404, {"error": "unknown_ward", "detail": ward})
    require_role(who, "nurse", "charge_nurse")
    try:
        result = fn(*args)
    except FamilyError as exc:
        raise HTTPException(exc.status, {"error": exc.error, "detail": exc.detail}) from exc
    request.app.state.ingestor.store.audit(who.staff_id, action, target)
    return result


@router.post("/admissions/{admissionId}/family/consents", status_code=201)
def record_consent(ward: str, admissionId: str, body: ConsentIn, request: Request, who: Staff) -> dict:  # noqa: N803
    """The nurse records the patient's (or legal representative's) consent for one relative."""
    family = request.app.state.family
    return _call(request, who, ward, "family.consent_recorded", admissionId, family.record_consent, admissionId,
                 body.relativeLabel, body.allowedKinds, body.givenBy, who.staff_id)


@router.get("/admissions/{admissionId}/family/consents")
def list_consents(ward: str, admissionId: str, request: Request, who: Staff) -> list:  # noqa: N803
    return _call(request, who, ward, "family.consents_read", admissionId, request.app.state.family.consents,
                 admissionId)


@router.post("/admissions/{admissionId}/family/consents/{consentId}/revoke")
def revoke_consent(ward: str, admissionId: str, consentId: str, request: Request, who: Staff) -> dict:  # noqa: N803
    """Takes effect immediately; family-gateway is told to stop serving the relative (invariant 4)."""
    return _call(request, who, ward, "family.consent_revoked", consentId, request.app.state.family.revoke_consent,
                 admissionId, consentId, who.staff_id)


@router.post("/admissions/{admissionId}/family/invites", status_code=201)
def create_invite(ward: str, admissionId: str, body: InviteIn, request: Request, who: Staff) -> dict:  # noqa: N803
    """The one-time code is in this response only; just its hash leaves the ward."""
    return _call(request, who, ward, "family.invite_created", body.consentId, request.app.state.family.create_invite,
                 admissionId, body.consentId, who.staff_id)


@router.post("/admissions/{admissionId}/family/updates", status_code=201)
def draft_update(ward: str, admissionId: str, body: DraftIn, request: Request, who: Staff) -> dict:  # noqa: N803
    return _call(request, who, ward, "family.update_drafted", admissionId, request.app.state.family.draft_update,
                 admissionId, body.kind, body.text, who.staff_id)


@router.get("/family/updates")
def list_updates(ward: str, request: Request, who: Staff, status: str | None = None) -> list:
    return _call(request, who, ward, "family.updates_read", ward, request.app.state.family.updates, status)


@router.post("/family/updates/{updateId}/decision")
def decide_update(ward: str, updateId: str, body: DecisionIn, request: Request, who: Staff) -> dict:  # noqa: N803
    """Approve runs the privacy filter and queues the allow-listed payload for outbound publishing."""
    action = {"approve": "family.update_approved", "reject": "family.update_rejected"}[body.decision]
    return _call(request, who, ward, action, updateId,
                 request.app.state.family.decide_update, updateId, body.decision, who.staff_id, body.reason)
