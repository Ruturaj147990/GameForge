"""GameForge Runtime Definition (gfdef/1) builder and validator (WI-5.1).

Transforms typed GameDesignSpec into gfdef/1 JSON contract for GameForgeRuntime.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.gameforge_ide.design.gds import GameDesignSpec
from .registry import get_module


def build_runtime_def(gds: GameDesignSpec, seed: int = 2026) -> Dict[str, Any]:
    """Generate gfdef/1 dictionary from GameDesignSpec."""
    from src.gameforge_ide.design.gds import EntityKind

    # Player settings (WI-7.2: mesh, anim_class, material_tint)
    player_data = {
        "camera": gds.overview.camera.value if hasattr(gds.overview.camera, "value") else str(gds.overview.camera),
        "move_speed": 600.0,
        "jump_velocity": 650.0,
        "max_health": 100.0,
        "lives": 0,
        "kill_z": -2000.0,
        "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
        "anim_class": "/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C",
        "material_tint": [1.0, 1.0, 1.0, 1.0],
    }

    # Populate customized player props if defined on player entity
    player_ent = next((e for e in gds.entities if getattr(e, "kind", None) == EntityKind.PLAYER), None)
    if player_ent and getattr(player_ent, "props", None):
        p_props = player_ent.props if isinstance(player_ent.props, dict) else player_ent.props.model_dump()
        for k, v in p_props.items():
            if k in ("move_speed", "jump_velocity", "max_health", "lives", "kill_z", "attack_damage", "attack_mode", "weapons", "projectile_speed"):
                player_data[k] = v

    camera_str = str(player_data.get("camera", "")).lower()
    genre_str = str(getattr(gds.overview, "genre", "")).lower()
    if "first_person" in camera_str or "shooter" in genre_str or "arena" in genre_str:
        player_data.setdefault("attack_mode", "projectile")
        player_data.setdefault("projectile_speed", 2500.0)
        player_data.setdefault("attack_damage", 35.0)

    # Enhanced input default mapping
    input_bindings = [
        {
            "action": "IA_Move",
            "type": "axis2d",
            "bindings": [
                {"key": "W", "mods": ["swizzle"]},
                {"key": "S", "mods": ["swizzle", "negate"]},
                {"key": "D", "mods": []},
                {"key": "A", "mods": ["negate"]},
            ],
        },
        {
            "action": "IA_Look",
            "type": "axis2d",
            "bindings": [{"key": "MouseXY", "mods": []}],
        },
        {
            "action": "IA_Jump",
            "type": "digital",
            "bindings": [{"key": "SpaceBar", "mods": []}],
        },
        {
            "action": "IA_Interact",
            "type": "digital",
            "bindings": [{"key": "E", "mods": []}],
        },
        {
            "action": "IA_Attack",
            "type": "digital",
            "bindings": [{"key": "LeftMouseButton", "mods": []}],
        },
        {
            "action": "IA_Fire",
            "type": "digital",
            "bindings": [{"key": "LeftMouseButton", "mods": []}],
        },
    ]

    # Stats
    player_max_health = float(player_data.get("max_health", 100.0))
    stats_data: Dict[str, Any] = {
        "player.health": {"initial": player_max_health, "min": 0.0, "max": player_max_health},
        "game.score": {"initial": 0.0},
    }

    from ..design.gds import EntityKind
    for ent in gds.entities:
        kind_val = ent.kind.value if hasattr(ent.kind, "value") else str(ent.kind).lower()
        if kind_val in ("enemy", "ranged_enemy", "guard"):
            count = getattr(ent, "count", None)
            if count is None and hasattr(ent, "props") and isinstance(ent.props, dict):
                count = ent.props.get("count", 1)
            cnt = float(count if count is not None else 1)
            placed_count = 0
            if hasattr(gds, "scene") and gds.scene and getattr(gds.scene, "levels", None):
                for lvl in gds.scene.levels:
                    for pl in getattr(lvl, "placements", []):
                        if pl.entity_id == ent.entity_id:
                            placed_count += 1
            effective_count = float(placed_count if placed_count > 0 else cnt)
            stats_data[f"entity.{ent.entity_id}.remaining"] = {
                "initial": effective_count,
                "min": 0.0,
            }

    # Entities
    entities_data: Dict[str, Any] = {}
    for ent in gds.entities:
        mod_cls = "/Script/GameForgeRuntime.GameForgePickup"
        try:
            m = get_module(ent.module)
            mod_cls = m.runtime_class
        except KeyError:
            pass

        # Visual settings for kit pawns (WI-7.2)
        visual_data = {}
        is_humanoid = any(k in ent.entity_id.lower() or k in ent.module.lower()
                          for k in ("enemy", "guard", "npc", "quest_giver", "hermit", "character"))
        if is_humanoid:
            visual_data = {
                "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple",
                "anim_class": "/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C",
                "material_tint": [0.8, 0.2, 0.2, 1.0] if "enemy" in ent.entity_id.lower() or "guard" in ent.entity_id.lower() else [0.2, 0.5, 0.9, 1.0],
            }

        entities_data[ent.entity_id] = {
            "class": mod_cls,
            "spawn_tag": f"GF_SP_{ent.entity_id}",
            "count": ent.count,
            "properties": dict(ent.props),
            "visual": visual_data,
        }

    # Rules
    rules_data: List[Dict[str, Any]] = []
    for r in gds.rules:
        when_data = {
            "e": r.when.event,
            "ent": r.when.source if r.when.source else None,
        }
        if_data = [c.model_dump(exclude_none=True) for c in r.conditions]
        do_data = [e.model_dump(exclude_none=True) for e in r.effects]

        rules_data.append({
            "id": getattr(r, "rule_id", getattr(r, "id", f"rule_{len(rules_data)}")),
            "when": when_data,
            "if": if_data,
            "do": do_data,
        })

    # Win & Lose
    win_data = [c.model_dump(exclude_none=True) for c in gds.goals.win]
    lose_data = [c.model_dump(exclude_none=True) for c in gds.goals.lose]

    # Feedback
    feedback_data: List[Dict[str, Any]] = []
    for fb in gds.feedback:
        evt = fb.on.event if hasattr(fb, "on") else getattr(fb, "trigger", None)
        feedback_data.append({
            "e": evt,
            "vfx": fb.vfx,
            "sfx": fb.sfx,
            "shake": fb.camera_shake,
            "msg": fb.ui_message,
        })

    # Default feedback if empty
    if not feedback_data:
        feedback_data.append({
            "e": "pickup.collected",
            "vfx": "/Game/GameForge/VFX/NS_Sparkle",
            "sfx": "/Game/GameForge/SFX/S_Chime",
            "shake": 0.0,
            "msg": None,
        })

    # HUD Elements
    hud_data: List[Dict[str, Any]] = []
    for elem in gds.ui.hud:
        hud_data.append({
            "id": elem.element_id,
            "kind": elem.kind,
            "stat": elem.binds,
            "label": elem.label,
        })

    # Menus
    menus_data = {
        "main": gds.ui.main_menu,
        "pause": gds.ui.pause_menu,
        "end": gds.ui.end_screen,
    }

    gfdef: Dict[str, Any] = {
        "schema": "gfdef/1",
        "title": gds.meta.title,
        "seed": seed,
        "player": player_data,
        "input": input_bindings,
        "stats": stats_data,
        "entities": entities_data,
        "rules": rules_data,
        "win": win_data,
        "lose": lose_data,
        "feedback": feedback_data,
        "hud": hud_data,
        "menus": menus_data,
        "custom_rules": [],
    }

    return gfdef


def validate_runtime_def(data: Dict[str, Any]) -> List[str]:
    """Validate gfdef/1 schema structure and semantics; returns list of errors."""
    errors: List[str] = []
    if data.get("schema") != "gfdef/1":
        errors.append(f"Invalid schema: expected 'gfdef/1', got {data.get('schema')!r}")

    if not data.get("title"):
        errors.append("Missing title")

    if not isinstance(data.get("player"), dict):
        errors.append("Missing or invalid 'player' section")

    if not isinstance(data.get("stats"), dict):
        errors.append("Missing or invalid 'stats' section")

    if not isinstance(data.get("rules"), list):
        errors.append("Missing or invalid 'rules' list")

    if not isinstance(data.get("win"), list):
        errors.append("Missing or invalid 'win' conditions")

    if not isinstance(data.get("lose"), list):
        errors.append("Missing or invalid 'lose' conditions")

    return errors
