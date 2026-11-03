"""Deterministic change request rules and shortcuts (WI-8.1).

Parses common natural language requests into typed RFC 6902 JSON Patch ops
without calling a model, with strict bounds and schema validation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .gds import EntityKind, GameDesignSpec
from .patch import ProposedPatch


def match_deterministic_rule(gds: GameDesignSpec, request: str) -> Optional[ProposedPatch]:
    """Inspect natural language request and match against deterministic pattern rules."""
    req = request.strip()

    # Rule 1: Faster / slower <entity>
    patch = _match_speed(gds, req)
    if patch:
        return patch

    # Rule 2: More / fewer <entity>
    patch = _match_count_adjustment(gds, req)
    if patch:
        return patch

    # Rule 3: Add N <entity>
    patch = _match_add_n(gds, req)
    if patch:
        return patch

    # Rule 3b: Add pickup / relic
    patch = _match_add_pickup(gds, req)
    if patch:
        return patch

    # Rule 4: Lighting (day / dusk / night / indoor)
    patch = _match_lighting(gds, req)
    if patch:
        return patch

    # Rule 5: Add checkpoint
    patch = _match_add_checkpoint(gds, req)
    if patch:
        return patch

    # Rule 6: Add hazard
    patch = _match_add_hazard(gds, req)
    if patch:
        return patch

    # Rule 7: Add second level
    patch = _match_add_second_level(gds, req)
    if patch:
        return patch

    # Rule 8: Change win to also require reaching gate / goal
    patch = _match_reach_gate_win(gds, req)
    if patch:
        return patch

    # Rule 9: Rename title
    patch = _match_rename_title(gds, req)
    if patch:
        return patch

    # Rule 10: Remove <entity>
    patch = _match_remove_entity(gds, req)
    if patch:
        return patch

    # Rule 11: Add door with key
    patch = _match_add_door_key(gds, req)
    if patch:
        return patch

    # Rule 12: Complete game / add shooting combat / enemies
    patch = _match_complete_game_or_add_combat(gds, req)
    if patch:
        return patch

    # Rule 13: Player / enemy health
    patch = _match_health(gds, req)
    if patch:
        return patch

    # Rule 14: Jump velocity / force
    patch = _match_jump(gds, req)
    if patch:
        return patch

    # Rule 15: Progression difficulty
    patch = _match_difficulty(gds, req)
    if patch:
        return patch

    # Rule 16: Art style
    patch = _match_art_style(gds, req)
    if patch:
        return patch

    # Rule 17: Camera perspective
    patch = _match_camera(gds, req)
    if patch:
        return patch

    # Rule 18: Lose timer duration
    patch = _match_timer(gds, req)
    if patch:
        return patch

    return None


def _find_entity_idx(gds: GameDesignSpec, term: str) -> Optional[int]:
    term = term.lower().rstrip("s")  # singularize e.g. "guards" -> "guard"
    for idx, e in enumerate(gds.entities):
        eid = e.entity_id.lower().rstrip("s")
        kind_str = e.kind.value.lower().rstrip("s")
        if term == eid or term == kind_str or term in eid:
            return idx
    return None


def _match_speed(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    # Skip if compound request
    if any(k in req.lower() for k in (" and ", " with ", " also ", "plus")):
        return None

    m = re.search(r"(?i)\b(faster|slower|speed\s+up|slow\s+down)\b\s+(?:the\s+)?([a-z0-9_]+)", req)
    if not m:
        m = re.search(r"(?i)\b(?:make|set|increase|decrease)\s+(?:the\s+)?([a-z0-9_]+)(?:'s)?\s+(?:move\s+)?speed\s+(?:to\s+)?(\d+(?:\.\d+)?)\b", req)
        if m:
            target = m.group(1).lower()
            explicit_val = float(m.group(2))
            direction = "faster"
        else:
            m = re.search(r"(?i)\bmake\s+(?:the\s+)?([a-z0-9_]+)\s+(faster|slower)\b", req)
            if m:
                direction = m.group(2).lower()
                target = m.group(1).lower()
                explicit_val = None
            else:
                return None
    else:
        direction = m.group(1).lower()
        target = m.group(2).lower()
        explicit_val = None

    idx = _find_entity_idx(gds, target)
    if idx is None:
        return None

    ent = gds.entities[idx]
    props = ent.props if isinstance(ent.props, dict) else ent.props.model_dump()
    speed_prop = next((k for k in ("player_speed", "move_speed", "patrol_speed", "speed") if k in props), None)
    if not speed_prop:
        speed_prop = "player_speed" if ("player" in ent.entity_id.lower() or getattr(ent, "kind", "") == "player") else "move_speed"
        old_val = 600.0
        op_type = "add"
    else:
        old_val = float(props[speed_prop])
        op_type = "replace"

    if explicit_val is not None:
        new_val = explicit_val
    else:
        m_num = re.search(r"\bto\s+(\d+(?:\.\d+)?)\b", req, re.I)
        if m_num:
            new_val = float(m_num.group(1))
        else:
            factor = 1.25 if direction in ("faster", "speed up") else 0.8
            new_val = round(old_val * factor, 1)

    ops = [
        {
            "op": op_type,
            "path": f"/entities/{idx}/props/{speed_prop}",
            "value": new_val,
        }
    ]
    summary = f"{ent.entity_id.capitalize()}: {speed_prop} {old_val} -> {new_val}"
    return ProposedPatch(ops=ops, summary=summary, status="OK")


def _match_count_adjustment(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    # Skip compound requests and property changes
    if any(k in req.lower() for k in ("speed", "health", "hp", "damage", "jump", "gravity", "size", "time", "timer", "seconds", " and ", " with ", " also ", "plus")):
        return None

    m = re.search(r"(?i)\b(more|fewer|less|increase|decrease)\b\s+(?:the\s+)?([a-z0-9_]+)", req)
    if not m:
        return None

    direction = m.group(1).lower()
    target = m.group(2).lower()

    # Never adjust player count via generic count adjustment
    if target in ("player", "character", "hero"):
        return None

    idx = _find_entity_idx(gds, target)
    if idx is None:
        return None

    ent = gds.entities[idx]
    cur_count = ent.count
    if direction in ("more", "increase"):
        delta = max(1, round(cur_count * 0.5))
        new_count = min(100, cur_count + delta)
    else:
        delta = max(1, round(cur_count * 0.5))
        new_count = max(1, cur_count - delta)

    ops = [
        {
            "op": "replace",
            "path": f"/entities/{idx}/count",
            "value": new_count,
        }
    ]

    # Also update goal required_value if this entity is the objective
    summary = f"{ent.entity_id.capitalize()}: count {cur_count} -> {new_count}"
    goal_idx = next((i for i, e in enumerate(gds.entities) if e.kind == EntityKind.GOAL), None)
    if goal_idx is not None:
        gprops = gds.entities[goal_idx].props
        if isinstance(gprops, dict) and gprops.get("required_stat") == f"entity.{ent.entity_id}.collected":
            ops.append(
                {
                    "op": "replace",
                    "path": f"/entities/{goal_idx}/props/required_value",
                    "value": float(new_count),
                }
            )
            summary += f", updated goal requirement to {new_count}"

    return ProposedPatch(ops=ops, summary=summary, status="OK")


def _match_add_n(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    m = re.search(r"(?i)\badd\s+(\d+)\s+([a-z0-9_]+)", req)
    if not m:
        return None

    num = int(m.group(1))
    target = m.group(2).lower()
    idx = _find_entity_idx(gds, target)
    if idx is not None:
        ent = gds.entities[idx]
        new_count = ent.count + num
        ops = [{"op": "replace", "path": f"/entities/{idx}/count", "value": new_count}]
        return ProposedPatch(
            ops=ops,
            summary=f"Increased {ent.entity_id} count by {num} ({ent.count} -> {new_count})",
            status="OK",
        )

    # If entity does not exist yet, instantiate a new one with the specified count
    target_clean = target.rstrip("s")
    kind_map = {
        "hazard": (EntityKind.HAZARD, "kit.hazard", {"damage_per_second": 25.0, "shape_extent": 150.0}),
        "obstacle": (EntityKind.HAZARD, "kit.hazard", {"damage_per_second": 25.0, "shape_extent": 150.0}),
        "trap": (EntityKind.HAZARD, "kit.hazard", {"damage_per_second": 25.0, "shape_extent": 150.0}),
        "guard": (EntityKind.GUARD, "kit.guard", {"patrol_speed": 400.0, "detection_radius": 800.0}),
        "enemy": (EntityKind.ENEMY, "kit.enemy", {"enemy_speed": 350.0, "health": 100}),
        "bot": (EntityKind.ENEMY, "kit.enemy", {"enemy_speed": 350.0, "health": 100}),
        "pickup": (EntityKind.PICKUP, "kit.pickup", {"value": 1}),
        "coin": (EntityKind.PICKUP, "kit.pickup", {"value": 1}),
        "relic": (EntityKind.PICKUP, "kit.pickup", {"value": 1}),
        "gem": (EntityKind.PICKUP, "kit.pickup", {"value": 1}),
        "checkpoint": (EntityKind.CHECKPOINT, "kit.checkpoint", {"activate_once": True}),
        "spawner": (EntityKind.SPAWNER, "kit.spawner", {"wave_count": 3, "enemies_per_wave": 5}),
        "prop": (EntityKind.PROP, "kit.prop", {}),
        "landmark": (EntityKind.LANDMARK, "kit.landmark", {}),
        "door": (EntityKind.DOOR, "kit.door", {}),
        "platform": (EntityKind.MOVING_PLATFORM, "kit.moving_platform", {}),
        "moving_platform": (EntityKind.MOVING_PLATFORM, "kit.moving_platform", {}),
    }

    if target_clean in kind_map:
        kind, module, default_props = kind_map[target_clean]
        existing_kind = [e for e in gds.entities if e.kind == kind]
        ent_id = f"{kind.value}_{len(existing_kind) + 1}" if existing_kind else (f"{kind.value}s" if num > 1 else kind.value)
        level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"
        new_entity = {
            "entity_id": ent_id,
            "kind": kind.value,
            "module": module,
            "level_id": level_id,
            "count": num,
            "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
            "tags": ["GF_Owned"],
            "props": dict(default_props),
        }
        ops = [{"op": "add", "path": "/entities/-", "value": new_entity}]
        return ProposedPatch(
            ops=ops,
            summary=f"Added {num} {kind.value} ('{ent_id}')",
            status="OK",
        )

    return None


def _match_add_pickup(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    if not re.search(r"(?i)\badd\s+(?:1\s+|one\s+|a\s+)?(?:kit\s+)?(pickup|relic|coin)\b", req):
        return None

    level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"
    existing_pickups = [e for e in gds.entities if e.kind == EntityKind.PICKUP]
    p_id = f"pickup_{len(existing_pickups) + 1}"
    new_entity = {
        "entity_id": p_id,
        "kind": "pickup",
        "module": "kit.pickup",
        "level_id": level_id,
        "count": 1,
        "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
        "tags": ["GF_Owned"],
        "props": {"value": 1, "objective_id": p_id},
    }
    ops = [{"op": "add", "path": "/entities/-", "value": new_entity}]
    return ProposedPatch(ops=ops, summary=f"Added kit pickup '{p_id}'", status="OK")


def _match_lighting(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    m = re.search(r"(?i)\b(night|dusk|day|indoor|sunset|dark)\s*(?:lighting|light)?\b", req)
    if not m:
        m = re.search(r"(?i)\bmake\s+it\s+(night|dusk|day|indoor|sunset|dark)\b", req)
        if not m:
            m = re.search(r"(?i)\b(?:set|change|switch)\s+(?:the\s+)?lighting\s+(?:to\s+)?(night|dusk|day|indoor|sunset|dark)\b", req)
            if not m:
                return None

    raw_val = m.group(1).lower()
    val_map = {"sunset": "dusk", "dark": "night"}
    val = val_map.get(raw_val, raw_val)
    ops = [{"op": "replace", "path": "/scene/levels/0/lighting", "value": val}]
    return ProposedPatch(ops=ops, summary=f"Scene lighting set to {val}", status="OK")


def _match_add_checkpoint(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    if not re.search(r"(?i)\badd\s+(?:a\s+)?checkpoint\b", req):
        return None

    level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"
    existing_cps = [e for e in gds.entities if e.kind == EntityKind.CHECKPOINT]
    cp_id = f"checkpoint_{len(existing_cps) + 1}"

    new_entity = {
        "entity_id": cp_id,
        "kind": "checkpoint",
        "module": "kit.checkpoint",
        "level_id": level_id,
        "count": 1,
        "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
        "props": {"activate_once": True},
        "tags": ["GF_Owned"],
    }
    ops = [{"op": "add", "path": "/entities/-", "value": new_entity}]
    return ProposedPatch(ops=ops, summary=f"Added checkpoint '{cp_id}'", status="OK")


def _match_add_hazard(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    if not re.search(r"(?i)\badd\s+(?:a\s+)?hazard(?:\s+area)?\b", req):
        return None

    level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"
    existing_hazards = [e for e in gds.entities if e.kind == EntityKind.HAZARD]
    h_id = f"hazard_{len(existing_hazards) + 1}"

    new_entity = {
        "entity_id": h_id,
        "kind": "hazard",
        "module": "kit.hazard",
        "level_id": level_id,
        "count": 1,
        "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
        "props": {"damage_per_second": 25.0, "shape_extent": 150.0},
        "tags": ["GF_Owned"],
    }
    ops = [{"op": "add", "path": "/entities/-", "value": new_entity}]
    return ProposedPatch(ops=ops, summary=f"Added hazard area '{h_id}'", status="OK")


def _match_add_second_level(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    if not re.search(r"(?i)\badd\s+(?:a\s+)?(?:second\s+level|level\s+2)\b", req):
        return None

    new_level = {
        "level_id": "level_2",
        "layout": "arena",
        "size_m": {"x": 100.0, "y": 100.0},
        "biome": "dungeon",
        "lighting": "dusk",
        "seed": 2026,
        "layout_params": {},
    }
    ops = [{"op": "add", "path": "/scene/levels/-", "value": new_level}]
    return ProposedPatch(ops=ops, summary="Added second level 'level_2'", status="OK")


def _match_reach_gate_win(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    if not re.search(r"(?i)\b(?:reach(?:ing)?\s+(?:the\s+)?gate|require\s+reaching\s+the\s+gate|win\s+to\s+also\s+require)\b", req):
        return None

    # Check if goal entity exists, otherwise add it
    goal_ent = next((e for e in gds.entities if e.kind == EntityKind.GOAL or e.entity_id == "goal"), None)
    ops = []
    level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"
    if goal_ent is None:
        ops.append(
            {
                "op": "add",
                "path": "/entities/-",
                "value": {
                    "entity_id": "goal",
                    "kind": "goal",
                    "module": "kit.goal",
                    "level_id": level_id,
                    "count": 1,
                    "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
                    "tags": ["GF_Owned"],
                    "props": {},
                },
            }
        )

    # Add win condition
    ops.append(
        {
            "op": "add",
            "path": "/goals/win/-",
            "value": {
                "kind": "event",
                "event": "goal.reached",
                "source": "goal",
            },
        }
    )
    return ProposedPatch(ops=ops, summary="Updated win goal: require reaching the gate/goal", status="OK")


def _match_rename_title(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    m = re.search(r"(?i)\brename\s+(?:the\s+)?title\s+(?:to\s+)?[\"']?([^\"'\n]+)[\"']?", req)
    if not m:
        return None

    new_title = m.group(1).strip()
    ops = [{"op": "replace", "path": "/meta/title", "value": new_title}]
    return ProposedPatch(ops=ops, summary=f"Renamed game title to '{new_title}'", status="OK")


def _match_remove_entity(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    m = re.search(r"(?i)\b(remove|delete|destroy|eliminate|clear)\s+(?:the\s+|all\s+)?([a-z0-9_]+)", req)
    if not m:
        return None

    target = m.group(2).lower()
    idx = _find_entity_idx(gds, target)
    if idx is None:
        return None

    ent = gds.entities[idx]
    ops = [{"op": "remove", "path": f"/entities/{idx}"}]
    return ProposedPatch(ops=ops, summary=f"Removed {ent.kind.value} '{ent.entity_id}'", status="OK")


def _match_add_door_key(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    if not re.search(r"(?i)\badd\s+(?:a\s+)?door\s+with\s+(?:a\s+)?key\b", req):
        return None

    level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"
    key_ent = {
        "entity_id": "key_bronze",
        "kind": "pickup",
        "module": "kit.pickup",
        "level_id": level_id,
        "count": 1,
        "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
        "tags": ["GF_Owned"],
        "props": {"value": 1, "objective_id": "key_bronze"},
    }
    door_ent = {
        "entity_id": "door_gate",
        "kind": "door",
        "module": "kit.door",
        "level_id": level_id,
        "count": 1,
        "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 2.0},
        "tags": ["GF_Owned"],
        "props": {"required_stat": "entity.key_bronze.collected", "required_value": 1.0, "open_seconds": 1.0},
    }
    ops = [
        {"op": "add", "path": "/entities/-", "value": key_ent},
        {"op": "add", "path": "/entities/-", "value": door_ent},
    ]
    return ProposedPatch(ops=ops, summary="Added door 'door_gate' with key 'key_bronze'", status="OK")


def _match_complete_game_or_add_combat(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to complete the game, add gameplay, shooting, enemies, or combat."""
    pattern = re.compile(
        r"(?i)\b(complete|finish|expand|build\s+out|add\s+gameplay|only\s+a\s+box|shooting|shooter|counterstrike|counter-strike|combat|enemies|weapons?|bots?|5v5|five\s+v\s+five)\b"
    )
    if not pattern.search(req):
        return None

    ops = []
    level_id = gds.scene.levels[0].level_id if gds.scene.levels else "level_1"

    # 1. Add enemy wave spawner if no kit.spawner entity exists
    has_spawner = any(e.kind == EntityKind.SPAWNER or getattr(e, "module", "") == "kit.spawner" or "spawner" in e.entity_id.lower() for e in gds.entities)
    if not has_spawner:
        spawner_ent = {
            "entity_id": "spawner",
            "kind": "spawner",
            "module": "kit.spawner",
            "level_id": level_id,
            "count": 1,
            "placement": {"strategy": "scatter", "points_m": [], "min_spacing_m": 10.0, "slot": None},
            "props": {
                "wave_count": 3,
                "enemies_per_wave": 5,
                "enemy_max_health": 100,
                "enemy_attack_damage": 20,
                "enemy_speed": 350.0,
                "seconds_between_waves": 3.0,
                "spawn_radius": 500.0,
            },
            "tags": ["enemy", "hostile", "GF_Owned"],
        }
        ops.append({"op": "add", "path": "/entities/-", "value": spawner_ent})

    # 2. Update player props for projectile shooting combat if not configured
    player_idx = next((i for i, e in enumerate(gds.entities) if e.kind == EntityKind.PLAYER), None)
    if player_idx is not None:
        p_props = gds.entities[player_idx].props or {}
        if not isinstance(p_props, dict):
            p_props = p_props.model_dump()
        if p_props.get("attack_mode") != "projectile":
            ops.append({"op": "add", "path": f"/entities/{player_idx}/props/attack_mode", "value": "projectile"})
        if "move_speed" not in p_props or float(p_props["move_speed"]) < 600:
            ops.append({"op": "add", "path": f"/entities/{player_idx}/props/move_speed", "value": 650.0})
        if "player_max_health" not in p_props:
            ops.append({"op": "add", "path": f"/entities/{player_idx}/props/player_max_health", "value": 100})

        # Configure weapons if mentioned in request
        weapons = []
        if re.search(r"\bpistols?\b", req, re.I):
            weapons.append("pistol")
        if re.search(r"\brifles?\b", req, re.I):
            weapons.append("rifle")
        if re.search(r"\bknif(?:e|es)\b", req, re.I):
            weapons.append("knife")
        if weapons and "weapons" not in p_props:
            ops.append({"op": "add", "path": f"/entities/{player_idx}/props/weapons", "value": weapons})

    # 3. Upgrade level layout to arena for combat/shooter games (composer routes tactical/CS to tactical_fps)
    target_layout = "arena"
    if gds.scene.levels:
        cur_layout = getattr(gds.scene.levels[0], "layout", None)
        layout_val = cur_layout.value if hasattr(cur_layout, "value") else str(cur_layout)
        if layout_val != target_layout:
            ops.append({"op": "replace", "path": "/scene/levels/0/layout", "value": target_layout})

    # Set camera mode to first_person if requested or Counter-Strike
    if any(w in req.lower() for w in ("first person", "first-person", "fps", "counter", "strike", "tactical")):
        cur_cam = getattr(gds.overview, "camera", None)
        cam_val = cur_cam.value if hasattr(cur_cam, "value") else str(cur_cam)
        if cam_val != "first_person":
            ops.append({"op": "replace", "path": "/overview/camera", "value": "first_person"})

    # 4. Add wave cleared tracking rule if missing
    has_wave_rule = any("wave.cleared" in getattr(r.when, "event", "") for r in gds.rules)
    if not has_wave_rule:
        wave_rule = {
            "rule_id": "rule_wave_cleared",
            "when": {"event": "wave.cleared", "source": None},
            "conditions": [],
            "effects": [{"kind": "add_stat", "stat": "game.counter.waves_cleared", "delta": 1.0}],
            "description": "Track cleared waves",
        }
        ops.append({"op": "add", "path": "/rules/-", "value": wave_rule})

    # 5. Ensure win condition accounts for wave completion or defeat all
    has_wave_win = any("wave.cleared" in str(w) for w in gds.goals.win)
    if not has_wave_win:
        win_goal = [
            {
                "kind": "all",
                "items": [
                    {"kind": "event", "event": "wave.cleared", "source": None},
                    {"kind": "stat", "stat": "game.counter.waves_cleared", "op": ">=", "value": 3.0},
                ],
            }
        ]
        ops.append({"op": "replace", "path": "/goals/win", "value": win_goal})

    if not ops:
        return None

    return ProposedPatch(
        ops=ops,
        summary="Completed game design: Added enemy wave spawner with 5 combat bots, enabled projectile shooting mechanics for player, updated level layout to arena with cover, and configured wave-cleared win condition.",
        status="OK",
    )


