"""Inference service: stateless decision engines behind an internal HTTP API (ADR 0009).

Reachable only on the ward network. The server sends inputs; this service returns results
with their rule trace and confidence. It never stores or changes anything.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import assignment, news2

ParamValue = int | float | bool | str


class ReadingIn(BaseModel):
    value: ParamValue
    status: Literal["fresh", "stale", "invalid"]
    ageS: int = Field(ge=0)
    staleAfterS: int = Field(ge=1)


class BedIn(BaseModel):
    bed: str
    spo2Scale: Literal[1, 2] = 1
    params: dict[str, ReadingIn]


class News2BatchIn(BaseModel):
    asOf: str
    beds: list[BedIn]


class NurseIn(BaseModel):
    staffId: str
    skills: list[str] = []


class BedNeedIn(BaseModel):
    bed: str
    room: str
    acuity: int = Field(ge=1, le=4)
    news2Total: int | None = Field(default=None, ge=0)
    news2Fresh: bool = False
    currentNurse: str | None = None
    locked: bool = False
    requiredSkills: list[str] = []


class AssignmentIn(BaseModel):
    nurses: list[NurseIn]
    beds: list[BedNeedIn]


def create_app(config_path: Path | None = None) -> FastAPI:
    path = config_path or Path(os.environ.get("INFERENCE_NEWS2_CONFIG", str(news2.DEFAULT_CONFIG)))
    cfg = news2.News2Config.load(path)
    assign_cfg = assignment.AssignmentConfig.load(
        Path(os.environ.get("INFERENCE_ASSIGNMENT_CONFIG", str(assignment.DEFAULT_CONFIG))))
    app = FastAPI(title="Borj inference", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/news2/batch")
    def news2_batch(body: News2BatchIn) -> dict[str, Any]:
        results = {}
        for bed in body.beds:
            readings = {
                p: news2.Reading(r.value, r.status, r.ageS, r.staleAfterS)
                for p, r in bed.params.items()
                if p in news2.PARAMS
            }
            result = news2.score(readings, cfg, bed.spo2Scale)
            result["computedAt"] = body.asOf
            results[bed.bed] = result
        return {"results": results}

    @app.post("/v1/assignment")
    def assignment_suggestion(body: AssignmentIn) -> dict[str, Any]:
        """A suggestion only: the server stores it as pending until a charge nurse decides."""
        nurses = [assignment.Nurse(n.staffId, frozenset(n.skills)) for n in body.nurses]
        beds = [assignment.BedNeed(b.bed, b.room, b.acuity, b.news2Total, b.news2Fresh, b.currentNurse, b.locked,
                                   frozenset(b.requiredSkills)) for b in body.beds]
        return assignment.suggest(nurses, beds, assign_cfg)

    return app


app = create_app()
