"""Niagara VFX system presets and parameter overrides (P7 WI-7.8).

Defines standard visual effect presets with template paths, Niagara user parameter
names, and default values matching game events (pickup, impact, defeat, magic, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class VFXPreset:
    preset_id: str
    template_path: str
    description: str
    user_parameters: Dict[str, Any] = field(default_factory=dict)
    event_triggers: List[str] = field(default_factory=list)

    def resolve_parameters(self, palette_accent: Optional[Tuple[float, float, float]] = None) -> Dict[str, Any]:
        """Return parameters with optional theme accent colour override."""
        params = dict(self.user_parameters)
        if palette_accent and "User.Color" in params:
            params["User.Color"] = [palette_accent[0], palette_accent[1], palette_accent[2], 1.0]
        return params


VFX_PRESETS: Dict[str, VFXPreset] = {
    # 1. Sparkle Burst
    "vfx.sparkle_burst": VFXPreset(
        preset_id="vfx.sparkle_burst",
        template_path="/Game/GameForge/VFX/NS_Sparkle",
        description="Burst of bright glittering stars",
        user_parameters={
            "User.Color": [1.0, 0.85, 0.2, 1.0],
            "User.SpawnCount": 35,
            "User.Lifetime": 0.8,
            "User.Radius": 60.0,
        },
        event_triggers=["pickup.collected", "objective.completed"],
    ),

    # 2. Hit Flash
    "vfx.hit_flash": VFXPreset(
        preset_id="vfx.hit_flash",
        template_path="/Game/GameForge/VFX/NS_HitFlash",
        description="High-energy impact flash with sparks",
        user_parameters={
            "User.Color": [1.0, 0.3, 0.1, 1.0],
            "User.SpawnCount": 20,
            "User.Lifetime": 0.35,
            "User.Radius": 40.0,
        },
        event_triggers=["player.damaged", "enemy.damaged"],
    ),

    # 3. Poof
    "vfx.poof": VFXPreset(
        preset_id="vfx.poof",
        template_path="/Game/GameForge/VFX/NS_Poof",
        description="Soft cloud puff for vanishing entities",
        user_parameters={
            "User.Color": [0.85, 0.85, 0.9, 0.8],
            "User.SpawnCount": 25,
            "User.Lifetime": 0.6,
            "User.Radius": 50.0,
        },
        event_triggers=["enemy.killed", "actor.destroyed"],
    ),

    # 4. Confetti
    "vfx.confetti": VFXPreset(
        preset_id="vfx.confetti",
        template_path="/Game/GameForge/VFX/NS_Confetti",
        description="Celebratory multi-colour shower",
        user_parameters={
            "User.Color": [0.2, 0.8, 1.0, 1.0],
            "User.SpawnCount": 80,
            "User.Lifetime": 2.5,
            "User.Radius": 150.0,
        },
        event_triggers=["game.won", "level.completed"],
    ),

    # 5. Ring
    "vfx.ring": VFXPreset(
        preset_id="vfx.ring",
        template_path="/Game/GameForge/VFX/NS_Ring",
        description="Expanding horizontal energy wave ring",
        user_parameters={
            "User.Color": [0.3, 0.9, 0.4, 1.0],
            "User.SpawnCount": 1,
            "User.Lifetime": 0.75,
            "User.Radius": 200.0,
        },
        event_triggers=["checkpoint.reached", "switch.toggled"],
    ),

    # 6. Fire
    "vfx.fire": VFXPreset(
        preset_id="vfx.fire",
        template_path="/Game/GameForge/VFX/NS_Fire",
        description="Flickering flame column with embers",
        user_parameters={
            "User.Color": [1.0, 0.45, 0.05, 1.0],
            "User.SpawnCount": 40,
            "User.Lifetime": 1.2,
            "User.Radius": 30.0,
        },
        event_triggers=["hazard.active", "torch.lit"],
    ),

    # 7. Smoke
    "vfx.smoke": VFXPreset(
        preset_id="vfx.smoke",
        template_path="/Game/GameForge/VFX/NS_Smoke",
        description="Rising billowing dark smoke",
        user_parameters={
            "User.Color": [0.25, 0.25, 0.28, 0.6],
            "User.SpawnCount": 30,
            "User.Lifetime": 2.0,
            "User.Radius": 45.0,
        },
        event_triggers=["hazard.smoke", "explosion.impact"],
    ),

    # 8. Magic Trail
    "vfx.magic_trail": VFXPreset(
        preset_id="vfx.magic_trail",
        template_path="/Game/GameForge/VFX/NS_MagicTrail",
        description="Ethereal particle ribbon following moving actors",
        user_parameters={
            "User.Color": [0.75, 0.25, 0.95, 1.0],
            "User.SpawnCount": 50,
            "User.Lifetime": 1.0,
            "User.Radius": 20.0,
        },
        event_triggers=["projectile.spawned", "spell.cast"],
    ),
}


def get_vfx_preset(preset_id: str) -> Optional[VFXPreset]:
    """Retrieve a VFXPreset by ID."""
    return VFX_PRESETS.get(preset_id)
