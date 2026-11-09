"""GameForge Runtime Definition (gfdef/1) builder and validator (WI-5.1).

Transforms typed GameDesignSpec into gfdef/1 JSON contract for GameForgeRuntime.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..design.gds import GameDesignSpec
from .registry import get_module


def _compile_input_bindings(gds: GameDesignSpec) -> List[Dict[str, Any]]:
    """Compile core movement/combat bindings plus all custom actions in gds.input.actions."""
    input_bindings: List[Dict[str, Any]] = [
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
    seen_actions = {b["action"] for b in input_bindings}

    input_spec = getattr(gds, "input", None)
    for act in getattr(input_spec, "actions", []) or []:
        act_id = getattr(act, "action_id", "")
        if not act_id or act_id in seen_actions:
            continue
        val_type = getattr(act, "value_type", "bool")
        mapped_type = "axis2d" if val_type == "axis2d" else ("axis1d" if val_type == "axis1d" else "digital")
        key_entries: List[Dict[str, Any]] = []
        for raw_key in getattr(act, "bindings", []) or []:
            if ":" in raw_key:
                k_name, mod_str = raw_key.split(":", 1)
                mods = [m for m in mod_str.replace("swizzle_negate", "swizzle+negate").split("+") if m]
            else:
                k_name, mods = raw_key, []
            if k_name == "Mouse2D":
                k_name = "MouseXY"
            key_entries.append({"key": k_name, "mods": mods})
        if key_entries:
            input_bindings.append({
                "action": act_id,
                "type": mapped_type,
                "bindings": key_entries,
            })
            seen_actions.add(act_id)

    return input_bindings


def build_runtime_def(gds: GameDesignSpec, seed: int = 2026) -> Dict[str, Any]:
    """Generate gfdef/1 dictionary from GameDesignSpec."""
    from ..design.gds import EntityKind

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
        aliases = {"player_speed": "move_speed", "player_max_health": "max_health",
                   "player_attack_damage": "attack_damage", "player_attack_range": "attack_range",
                   "player_attack_cooldown": "attack_cooldown"}
        allowed = ("move_speed", "jump_velocity", "max_health", "max_stamina", "lives", "kill_z", "attack_damage",
                   "attack_mode", "weapons", "projectile_speed", "attack_range", "attack_cooldown", "air_control",
                   "gravity_scale", "max_jumps", "double_jump", "sprint_multiplier", "dash_impulse")
        for k, v in p_props.items():
            key = aliases.get(k, k)
            if key in allowed and v is not None and not (key != k and key in p_props):
                player_data[key] = v

    camera_str = str(player_data.get("camera", "")).lower()
    genre_str = str(getattr(gds.overview, "genre", "")).lower()
    if "first_person" in camera_str or "shooter" in genre_str or "arena" in genre_str:
        player_data.setdefault("attack_mode", "projectile")
        player_data.setdefault("projectile_speed", 2500.0)
        player_data.setdefault("attack_damage", 35.0)

    # Enhanced input mapping including dynamic GDS input actions
    input_bindings = _compile_input_bindings(gds)

    # Stats
    player_max_health = float(player_data.get("max_health", 100.0))
    stats_data: Dict[str, Any] = {
        "player.health": {"initial": player_max_health, "min": 0.0, "max": player_max_health},
        "player.max_health": {"initial": player_max_health},
        "game.score": {"initial": 0.0, "min": 0.0},
        "game.counter.waves_cleared": {"initial": 0.0, "min": 0.0},
    }
    lives = int(player_data.get("lives", 0) or 0)
    if lives > 0:
        stats_data["player.lives"] = {"initial": float(lives), "min": 0.0}

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
        elif kind_val == "pickup":
            stats_data[f"entity.{ent.entity_id}.collected"] = {
                "initial": 0.0,
                "min": 0.0,
                "max": float(getattr(ent, "count", 1) or 1),
            }

    # Initialize dynamic stats referenced in HUD elements or rules
    dynamic_defaults = {
        "player.shield": {"initial": 100.0, "min": 0.0, "max": 100.0},
        "player.oxygen": {"initial": 100.0, "min": 0.0, "max": 100.0},
        "player.mana": {"initial": 100.0, "min": 0.0, "max": 100.0},
        "player.stamina": {"initial": float(player_data.get("max_stamina", 100.0) or 100.0), "min": 0.0, "max": float(player_data.get("max_stamina", 100.0) or 100.0)},
        "player.ammo": {"initial": 30.0, "min": 0.0, "max": 300.0},
        "game.gold": {"initial": 0.0, "min": 0.0},
        "game.laps": {"initial": 0.0, "min": 0.0},
        "game.counter.collected": {"initial": 0.0, "min": 0.0},
    }
    for elem in getattr(gds.ui, "hud", []) or []:
        b_stat = getattr(elem, "binds", None)
        if b_stat and b_stat not in stats_data:
            stats_data[b_stat] = dict(dynamic_defaults.get(b_stat, {"initial": 0.0, "min": 0.0}))
    for r in getattr(gds, "rules", []) or []:
        for eff in getattr(r, "effects", []) or []:
            e_stat = getattr(eff, "stat", None)
            if e_stat and e_stat not in stats_data:
                stats_data[e_stat] = dict(dynamic_defaults.get(e_stat, {"initial": 0.0, "min": 0.0}))

    # Entities
    entities_data: Dict[str, Any] = {}
    for ent in gds.entities:
        mod_cls = "/Script/GameForgeRuntime.GameForgePickup"
        try:
            m = get_module(ent.module)
            mod_cls = m.runtime_class
        except KeyError:
            pass

        visual_data = {}
        is_humanoid = any(k in ent.entity_id.lower() or k in ent.module.lower()
                          for k in ("enemy", "guard", "npc", "quest_giver", "hermit", "character"))
        if is_humanoid:
            visual_data = {
                "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple",
                "anim_class": "/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C",
                "material_tint": [0.8, 0.2, 0.2, 1.0] if "enemy" in ent.entity_id.lower() or "guard" in ent.entity_id.lower() else [0.2, 0.5, 0.9, 1.0],
            }

        props_out = dict(ent.props)
        color_tag = next((t.split(":", 1)[1] for t in ent.tags if isinstance(t, str) and t.startswith("color:")), None)
        if color_tag and len(color_tag) == 7:
            rgb = [round(int(color_tag[i:i + 2], 16) / 255.0, 3) for i in (1, 3, 5)]
            props_out["body_color"] = rgb + [1.0]
            if visual_data:
                visual_data["material_tint"] = rgb + [1.0]
        label = next((t.split(":", 1)[1] for t in ent.tags if isinstance(t, str) and t.startswith("label:")), None)
        entities_data[ent.entity_id] = {
            "class": mod_cls,
            "spawn_tag": f"GF_SP_{ent.entity_id}",
            "count": ent.count,
            "label": label or ent.entity_id.replace("_", " ").title(),
            "properties": props_out,
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
            "vfx": _resolve_vfx(fb.vfx),
            "sfx": _resolve_sfx(fb.sfx),
            "shake": fb.camera_shake,
            "msg": fb.ui_message,
        })

    if not feedback_data:
        feedback_data.append({
            "e": "pickup.collected",
            "vfx": "/Game/GameForge/VFX/NS_Sparkle",
            "sfx": "/Game/GameForge/SFX/S_PickupChime",
            "shake": 0.0,
            "msg": None,
        })

    # HUD Elements
    timer_limit = None
    for c in list(gds.goals.lose) + list(gds.goals.win):
        if getattr(c, "kind", None) == "timer":
            timer_limit = float(c.seconds)
            break
    hud_data: List[Dict[str, Any]] = []
    for elem in gds.ui.hud:
        row: Dict[str, Any] = {
            "id": elem.element_id,
            "kind": elem.kind,
            "stat": elem.binds,
            "label": elem.label,
        }
        stat = elem.binds or ""
        if elem.kind == "bar" and stat == "player.health":
            row["of"] = player_max_health
        elif elem.kind == "bar" and stat in ("player.shield", "player.oxygen", "player.mana", "player.stamina"):
            row["of"] = float(stats_data.get(stat, {}).get("max", 100.0))
        elif elem.kind == "timer" and timer_limit:
            row["of"] = timer_limit
        elif stat.startswith("entity.") and stat.endswith(".collected"):
            ent = next((e for e in gds.entities if e.entity_id == stat.split(".")[1]), None)
            if ent is not None:
                row["of"] = float(ent.count)
        elif stat == "game.counter.waves_cleared":
            sp = next((e for e in gds.entities if getattr(e, "module", "") == "kit.spawner"), None)
            if sp is not None:
                row["of"] = float(sp.props.get("wave_count", 3))
        hud_data.append(row)

    # Menus
    menus_data = {
        "main": gds.ui.main_menu,
        "pause": gds.ui.pause_menu,
        "end": gds.ui.end_screen,
    }

    gfdef: Dict[str, Any] = {
        "schema": "gfdef/1",
        "title": gds.meta.title,
        "pitch": gds.overview.pitch,
        "objective": describe_objective(gds),
        "controls": describe_controls(gds, player_data),
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
    if getattr(gds, "architecture", None) is not None:
        gfdef["architecture"] = gds.architecture.model_dump(exclude_none=True)

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


_VFX_FALLBACK = {
    "vfx.sparkle_burst": "/Game/GameForge/VFX/NS_Sparkle",
    "vfx.sparkle": "/Game/GameForge/VFX/NS_Sparkle",
    "vfx.burst": "/Game/GameForge/VFX/NS_Burst",
    "vfx.hit_flash": "/Game/GameForge/VFX/NS_HitFlash",
    "vfx.explosion": "/Game/GameForge/VFX/NS_Explosion",
    "vfx.slash": "/Game/GameForge/VFX/NS_Slash",
    "vfx.poof": "/Game/GameForge/VFX/NS_Poof",
    "vfx.confetti": "/Game/GameForge/VFX/NS_Confetti",
    "vfx.ring": "/Game/GameForge/VFX/NS_Ring",
    "vfx.magic_trail": "/Game/GameForge/VFX/NS_MagicTrail",
    "vfx.fire": "/Game/GameForge/VFX/NS_Fire",
    "vfx.smoke": "/Game/GameForge/VFX/NS_Smoke",
}

_SFX_FALLBACK = {
    "sfx.pickup_chime": "/Game/GameForge/SFX/S_PickupChime",
    "sfx.pickup": "/Game/GameForge/SFX/S_PickupChime",
    "sfx.impact": "/Game/GameForge/SFX/S_Impact",
    "sfx.hit": "/Game/GameForge/SFX/S_Impact",
    "sfx.defeat": "/Game/GameForge/SFX/S_Defeat",
    "sfx.lose": "/Game/GameForge/SFX/S_Defeat",
    "sfx.fanfare": "/Game/GameForge/SFX/S_Fanfare",
    "sfx.win": "/Game/GameForge/SFX/S_Fanfare",
    "sfx.chime_low": "/Game/GameForge/SFX/S_ChimeLow",
    "sfx.ui_click": "/Game/GameForge/SFX/S_UiClick",
    "sfx.footstep_soft": "/Game/GameForge/SFX/S_FootstepSoft",
}


def _resolve_vfx(preset: Optional[str]) -> Optional[str]:
    if not preset or preset.startswith("/"):
        return preset
    try:
        from ..content.vfx_presets import VFX_PRESETS
        p = VFX_PRESETS.get(preset)
        if p is not None:
            return getattr(p, "target_asset_path", None) or getattr(p, "template_path", None) or _VFX_FALLBACK.get(preset)
    except Exception:
        pass
    return _VFX_FALLBACK.get(preset, f"/Game/GameForge/VFX/NS_{preset.split('.', 1)[-1].title().replace('_', '')}")


def _resolve_sfx(preset: Optional[str]) -> Optional[str]:
    """sfx.pickup_chime -> /Game/GameForge/SFX/S_PickupChime."""
    if not preset or preset.startswith("/"):
        return preset
    if preset in _SFX_FALLBACK:
        return _SFX_FALLBACK[preset]
    name = preset.split(".", 1)[-1]
    return f"/Game/GameForge/SFX/S_{name.title().replace('_', '')}"


def _label(ent: Any, plural: bool = False) -> str:
    lab = next((t.split(":", 1)[1] for t in getattr(ent, "tags", []) if isinstance(t, str) and t.startswith("label:")), None)
    lab = lab or ent.entity_id.replace("_", " ").rstrip("s").title()
    if plural and ent.count != 1 and not lab.endswith("s"):
        lab = lab[:-1] + "ies" if lab.endswith("y") and lab[-2:-1] not in "aeiou" else lab + "s"
    return lab


def describe_objective(gds: GameDesignSpec) -> str:
    """One readable sentence of what the player must do, built from the actual win/lose conditions."""
    ents = {e.entity_id: e for e in gds.entities}
    parts: List[str] = []

    def cond_text(c: Any) -> Optional[str]:
        kind = getattr(c, "kind", None)
        if kind == "count_at_least" and c.event == "pickup.collected":
            pick = next((e for e in gds.entities if e.module == "kit.pickup"), None)
            return f"Collect {c.n} {_label(pick, True) if pick else 'items'}"
        if kind == "event":
            if c.event == "goal.reached":
                goal = next((e for e in gds.entities if e.module == "kit.goal"), None)
                req = goal.props.get("required_stat") if goal else None
                if req == "game.counter.collected":
                    picks = [e for e in gds.entities if e.module == "kit.pickup"]
                    need = int(float(goal.props.get("required_value", 0)))
                    names = " and ".join(_label(e, True) for e in picks[:3]) or "items"
                    return f"Collect all {need} {names}, then reach the {_label(goal)}"
                if req and str(req).endswith(".collected"):
                    src = ents.get(str(req).split(".")[1])
                    need = int(float(goal.props.get("required_value", 0)))
                    return f"Collect {need} {_label(src, True) if src else 'items'}, then reach the {_label(goal)}"
                return f"Reach the {_label(goal) if goal else 'goal'}"
            return {"board.win": "Win the board", "match.won": "Win the match", "wave.cleared": None,
                    "landmark.discovered": "Discover the landmark"}.get(c.event)
        if kind == "stat":
            if c.stat.endswith(".remaining") and c.op in ("<=", "<"):
                e = ents.get(c.stat.split(".")[1])
                return f"Defeat every {_label(e) if e else 'enemy'}"
            if c.stat == "game.score":
                return f"Score {int(c.value)} points"
            if c.stat == "game.counter.waves_cleared":
                return f"Clear {int(c.value)} waves"
        if kind == "timer":
            secs = int(c.seconds)
            return f"Survive {secs // 60} min {secs % 60:02d} s" if secs >= 60 else f"Survive {secs} seconds"
        if kind in ("all", "any"):
            sub = [t for t in (cond_text(i) for i in c.items) if t]
            return " and ".join(sub) if kind == "all" else " or ".join(sub)
        return None

    for c in gds.goals.win:
        t = cond_text(c)
        if t and t not in parts:
            parts.append(t)
    text = " - or - ".join(parts[:2]) if parts else "Explore"
    lose_bits: List[str] = []
    for c in gds.goals.lose:
        k = getattr(c, "kind", None)
        if k == "timer":
            lose_bits.append(f"before {int(c.seconds)} s run out")
        elif k == "event" and c.event == "guard.spotted_player":
            lose_bits.append("without being spotted")
    if lose_bits:
        text += " " + " and ".join(lose_bits)
    return text[:120]


def describe_controls(gds: GameDesignSpec, player_data: Dict[str, Any]) -> str:
    cam = str(player_data.get("camera", ""))
    if cam in ("fixed_board",):
        return "Click to play  -  P pause"
    bits = ["WASD move", "Mouse look" if cam in ("third_person", "first_person") else ""]
    if cam != "fixed_board":
        bits.append("Space jump" + (" (x2)" if player_data.get("double_jump") or int(player_data.get("max_jumps", 1) or 1) > 1 else ""))
        bits.append("Shift dash" if player_data.get("dash_impulse") else "Shift sprint")
    has_combat = any(e.module in ("kit.enemy_melee", "kit.enemy_ranged", "kit.spawner") for e in gds.entities)
    if has_combat:
        bits.append("Click shoot" if player_data.get("attack_mode") == "projectile" else "Click attack")
    if any(e.module in ("kit.door", "kit.switch", "kit.quest_giver", "kit.bomb_site") for e in gds.entities):
        bits.append("E interact")
    bits.append("P pause")
    return "  -  ".join(b for b in bits if b)
