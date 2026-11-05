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
    "snakes_and_ladders",
    "seed",
    "difficulty",
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
        emit(
            "spawn_actor",
            {
                "actor_class": "PlayerStart",
                "label": "GF_PlayerStart",
                "location": {"x": plan.player_start[0], "y": plan.player_start[1], "z": plan.player_start[2]},
            },
            purpose="Spawn primary player start point",
        )
        has_spawned_player_start = True

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

    # 4. Placed actors (filter out any duplicates of PlayerStart or duplicate labels)
    spawned_labels: Set[str] = {"GF_PlayerStart"} if has_spawned_player_start else set()
    for a in plan.actors:
        if a.actor_id in spawned_labels:
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
            if prop_val is None:
                continue
            if not isinstance(prop_name, str) or not prop_name.strip():
                continue
            p_clean = prop_name.strip()
            if p_clean.lower() in NON_UE_GDS_PROPS or p_clean.startswith("_"):
                continue
            # Guard: property name must be a valid C++/Unreal identifier
            if not p_clean.isidentifier():
                continue
            # Guard: filter complex nested dicts that Unreal cannot assign directly
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
    # For grid board / card / puzzle games with no enemy AI or navigation checks,
    # skip NavMeshBoundsVolume and nav_rebuild to prevent rebuild warnings/errors.
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

    # Validation: ensure new_level always precedes load_level in assembly sequence
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
    """Verify that placed actors match their planned locations and rotations within tolerance.

    Args:
        plan: The LevelPlan containing planned actors.
        actual_records: Map of actor label -> dict containing location/rotation info.
        tolerance_cm: Maximum allowed Euclidean distance in centimetres for minor warnings.
        severe_tolerance_cm: Threshold distance above which a discrepancy is deemed critical.
        yaw_tolerance_deg: Maximum allowed yaw angle difference in degrees.

    Returns:
        List of warning strings describing any location discrepancies.
    """
    warnings: List[str] = []

    # Verify primary PlayerStart if recorded
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
            dist = ((ax - px) ** 2 + (ay - py) ** 2 + (az - pz) ** 2) ** 0.5
            if dist > tolerance_cm:
                prefix = "CRITICAL: " if dist > severe_tolerance_cm else ""
                warnings.append(
                    f"{prefix}Actor {label} ({a.runtime_class}) location mismatch: requested ({px:.1f}, {py:.1f}, {pz:.1f}) "
                    f"vs confirmed ({ax:.1f}, {ay:.1f}, {az:.1f}), delta={dist:.1f}cm > tolerance={tolerance_cm:.1f}cm"
                )

        # Check yaw rotation if planned yaw is non-zero
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
