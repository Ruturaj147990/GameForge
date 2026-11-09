"""Composer level ops generator (WI-6.4).

Turns a LevelPlan into a strictly validated sequence of OpCalls:
level creation, lighting rig, geometry, placed actors, navmesh,
nav reachability checks, runtime gamedef serialization, and save.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple
from .model import LevelPlan, OpCall, PlacedActor
from ..unreal import op_schemas
from ..backend.tools import biomes
from ..content.procedural_props import PROP_RECIPES, expand_prop_to_ops


NON_UE_GDS_PROPS = frozenset({
    "count",
    "value",
    "respawns",
    "respawn_seconds",
    "min_spacing_m",
    "min_spacing_cm",
    "strategy",
    "slot",
    "attack_mode",
    "location",
    "rotation",
    "scale",
    "yaw",
    "pitch",
    "roll",
    "tags",
    "kind",
    "module",
    "level_id",
    "entity_id",
    "actor_id",
    "property_overrides",
    "patrol_radius",
    "behavior",
    "shape",
    "speed",
    "color",
    "type",
    "recipe",
    "genre",
    "snakes",
    "ladders",
    "seed",
    "difficulty",
    "ScaleX",
    "ScaleY",
    "ScaleZ",
})


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

    # 1. new_level: must always precede any load_level or actor spawning
    emit(
        "new_level",
        {
            "level_path": plan.map_path,
            "partitioned": plan.partitioned,
            "if_exists": "replace",
        },
        purpose=f"Create level {plan.level_id}",
    )

    # 1b. Spawn PlayerStart actor at planned spawn location (avoid duplicates)
    geometry_has_player_start = any(
        g_op.op == "spawn_actor"
        and (
            g_op.args.get("actor_class") in ("PlayerStart", "/Script/Engine.PlayerStart")
            or str(g_op.args.get("actor_class", "")).endswith(".PlayerStart")
            or g_op.args.get("label") in ("GF_PlayerStart", "PlayerStart")
        )
        for g_op in plan.geometry_ops
    )
    actors_has_player_start = any(
        a.runtime_class in ("PlayerStart", "/Script/Engine.PlayerStart")
        or a.runtime_class.endswith(".PlayerStart")
        or a.actor_id in ("GF_PlayerStart", "PlayerStart")
        or a.entity_id == "player_start"
        for a in plan.actors
    )
    has_spawned_player_start = geometry_has_player_start

    if not has_spawned_player_start and not actors_has_player_start and plan.player_start is not None:
        ps_args: Dict[str, Any] = {
            "actor_class": "PlayerStart",
            "label": "GF_PlayerStart",
            "location": {"x": plan.player_start[0], "y": plan.player_start[1], "z": plan.player_start[2]},
        }
        deferred_player_start = any(a.snap_to_ground for a in plan.actors)
        if not deferred_player_start:
            emit("spawn_actor", ps_args, purpose="Spawn primary player start point")
        has_spawned_player_start = True
    else:
        ps_args, deferred_player_start = {}, False

    # 2. Lighting preset
    light_key = plan.lighting
    if light_key == "day":
        light_key = "day_clear"
    if light_key in biomes.LIGHTING:
        for light in biomes.lighting_rig(light_key):
            if plan.sun_color and light.get("actor_class") == "DirectionalLight":
                light = {**light, "light_color": list(plan.sun_color)}
            emit("spawn_actor", light, purpose=f"Spawn {light.get('label', 'light')}")

    # 3. Geometry ops from the layout
    for g_op in plan.geometry_ops:
        emit(g_op.op, g_op.args, purpose=g_op.purpose, expect=g_op.expect)

    if deferred_player_start and ps_args:
        emit("spawn_actor", {**ps_args, "snap_to_ground": True, "ground_offset": 110.0},
             purpose="Spawn primary player start point (snapped to terrain)")

    # 4. Placed actors (filter out non-actor Subsystems, duplicates of PlayerStart, or duplicate labels)
    spawned_labels: Set[str] = {"GF_PlayerStart"} if has_spawned_player_start else set()
    for a in plan.actors:
        if a.actor_id in spawned_labels:
            continue
        # Skip UGameInstanceSubsystem classes (e.g. kit.objective -> GameForgeObjectiveSubsystem)
        if "Subsystem" in a.runtime_class:
            continue

        is_player_start_actor = (
            a.runtime_class in ("PlayerStart", "/Script/Engine.PlayerStart")
            or a.runtime_class.endswith(".PlayerStart")
            or a.actor_id in ("GF_PlayerStart", "PlayerStart")
            or a.entity_id == "player_start"
        )
        if is_player_start_actor:
            if has_spawned_player_start:
                continue
            has_spawned_player_start = True

        spawned_labels.add(a.actor_id)

        # Expand procedural CSG prop recipes for StaticMeshActor props when a recipe is specified
        recipe_name = a.properties.get("recipe")
        if a.runtime_class.endswith("StaticMeshActor") and recipe_name:
            scale_tuple = (
                float(a.properties.get("ScaleX", a.properties.get("scale_x", 1.0)) or 1.0),
                float(a.properties.get("ScaleY", a.properties.get("scale_y", 1.0)) or 1.0),
                float(a.properties.get("ScaleZ", a.properties.get("scale_z", 1.0)) or 1.0),
            )
            part_ops = expand_prop_to_ops(
                actor_id=a.actor_id,
                recipe_name=str(recipe_name),
                location=a.location,
                yaw=a.yaw,
                scale=scale_tuple,
            )
            if part_ops:
                for p_idx, part_args in enumerate(part_ops):
                    if p_idx == 0 and a.snap_to_ground:
                        part_args["snap_to_ground"] = True
                        part_args["ground_offset"] = float(a.ground_offset)
                    emit("spawn_actor", part_args, purpose=f"Spawn CSG prop {a.actor_id} ({recipe_name} part {p_idx})")
                if a.tags:
                    emit("actor_set_tags", {"label": a.actor_id, "tags": a.tags}, purpose=f"Set tags for {a.actor_id}")
                continue

        spawn_args: Dict[str, Any] = {
            "actor_class": "StaticMeshActor" if a.runtime_class.endswith("StaticMeshActor") else a.runtime_class,
            "label": a.actor_id,
            "location": {"x": a.location[0], "y": a.location[1], "z": a.location[2]},
            "rotation": {"pitch": 0.0, "yaw": a.yaw, "roll": 0.0},
        }
        if a.runtime_class.endswith("StaticMeshActor"):
            spawn_args["static_mesh"] = str(a.properties.get("StaticMesh", "/Engine/BasicShapes/Cube.Cube"))
            sx = float(a.properties.get("ScaleX", 1.0) or 1.0)
            sy = float(a.properties.get("ScaleY", 1.0) or 1.0)
            sz = float(a.properties.get("ScaleZ", 1.0) or 1.0)
            if (sx, sy, sz) != (1.0, 1.0, 1.0):
                spawn_args["scale"] = {"x": sx, "y": sy, "z": sz}
        if a.snap_to_ground:
            spawn_args["snap_to_ground"] = True
            spawn_args["ground_offset"] = float(a.ground_offset)
        emit("spawn_actor", spawn_args, purpose=f"Spawn placed actor {a.actor_id}")

        if a.entity_id and "EntityId" not in a.properties and a.runtime_class.startswith("/Script/GameForgeRuntime."):
            emit("set_actor_property", {"label": a.actor_id, "property": "EntityId", "value": a.entity_id},
                 purpose=f"Set EntityId on {a.actor_id}")

        if a.tags:
            emit("actor_set_tags", {"label": a.actor_id, "tags": a.tags}, purpose=f"Set tags for {a.actor_id}")

        for prop_name, prop_val in a.properties.items():
            if prop_val is None:
                continue
            if not isinstance(prop_name, str) or not prop_name.strip():
                continue
            p_clean = prop_name.strip()
            if p_clean in NON_UE_GDS_PROPS or p_clean.startswith("_"):
                continue
            if a.runtime_class.endswith("StaticMeshActor") and p_clean == "StaticMesh":
                continue
            if p_clean[0].islower() and not (p_clean[0] == "b" and len(p_clean) > 1 and p_clean[1].isupper()):
                continue
            if not p_clean.isidentifier():
                continue
            if isinstance(prop_val, dict) and not (set(prop_val).issubset({"x", "y", "z"}) or set(prop_val).issubset({"r", "g", "b", "a"})):
                continue

            is_asset = (
                isinstance(prop_val, str)
                and (prop_val.startswith("/Game/") or prop_val.startswith("/Engine/") or prop_val.startswith("/Script/"))
            )
            set_args: Dict[str, Any] = {
                "label": a.actor_id,
                "property": p_clean,
                "value": prop_val,
            }
            if is_asset:
                set_args["asset"] = True
            emit(
                "set_actor_property",
                set_args,
                purpose=f"Set {p_clean} on {a.actor_id}",
            )

    # 5. NavMeshBoundsVolume and nav rebuild
    is_board_layout = (
        any(
            "GridBoard" in a.runtime_class
            or "CardTable" in a.runtime_class
            or "GF_Board" in a.tags
            for a in plan.actors
        )
        or "board" in plan.level_id.lower()
    )
    has_nav_requirements = bool(plan.nav_checks) or any(
        "enemy" in a.tags or "ai" in a.tags or "GameForgeEnemy" in a.runtime_class
        for a in plan.actors
    )

    if not (is_board_layout and not has_nav_requirements):
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

    new_level_indices = [i for i, op in enumerate(ops) if op.op == "new_level"]
    load_level_indices = [i for i, op in enumerate(ops) if op.op == "load_level"]
    if load_level_indices and (not new_level_indices or load_level_indices[0] < new_level_indices[0]):
        raise ValueError("Invalid operation sequence: load_level cannot precede new_level during assembly")

    return ops


def _parse_location_record(rec: Any) -> Optional[Tuple[float, float, float]]:
    """Robustly extract (x, y, z) coordinates from diverse actual record representations."""
    if rec is None:
        return None
    if isinstance(rec, (list, tuple)) and len(rec) >= 3:
        return float(rec[0]), float(rec[1]), float(rec[2])
    if hasattr(rec, "x") and hasattr(rec, "y") and hasattr(rec, "z"):
        return float(rec.x), float(rec.y), float(rec.z)
    if isinstance(rec, dict):
        if "location" in rec:
            loc_sub = rec["location"]
            if isinstance(loc_sub, (list, tuple)) and len(loc_sub) >= 3:
                return float(loc_sub[0]), float(loc_sub[1]), float(loc_sub[2])
            if hasattr(loc_sub, "x") and hasattr(loc_sub, "y") and hasattr(loc_sub, "z"):
                return float(loc_sub.x), float(loc_sub.y), float(loc_sub.z)
            if isinstance(loc_sub, dict) and "x" in loc_sub:
                return float(loc_sub.get("x", 0.0)), float(loc_sub.get("y", 0.0)), float(loc_sub.get("z", 0.0))
        if "x" in rec and "y" in rec:
            return float(rec.get("x", 0.0)), float(rec.get("y", 0.0)), float(rec.get("z", 0.0))
    return None


def verify_placed_actor_transforms(
    plan: LevelPlan,
    actual_records: Dict[str, Dict[str, Any]],
    tolerance_cm: float = 50.0,
    severe_tolerance_cm: float = 500.0,
    yaw_tolerance_deg: float = 15.0,
) -> List[str]:
    """Verify that placed actors match their planned locations and rotations within tolerance."""
    warnings: List[str] = []

    ps_rec = actual_records.get("GF_PlayerStart") or actual_records.get("PlayerStart")
    if ps_rec is not None and plan.player_start:
        coords = _parse_location_record(ps_rec)
        if coords:
            ax, ay, az = coords
            px, py, pz = plan.player_start
            dist = ((ax - px) ** 2 + (ay - py) ** 2 + (az - pz) ** 2) ** 0.5
            if dist > tolerance_cm:
                prefix = "CRITICAL: " if dist > severe_tolerance_cm else ""
                warnings.append(
                    f"{prefix}PlayerStart location mismatch: requested ({px:.1f}, {py:.1f}, {pz:.1f}) "
                    f"vs confirmed ({ax:.1f}, {ay:.1f}, {az:.1f}), delta={dist:.1f}cm > tolerance={tolerance_cm:.1f}cm"
                )

    for a in plan.actors:
        label = a.actor_id
        rec = actual_records.get(label) or actual_records.get(f"GF_{label}") or actual_records.get(a.entity_id)
        if rec is None:
            continue
        coords = _parse_location_record(rec)
        if coords:
            ax, ay, az = coords
            px, py, pz = a.location
            if a.snap_to_ground:
                az = pz
            dist = ((ax - px) ** 2 + (ay - py) ** 2 + (az - pz) ** 2) ** 0.5
            if dist > tolerance_cm:
                prefix = "CRITICAL: " if dist > severe_tolerance_cm else ""
                warnings.append(
                    f"{prefix}Actor {label} ({a.runtime_class}) location mismatch: requested ({px:.1f}, {py:.1f}, {pz:.1f}) "
                    f"vs confirmed ({ax:.1f}, {ay:.1f}, {az:.1f}), delta={dist:.1f}cm > tolerance={tolerance_cm:.1f}cm"
                )

        if a.yaw != 0.0 and isinstance(rec, dict):
            rot = rec.get("rotation")
            actual_yaw = None
            if isinstance(rot, dict) and "yaw" in rot:
                actual_yaw = float(rot["yaw"])
            elif isinstance(rot, (list, tuple)) and len(rot) >= 2:
                actual_yaw = float(rot[1])
            elif "yaw" in rec:
                actual_yaw = float(rec["yaw"])

            if actual_yaw is not None:
                yaw_diff = abs((actual_yaw - a.yaw + 180.0) % 360.0 - 180.0)
                if yaw_diff > yaw_tolerance_deg:
                    warnings.append(
                        f"Actor {label} yaw mismatch: requested {a.yaw:.1f} deg vs confirmed {actual_yaw:.1f} deg, "
                        f"delta={yaw_diff:.1f} deg > tolerance={yaw_tolerance_deg:.1f} deg"
                    )

    return warnings
