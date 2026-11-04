"""Level Sequence intro cinematics generator (WI-10.5).

Generates camera spline flythroughs focusing on landmarks and goals
with audio mood progression and shot cut detection.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from ..design.gds import GameDesignSpec


def generate_intro_cinematic(
    gds: GameDesignSpec,
    focus_entity_locations: Optional[Dict[str, Tuple[float, float, float]]] = None,
) -> Dict[str, Any]:
    """Build Level Sequence definition for intro flythrough."""
    intro_spec = gds.presentation.intro
    duration_s = intro_spec.seconds if intro_spec.enabled else 8.0
    focus_kinds = intro_spec.focus or ["landmark", "goal"]

    focus_locs = focus_entity_locations or {
        "player_start": (0.0, 0.0, 100.0),
        "landmark": (2000.0, 1500.0, 400.0),
        "goal": (4000.0, 3000.0, 200.0),
    }

    # Generate keyframes along camera spline
    keyframes = []
    fps = 30
    total_frames = int(duration_s * fps)

    # Shots: map to focus_kinds dynamically
    primary_focus = focus_kinds[0] if len(focus_kinds) > 0 else "landmark"
    secondary_focus = focus_kinds[1] if len(focus_kinds) > 1 else primary_focus
    shot_segments = [
        {"name": f"Shot_01_Establishing_{primary_focus.capitalize()}", "fraction": 0.35, "focus": primary_focus},
        {"name": f"Shot_02_FocusPOI_{primary_focus.capitalize()}", "fraction": 0.35, "focus": primary_focus},
        {"name": f"Shot_03_RevealGoal_{secondary_focus.capitalize()}", "fraction": 0.30, "focus": secondary_focus},
    ]

    cuts = []
    current_frame = 0
    for shot in shot_segments:
        cuts.append(current_frame)
        shot_frames = int(shot["fraction"] * total_frames)
        target = focus_locs.get(shot["focus"], (2000.0, 2000.0, 200.0))
        for sf in range(shot_frames):
            t = sf / max(1, shot_frames - 1)
            # Smooth interpolation
            cam_x = target[0] - 1200.0 + (t * 400.0)
            cam_y = target[1] - 800.0 + (t * 300.0)
            cam_z = target[2] + 500.0 - (t * 100.0)
            keyframes.append({
                "frame": current_frame,
                "time_s": round(current_frame / fps, 3),
                "location": {"x": round(cam_x, 1), "y": round(cam_y, 1), "z": round(cam_z, 1)},
                "pitch": -15.0,
                "yaw": round(math.degrees(math.atan2(target[1] - cam_y, target[0] - cam_x)), 1),
                "roll": 0.0,
            })
            current_frame += 1

    return {
        "sequence_name": f"LS_{gds.meta.project_name}_Intro",
        "duration_seconds": round(duration_s, 2),
        "fps": fps,
        "total_frames": len(keyframes),
        "shots": [s["name"] for s in shot_segments],
        "cuts": cuts,
        "cut_count": len(cuts),
        "keyframes_count": len(keyframes),
        "audio_track": {
            "sound_cue": "/Game/GameForge/Audio/A_Music_Intro",
            "fade_in_seconds": 1.0,
            "fade_out_seconds": 1.5,
        },
        "playback_policy": {
            "play_on_game_start": True,
            "skippable": True,
            "skip_input_action": "AnyKey",
            "freeze_player_input": True,
        },
    }
