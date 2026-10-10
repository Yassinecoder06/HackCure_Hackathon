"""Nurse assignment suggestions: advisory only (safety invariant 1, HackCure section 6).

- A suggestion is computed by the inference layer from the live twin and kept as PENDING. It is
  audited when created, and nothing in the ward changes.
- Only a charge nurse's approval (POST .../decision) turns it into an `assignment` event, which is
  stored and replayed like every other event, and audited with the decider's name.
- If the ward changed since the suggestion was made (someone moved a bed meanwhile), approval is
  refused as stale instead of applying an outdated plan.
- Suggestions are made on request, and automatically when staff presence or admissions change
  (debounced, off the MQTT thread).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import borj_contracts as bc

from .ids import new_ulid
from .ingest import Ingestor
from .timeutil import format_ts

log = logging.getLogger(__name__)

TRIGGER_SCHEMAS = {"staff-presence", "binding"}


class SuggestionError(Exception):
    def __init__(self, status: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status, self.error, self.detail = status, error, detail


class AssignmentService:
    def __init__(
        self,
        ingestor: Ingestor,
        solve: Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any] | None],
        news2_by_bed: Callable[[], dict[str, dict[str, Any] | None]],
        on_suggestion: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.ingestor = ingestor
        self.solve = solve
        self.news2_by_bed = news2_by_bed
        self.on_suggestion = on_suggestion
        self.suggestions: dict[str, dict[str, Any]] = {}  # newest last
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="assignment")
        self._queued = threading.Event()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --- automatic triggers -----------------------------------------------------------------

    def on_event(self, schema: str, payload: dict[str, Any]) -> None:
        if schema not in TRIGGER_SCHEMAS or self._queued.is_set():
            return
        trigger = (f"{payload['staffId']}: {payload['reason'].replace('_', ' ')}" if schema == "staff-presence"
                   else f"{payload['bed']}: {payload['action'].replace('_', ' ')}")
        self._queued.set()  # debounce: a burst of admissions gives one suggestion
        self._executor.submit(self._auto, trigger)

    def _auto(self, trigger: str) -> None:
        self._queued.clear()
        try:
            self.suggest(trigger, automatic=True)
        except SuggestionError as exc:
            log.info("no automatic suggestion (%s): %s", trigger, exc.detail)
        except Exception:
            log.exception("automatic suggestion failed")

    # --- suggestions --------------------------------------------------------------------------

    def inputs(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        news2 = self.news2_by_bed()
        with self.ingestor.lock:
            twin = self.ingestor.twin
            nurses = [{"staffId": s.staff_id, "skills": list(s.skills)}
                      for s in twin.staff.values() if s.role == "nurse" and s.on_ward]
            beds = []
            for bed in twin.beds.values():
                if bed.admission is None:
                    continue
                result = news2.get(bed.bed)
                beds.append({
                    "bed": bed.bed, "room": bed.room, "acuity": bed.admission.acuity,
                    "news2Total": result["total"] if result else None,
                    "news2Fresh": bool(result and result["complete"]),
                    "currentNurse": twin.assignments.get(bed.bed),
                })
        return nurses, beds

    def suggest(self, trigger: str, automatic: bool = False) -> dict[str, Any]:
        nurses, beds = self.inputs()
        result = self.solve(nurses, beds)
        if result is None:
            raise SuggestionError(503, "inference_unavailable", "the inference layer could not be reached")
        if automatic and not result["changes"]:
            raise SuggestionError(200, "no_change", "current assignment is already the best one")
        suggestion = {
            "suggestionId": f"S-{new_ulid()[:16]}",
            "createdAt": format_ts(self.ingestor.event_now()),
            "trigger": trigger,
            "status": "pending" if result["status"] != "infeasible" else "expired",
            "changes": result["changes"],
            "reasons": result["reasons"],
            "confidence": result["confidence"],
            "loadBefore": result["loadBefore"],
            "loadAfter": result["loadAfter"],
        }
        with self._lock:
            for older in self.suggestions.values():
                if older["status"] == "pending":
                    older["status"] = "expired"  # superseded: only the newest plan can be approved
            self.suggestions[suggestion["suggestionId"]] = suggestion
        self.ingestor.store.audit("system", "suggestion.created", suggestion["suggestionId"],
                                  {"trigger": trigger, "changes": suggestion["changes"],
                                   "confidence": suggestion["confidence"]})
        if self.on_suggestion:
            self.on_suggestion(suggestion)
        return suggestion

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self.suggestions.values())
        return [s for s in reversed(items) if status is None or s["status"] == status]

    def decide(self, suggestion_id: str, decision: str, staff_id: str, reason: str | None) -> dict[str, Any]:
        with self._lock:
            suggestion = self.suggestions.get(suggestion_id)
            if suggestion is None:
                raise SuggestionError(404, "not_found", f"suggestion {suggestion_id}")
            if suggestion["status"] != "pending":
                raise SuggestionError(409, "conflict", f"suggestion is {suggestion['status']}")
            if decision == "approve":
                self._apply(suggestion, staff_id)
            suggestion.update(status="approved" if decision == "approve" else "rejected", decidedBy=staff_id,
                              decidedAt=format_ts(self.ingestor.event_now()))
            if reason:
                suggestion["decisionReason"] = reason
        self.ingestor.store.audit(staff_id, f"suggestion.{suggestion['status']}", suggestion_id,
                                  {"reason": reason or "", "changes": suggestion["changes"]})
        if self.on_suggestion:
            self.on_suggestion(suggestion)
        return suggestion

    def _apply(self, suggestion: dict[str, Any], staff_id: str) -> None:
        with self.ingestor.lock:
            current = dict(self.ingestor.twin.assignments)
        stale = [c["bed"] for c in suggestion["changes"] if current.get(c["bed"]) != c.get("fromStaffId")]
        if stale:
            suggestion["status"] = "expired"
            beds = ", ".join(stale)
            raise SuggestionError(409, "stale_suggestion",
                                  f"the ward changed since this suggestion (beds {beds}); ask for a new one")
        if not suggestion["changes"]:
            return
        ward = self.ingestor.layout.ward
        payload = {
            "schemaVersion": 1, "eventId": new_ulid(), "ts": format_ts(self.ingestor.event_now()), "ward": ward,
            "source": "borj-server", "sourceType": "server", "suggestionId": suggestion["suggestionId"],
            "decidedBy": staff_id, "changes": suggestion["changes"],
        }
        result = self.ingestor.handle(bc.topic("assignment", ward), payload)
        if result.status != "accepted":
            raise SuggestionError(500, "not_applied", f"{result.status}: {result.detail}")
