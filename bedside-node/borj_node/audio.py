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
        self.device = None
        try:
            cards = Path("/proc/asound/cards").read_text()
            if "MAX98357A" in cards:
                self.device = "plughw:CARD=MAX98357A,DEV=0"
        except Exception:
            pass

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
                    cmd = [self._aplay_cmd, "-q"]
                    if self.device:
                        cmd.extend(["-D", self.device])
                    cmd.append(str(sound_path))
                    log.info("Playing audio %s (via %s)", sound_name, self.device or "default")
                    self._current_proc = subprocess.Popen(
                        cmd,
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

    def play_chime(self, wait: bool = False) -> None:
        """Standard two-tone confirmation chime."""
        self.play("chime", wait=wait)

    def play_soft_chime(self, wait: bool = False) -> None:
        """Gentle 3-tone arpeggio for comfort requests."""
        self.play("soft_chime", wait=wait)

    def play_buzzer(self, wait: bool = False) -> None:
        """Fast buzz alarm for not_sent / network outage."""
        self.play("buzzer", wait=wait)

    def play_triple_tap_alarm(self, wait: bool = False) -> None:
        """Urgent 3-stage rising acoustic alert triggered by triple-tap emergency."""
        self.play("triple_tap_alarm", wait=wait)

    def play_emergency_bell(self, wait: bool = False) -> None:
        """Pre-recorded voice prompt telling patient to use the emergency bell."""
        self.play("emergency_bell", wait=wait)

    def play_emergency_trigger(self, lang: str = "fr") -> None:
        """Full emergency escalation: urgent acoustic alarm + spoken emergency voice alert."""
        prompt_key = "emergency_trigger_en" if lang.lower().startswith("en") else "emergency_trigger_fr"

        def _seq() -> None:
            self.play("triple_tap_alarm", wait=True)
            self.play(prompt_key, wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-emergency-seq").start()

    def play_ack_reassurance(self, lang: str = "fr") -> None:
        """Requirement C: Reassuring chime + spoken 'Votre appel a été pris en compte, un soignant arrive.'"""
        prompt_key = "ack_reassurance_en" if lang.lower().startswith("en") else "ack_reassurance"

        def _seq() -> None:
            self.play("chime", wait=True)
            self.play(prompt_key, wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-ack-seq").start()

    def play_comfort_ack(self, lang: str = "fr") -> None:
        """Gentle soft chime + spoken comfort assistance confirmation."""
        prompt_key = "comfort_ack_en" if lang.lower().startswith("en") else "comfort_ack_fr"

        def _seq() -> None:
            self.play("soft_chime", wait=True)
            self.play(prompt_key, wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-comfort-seq").start()

    def play_doctor_instruction(self, lang: str = "fr") -> None:
        """Physician order cue + spoken clinical instruction update."""
        prompt_key = "doctor_instruction_en" if lang.lower().startswith("en") else "doctor_instruction_fr"

        def _seq() -> None:
            self.play("doctor_order_chime", wait=True)
            self.play(prompt_key, wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-doctor-seq").start()

    def play_med_round(self, lang: str = "fr") -> None:
        """Medication round chime + spoken medication reminder prompt."""
        prompt_key = "med_round_en" if lang.lower().startswith("en") else "med_round_fr"

        def _seq() -> None:
            self.play("med_round_chime", wait=True)
            self.play(prompt_key, wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-med-seq").start()

    def play_vitals_check(self, lang: str = "fr") -> None:
        """Spoken vital signs check notification."""
        prompt_key = "vitals_check_en" if lang.lower().startswith("en") else "vitals_check_fr"
        self.play(prompt_key, wait=False)

    def play_staff_present(self, lang: str = "fr") -> None:
        """Ascending presence chime + spoken call completion announcement."""
        prompt_key = "staff_present_en" if lang.lower().startswith("en") else "staff_present_fr"

        def _seq() -> None:
            self.play("presence_chime", wait=True)
            self.play(prompt_key, wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-presence-seq").start()

    def play_outage_alert(self) -> None:
        """Requirement A: Fail-safe buzzer + voice prompt 'Veuillez utiliser la sonnette d'urgence.'"""
        def _seq() -> None:
            self.play("buzzer", wait=True)
            self.play("emergency_bell", wait=False)

        threading.Thread(target=_seq, daemon=True, name="audio-outage-seq").start()

    def stop(self) -> None:
        with self._lock:
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                except Exception:
                    pass
                self._current_proc = None
