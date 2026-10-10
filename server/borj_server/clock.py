"""The ward's notion of "now".

In demo mode the simulator runs faster than real time and publishes borj/{ward}/sim/clock.
Freshness and escalation timers must then use simulated time, otherwise every reading
would look stale (or never stale) depending on the simulator speed.
"""

from __future__ import annotations

from datetime import datetime

from .timeutil import parse_ts, utcnow


class Clock:
    def __init__(self, mode: str = "sim") -> None:
        if mode not in {"sim", "wall"}:
            raise ValueError(f"clock mode must be 'sim' or 'wall', got {mode!r}")
        self.mode = mode
        self._sim_now: datetime | None = None

    def update_from_message(self, payload: dict) -> None:
        if self.mode == "sim":
            self._sim_now = parse_ts(payload["simTs"])

    @property
    def effective_mode(self) -> str:
        """'sim' only once a simulator clock has actually been received."""
        return "sim" if self.mode == "sim" and self._sim_now is not None else "wall"

    def now(self) -> datetime:
        if self.effective_mode == "sim":
            assert self._sim_now is not None
            return self._sim_now
        return utcnow()
