"""Niagara VFX system presets and parameter overrides (P7 WI-7.8).

Defines standard visual effect presets with template paths, Niagara user parameter
names, and default values matching game events (pickup, impact, defeat, magic, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


VALID_TEMPLATE_SYSTEMS = (
    "AttributeReaderTrails",
    "DirectionalBurst",
    "DirectionalBurstLightweight",
    "FountainLightweight",
    "MinimalLightweight",
    "RadialBurst",
    "SimpleExplosion",
)

VALID_TEMPLATE_EMITTERS = (
    "BlowingParticles",
    "ConfettiBurst",
    "DirectionalBurst",
    "DynamicBeam",
    "Fountain",
    "HangingParticulates",
    "LocationBasedRibbon",
    "Minimal",
    "OmnidirectionalBurst",
    "RecycleParticlesInView",
    "SimpleSpriteBurst",
    "SingleLoopingParticle",
    "StaticBeam",
    "UpwardMeshBurst",
)


@dataclass
class VFXPreset:
    preset_id: str
    template_path: str
    description: str
    template_system: str = "RadialBurst"
    template_emitters: List[str] = field(default_factory=list)
    target_asset_path: str = ""
    user_parameters: Dict[str, Any] = field(default_factory=dict)
    event_triggers: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.target_asset_path and self.template_path:
            self.target_asset_path = self.template_path
        if not self.template_path and self.target_asset_path:
            self.template_path = self.target_asset_path
        self.validate()

    def validate(self) -> None:
        """Validate template system and emitters against valid UE 5.7 Niagara assets."""
        if not self.preset_id:
            raise ValueError("VFXPreset preset_id must be non-empty")
        if self.template_system and self.template_system not in VALID_TEMPLATE_SYSTEMS:
            raise ValueError(
                f"Invalid template_system: {self.template_system!r}. "
                f"Valid engine systems: {VALID_TEMPLATE_SYSTEMS}"
            )
        for emitter in self.template_emitters:
            if emitter not in VALID_TEMPLATE_EMITTERS:
                raise ValueError(
                    f"Invalid template_emitter: {emitter!r}. "
                    f"Valid engine emitters: {VALID_TEMPLATE_EMITTERS}"
                )

    def to_create_args(self, asset_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate schema-compliant argument payload for vfx_create_system op."""
        self.validate()
        args: Dict[str, Any] = {
            "asset_path": asset_path or self.target_asset_path or self.template_path,
        }
        if self.template_system:
            args["template_system"] = self.template_system
        if self.template_emitters:
            args["template_emitters"] = list(self.template_emitters)
        return args

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
        template_system="RadialBurst",
        template_emitters=["OmnidirectionalBurst"],
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
        template_system="SimpleExplosion",
        template_emitters=["DirectionalBurst"],
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
        template_system="RadialBurst",
        template_emitters=["Minimal"],
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
        template_system="FountainLightweight",
        template_emitters=["ConfettiBurst"],
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
        template_system="RadialBurst",
        template_emitters=["OmnidirectionalBurst"],
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
        template_system="FountainLightweight",
        template_emitters=["Fountain"],
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
        template_system="FountainLightweight",
        template_emitters=["BlowingParticles"],
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
        template_system="AttributeReaderTrails",
        template_emitters=["LocationBasedRibbon"],
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
