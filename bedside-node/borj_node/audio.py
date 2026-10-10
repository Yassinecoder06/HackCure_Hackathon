"""Audio playback manager for the bedside node.

Plays acoustic cues and pre-recorded prompts (aplay on Linux / Raspberry Pi)
asynchronously so button responsiveness and MQTT traffic are never blocked.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

from .sound_gen import ensure_default_sounds

log = logging.getLogger(__name__)


class AudioManager:
    def __init__(self, sounds_dir: Path | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self._aplay_cmd = shutil.which("aplay")
        self.sounds = ensure_default_sounds()
        self._current_proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def play(self, sound_name: str, wait: bool = False) -> None:
        if not self.enabled:
            return

        sound_path = self.sounds.get(sound_name)
        if not sound_path or not sound_path.exists():
            log.warning("sound file %s not found", sound_name)
            return

        if not self._aplay_cmd:
            log.info("[AUDIO MOCK] Playing %s (%s)", sound_name, sound_path.name)
            return

        def _run() -> None:
            with self._lock:
                # stop previous if still playing
                if self._current_proc and self._current_proc.poll() is None:
                    try:
                        self._current_proc.terminate()
                    except Exception:
                        pass
                try:
                    self._current_proc = subprocess.Popen(
                        [self._aplay_cmd, "-q", str(sound_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception as exc:
                    log.warning("failed to play %s via aplay: %s", sound_name, exc)
                    return

            if wait and self._current_proc:
                self._current_proc.wait()

        if wait:
            _run()
        else:
            threading.Thread(target=_run, daemon=True, name=f"audio-{sound_name}").start()

    def play_beep(self) -> None:
        """Immediate short audio cue on button press."""
        self.play("beep")

    def play_chime(self) -> None:
        """Comforting confirmation chime when staff acknowledges the call."""
        self.play("chime")

    def play_buzzer(self) -> None:
        """Fast buzz alarm for not_sent / network outage."""
        self.play("buzzer")

    def play_emergency_bell(self) -> None:
        """Pre-recorded voice prompt telling patient to use the emergency bell."""
        self.play("emergency_bell")

    def stop(self) -> None:
        with self._lock:
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                except Exception:
                    pass
                self._current_proc = None