def _match_health(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to set or scale health / HP for player or enemies."""
    m = re.search(r"(?i)\b(?:set|make|give|increase|change|adjust)\s+(?:the\s+)?(player|enemy|enemies|guards?)(?:'s)?\s+(?:health|hp|max\s+health)\s+(?:to\s+)?(\d+(?:\.\d+)?)\b", req)
    if not m:
        m = re.search(r"(?i)\b(double|halve)\s+(?:the\s+)?(player|enemy|enemies|guards?)(?:'s)?\s+(?:health|hp|max\s+health)\b", req)
        if not m:
            return None
        action = m.group(1).lower()
        target = m.group(2).lower()
        explicit_val = None
    else:
        target = m.group(1).lower()
        explicit_val = float(m.group(2))
        action = "set"

    target_clean = "player" if "player" in target else ("enemy" if "enem" in target else "guard")
    idx = _find_entity_idx(gds, target_clean)
    if idx is None:
        return None

    ent = gds.entities[idx]
    props = ent.props if isinstance(ent.props, dict) else ent.props.model_dump()
    prop_key = next((k for k in ("player_max_health", "enemy_max_health", "health", "max_health") if k in props), None)
    if not prop_key:
        prop_key = "player_max_health" if target_clean == "player" else ("enemy_max_health" if target_clean == "enemy" else "health")
        old_val = 100.0
        op_type = "add"
    else:
        old_val = float(props[prop_key])
        op_type = "replace"

    if explicit_val is not None:
        new_val = explicit_val
    elif action == "double":
        new_val = old_val * 2.0
    else:
        new_val = max(1.0, old_val * 0.5)

    ops = [{"op": op_type, "path": f"/entities/{idx}/props/{prop_key}", "value": new_val}]
    return ProposedPatch(ops=ops, summary=f"{ent.entity_id.capitalize()}: {prop_key} {old_val} -> {new_val}", status="OK")


def _match_jump(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to adjust jump height, velocity, or force."""
    m = re.search(r"(?i)\b(?:set|increase|change|adjust)\s+(?:the\s+)?jump\s+(?:velocity|height|force)\s+(?:to\s+)?(\d+(?:\.\d+)?)\b", req)
    if not m:
        m = re.search(r"(?i)\b(double|increase)\s+(?:the\s+)?jump\s+(?:velocity|height|force)\b", req)
        if not m:
            m = re.search(r"(?i)\bmake\s+(?:the\s+)?player\s+jump\s+higher\b", req)
            if not m:
                return None
            action = "increase"
            explicit_val = None
        else:
            action = m.group(1).lower()
            explicit_val = None
    else:
        explicit_val = float(m.group(1))
        action = "set"

    player_idx = next((i for i, e in enumerate(gds.entities) if e.kind == EntityKind.PLAYER), None)
    if player_idx is None:
        return None

    ent = gds.entities[player_idx]
    props = ent.props if isinstance(ent.props, dict) else ent.props.model_dump()
    old_val = float(props.get("jump_velocity", 600.0))
    op_type = "replace" if "jump_velocity" in props else "add"

    if explicit_val is not None:
        new_val = explicit_val
    elif action == "double":
        new_val = old_val * 2.0
    else:
        new_val = round(old_val * 1.3, 1)

    ops = [{"op": op_type, "path": f"/entities/{player_idx}/props/jump_velocity", "value": new_val}]
    return ProposedPatch(ops=ops, summary=f"Player: jump_velocity {old_val} -> {new_val}", status="OK")


def _match_difficulty(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to change progression difficulty."""
    m = re.search(r"(?i)\b(?:set|change|make)\s+(?:the\s+)?(?:difficulty\s+(?:to\s+)?)?(easy|normal|hard)\b", req)
    if not m:
        return None
    val = m.group(1).lower()
    ops = [{"op": "replace", "path": "/progression/difficulty", "value": val}]
    return ProposedPatch(ops=ops, summary=f"Progression difficulty set to '{val}'", status="OK")


def _match_art_style(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to change visual art style."""
    m = re.search(r"(?i)\b(?:set|change|switch)\s+(?:the\s+)?art\s+style\s+(?:to\s+)?(stylized|realistic|low_poly|low\s+poly|toon)\b", req)
    if not m:
        m = re.search(r"(?i)\bmake\s+(?:it|the\s+style)\s+(stylized|realistic|low_poly|low\s+poly|toon)\b", req)
        if not m:
            return None
    val = m.group(1).lower().replace(" ", "_")
    ops = [{"op": "replace", "path": "/art/style", "value": val}]
    return ProposedPatch(ops=ops, summary=f"Art style set to '{val}'", status="OK")


def _match_camera(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to change camera perspective."""
    m = re.search(r"(?i)\b(?:set|change|switch)\s+(?:the\s+)?camera(?:\s+mode|\s+view)?\s+(?:to\s+)?(first[- ]person|third[- ]person|top[- ]down|side[- ]scroller|fixed[- ]board)\b", req)
    if not m:
        return None
    cam_str = m.group(1).lower().replace(" ", "_").replace("-", "_")
    ops = [{"op": "replace", "path": "/overview/camera", "value": cam_str}]
    return ProposedPatch(ops=ops, summary=f"Camera mode set to '{cam_str}'", status="OK")


def _match_timer(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    """Matches requests to set or add lose timer condition."""
    m = re.search(r"(?i)\b(?:set|change)\s+(?:the\s+)?(?:time\s+limit|timer)\s+(?:to\s+)?(\d+)\s*(?:s|sec|seconds?)?\b", req)
    if not m:
        m = re.search(r"(?i)\badd\s+(?:a\s+)?(\d+)\s*(?:s|sec|seconds?)\s+timer\b", req)
        if not m:
            return None
    seconds = float(m.group(1))

    timer_idx = None
    for idx, cond in enumerate(gds.goals.lose):
        if getattr(cond, "kind", "") == "timer":
            timer_idx = idx
            break

    if timer_idx is not None:
        ops = [{"op": "replace", "path": f"/goals/lose/{timer_idx}/seconds", "value": seconds}]
    else:
        timer_cond = {"kind": "timer", "seconds": seconds}
        ops = [{"op": "add", "path": "/goals/lose/-", "value": timer_cond}]

    return ProposedPatch(ops=ops, summary=f"Set game lose timer to {int(seconds)} seconds", status="OK")

