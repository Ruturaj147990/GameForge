"""Procedural sound-effect synthesizer (roadmap M14 step 1). Provenance class: ``procedural``.

Seeded numpy synthesis of short game SFX written as 16-bit PCM WAV (the format Unreal imports as USoundWave):
click, whoosh, impact, pickup chime and a seamlessly looping ambient wind bed. ``analyze_wav`` re-reads a file
and reports duration, peak, RMS, clipping and (for loops) the seam discontinuity.
"""

from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

GENERATOR = "GameForge-ProceduralSFX-V1"
SAMPLE_RATE = 44100
KINDS = ("click", "whoosh", "impact", "pickup", "wind_loop")


@dataclass
class SFXSpec:
    name: str
    kind: str
    seed: int = 0
    duration_s: float = 0.0  # 0 = the kind's default
    gain: float = 0.8

    def validate(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError("name must be non-empty alphanumeric/underscore")
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if not 0.0 < self.gain <= 0.98:
            raise ValueError("gain must be in (0, 0.98] to leave headroom")
        if self.duration_s < 0 or self.duration_s > 30:
            raise ValueError("duration_s must be within 0..30 s")


_DEFAULT_DURATION = {"click": 0.04, "whoosh": 0.6, "impact": 0.5, "pickup": 0.35, "wind_loop": 4.0}


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n, endpoint=False)
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    r = np.clip((1.0 - t) / max(release, 1e-6), 0, 1)
    return a * r


def _lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    """One-pole low-pass, alpha in (0, 1]; smaller = darker."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def synthesize(spec: SFXSpec) -> np.ndarray:
    spec.validate()
    rng = np.random.default_rng(spec.seed)
    dur = spec.duration_s or _DEFAULT_DURATION[spec.kind]
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    if spec.kind == "click":
        x = rng.uniform(-1, 1, n) * np.exp(-t * 180.0) + 0.6 * np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 120.0)
    elif spec.kind == "whoosh":
        noise = rng.uniform(-1, 1, n)
        sweep = np.linspace(0.02, 0.35, n) ** 1.5  # opening filter
        x = np.zeros(n)
        acc = 0.0
        for i in range(n):
            acc += sweep[i] * (noise[i] - acc)
            x[i] = acc
        x *= np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    elif spec.kind == "impact":
        thump = np.sin(2 * np.pi * (90 - 50 * t / dur) * t) * np.exp(-t * 9.0)
        crack = _lowpass(rng.uniform(-1, 1, n), 0.5) * np.exp(-t * 40.0)
        x = thump + 0.5 * crack
    elif spec.kind == "pickup":
        half = n // 2
        tone = np.where(np.arange(n) < half, np.sin(2 * np.pi * 988 * t), np.sin(2 * np.pi * 1319 * t))
        x = tone * _env(n, 0.02, 0.5) + 0.25 * np.sin(2 * np.pi * 2637 * t) * _env(n, 0.02, 0.3)
    else:  # wind_loop: filtered noise whose slow gust LFO completes whole cycles, crossfaded at the seam
        noise = _lowpass(rng.uniform(-1, 1, n), 0.04)
        gust = 0.6 + 0.4 * np.sin(2 * np.pi * 2 * np.arange(n) / n)
        x = noise * gust
        fade = int(0.25 * SAMPLE_RATE)
        ramp = np.linspace(0.0, 1.0, fade)
        head, tail = x[:fade].copy(), x[-fade:].copy()
        x[:fade] = head * ramp + tail * (1.0 - ramp)
        x = x[:-fade] if n - fade > fade else x
    peak = float(np.max(np.abs(x))) or 1.0
    return x / peak * spec.gain


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def analyze_wav(path: str | Path, loop: bool = False) -> dict:
    with wave.open(str(path), "rb") as w:
        rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        data = np.frombuffer(w.readframes(frames), dtype="<i2").astype(np.float64) / 32768.0
    out = {"sample_rate": rate, "channels": channels, "bits": width * 8, "duration_s": round(frames / rate, 4),
           "peak": round(float(np.max(np.abs(data))), 4) if frames else 0.0,
           "rms": round(float(np.sqrt(np.mean(data ** 2))), 4) if frames else 0.0,
           "clipped_samples": int(np.sum(np.abs(data) >= 0.9999))}
    if loop and frames > 2:
        typical = float(np.mean(np.abs(np.diff(data)))) or 1e-9
        out["loop_seam_ratio"] = round(abs(float(data[0] - data[-1])) / typical, 3)
    return out


def generate_sfx(spec: SFXSpec, output_dir: str | Path, asset_registry=None) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"SFX_{spec.name}.wav"
    write_wav(path, synthesize(spec))
    info = {"name": spec.name, "kind": spec.kind, "generator": GENERATOR, "provenance": "procedural",
            "license": "CC0-1.0", "spec": asdict(spec), "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "analysis": analyze_wav(path, loop=spec.kind == "wind_loop"), "looping": spec.kind == "wind_loop"}
    if asset_registry is not None:
        from ...backend.assets.registry import AssetRecord
        rid = asset_registry.register(AssetRecord(name=f"SFX_{spec.name}", asset_type="sound", purpose=f"{spec.kind} SFX",
                                                  provenance="procedural", backend=GENERATOR, backend_version="1.0.0",
                                                  license="CC0-1.0", spec=asdict(spec), tags=[spec.kind]))
        asset_registry.advance(rid, "SPEC", True, "spec validated")
        asset_registry.advance(rid, "GENERATE", True, artifact_path=str(path))
        info["registry_id"] = rid
    (out / f"SFX_{spec.name}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info
