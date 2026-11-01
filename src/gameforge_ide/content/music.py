"""Procedural musical background loop generator (P7 WI-7.8).

Generates 16-bar seamlessly looping chord progressions for 4 moods:
- calm: I–vi–IV–V at 80 bpm
- tense: i–VI–VII–i at 120 bpm
- heroic: I–V–vi–IV at 110 bpm
- playful: I–IV–V–IV at 128 bpm

Synthesized with harmonic sine/triangle voices and envelopes, written as 16-bit PCM WAV.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

SAMPLE_RATE = 44100

# Base note frequencies (Hz)
NOTE_FREQS: Dict[str, float] = {
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00, "A3": 220.00, "B3": 246.94,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88,
    "C5": 523.25,
}

MOOD_CONFIGS: Dict[str, Dict[str, Any]] = {
    "calm": {
        "bpm": 80.0,
        "progression": [
            ("C4", "E4", "G4"),  # I
            ("A3", "C4", "E4"),  # vi
            ("F3", "A3", "C4"),  # IV
            ("G3", "B3", "D4"),  # V
        ],
    },
    "tense": {
        "bpm": 120.0,
        "progression": [
            ("A3", "C4", "E4"),  # i
            ("F3", "A3", "C4"),  # VI
            ("G3", "B3", "D4"),  # VII
            ("A3", "C4", "E4"),  # i
        ],
    },
    "heroic": {
        "bpm": 110.0,
        "progression": [
            ("C4", "E4", "G4"),  # I
            ("G3", "B3", "D4"),  # V
            ("A3", "C4", "E4"),  # vi
            ("F3", "A3", "C4"),  # IV
        ],
    },
    "playful": {
        "bpm": 128.0,
        "progression": [
            ("C4", "E4", "G4"),  # I
            ("F3", "A3", "C4"),  # IV
            ("G3", "B3", "D4"),  # V
            ("F3", "A3", "C4"),  # IV
        ],
    },
}


def _synth_chord(notes: Tuple[str, ...], duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(duration_s * sample_rate), endpoint=False)
    signal = np.zeros_like(t)

    for note in notes:
        freq = NOTE_FREQS.get(note, 440.0)
        # Fundamental sine + second harmonic triangle
        fundamental = np.sin(2.0 * np.pi * freq * t)
        harmonic = 0.35 * np.sin(4.0 * np.pi * freq * t)
        sub = 0.25 * np.sin(np.pi * freq * t)
        signal += (fundamental + harmonic + sub)

    signal /= len(notes)

    # Smooth attack and decay envelope
    env = np.ones_like(t)
    attack_samples = int(0.05 * sample_rate)
    decay_samples = int(0.08 * sample_rate)
    if len(t) > attack_samples + decay_samples:
        env[:attack_samples] = np.linspace(0.0, 1.0, attack_samples)
        env[-decay_samples:] = np.linspace(1.0, 0.0, decay_samples)
    return signal * env


def generate_music_loop(mood: str, out_path: Path, sample_rate: int = SAMPLE_RATE) -> Path:
    """Generate a 16-bar seamlessly looping music track as a 16-bit PCM WAV."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    config = MOOD_CONFIGS.get(mood.lower(), MOOD_CONFIGS["calm"])
    bpm = config["bpm"]
    progression = config["progression"]

    # 4 beats per bar, 4 bars per cycle => 16 bars total = 4 repeats of the 4-bar progression
    bar_duration_s = (60.0 / bpm) * 4.0

    bars: List[np.ndarray] = []
    # 4 repeats = 16 bars
    for _ in range(4):
        for chord in progression:
            bars.append(_synth_chord(chord, bar_duration_s, sample_rate))

    audio = np.concatenate(bars)
    # Master peak normalize with -1.5 dB headroom
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = (audio / peak) * 0.84

    # Convert to 16-bit PCM
    pcm16 = (audio * 32767.0).astype(np.int16)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())

    return out_path
