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
    m = re.search(r"(?i)\b(faster|slower|speed\s+up|slow\s+down)\b\s+(?:the\s+)?([a-z0-9_]+)", req)
    if not m:
        m = re.search(r"(?i)\bmake\s+(?:the\s+)?([a-z0-9_]+)\s+(faster|slower)\b", req)
        if m:
            direction = m.group(2).lower()
            target = m.group(1).lower()
        else:
            return None
    else:
        direction = m.group(1).lower()
        target = m.group(2).lower()

    idx = _find_entity_idx(gds, target)
    if idx is None:
        return None

    ent = gds.entities[idx]
    props = ent.props if isinstance(ent.props, dict) else ent.props.model_dump()
    speed_prop = next((k for k in ("move_speed", "patrol_speed", "speed") if k in props), None)
    if not speed_prop:
        return None

    factor = 1.25 if direction in ("faster", "speed up") else 0.8
    old_val = float(props[speed_prop])
    new_val = round(old_val * factor, 1)

    ops = [
        {
            "op": "replace",
            "path": f"/entities/{idx}/props/{speed_prop}",
            "value": new_val,
        }
    ]
    summary = f"{ent.entity_id.capitalize()}: {speed_prop} {old_val} -> {new_val}"
    return ProposedPatch(ops=ops, summary=summary, status="OK")


def _match_count_adjustment(gds: GameDesignSpec, req: str) -> Optional[ProposedPatch]:
    m = re.search(r"(?i)\b(more|fewer|less|increase|decrease)\b\s+(?:the\s+)?([a-z0-9_]+)", req)
    if not m:
        return None

    direction = m.group(1).lower()
    target = m.group(2).lower()
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
    m = re.search(r"(?i)\b(night|dusk|day|indoor)\s*(?:lighting|light)?\b", req)
    if not m:
        m = re.search(r"(?i)\bmake\s+it\s+(night|dusk|day|indoor)\b", req)
        if not m:
            return None

    val = m.group(1).lower()
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
    m = re.search(r"(?i)\bremove\s+(?:the\s+)?([a-z0-9_]+)", req)
    if not m:
        return None

    target = m.group(1).lower()
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
