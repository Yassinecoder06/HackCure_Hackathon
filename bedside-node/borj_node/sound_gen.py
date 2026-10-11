"""Generates sound effects and voice prompts for the bedside node.

All audio files are standard 16-bit PCM WAV (44.1 kHz, mono) created with
Python's built-in wave and struct modules (zero external dependencies),
with automatic support for espeak-ng / espeak when available for natural speech.
"""

from __future__ import annotations

import logging
import math
import shutil
import struct
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"


def _write_wav(path: Path, samples: list[float], sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        import wave

        with wave.open(f, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            frames = bytearray()
            for s in samples:
                val = max(-32767, min(32767, int(s * 32767)))
                frames.extend(struct.pack("<h", val))
            wav.writeframes(frames)


def generate_beep_wav(path: Path, freq: float = 1000.0, duration_s: float = 0.08) -> None:
    """Crisp short audio cue on tactile button press."""
    rate = 44100
    n = int(rate * duration_s)
    samples = []
    for i in range(n):
        t = i / rate
        env = math.sin(math.pi * i / n)
        samples.append(0.85 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def generate_chime_wav(path: Path) -> None:
    """Classic hospital two-tone chime (D5 587 Hz -> A5 880 Hz)."""
    rate = 44100
    samples = []
    for freq, dur in [(587.33, 0.15), (880.0, 0.25)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-4.0 * t / dur)
            samples.append(0.85 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def generate_soft_chime_wav(path: Path) -> None:
    """Gentle 3-tone arpeggio (C5 523Hz -> E5 659Hz -> G5 784Hz) for comfort assistance."""
    rate = 44100
    samples = []
    for freq, dur in [(523.25, 0.18), (659.25, 0.18), (783.99, 0.35)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-3.5 * t / dur)
            samples.append(0.70 * env * (math.sin(2 * math.pi * freq * t) + 0.2 * math.sin(4 * math.pi * freq * t)))
    _write_wav(path, samples, rate)


def generate_triple_tap_alarm_wav(path: Path) -> None:
    """Urgent 3-stage rising acoustic alarm triggered by triple-tap emergency."""
    rate = 44100
    samples = []
    stages = [(880.0, 0.12), (1174.66, 0.12), (1567.98, 0.22)]
    # Repeat sequence twice for clear clinical emergency salience
    for _ in range(2):
        for freq, dur in stages:
            n = int(rate * dur)
            for i in range(n):
                t = i / rate
                env = math.sin(math.pi * i / n) ** 0.5
                s = 0.75 * math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t)
                samples.append(env * s)
            samples.extend([0.0] * int(rate * 0.04))
        samples.extend([0.0] * int(rate * 0.08))
    _write_wav(path, samples, rate)


def generate_buzzer_wav(path: Path) -> None:
    """3 quick alert buzzer bursts for network outage / fail-safe alert."""
    rate = 44100
    samples = []
    for _ in range(3):
        n_buzz = int(rate * 0.12)
        for i in range(n_buzz):
            t = i / rate
            s = 0.85 * (math.sin(2 * math.pi * 440 * t) + 0.3 * math.sin(2 * math.pi * 880 * t))
            samples.append(s)
        samples.extend([0.0] * int(rate * 0.06))
    _write_wav(path, samples, rate)


def generate_doctor_order_chime_wav(path: Path) -> None:
    """Clinical dual-tone telemetry ping for new physician orders."""
    rate = 44100
    samples = []
    for freq, dur in [(783.99, 0.14), (1046.50, 0.28)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-4.5 * t / dur)
            samples.append(0.80 * env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(3 * math.pi * freq * t)))
    _write_wav(path, samples, rate)


def generate_med_round_chime_wav(path: Path) -> None:
    """Calm double drop tone for medication delivery rounds."""
    rate = 44100
    samples = []
    for freq, dur in [(659.25, 0.18), (523.25, 0.32)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-3.0 * t / dur)
            samples.append(0.75 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def generate_presence_chime_wav(path: Path) -> None:
    """Gentle 4-tone ascending confirmation chime when nurse arrives at bedside."""
    rate = 44100
    samples = []
    for freq, dur in [(523.25, 0.10), (659.25, 0.10), (783.99, 0.10), (1046.50, 0.25)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-3.5 * t / dur)
            samples.append(0.70 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def generate_spoken_phrase_wav(
    path: Path,
    phrase: str,
    lang: str = "fr",
    fallback_kind: str = "reassurance",
) -> None:
    """Generate spoken speech WAV using espeak/espeak-ng with pure Python acoustic fallback."""
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [espeak, "-v", lang, "-s", "135", phrase, "-w", str(path)],
                check=True,
                capture_output=True,
            )
            return
        except Exception as exc:
            log.debug("espeak execution failed (%s), using synthetic fallback", exc)

    # Synthetic fallback when TTS binary is absent
    rate = 44100
    samples = []
    if fallback_kind == "emergency":
        for freq in [880.0, 1174.66, 880.0, 1174.66, 1567.98]:
            n = int(rate * 0.18)
            for i in range(n):
                t = i / rate
                env = math.sin(math.pi * i / n)
                samples.append(0.75 * env * math.sin(2 * math.pi * freq * t))
            samples.extend([0.0] * int(rate * 0.05))
    elif fallback_kind == "comfort":
        for freq in [440.0, 554.37, 659.25]:
            n = int(rate * 0.22)
            for i in range(n):
                t = i / rate
                env = math.exp(-3.0 * t / 0.22)
                samples.append(0.65 * env * math.sin(2 * math.pi * freq * t))
    elif fallback_kind == "order":
        for freq in [783.99, 1046.50]:
            n = int(rate * 0.20)
            for i in range(n):
                t = i / rate
                env = math.exp(-3.5 * t / 0.20)
                samples.append(0.70 * env * math.sin(2 * math.pi * freq * t))
    elif fallback_kind == "meds":
        for freq in [659.25, 523.25, 659.25]:
            n = int(rate * 0.18)
            for i in range(n):
                t = i / rate
                env = math.exp(-3.0 * t / 0.18)
                samples.append(0.65 * env * math.sin(2 * math.pi * freq * t))
    elif fallback_kind == "presence":
        for freq in [523.25, 659.25, 783.99, 1046.50]:
            n = int(rate * 0.12)
            for i in range(n):
                t = i / rate
                env = math.exp(-3.5 * t / 0.12)
                samples.append(0.65 * env * math.sin(2 * math.pi * freq * t))
    else:
        # Default reassuring harmonic chime
        for freq in [523.25, 659.25, 783.99]:
            n = int(rate * 0.20)
            for i in range(n):
                t = i / rate
                env = math.exp(-3.5 * t / 0.20)
                samples.append(0.70 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def ensure_default_sounds() -> dict[str, Path]:
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Acoustic tones
    beep = SOUNDS_DIR / "beep.wav"
    chime = SOUNDS_DIR / "chime.wav"
    soft_chime = SOUNDS_DIR / "soft_chime.wav"
    buzzer = SOUNDS_DIR / "buzzer.wav"
    triple_tap_alarm = SOUNDS_DIR / "triple_tap_alarm.wav"
    doctor_order_chime = SOUNDS_DIR / "doctor_order_chime.wav"
    med_round_chime = SOUNDS_DIR / "med_round_chime.wav"
    presence_chime = SOUNDS_DIR / "presence_chime.wav"

    if not beep.exists():
        generate_beep_wav(beep)
    if not chime.exists():
        generate_chime_wav(chime)
    if not soft_chime.exists():
        generate_soft_chime_wav(soft_chime)
    if not buzzer.exists():
        generate_buzzer_wav(buzzer)
    if not triple_tap_alarm.exists():
        generate_triple_tap_alarm_wav(triple_tap_alarm)
    if not doctor_order_chime.exists():
        generate_doctor_order_chime_wav(doctor_order_chime)
    if not med_round_chime.exists():
        generate_med_round_chime_wav(med_round_chime)
    if not presence_chime.exists():
        generate_presence_chime_wav(presence_chime)

    # 2. Spoken voice paragraph patterns
    prompts = {
        # Emergency Alert (Urgence médicale immédiate)
        "emergency_trigger_fr": (
            "emergency_trigger_fr.wav",
            "Urgence médicale déclenchée au chevet. L'équipe soignante et le médecin de garde ont été "
            "alertés immédiatement. Restez au lit, nous arrivons.",
            "fr",
            "emergency",
        ),
        "emergency_trigger_en": (
            "emergency_trigger_en.wav",
            "Medical emergency triggered at bedside. Care team and on-call physician alerted immediately. "
            "Please remain in bed, help is on the way.",
            "en",
            "emergency",
        ),
        # Nurse Call Acknowledgment / Reassurance
        "ack_reassurance": (
            "ack_fr.wav",
            "Votre appel a été pris en compte, un soignant arrive.",
            "fr",
            "reassurance",
        ),
        "ack_reassurance_en": (
            "ack_en.wav",
            "Your call has been received, a caregiver is on the way.",
            "en",
            "reassurance",
        ),
        # Comfort Request
        "comfort_ack_fr": (
            "comfort_ack_fr.wav",
            "Votre demande d'assistance a été transmise à l'aide-soignant. Nous arrivons pour vous aider.",
            "fr",
            "comfort",
        ),
        "comfort_ack_en": (
            "comfort_ack_en.wav",
            "Your comfort request has been forwarded to the care assistant. We are coming to assist you.",
            "en",
            "comfort",
        ),
        # Doctor Order
        "doctor_instruction_fr": (
            "doctor_instruction_fr.wav",
            "Nouvelle consigne médicale reçue du médecin de garde. L'équipe soignante adapte votre prise en charge.",
            "fr",
            "order",
        ),
        "doctor_instruction_en": (
            "doctor_instruction_en.wav",
            "New clinical order received from the on-call physician. Care team is updating your care plan.",
            "en",
            "order",
        ),
        # Medication Round
        "med_round_fr": (
            "med_round_fr.wav",
            "Tour de médication en cours. Votre soignant arrive pour l'administration de vos médicaments.",
            "fr",
            "meds",
        ),
        "med_round_en": (
            "med_round_en.wav",
            "Medication round in progress. Your caregiver will be here shortly with your medications.",
            "en",
            "meds",
        ),
        # Vital Signs Observation
        "vitals_check_fr": (
            "vitals_check_fr.wav",
            "Surveillance des constantes vitales. Veuillez vous détendre et respirer normalement.",
            "fr",
            "reassurance",
        ),
        "vitals_check_en": (
            "vitals_check_en.wav",
            "Vital signs observation in progress. Please relax and breathe normally.",
            "en",
            "reassurance",
        ),
        # Staff Presence at Bedside
        "staff_present_fr": (
            "staff_present_fr.wav",
            "Présence soignante confirmée au chevet. Appel d'assistance clôturé.",
            "fr",
            "presence",
        ),
        "staff_present_en": (
            "staff_present_en.wav",
            "Caregiver presence confirmed at bedside. Call completed.",
            "en",
            "presence",
        ),
        # Fail-Safe Outage Warning (Sonnette d'urgence filaire)
        "emergency_bell": (
            "emergency_fr.wav",
            "Attention : le réseau du chevet est indisponible. Veuillez utiliser la sonnette d'urgence filaire.",
            "fr",
            "emergency",
        ),
        "outage_alert_en": (
            "outage_en.wav",
            "Bedside network unavailable. Please use the manual emergency pull cord.",
            "en",
            "emergency",
        ),
    }

    sounds_map: dict[str, Path] = {
        "beep": beep,
        "chime": chime,
        "soft_chime": soft_chime,
        "buzzer": buzzer,
        "triple_tap_alarm": triple_tap_alarm,
        "doctor_order_chime": doctor_order_chime,
        "med_round_chime": med_round_chime,
        "presence_chime": presence_chime,
    }

    for key, (filename, phrase, lang, fallback) in prompts.items():
        file_path = SOUNDS_DIR / filename
        if not file_path.exists():
            generate_spoken_phrase_wav(file_path, phrase, lang=lang, fallback_kind=fallback)
        sounds_map[key] = file_path

    return sounds_map


if __name__ == "__main__":
    sounds = ensure_default_sounds()
    print("Generated sounds in:", SOUNDS_DIR)
    for k, v in sounds.items():
        print(f"  {k}: {v.name} ({v.stat().st_size} bytes)")
