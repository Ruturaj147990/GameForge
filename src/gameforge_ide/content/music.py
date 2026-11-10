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
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

SAMPLE_RATE = 44100

_SEMITONES: Dict[str, int] = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
    "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}


def note_to_freq(note: str) -> float:
    """Calculate mathematically exact frequency (Hz) using 12-TET tuning ($A_4 = 440.0$).
    
    Supports any standard scientific pitch notation (e.g., 'C4', 'Eb3', 'F#4', 'A4', 'Bb5').
    """
    s = note.strip().upper()
    if not s:
        return 440.0
    if s[-1].isdigit():
        name = s[:-1]
        octave = int(s[-1])
    else:
        name = s
        octave = 4
    if name not in _SEMITONES:
        return 440.0
    # Standard MIDI note: C4 is 60, A4 is 69
    midi = 12 * (octave + 1) + _SEMITONES[name]
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


# Base note frequencies cached for common notes; dynamic fallback via note_to_freq
NOTE_FREQS: Dict[str, float] = {
    n: note_to_freq(n)
    for n in [
        "C3", "D3", "E3", "F3", "G3", "A3", "B3",
        "C4", "D4", "E4", "F4", "G4", "A4", "B4",
        "C5", "D5", "E5", "F5", "G5", "A5", "B5"
    ]
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
    "boss": {
        "bpm": 135.0,
        "progression": [
            ("D3", "F3", "A3"),   # i
            ("BB2", "D3", "F3"),  # VI
            ("C3", "E3", "G3"),   # VII
            ("A2", "C#3", "E3"),  # V major
        ],
    },
    "action": {
        "bpm": 140.0,
        "progression": [
            ("E3", "G3", "B3"),   # i
            ("C3", "E3", "G3"),   # VI
            ("D3", "F#3", "A3"),  # VII
            ("B2", "D#3", "F#3"), # V major
        ],
    },
    "mysterious": {
        "bpm": 75.0,
        "progression": [
            ("D3", "F3", "A3"),  # i
            ("G3", "B3", "D4"),  # IV Dorian
            ("C3", "E3", "G3"),  # VII
            ("BB2", "D3", "F3"), # VI
        ],
    },
}


def _synth_chord(notes: Tuple[str, ...], n_samples: int, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    duration_s = n_samples / sample_rate
    t = np.linspace(0.0, duration_s, n_samples, endpoint=False)
    signal = np.zeros_like(t)

    for note in notes:
        freq = note_to_freq(note)
        # Fundamental sine + second harmonic triangle
        fundamental = np.sin(2.0 * np.pi * freq * t)
        harmonic = 0.35 * np.sin(4.0 * np.pi * freq * t)
        sub = 0.25 * np.sin(np.pi * freq * t)
        signal += (fundamental + harmonic + sub)

    signal /= max(len(notes), 1)

    # Smooth attack and decay envelope
    env = np.ones_like(t)
    attack_samples = int(0.04 * sample_rate)
    decay_samples = int(0.05 * sample_rate)
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
    # Compute exact integer sample counts per bar without floating-point accumulation drift
    total_duration_s = (60.0 / bpm) * 64.0
    total_samples = int(total_duration_s * sample_rate)
    chords = progression * 4  # 16 chords total

    bars: List[np.ndarray] = []
    for i, chord in enumerate(chords):
        start_samp = int(i * total_samples / 16.0)
        end_samp = int((i + 1) * total_samples / 16.0)
        bar_len = end_samp - start_samp
        bars.append(_synth_chord(chord, bar_len, sample_rate))

    audio = np.concatenate(bars)

    # Seamless circular loop boundary crossfade: blend tail into head and truncate
    fade_len = int(0.05 * sample_rate)
    if len(audio) > 2 * fade_len:
        ramp = np.linspace(0.0, 1.0, fade_len)
        head = audio[:fade_len].copy()
        tail = audio[-fade_len:].copy()
        audio[:fade_len] = head * ramp + tail * (1.0 - ramp)
        audio = audio[:-fade_len]

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


def analyze_music_loop(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Dict[str, Any]:
    """Analyze quality and loop seamlessness of a musical loop buffer."""
    peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) > 0 else 0.0
    seam_discontinuity = float(abs(audio[0] - audio[-1])) if len(audio) > 1 else 0.0
    seam_ratio = seam_discontinuity / max(rms, 1e-6)
    return {
        "duration_s": round(len(audio) / sample_rate, 3),
        "sample_rate": sample_rate,
        "samples": len(audio),
        "peak": round(peak, 4),
        "rms": round(rms, 4),
        "seam_discontinuity": round(seam_discontinuity, 5),
        "seam_ratio": round(seam_ratio, 3),
        "looping_smooth": seam_ratio < 2.0 and peak <= 0.90,
    }
