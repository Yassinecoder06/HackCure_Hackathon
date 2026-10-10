"""Button input handler for bedside node.

Listens for presses on Assist (GPIO 17) and Comfort (GPIO 27) buttons.
Includes hardware debouncing, pull-up configuration, and mock mode triggers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

try:
    from gpiozero import Button as GpioButton
except Exception:
    GpioButton = None


class ButtonController:
    """Manages the bedside physical push buttons."""

    def __init__(
        self,
        pin_assist: int = 17,
        pin_comfort: int = 27,
        pull_up: bool = True,
        bounce_time: float = 0.05,
        on_assist: Callable[[], None] | None = None,
        on_comfort: Callable[[], None] | None = None,
        mock: bool = False,
    ) -> None:
        self.pin_assist = pin_assist
        self.pin_comfort = pin_comfort
        self.pull_up = pull_up
        self.bounce_time = bounce_time
        self.on_assist = on_assist
        self.on_comfort = on_comfort
        self.mock = mock or (GpioButton is None)

        self._btn_assist: Any = None
        self._btn_comfort: Any = None

        if not self.mock and GpioButton is not None:
            try:
                self._btn_assist = GpioButton(pin_assist, pull_up=pull_up, bounce_time=bounce_time)
                self._btn_comfort = GpioButton(pin_comfort, pull_up=pull_up, bounce_time=bounce_time)

                if self.on_assist:
                    self._btn_assist.when_pressed = self._handle_assist
                if self.on_comfort:
                    self._btn_comfort.when_pressed = self._handle_comfort
                log.info("Physical buttons registered (Assist: GPIO %d, Comfort: GPIO %d)", pin_assist, pin_comfort)
            except Exception as exc:
                log.warning("Could not initialize physical buttons (%s), falling back to mock mode", exc)
                self.mock = True
                self._btn_assist = None
                self._btn_comfort = None

    def _handle_assist(self) -> None:
        log.info("🔘 Button ASSIST pressed (GPIO %d)", self.pin_assist)
        if self.on_assist:
            self.on_assist()

    def _handle_comfort(self) -> None:
        log.info("🔘 Button COMFORT pressed (GPIO %d)", self.pin_comfort)
        if self.on_comfort:
            self.on_comfort()

    def trigger_assist(self) -> None:
        """Manual / mock trigger for Assist."""
        self._handle_assist()

    def trigger_comfort(self) -> None:
        """Manual / mock trigger for Comfort."""
        self._handle_comfort()

    def close(self) -> None:
        if self._btn_assist:
            self._btn_assist.close()
        if self._btn_comfort:
            self._btn_comfort.close()
