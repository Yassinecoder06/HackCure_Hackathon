"""LED controller for the bedside node.

Drives red, green and optional amber indicators to reflect call state.
Supports pulsing, steady on, and fast blinking in background threads.
Clean mock fallback when running off-Pi or during testing.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

try:
    from gpiozero import LED as GpioLED
except Exception:
    GpioLED = None


class LedController:
    """Manages the visual call status indicators."""

    def __init__(
        self,
        pin_green: int | None = 22,
        pin_red: int | None = 23,
        pin_amber: int | None = None,
        mock: bool = False,
    ) -> None:
        self.pin_green = pin_green
        self.pin_red = pin_red
        self.pin_amber = pin_amber
        self.mock = mock or (GpioLED is None)

        self._led_green: Any = None
        self._led_red: Any = None
        self._led_amber: Any = None

        self._current_pattern = "off"
        self._stop_event = threading.Event()
        self._anim_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        if not self.mock and GpioLED is not None:
            try:
                if pin_green is not None:
                    self._led_green = GpioLED(pin_green)
                if pin_red is not None:
                    self._led_red = GpioLED(pin_red)
                if pin_amber is not None:
                    self._led_amber = GpioLED(pin_amber)
                log.info("Initialized physical LEDs (G:%s, R:%s, A:%s)", pin_green, pin_red, pin_amber)
            except Exception as exc:
                log.warning("Could not initialize physical LEDs (%s), falling back to mock", exc)
                self.mock = True
                self._led_green = None
                self._led_red = None
                self._led_amber = None

    def _set_raw(self, green: bool, red: bool, amber: bool = False) -> None:
        if self._led_green:
            if green:
                self._led_green.on()
            else:
                self._led_green.off()
        if self._led_red:
            if red:
                self._led_red.on()
            else:
                self._led_red.off()
        if self._led_amber:
            if amber:
                self._led_amber.on()
            else:
                self._led_amber.off()

    def _stop_animation(self) -> None:
        self._stop_event.set()
        if self._anim_thread and self._anim_thread.is_alive():
            self._anim_thread.join(timeout=0.5)
        self._stop_event.clear()

    def show_off(self) -> None:
        """All LEDs off."""
        with self._lock:
            self._stop_animation()
            self._current_pattern = "off"
            self._set_raw(False, False, False)
            log.debug("[LED] State: OFF")

    def show_pressed(self) -> None:
        """Brief pulse to confirm button touch."""
        with self._lock:
            self._stop_animation()
            self._current_pattern = "pressed"

            def _pulse() -> None:
                self._set_raw(True, False, False)
                time.sleep(0.18)
                if not self._stop_event.is_set():
                    self._set_raw(False, False, False)

            self._anim_thread = threading.Thread(target=_pulse, daemon=True, name="led-pulse")
            self._anim_thread.start()
            log.debug("[LED] State: PRESSED (brief pulse)")

    def show_sent(self) -> None:
        """Call delivered to ward server. Amber if present, otherwise steady green."""
        with self._lock:
            self._stop_animation()
            self._current_pattern = "sent"
            if self._led_amber:
                self._set_raw(False, False, True)
            else:
                # If no dedicated amber LED, use green steady
                self._set_raw(True, False, False)
            log.info("[LED] State: SENT (steady)")

    def show_acknowledged(self) -> None:
        """Staff acknowledged the call: green pulsing."""
        with self._lock:
            self._stop_animation()
            self._current_pattern = "acknowledged"

            def _pulse_green() -> None:
                while not self._stop_event.is_set():
                    self._set_raw(True, False, False)
                    self._stop_event.wait(0.6)
                    if self._stop_event.is_set():
                        break
                    self._set_raw(False, False, False)
                    self._stop_event.wait(0.4)

            self._anim_thread = threading.Thread(target=_pulse_green, daemon=True, name="led-ack")
            self._anim_thread.start()
            log.info("[LED] State: ACKNOWLEDGED (green pulsing)")

    def show_not_sent(self) -> None:
        """Call not delivered within timeout: fast red blink."""
        with self._lock:
            self._stop_animation()
            self._current_pattern = "not_sent"

            def _blink_red() -> None:
                while not self._stop_event.is_set():
                    self._set_raw(False, True, False)
                    self._stop_event.wait(0.12)
                    if self._stop_event.is_set():
                        break
                    self._set_raw(False, False, False)
                    self._stop_event.wait(0.12)

            self._anim_thread = threading.Thread(target=_blink_red, daemon=True, name="led-not-sent")
            self._anim_thread.start()
            log.warning("[LED] State: NOT_SENT (fast red blink)")

    def close(self) -> None:
        self.show_off()
        if self._led_green:
            self._led_green.close()
        if self._led_red:
            self._led_red.close()
        if self._led_amber:
            self._led_amber.close()
