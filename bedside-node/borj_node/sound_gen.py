"""Generates sound effects for the bedside node if they do not exist.

All audio files are standard 16-bit PCM WAV (44.1 kHz, mono) created with
Python's built-in wave and struct modules (zero external dependencies).
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
from pathlib import Path

SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"


def _write_wav(path: Path, samples: list[float], sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        # 16-bit mono PCM
        import wave

        with wave.open(f, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            # clamp and pack
            frames = bytearray()
            for s in samples:
                val = max(-32767, min(32767, int(s * 32767)))
                frames.extend(struct.pack("<h", val))
            wav.writeframes(frames)


def generate_beep_wav(path: Path, freq: float = 1000.0, duration_s: float = 0.08) -> None:
    rate = 44100
    n = int(rate * duration_s)
    samples = []
    for i in range(n):
        t = i / rate
        # envelope with fast attack and decay
        env = math.sin(math.pi * i / n)
        samples.append(0.35 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def generate_chime_wav(path: Path) -> None:
    rate = 44100
    samples = []
    # Two tones: D5 (587.3 Hz) for 0.15s, then A5 (880 Hz) for 0.25s
    for freq, dur in [(587.33, 0.15), (880.0, 0.25)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-4.0 * t / dur)
            samples.append(0.3 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def generate_buzzer_wav(path: Path) -> None:
    rate = 44100
    samples = []
    # 3 quick alert bursts: 440 Hz + 880 Hz harmonic
    for _ in range(3):
        n_buzz = int(rate * 0.12)
        for i in range(n_buzz):
            t = i / rate
            s = 0.4 * (math.sin(2 * math.pi * 440 * t) + 0.3 * math.sin(2 * math.pi * 880 * t))
            samples.append(s)
        # gap
        samples.extend([0.0] * int(rate * 0.06))
    _write_wav(path, samples, rate)


def generate_voice_fr_wav(path: Path) -> None:
    # Try espeak-ng if present on the system
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    phrase = "Veuillez utiliser la sonnette d'urgence."
    if espeak:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [espeak, "-v", "fr", "-s", "140", phrase, "-w", str(path)],
                check=True,
                capture_output=True,
            )
            return
        except Exception:
            pass

    # Fallback acoustic alert phrase if espeak is not installed
    rate = 44100
    samples = []
    # 4 alarm sweeps to signal emergency bell
    for _ in range(4):
        n = int(rate * 0.25)
        for i in range(n):
            t = i / rate
            freq = 600 + 400 * (i / n)
            samples.append(0.4 * math.sin(2 * math.pi * freq * t))
        samples.extend([0.0] * int(rate * 0.08))
    _write_wav(path, samples, rate)


def generate_voice_ack_fr_wav(path: Path) -> None:
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    phrase = "Votre appel a été pris en compte, un soignant arrive."
    if espeak:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [espeak, "-v", "fr", "-s", "130", phrase, "-w", str(path)],
                check=True,
                capture_output=True,
            )
            return
        except Exception:
            pass

    # Fallback chime + harmonic sequence
    rate = 44100
    samples = []
    for freq, dur in [(523.25, 0.2), (659.25, 0.2), (783.99, 0.35)]:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = math.exp(-3.5 * t / dur)
            samples.append(0.35 * env * math.sin(2 * math.pi * freq * t))
    _write_wav(path, samples, rate)


def ensure_default_sounds() -> dict[str, Path]:
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    beep = SOUNDS_DIR / "beep.wav"
    chime = SOUNDS_DIR / "chime.wav"
    buzzer = SOUNDS_DIR / "buzzer.wav"
    voice_fr = SOUNDS_DIR / "emergency_fr.wav"
    ack_fr = SOUNDS_DIR / "ack_fr.wav"

    if not beep.exists():
        generate_beep_wav(beep)
    if not chime.exists():
        generate_chime_wav(chime)
    if not buzzer.exists():
        generate_buzzer_wav(buzzer)
    if not voice_fr.exists():
        generate_voice_fr_wav(voice_fr)
    if not ack_fr.exists():
        generate_voice_ack_fr_wav(ack_fr)

    return {
        "beep": beep,
        "chime": chime,
        "buzzer": buzzer,
        "emergency_bell": voice_fr,
        "ack_reassurance": ack_fr,
    }


if __name__ == "__main__":
    sounds = ensure_default_sounds()
    print("Generated sounds in:", SOUNDS_DIR)
    for k, v in sounds.items():
        print(f"  {k}: {v}")
