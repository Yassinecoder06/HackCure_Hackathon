"""Rotary encoder controller for volume and bedside settings.

Integrates KY-040 rotary encoder (CLK on GPIO 23, DT on GPIO 24)
to smoothly control speaker volume via ALSA Master mixer.
Graceful mock fallback when running off-Pi.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable

log = logging.getLogger(__name__)

try:
    from gpiozero import RotaryEncoder as GpioRotaryEncoder
except Exception:
    GpioRotaryEncoder = None


class RotaryEncoderController:
    """Manages the physical KY-040 rotary encoder."""

    def __init__(
        self,
        pin_clk: int = 23,
        pin_dt: int = 24,
        max_steps: int = 20,
        initial_percent: int = 90,
        mock: bool = False,
        on_change: Callable[[int], None] | None = None,
    ) -> None:
        self.pin_clk = pin_clk
        self.pin_dt = pin_dt
        self.max_steps = max(1, max_steps)
        self.current_percent = max(0, min(100, initial_percent))
        self.mock = mock or (GpioRotaryEncoder is None)
        self.on_change = on_change

        self._encoder = None
        self._has_amixer = shutil.which("amixer") is not None

        if not self.mock and GpioRotaryEncoder is not None:
            try:
                self._encoder = GpioRotaryEncoder(
                    self.pin_clk,
                    self.pin_dt,
                    max_steps=self.max_steps,
                    bounce_time=0.002,
                )
                self._encoder.steps = int((self.current_percent / 100.0) * self.max_steps)
                self._encoder.when_rotated = self._handle_rotate
                log.info(
                    "Initialized physical Rotary Encoder on CLK:%d DT:%d (Volume: %d%%)",
                    pin_clk,
                    pin_dt,
                    self.current_percent,
                )
            except Exception as exc:
                log.warning("Could not initialize physical encoder (%s), using mock mode", exc)
                self.mock = True
                self._encoder = None

        # Apply initial volume if amixer is available
        self._apply_system_volume(self.current_percent)

    def _handle_rotate(self) -> None:
        if self._encoder is None:
            return
        steps = self._encoder.steps
        # Clamp steps
        if steps < 0:
            steps = 0
            self._encoder.steps = 0
        elif steps > self.max_steps:
            steps = self.max_steps
            self._encoder.steps = self.max_steps

        percent = int(round((steps / self.max_steps) * 100))
        if percent != self.current_percent:
            self.current_percent = percent
            log.info("[ENCODER] Volume set to %d%%", percent)
            self._apply_system_volume(percent)
            if self.on_change:
                try:
                    self.on_change(percent)
                except Exception as exc:
                    log.error("Error in on_change callback: %s", exc)

    def _apply_system_volume(self, percent: int) -> None:
        if not self._has_amixer:
            return
        try:
            subprocess.run(
                ["amixer", "set", "Master", f"{percent}%"],
                capture_output=True,
                check=False,
                timeout=1.0,
            )
        except Exception as exc:
            log.debug("Failed to set ALSA volume via amixer: %s", exc)

    def set_volume(self, percent: int) -> None:
        """Programmatically adjust volume (0-100)."""
        self.current_percent = max(0, min(100, percent))
        if self._encoder is not None:
            self._encoder.steps = int((self.current_percent / 100.0) * self.max_steps)
        self._apply_system_volume(self.current_percent)

    def close(self) -> None:
        """Release GPIO resources."""
        if self._encoder is not None:
            try:
                self._encoder.close()
            except Exception:
                pass
            self._encoder = None
