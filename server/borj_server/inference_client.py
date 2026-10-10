"""HTTP client for the inference layer (ADR 0009).

Scoring is on the triage path, so calls use a short timeout. If the inference service is
unreachable, callers get None and must show the score as unavailable, never guessed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class InferenceClient:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    @classmethod
    def from_url(cls, base_url: str, timeout_s: float) -> InferenceClient:
        return cls(httpx.Client(base_url=base_url, timeout=timeout_s))

    def news2_batch(self, as_of: str, beds: list[dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
        if not beds:
            return {}
        try:
            resp = self.http.post("/v1/news2/batch", json={"asOf": as_of, "beds": beds})
            resp.raise_for_status()
            return resp.json()["results"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("inference unavailable: %s", exc)
            return None

    def close(self) -> None:
        self.http.close()
