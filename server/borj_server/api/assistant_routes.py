"""The ward assistant (ADR 0013): questions about the ward's current state, answered from selected facts. Staff only;
every question and answer is written to the audit log. Advisory: it never changes anything."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import Principal, require_staff
from ..explain import pick_lang

router = APIRouter(prefix="/api/v1/wards/{ward}/assistant")
Staff = Annotated[Principal, Depends(require_staff)]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    bed: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,16}$")
    lang: str | None = Field(default=None, pattern="^(en|fr)$")


def _check_ward(request: Request, ward: str) -> None:
    if ward != request.app.state.ingestor.layout.ward:
        raise HTTPException(404, {"error": "unknown_ward", "detail": ward})


@router.post("/ask")
def ask(ward: str, body: AskIn, request: Request, who: Staff) -> dict:
    _check_ward(request, ward)
    lang = pick_lang(body.lang, request.headers.get("accept-language"), default=request.app.state.settings.default_lang)
    return request.app.state.assistant.ask(body.question, lang, who.staff_id, body.bed)


@router.get("/status")
def status(ward: str, request: Request, who: Staff) -> dict:
    """Is the local model reachable, and how often has the verifier rejected it (the hallucination rate we report)?"""
    _check_ward(request, ward)
    return request.app.state.assistant.status()
