"""Composer content resolution (WI-6.7).

Handles minimal VFX and procedural SFX content requests for presets.
"""
from __future__ import annotations

from typing import Any, Dict, List
from .model import OpCall


VFX_PRESET_MAP: Dict[str, str] = {
    "vfx.burst": "/Game/GameForge/VFX/NS_Burst",
    "vfx.sparkle": "/Game/GameForge/VFX/NS_Sparkle",
    "vfx.explosion": "/Game/GameForge/VFX/NS_Explosion",
    "vfx.slash": "/Game/GameForge/VFX/NS_Slash",
}

SFX_PRESET_MAP: Dict[str, str] = {
    "sfx.pickup": "/Game/GameForge/Audio/A_Pickup",
    "sfx.hit": "/Game/GameForge/Audio/A_Hit",
    "sfx.win": "/Game/GameForge/Audio/A_Win",
    "sfx.lose": "/Game/GameForge/Audio/A_Lose",
}


def resolve_vfx_path(preset_id: str) -> str:
    return VFX_PRESET_MAP.get(preset_id, f"/Game/GameForge/VFX/{preset_id.replace('.', '_')}")


def resolve_sfx_path(preset_id: str) -> str:
    return SFX_PRESET_MAP.get(preset_id, f"/Game/GameForge/Audio/{preset_id.replace('.', '_')}")


def plan_content_ops(content_requests: List[Dict[str, Any]]) -> List[OpCall]:
    """Generate content preparation ops for requested VFX/SFX."""
    ops: List[OpCall] = []
    # In P6, assets are generated/linked as needed
    return ops
