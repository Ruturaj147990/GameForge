"""SFX sound effect presets and synthesis parameters (P7 WI-7.8).

Defines parameter presets per event (pickup_chime, impact, defeat, fanfare, chime_low,
ui_click, footstep_soft) across three sound styling sets (default, retro, soft).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..backend.tools.sfx_synth import SFXSpec, synthesize, write_wav


@dataclass
class SFXPreset:
    preset_id: str
    kind: str
    gain: float = 0.8
    duration_s: float = 0.0
    description: str = ""


# Sound styles: default, retro, soft
SFX_SETS: Dict[str, Dict[str, SFXPreset]] = {
    "default": {
        "pickup_chime": SFXPreset("pickup_chime", "pickup", gain=0.85, duration_s=0.35, description="Bright ascending chime"),
        "impact": SFXPreset("impact", "impact", gain=0.80, duration_s=0.45, description="Thudding physical impact"),
        "defeat": SFXPreset("defeat", "impact", gain=0.90, duration_s=0.90, description="Dissonant low fall"),
        "fanfare": SFXPreset("fanfare", "pickup", gain=0.90, duration_s=1.20, description="Triumphant high sequence"),
        "chime_low": SFXPreset("chime_low", "pickup", gain=0.75, duration_s=0.50, description="Subtle warm notification"),
        "ui_click": SFXPreset("ui_click", "click", gain=0.70, duration_s=0.04, description="Crisp mechanical button click"),
        "footstep_soft": SFXPreset("footstep_soft", "impact", gain=0.40, duration_s=0.12, description="Soft footfall tap"),
        "laser": SFXPreset("laser", "whoosh", gain=0.80, duration_s=0.22, description="High-energy sci-fi laser zap"),
        "explosion": SFXPreset("explosion", "impact", gain=0.92, duration_s=0.75, description="Deep concussive blast"),
        "switch": SFXPreset("switch", "click", gain=0.78, duration_s=0.14, description="Mechanical latch switch activation"),
    },
    "retro": {
        "pickup_chime": SFXPreset("pickup_chime", "pickup", gain=0.80, duration_s=0.25, description="8-bit arpeggio burst"),
        "impact": SFXPreset("impact", "impact", gain=0.85, duration_s=0.30, description="Square wave noise thud"),
        "defeat": SFXPreset("defeat", "impact", gain=0.85, duration_s=0.70, description="Descending retro pitch slide"),
        "fanfare": SFXPreset("fanfare", "pickup", gain=0.85, duration_s=1.00, description="8-bit celebratory victory chime"),
        "chime_low": SFXPreset("chime_low", "click", gain=0.70, duration_s=0.15, description="Low retro blip"),
        "ui_click": SFXPreset("ui_click", "click", gain=0.75, duration_s=0.03, description="Chiptune tick"),
        "footstep_soft": SFXPreset("footstep_soft", "click", gain=0.35, duration_s=0.08, description="Light chiptune tap"),
        "laser": SFXPreset("laser", "pickup", gain=0.78, duration_s=0.18, description="8-bit pew laser pulse"),
        "explosion": SFXPreset("explosion", "impact", gain=0.88, duration_s=0.60, description="Retro noise rumble blast"),
        "switch": SFXPreset("switch", "click", gain=0.75, duration_s=0.10, description="Retro toggle beep"),
    },
    "soft": {
        "pickup_chime": SFXPreset("pickup_chime", "pickup", gain=0.60, duration_s=0.40, description="Soft mellow bell ring"),
        "impact": SFXPreset("impact", "whoosh", gain=0.55, duration_s=0.35, description="Muffled air pulse"),
        "defeat": SFXPreset("defeat", "whoosh", gain=0.65, duration_s=0.80, description="Fading wind descent"),
        "fanfare": SFXPreset("fanfare", "pickup", gain=0.70, duration_s=1.10, description="Gentle warm chord bloom"),
        "chime_low": SFXPreset("chime_low", "pickup", gain=0.50, duration_s=0.60, description="Distant resonance"),
        "ui_click": SFXPreset("ui_click", "click", gain=0.50, duration_s=0.03, description="Gentle woodblock click"),
        "footstep_soft": SFXPreset("footstep_soft", "whoosh", gain=0.30, duration_s=0.10, description="Whisper step"),
        "laser": SFXPreset("laser", "whoosh", gain=0.58, duration_s=0.25, description="Soft harmonic energy pulse"),
        "explosion": SFXPreset("explosion", "whoosh", gain=0.68, duration_s=0.65, description="Warm low-end swell"),
        "switch": SFXPreset("switch", "click", gain=0.55, duration_s=0.12, description="Muted wooden toggle click"),
    },
}


def synthesize_sfx_preset(
    preset_name: str,
    out_path: Path,
    style: str = "default",
    seed: int = 42,
    sample_rate: int = 44100,
) -> Path:
    """Synthesize a named SFX preset to a 16-bit PCM WAV file with sample-rate support."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sfx_set = SFX_SETS.get(style, SFX_SETS["default"])
    preset = sfx_set.get(preset_name, sfx_set["pickup_chime"])

    spec = SFXSpec(
        name=preset_name,
        kind=preset.kind,
        seed=seed,
        duration_s=preset.duration_s,
        gain=preset.gain,
    )
    samples = synthesize(spec)

    # If requested sample rate differs from synth native 44.1kHz, resample cleanly
    if sample_rate != 44100 and len(samples) > 1:
        import numpy as np
        num_target = int(len(samples) * sample_rate / 44100)
        orig_indices = np.linspace(0.0, 1.0, len(samples), endpoint=False)
        target_indices = np.linspace(0.0, 1.0, num_target, endpoint=False)
        samples = np.interp(target_indices, orig_indices, samples)

    import numpy as np
    import wave
    pcm = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())

    return out_path


def get_sfx_preset(preset_name: str, style: str = "default") -> Optional[SFXPreset]:
    """Retrieve an SFXPreset definition by name and style."""
    sfx_set = SFX_SETS.get(style, SFX_SETS["default"])
    return sfx_set.get(preset_name)


def list_sfx_presets(style: str = "default") -> List[str]:
    """List all available preset names for a given style."""
    sfx_set = SFX_SETS.get(style, SFX_SETS["default"])
    return list(sfx_set.keys())
