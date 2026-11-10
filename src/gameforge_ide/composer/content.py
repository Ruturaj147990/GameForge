"""Composer content resolution (WI-6.7).

Handles unified VFX and procedural SFX content resolution and OpCall planning.
"""
from __future__ import annotations

from typing import Any, Dict, List
from .model import OpCall
from ..content.vfx_presets import VFX_PRESETS, get_vfx_preset


VFX_PRESET_MAP: Dict[str, str] = {
    "vfx.burst": "/Game/GameForge/VFX/NS_Burst",
    "vfx.sparkle": "/Game/GameForge/VFX/NS_Sparkle",
    "vfx.sparkle_burst": "/Game/GameForge/VFX/NS_Sparkle",
    "vfx.hit_flash": "/Game/GameForge/VFX/NS_HitFlash",
    "vfx.poof": "/Game/GameForge/VFX/NS_Poof",
    "vfx.confetti": "/Game/GameForge/VFX/NS_Confetti",
    "vfx.ring": "/Game/GameForge/VFX/NS_Ring",
    "vfx.fire": "/Game/GameForge/VFX/NS_Fire",
    "vfx.smoke": "/Game/GameForge/VFX/NS_Smoke",
    "vfx.magic_trail": "/Game/GameForge/VFX/NS_MagicTrail",
    "vfx.explosion": "/Game/GameForge/VFX/NS_Explosion",
    "vfx.slash": "/Game/GameForge/VFX/NS_Slash",
    "vfx.shield_hit": "/Game/GameForge/VFX/NS_HitFlash",
    "vfx.boost": "/Game/GameForge/VFX/NS_Ring",
    "vfx.ability_activate": "/Game/GameForge/VFX/NS_Burst",
    "vfx.stealth_cloak": "/Game/GameForge/VFX/NS_Smoke",
    "vfx.boss_enrage": "/Game/GameForge/VFX/NS_Fire",
    "vfx.portal_warp": "/Game/GameForge/VFX/NS_Ring",
    "vfx.dash": "/Game/GameForge/VFX/NS_MagicTrail",
    "vfx.loot_drop": "/Game/GameForge/VFX/NS_Sparkle",
}

SFX_PRESET_MAP: Dict[str, str] = {
    "sfx.pickup": "/Game/GameForge/SFX/S_PickupChime",
    "sfx.pickup_chime": "/Game/GameForge/SFX/S_PickupChime",
    "sfx.hit": "/Game/GameForge/SFX/S_Impact",
    "sfx.impact": "/Game/GameForge/SFX/S_Impact",
    "sfx.win": "/Game/GameForge/SFX/S_Fanfare",
    "sfx.fanfare": "/Game/GameForge/SFX/S_Fanfare",
    "sfx.lose": "/Game/GameForge/SFX/S_Defeat",
    "sfx.defeat": "/Game/GameForge/SFX/S_Defeat",
    "sfx.chime_low": "/Game/GameForge/SFX/S_ChimeLow",
    "sfx.ui_click": "/Game/GameForge/SFX/S_UiClick",
    "sfx.footstep_soft": "/Game/GameForge/SFX/S_FootstepSoft",
    "sfx.laser": "/Game/GameForge/SFX/S_Impact",
    "sfx.explosion": "/Game/GameForge/SFX/S_Defeat",
    "sfx.switch": "/Game/GameForge/SFX/S_ChimeLow",
    "sfx.ability_ready": "/Game/GameForge/SFX/S_ChimeLow",
    "sfx.stealth_enter": "/Game/GameForge/SFX/S_FootstepSoft",
    "sfx.boss_roar": "/Game/GameForge/SFX/S_Defeat",
    "sfx.weapon_shoot": "/Game/GameForge/SFX/S_Impact",
    "sfx.dash": "/Game/GameForge/SFX/S_FootstepSoft",
    "sfx.gate_unlock": "/Game/GameForge/SFX/S_Fanfare",
}


def resolve_vfx_path(preset_id: str) -> str:
    if not preset_id or preset_id.startswith("/"):
        return preset_id
    preset = get_vfx_preset(preset_id)
    if preset is not None:
        return preset.target_asset_path or preset.template_path
    if preset_id in VFX_PRESET_MAP:
        return VFX_PRESET_MAP[preset_id]
    suffix = preset_id.split(".", 1)[-1].title().replace("_", "")
    return f"/Game/GameForge/VFX/NS_{suffix}"


def resolve_sfx_path(preset_id: str) -> str:
    if not preset_id or preset_id.startswith("/"):
        return preset_id
    if preset_id in SFX_PRESET_MAP:
        return SFX_PRESET_MAP[preset_id]
    suffix = preset_id.split(".", 1)[-1].title().replace("_", "")
    return f"/Game/GameForge/SFX/S_{suffix}"


def plan_content_ops(content_requests: Any) -> List[OpCall]:
    """Generate content preparation ops for requested VFX/SFX from either a list of requests or a GDS."""
    ops: List[OpCall] = []
    seen_assets = set()

    requests: List[Dict[str, Any]] = []
    if hasattr(content_requests, "feedback"):
        for fb in getattr(content_requests, "feedback", []) or []:
            if getattr(fb, "vfx", None):
                requests.append({"kind": "vfx", "preset": fb.vfx})
            if getattr(fb, "sfx", None):
                requests.append({"kind": "sfx", "preset": fb.sfx})
    elif isinstance(content_requests, list):
        requests = [r for r in content_requests if isinstance(r, dict)]

    for req in requests:
        kind = str(req.get("kind", "")).lower()
        preset_id = str(req.get("preset", "")).strip()
        if not preset_id:
            continue
        if kind == "vfx" or preset_id.startswith("vfx."):
            asset_path = resolve_vfx_path(preset_id)
            if asset_path in seen_assets:
                continue
            seen_assets.add(asset_path)
            vfx_preset = get_vfx_preset(preset_id)
            if vfx_preset is not None:
                args = vfx_preset.to_create_args(asset_path=asset_path)
            else:
                args = {
                    "asset_path": asset_path,
                    "template_system": "RadialBurst",
                    "template_emitters": ["OmnidirectionalBurst"],
                }
            ops.append(OpCall(op="vfx_create_system", args=args, purpose=f"Create Niagara VFX system for {preset_id}"))
        elif (kind == "sfx" or preset_id.startswith("sfx.")) and req.get("source_wav"):
            asset_path = resolve_sfx_path(preset_id)
            if asset_path in seen_assets:
                continue
            seen_assets.add(asset_path)
            ops.append(
                OpCall(
                    op="import_sound",
                    args={
                        "source_wav": str(req["source_wav"]),
                        "destination_path": asset_path,
                    },
                    purpose=f"Import procedural WAV for {preset_id}",
                )
            )

    return ops
