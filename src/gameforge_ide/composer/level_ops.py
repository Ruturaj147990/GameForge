"""Composer level ops generator (WI-6.4).

Turns a LevelPlan into a strictly validated sequence of OpCalls:
level creation, lighting rig, geometry, placed actors, navmesh,
nav reachability checks, runtime gamedef serialization, and save.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from .model import LevelPlan, OpCall, PlacedActor
from ..unreal import op_schemas
from ..backend.tools import biomes


def _validate_call(op: str, args: Dict[str, Any]) -> None:
    """Validate op call against op_schemas in strict mode."""
    _, errs = op_schemas.validate_args(op, args)
    if errs:
        raise ValueError(f"OpCall {op!r} failed strict schema validation: {errs}")


def plan_to_op_calls(
    plan: LevelPlan,
    gfdef: Optional[Dict[str, Any]] = None,
    is_first_level: bool = True,
) -> List[OpCall]:
    """Convert a LevelPlan into a validated sequence of OpCalls."""
    ops: List[OpCall] = []

    def emit(op: str, args: Dict[str, Any], purpose: str = "", expect: Optional[Dict[str, Any]] = None) -> None:
        _validate_call(op, args)
        ops.append(OpCall(op=op, args=args, expect=expect or {}, purpose=purpose))

    # 1. new_level
    emit(
        "new_level",
        {
            "level_path": plan.map_path,
            "partitioned": plan.partitioned,
            "if_exists": "replace",
        },
        purpose=f"Create level {plan.level_id}",
    )

    # 2. Lighting preset
    light_key = plan.lighting
    if light_key == "day":
        light_key = "day_clear"
    if light_key in biomes.LIGHTING:
        for light in biomes.lighting_rig(light_key):
            emit("spawn_actor", light, purpose=f"Spawn {light.get('label', 'light')}")

    # 3. Geometry ops from the layout
    for g_op in plan.geometry_ops:
        emit(g_op.op, g_op.args, purpose=g_op.purpose, expect=g_op.expect)

    # 4. Placed actors
    for a in plan.actors:
        spawn_args: Dict[str, Any] = {
            "actor_class": a.runtime_class,
            "label": a.actor_id,
            "location": {"x": a.location[0], "y": a.location[1], "z": a.location[2]},
            "rotation": {"pitch": 0.0, "yaw": a.yaw, "roll": 0.0},
        }
        emit("spawn_actor", spawn_args, purpose=f"Spawn placed actor {a.actor_id}")

        if a.tags:
            emit("actor_set_tags", {"label": a.actor_id, "tags": a.tags}, purpose=f"Set tags for {a.actor_id}")

        for prop_name, prop_val in a.properties.items():
            emit(
                "set_actor_property",
                {"label": a.actor_id, "property": prop_name, "value": prop_val},
                purpose=f"Set {prop_name} on {a.actor_id}",
            )

    # 5. NavMeshBoundsVolume and nav rebuild
    nav_center, nav_extent = plan.nav_bounds
    nav_scale_x = max(1.0, nav_extent[0] / 100.0)
    nav_scale_y = max(1.0, nav_extent[1] / 100.0)
    nav_scale_z = max(1.0, nav_extent[2] / 100.0)

    emit(
        "spawn_actor",
        {
            "actor_class": "NavMeshBoundsVolume",
            "label": "GF_NavMeshBounds",
            "location": {"x": nav_center[0], "y": nav_center[1], "z": nav_center[2]},
            "scale": {"x": nav_scale_x, "y": nav_scale_y, "z": nav_scale_z},
        },
        purpose="Spawn NavMesh bounds volume",
    )
    emit("nav_rebuild", {}, purpose="Rebuild NavMesh")

    # 6. Nav reachability checks
    actor_locs: Dict[str, Tuple[float, float, float]] = {a.actor_id: a.location for a in plan.actors}
    actor_locs["player_start"] = plan.player_start

    for from_actor, to_actor in plan.nav_checks:
        start_pt = actor_locs.get(from_actor, plan.player_start)
        end_pt = actor_locs.get(to_actor, plan.player_start)
        emit(
            "nav_find_path",
            {
                "start": {"x": start_pt[0], "y": start_pt[1], "z": start_pt[2]},
                "end": {"x": end_pt[0], "y": end_pt[1], "z": end_pt[2]},
            },
            expect={"data.found": True},
            purpose=f"Verify reachability: {from_actor} -> {to_actor}",
        )

    # 7. gamedef_write (once per project, on first level)
    if is_first_level and gfdef is not None:
        gfdef_str = json.dumps(gfdef, indent=2, sort_keys=True)
        emit(
            "gamedef_write",
            {"asset_path": "/Game/GameForge/GD_Main", "json": gfdef_str},
            purpose="Write runtime game definition asset",
        )

    # 8. save_all
    emit("save_all", {}, purpose="Save modified assets and level")

    return ops
