"""Procedural environmental ambience loop generator (P7 WI-7.8).

Generates ambient audio beds:
- wind: bandpass-filtered noise modulated with a slow LFO (0.1 Hz)
- forest: wind bed combined with sporadic high-frequency bird chirps
- dungeon: resonant low-frequency drone (55 Hz / 110 Hz) with random water drip impulses

Outputs 16-bit PCM WAV suitable for seamless looping in Unreal Engine.
"""
from __future__ import annotations
from typing import Any, Dict

import wave
from pathlib import Path
import numpy as np

SAMPLE_RATE = 44100


def _filtered_noise(duration_s: float, lfo_hz: float = 0.12, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n_samples = int(duration_s * sample_rate)
    noise = np.random.normal(0.0, 0.4, n_samples)

    # Slow LFO
    t = np.linspace(0.0, duration_s, n_samples, endpoint=False)
    lfo = 0.5 + 0.4 * np.sin(2.0 * np.pi * lfo_hz * t)

    # Simple lowpass filter
    filtered = np.empty_like(noise)
    acc = 0.0
    alpha = 0.08
    for i, v in enumerate(noise):
        acc += alpha * (v - acc)
        filtered[i] = acc

    return filtered * lfo


def generate_ambience_loop(
    kind: str,
    out_path: Path,
    duration_s: float = 8.0,
    sample_rate: int = SAMPLE_RATE,
    seed: int = 42,
) -> Path:
    """Generate a looping ambient sound bed (wind, forest, dungeon) as a 16-bit PCM WAV."""
    np.random.seed(seed)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_samples = int(duration_s * sample_rate)
    t = np.linspace(0.0, duration_s, n_samples, endpoint=False)

    if kind == "wind":
        audio = _filtered_noise(duration_s, lfo_hz=0.15, sample_rate=sample_rate)

    elif kind == "forest":
        wind = _filtered_noise(duration_s, lfo_hz=0.2, sample_rate=sample_rate) * 0.6
        # Add random bird chirps
        chirps = np.zeros(n_samples)
        num_chirps = int(duration_s * 1.5)
        for _ in range(num_chirps):
            start = np.random.randint(0, n_samples - int(0.2 * sample_rate))
            chirp_dur = int(np.random.uniform(0.05, 0.15) * sample_rate)
            ct = np.linspace(0.0, chirp_dur / sample_rate, chirp_dur, endpoint=False)
            freq_start = np.random.uniform(2200.0, 3200.0)
            freq_end = freq_start + np.random.uniform(-600.0, 800.0)
            inst_freq = np.linspace(freq_start, freq_end, chirp_dur)
            phase = 2.0 * np.pi * np.cumsum(inst_freq) / sample_rate
            env = np.sin(np.pi * np.linspace(0.0, 1.0, chirp_dur))
            chirps[start:start + chirp_dur] += 0.25 * np.sin(phase) * env
        audio = wind + chirps

    elif kind == "dungeon":
        # Low rumble: 55 Hz (A1) + 110 Hz (A2) + noise
        drone = 0.4 * np.sin(2.0 * np.pi * 55.0 * t) + 0.25 * np.sin(2.0 * np.pi * 110.0 * t)
        drone += 0.15 * np.sin(2.0 * np.pi * 82.4 * t)  # E2 fifth
        sub_noise = _filtered_noise(duration_s, lfo_hz=0.08, sample_rate=sample_rate) * 0.3

        # Drips: occasional resonant decay pings
        drips = np.zeros(n_samples)
        num_drips = int(duration_s * 0.8)
        for _ in range(num_drips):
            start = np.random.randint(0, n_samples - int(0.3 * sample_rate))
            drip_dur = int(0.25 * sample_rate)
            dt = np.linspace(0.0, 0.25, drip_dur, endpoint=False)
            drip_freq = np.random.choice([1200.0, 1450.0, 1800.0, 2100.0])
            decay = np.exp(-dt * 24.0)
            drips[start:start + drip_dur] += 0.3 * np.sin(2.0 * np.pi * drip_freq * dt) * decay

        audio = drone + sub_noise + drips
    elif kind == "city":
        # Distant urban traffic rumble + subtle electrical hum + sporadic horn/siren harmonic sweeps
        traffic = _filtered_noise(duration_s, lfo_hz=0.22, sample_rate=sample_rate) * 0.65
        hum = 0.12 * np.sin(2.0 * np.pi * 60.0 * t) + 0.06 * np.sin(2.0 * np.pi * 120.0 * t)
        pulses = np.zeros(n_samples)
        num_pulses = max(1, int(duration_s * 0.5))
        for _ in range(num_pulses):
            start = np.random.randint(0, max(1, n_samples - int(0.4 * sample_rate)))
            p_dur = int(0.35 * sample_rate)
            pt = np.linspace(0.0, 0.35, p_dur, endpoint=False)
            f0 = np.random.choice([380.0, 440.0, 520.0])
            env = np.sin(np.pi * np.linspace(0.0, 1.0, p_dur)) * 0.18
            pulses[start:start + p_dur] += env * (np.sin(2.0 * np.pi * f0 * pt) + 0.5 * np.sin(2.0 * np.pi * (f0 * 1.25) * pt))
        audio = traffic + hum + pulses
    else:
        audio = _filtered_noise(duration_s, sample_rate=sample_rate)

    # True seamless circular crossfade: blend tail into head and truncate overlapped tail
    fade_len = int(0.25 * sample_rate)
    if len(audio) > 2 * fade_len:
        ramp = np.linspace(0.0, 1.0, fade_len)
        head = audio[:fade_len].copy()
        tail = audio[-fade_len:].copy()
        audio[:fade_len] = head * ramp + tail * (1.0 - ramp)
        audio = audio[:-fade_len]

    # Normalize with headroom
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = (audio / peak) * 0.82

    pcm16 = (audio * 32767.0).astype(np.int16)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())

    return out_path


def analyze_ambience_loop(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Dict[str, Any]:
    """Analyze quality and loop seamlessness of an ambient audio buffer."""
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
        "looping_smooth": seam_ratio < 2.0 and peak <= 0.98,
    }
