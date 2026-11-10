"""Level Sequence intro cinematics generator (WI-10.5).

Generates camera spline flythroughs focusing on landmarks, goals, and key POIs
with audio mood progression and shot cut detection.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from ..design.gds import GameDesignSpec


def generate_intro_cinematic(
    gds: GameDesignSpec,
    focus_entity_locations: Optional[Dict[str, Tuple[float, float, float]]] = None,
) -> Dict[str, Any]:
    """Build Level Sequence definition for intro flythrough."""
    intro_spec = gds.presentation.intro
    duration_s = float(intro_spec.seconds) if intro_spec.enabled else 8.0
    focus_kinds = intro_spec.focus or ["landmark", "goal"]

    default_locs: Dict[str, Tuple[float, float, float]] = {
        "player_start": (0.0, 0.0, 100.0),
        "landmark": (2000.0, 1500.0, 400.0),
        "goal": (4000.0, 3000.0, 200.0),
    }
    if hasattr(gds, "entities"):
        for ent in gds.entities:
            pts = getattr(getattr(ent, "placement", None), "points_m", None)
            if pts:
                p0 = pts[0]
                default_locs[str(getattr(ent.kind, "value", ent.kind))] = (
                    float(p0.x) * 100.0,
                    float(p0.y) * 100.0,
                    float(p0.z) * 100.0 + 100.0,
                )

    focus_locs = {**default_locs, **(focus_entity_locations or {})}

    keyframes = []
    fps = 30
    total_frames = max(30, int(duration_s * fps))

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
        shot_frames = max(2, int(shot["fraction"] * total_frames))
        target = focus_locs.get(shot["focus"], (2000.0, 2000.0, 200.0))
        for sf in range(shot_frames):
            t = sf / max(1, shot_frames - 1)
            # Smooth curved orbit dolly around focus POI
            angle = (t - 0.5) * 0.8  # sweep orbit
            radius = 1400.0 - (t * 200.0)
            cam_x = target[0] + radius * math.cos(angle + math.pi * 0.75)
            cam_y = target[1] + radius * math.sin(angle + math.pi * 0.75)
            cam_z = target[2] + 450.0 - (t * 120.0)
            
            dx = target[0] - cam_x
            dy = target[1] - cam_y
            dz = target[2] - cam_z
            horiz_dist = max(1.0, math.hypot(dx, dy))
            
            yaw = round(math.degrees(math.atan2(dy, dx)), 1)
            pitch = round(math.degrees(math.atan2(dz, horiz_dist)), 1)
            fov = round(70.0 - (t * 15.0), 1)  # cinematic subtle zoom-in

            keyframes.append({
                "frame": current_frame,
                "time_s": round(current_frame / fps, 3),
                "location": {"x": round(cam_x, 1), "y": round(cam_y, 1), "z": round(cam_z, 1)},
                "pitch": pitch,
                "yaw": yaw,
                "roll": 0.0,
                "fov": fov,
            })
            current_frame += 1

    # Extract audio mood if configured
    music_track = "/Game/GameForge/Audio/A_Music_Intro"
    if hasattr(gds.presentation, "audio") and getattr(gds.presentation.audio, "music_theme", None):
        music_theme = gds.presentation.audio.music_theme.lower()
        music_track = f"/Game/GameForge/Audio/Music/A_Music_{music_theme.capitalize()}"

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
            "sound_cue": music_track,
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
