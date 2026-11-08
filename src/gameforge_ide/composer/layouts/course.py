"""Composer platformer course layout (WI-6.3, reworked).

A course of floating platforms the player has to *jump* across. The previous version placed 3 m platforms 2.6-4.2 m
apart centre-to-centre (so edge gaps of -0.4..1.2 m: platforms touched or overlapped) and then bridged every gap with a
walkway ramp, so the "platformer" was a straight flat walk with no jump required.

Now:
* gaps are measured edge-to-edge and sized from the player's real ballistic jump (``validate_jump_reachability``),
  scaled by difficulty;
* the course zig-zags laterally and climbs, with varied platform sizes;
* some gaps get moving platforms, hazard platforms and bonus pickups that need a jump;
* walkway bridges only exist on easy difficulty (and are then narrow planks), so navmesh reachability checks are only
  emitted when the course is actually walkable;
* a kill volume below the course catches falls and the game mode respawns the player at the last checkpoint.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from ..model import LevelPlan, OpCall, PlacedActor, map_package_path


def validate_jump_reachability(
    gap_cm: float,
    height_delta_cm: float,
    move_speed: float = 600.0,
    jump_velocity: float = 650.0,
    gravity_scale: float = 1.2,
) -> Tuple[bool, float, float]:
    """Validate jump reachability using the ballistic flight formula (WI-6.3).

    Returns:
        (is_reachable, max_allowable_h_cm, max_allowable_gap_cm)
    """
    g_acc = max(100.0, gravity_scale * 980.0)  # cm/s^2
    t_apex = jump_velocity / g_acc
    max_h = (jump_velocity ** 2) / (2.0 * g_acc)

    # Allow up to 92% of peak jump height for execution margin
    max_allowable_h = 0.92 * max_h
    if height_delta_cm > max_allowable_h:
        apex_gap = 0.85 * move_speed * t_apex
        return False, max_allowable_h, max(150.0, apex_gap)

    fall_dist = max(0.0, max_h - height_delta_cm)
    t_fall = math.sqrt((2.0 * fall_dist) / g_acc)
    t_air = t_apex + t_fall
    max_allowable_gap = 0.85 * move_speed * t_air

    is_reachable = gap_cm <= max_allowable_gap
    return is_reachable, max_allowable_h, max_allowable_gap


_DIFFICULTY = {
    # (gap fraction of max jump, platform size m (min, max), rise fraction of max height, bridge every N gaps (0 = none))
    "easy": (0.35, (3.6, 4.6), 0.30, 1),
    "normal": (0.55, (2.8, 3.8), 0.45, 0),
    "hard": (0.72, (2.0, 3.0), 0.60, 0),
}


def _player_physics(gds: Any) -> Tuple[float, float, float, int]:
    move_speed, jump_velocity, gravity_scale, jumps = 600.0, 700.0, 1.2, 1
    for ent in getattr(gds, "entities", []) or []:
        kind = str(getattr(ent.kind, "value", ent.kind))
        if kind in ("player", "character", "hero") or ent.entity_id == "player":
            p = ent.props
            move_speed = float(p.get("move_speed", p.get("player_speed", move_speed)) or move_speed)
            jump_velocity = float(p.get("jump_velocity", jump_velocity) or jump_velocity)
            gravity_scale = float(p.get("gravity_scale", gravity_scale) or gravity_scale)
            jumps = 2 if p.get("double_jump") else int(p.get("max_jumps", 1) or 1)
    return move_speed, jump_velocity, gravity_scale, jumps


def _count_kind(gds: Any, kinds: Tuple[str, ...], module: Optional[str] = None) -> List[Tuple[Any, int]]:
    out = []
    for ent in getattr(gds, "entities", []) or []:
        kind = str(getattr(ent.kind, "value", ent.kind))
        if kind in kinds or (module and getattr(ent, "module", "") == module):
            out.append((ent, int(getattr(ent, "count", 1) or 1)))
    return out


def _tags(entity_id: str, kind: str, i: int, actor_id: str) -> List[str]:
    cap = kind.capitalize()
    return list(dict.fromkeys([f"GF_E_{entity_id}", "GF_Owned", f"GF_{cap}", kind, cap, f"{cap}_{i + 1}",
                               f"{kind}_{i + 1}", f"GF_{cap}_{i + 1}", actor_id]))


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = map_package_path(level_id)

    difficulty = str(getattr(getattr(gds, "progression", None), "difficulty", "normal") or "normal")
    gap_frac, (size_min, size_max), rise_frac, bridge_every = _DIFFICULTY.get(difficulty, _DIFFICULTY["normal"])
    move_speed, jump_velocity, gravity_scale, jumps = _player_physics(gds)
    if jumps > 1:
        gap_frac = min(0.85, gap_frac + 0.12)   # double jump earns wider gaps
        rise_frac = min(0.8, rise_frac + 0.15)

    _ok, max_h, max_gap_flat = validate_jump_reachability(0.0, 0.0, move_speed, jump_velocity, gravity_scale)

    pickup_requests = [(e.entity_id, c, e) for e, c in _count_kind(gds, ("pickup", "collectible"), "kit.pickup")]
    hazard_requests = [(e.entity_id, c, e) for e, c in _count_kind(gds, ("hazard",), "kit.hazard")]
    mover_requests = [(e.entity_id, c, e) for e, c in _count_kind(gds, ("moving_platform",), "kit.moving_platform")]
    checkpoint_ents = [e for e, _c in _count_kind(gds, ("checkpoint",), "kit.checkpoint")]
    goal_ent = next((e for e, _c in _count_kind(gds, ("goal",), "kit.goal")), None)

    total_pickups = sum(c for _id, c, _e in pickup_requests)
    num_platforms = max(9, min(40, int(math.ceil(total_pickups * 0.8)) + 6))

    geometry_ops: List[OpCall] = []
    actors: List[PlacedActor] = []

    # 1. Start pad
    start_half = 300.0
    geometry_ops.append(OpCall(op="spawn_actor", purpose="Spawn start platform", args={
        "actor_class": "StaticMeshActor", "label": "GF_Platform_Start",
        "static_mesh": "/Engine/BasicShapes/Cube.Cube",
        "location": {"x": 0.0, "y": 0.0, "z": -25.0}, "scale": {"x": 6.0, "y": 6.0, "z": 0.5},
    }))

    # platform record: (x, y, top_z, half_size)
    platforms: List[Tuple[float, float, float, float]] = [(0.0, 0.0, 0.0, start_half)]
    gaps: List[Tuple[int, float]] = []   # (index of platform after the gap, edge gap cm)
    heading = 0.0
    for i in range(1, num_platforms):
        px, py, pz, phalf = platforms[-1]
        is_goal = i == num_platforms - 1
        half = (size_max * 50.0 + 60.0) if is_goal else rng.uniform(size_min, size_max) * 50.0

        # Height change first (gap depends on it), then a reachable edge gap for that height.
        rise = rng.uniform(-0.35, 1.0) * rise_frac * max_h
        target_z = max(-150.0, min(1600.0, pz + rise))
        dz = target_z - pz
        ok, _mh, max_gap = validate_jump_reachability(0.0, max(0.0, dz), move_speed, jump_velocity, gravity_scale)
        if not ok:
            dz = 0.85 * max_h
            target_z = pz + dz
            _ok2, _mh2, max_gap = validate_jump_reachability(0.0, dz, move_speed, jump_velocity, gravity_scale)
        gap = max(140.0, rng.uniform(0.75, 1.0) * gap_frac * max_gap)
        if i % 5 == 0 and not is_goal:
            gap = max(140.0, 0.35 * max_gap)   # breather jump

        # Zig-zag: turn up to +-35 degrees, but keep the course heading generally along +X.
        heading = max(-40.0, min(40.0, heading + rng.uniform(-35.0, 35.0)))
        rad = math.radians(heading)
        dist = phalf + gap + half
        nx, ny = px + math.cos(rad) * dist, py + math.sin(rad) * dist
        platforms.append((nx, ny, target_z, half))
        gaps.append((i, gap))

        geometry_ops.append(OpCall(op="spawn_actor", purpose=f"Spawn platform {i}", args={
            "actor_class": "StaticMeshActor", "label": "GF_Platform_Goal" if is_goal else f"GF_Platform_{i}",
            "static_mesh": "/Engine/BasicShapes/Cube.Cube",
            "location": {"x": round(nx, 1), "y": round(ny, 1), "z": round(target_z - 25.0, 1)},
            "rotation": {"pitch": 0.0, "yaw": round(heading, 1), "roll": 0.0},
            "scale": {"x": round(half / 50.0, 2), "y": round(half / 50.0, 2), "z": 0.5},
        }))

        # Easy courses get plank bridges so they stay walkable (and navmesh-verifiable).
        if bridge_every and i % bridge_every == 0:
            mid_x, mid_y = (px + nx) / 2.0, (py + ny) / 2.0
            mid_z = (pz + target_z) / 2.0 - 15.0
            span = math.hypot(nx - px, ny - py) - phalf - half + 80.0
            pitch = math.degrees(math.atan2(target_z - pz, max(1.0, span)))
            if abs(pitch) <= 30.0:
                geometry_ops.append(OpCall(op="spawn_actor", purpose=f"Plank bridge to platform {i}", args={
                    "actor_class": "StaticMeshActor", "label": f"GF_Walkway_{i}",
                    "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                    "location": {"x": round(mid_x, 1), "y": round(mid_y, 1), "z": round(mid_z, 1)},
                    "rotation": {"pitch": round(-pitch, 2), "yaw": round(heading, 1), "roll": 0.0},
                    "scale": {"x": round(max(1.0, span / 100.0), 2), "y": 1.2, "z": 0.3},
                }))

    walkable = bool(bridge_every)
    end_x = max(p[0] for p in platforms)
    min_y = min(p[1] for p in platforms) - 1500.0
    max_y = max(p[1] for p in platforms) + 1500.0

    # 2. Safety floor + kill volume (falls respawn at the last checkpoint via the game mode)
    floor_cx, floor_cy = end_x / 2.0, (min_y + max_y) / 2.0
    floor_len, floor_wid = end_x + 3000.0, (max_y - min_y)
    geometry_ops.append(OpCall(op="spawn_actor", purpose="Spawn course safety floor", args={
        "actor_class": "StaticMeshActor", "label": "GF_Course_SafetyFloor",
        "static_mesh": "/Engine/BasicShapes/Cube.Cube",
        "location": {"x": round(floor_cx, 1), "y": round(floor_cy, 1), "z": -450.0},
        "scale": {"x": round(floor_len / 100.0, 1), "y": round(floor_wid / 100.0, 1), "z": 0.2},
    }))
    actors.append(PlacedActor(
        actor_id="hazard_safety_floor", entity_id="hazard_safety_floor",
        runtime_class="/Script/GameForgeRuntime.GameForgeHazard",
        location=(round(floor_cx, 1), round(floor_cy, 1), -420.0),
        tags=["GF_Owned", "GF_Hazard", "hazard", "hazard_safety_floor", "safety_floor_hazard"],
        properties={"ShapeExtent": round(max(floor_len, floor_wid) / 2.0 + 500.0, 1), "bInstantKill": True,
                    "DamagePerSecond": 10000.0},
    ))

    # 3. Goal on the last platform
    gx, gy, gz, _gh = platforms[-1]
    goal_id = goal_ent.entity_id if goal_ent is not None else "goal"
    goal_props: Dict[str, Any] = {}
    if goal_ent is not None:
        if goal_ent.props.get("required_stat"):
            goal_props["RequiredStat"] = goal_ent.props["required_stat"]
            goal_props["RequiredValue"] = goal_ent.props.get("required_value", 0.0)
    actors.append(PlacedActor(actor_id=f"{goal_id}_0", entity_id=goal_id,
                              runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
                              location=(round(gx, 1), round(gy, 1), round(gz + 60.0, 1)),
                              tags=_tags(goal_id, "goal", 0, f"{goal_id}_0") + ["goal_0", "Goal"],
                              properties=goal_props))

    # 4. Checkpoints spread along the course
    cp_id = checkpoint_ents[0].entity_id if checkpoint_ents else "checkpoint"
    cp_count = max(1, min(4, (checkpoint_ents[0].count if checkpoint_ents else 1), num_platforms // 4))
    cp_indices = sorted({max(1, int(round((k + 1) * (num_platforms - 1) / (cp_count + 1)))) for k in range(cp_count)})
    for k, idx in enumerate(cp_indices):
        x, y, z, _h = platforms[idx]
        actors.append(PlacedActor(actor_id=f"{cp_id}_{k}", entity_id=cp_id,
                                  runtime_class="/Script/GameForgeRuntime.GameForgeCheckpoint",
                                  location=(round(x, 1), round(y, 1), round(z + 50.0, 1)),
                                  tags=_tags(cp_id, "checkpoint", k, f"{cp_id}_{k}") + (["cp_0"] if k == 0 else []),
                                  properties={}))
    reserved = set(cp_indices) | {0, num_platforms - 1}

    # 5. Hazard platforms (the hazard sits on one half of a platform so the jump target must be chosen)
    hazard_slots = [i for i in range(2, num_platforms - 1) if i not in reserved]
    rng.shuffle(hazard_slots)
    for entity_id, count, ent in hazard_requests:
        for c_i in range(min(count, max(0, len(hazard_slots) // 2))):
            idx = hazard_slots.pop()
            x, y, z, half = platforms[idx]
            off = half * 0.45 * rng.choice((-1.0, 1.0))
            props = {"ShapeExtent": round(max(40.0, half * 0.45), 1)}
            dps = ent.props.get("damage_per_second")
            if dps is not None:
                props["DamagePerSecond"] = float(dps)
            actors.append(PlacedActor(actor_id=f"{entity_id}_{c_i}", entity_id=entity_id,
                                      runtime_class="/Script/GameForgeRuntime.GameForgeHazard",
                                      location=(round(x + off, 1), round(y, 1), round(z + 5.0, 1)),
                                      tags=_tags(entity_id, "hazard", c_i, f"{entity_id}_{c_i}"), properties=props))
            reserved.add(idx)

    # 6. Moving platforms replace a few static ones: they shuttle sideways across their gap.
    mover_slots = [i for i in range(2, num_platforms - 1) if i not in reserved]
    rng.shuffle(mover_slots)
    mover_total = sum(c for _id, c, _e in mover_requests) or (2 if difficulty != "easy" and num_platforms >= 12 else 0)
    mover_entity = mover_requests[0][0] if mover_requests else "moving_platforms"
    for m_i in range(min(mover_total, len(mover_slots), 4)):
        idx = mover_slots.pop()
        x, y, z, half = platforms[idx]
        travel = rng.choice((-1.0, 1.0)) * rng.uniform(250.0, 450.0)
        actors.append(PlacedActor(actor_id=f"{mover_entity}_{m_i}", entity_id=mover_entity,
                                  runtime_class="/Script/GameForgeRuntime.GameForgeMovingPlatform",
                                  location=(round(x, 1), round(y - travel / 2.0, 1), round(z + 40.0, 1)),
                                  tags=_tags(mover_entity, "moving_platform", m_i, f"{mover_entity}_{m_i}"),
                                  properties={"EndOffset": {"x": 0.0, "y": round(travel, 1), "z": 0.0},
                                              "Seconds": round(rng.uniform(2.0, 3.5), 2), "PauseSeconds": 0.6}))
        reserved.add(idx)

    # 7. Pickups: on platforms, plus bonus pickups floating over gaps (reachable in a normal jump arc).
    on_platform = [i for i in range(1, num_platforms - 1) if i not in reserved] or list(range(1, num_platforms - 1))
    pick_slot = 0
    gap_iter = iter([g for g in gaps if g[0] not in reserved and g[1] > 200.0])
    for entity_id, count, ent in pickup_requests:
        props: Dict[str, Any] = {}
        if ent.props.get("value") is not None:
            props["Value"] = int(ent.props["value"])
        color = next((t.split(":", 1)[1] for t in ent.tags if isinstance(t, str) and t.startswith("color:")), None)
        if color and len(color) == 7:
            props["PickupColor"] = {"r": int(color[1:3], 16) / 255.0, "g": int(color[3:5], 16) / 255.0,
                                    "b": int(color[5:7], 16) / 255.0, "a": 1.0}
        for c_i in range(count):
            over_gap = next(gap_iter, None) if c_i % 3 == 2 else None
            if over_gap is not None:
                after = over_gap[0]
                ax, ay, az, _ah = platforms[after - 1]
                bx, by, bz, _bh = platforms[after]
                loc = ((ax + bx) / 2.0, (ay + by) / 2.0, max(az, bz) + 0.55 * max_h)
            else:
                idx = on_platform[pick_slot % len(on_platform)]
                x, y, z, half = platforms[idx]
                stack = pick_slot // len(on_platform)
                spread = (c_i % 3 - 1) * min(120.0, half * 0.5)
                loc = (x + spread, y, z + 70.0 + stack * 90.0)
                pick_slot += 1
            actor_id = f"{entity_id}_{c_i}"
            actors.append(PlacedActor(actor_id=actor_id, entity_id=entity_id,
                                      runtime_class="/Script/GameForgeRuntime.GameForgePickup",
                                      location=(round(loc[0], 1), round(loc[1], 1), round(loc[2], 1)),
                                      tags=_tags(entity_id, "pickup", c_i, actor_id), properties=dict(props)))

    nav_center = (end_x / 2.0, (min_y + max_y) / 2.0, 300.0)
    nav_extent = (end_x / 2.0 + 800.0, (max_y - min_y) / 2.0, 2000.0)
    goal_actor_id = f"{goal_id}_0"
    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=(nav_center, nav_extent),
        geometry_ops=geometry_ops,
        actors=actors,
        lighting=getattr(getattr(level, "lighting", "day"), "value", getattr(level, "lighting", "day")),
        # A jump course is not navmesh-connected; only bridged (easy) courses can be verified that way.
        nav_checks=[("player_start", goal_actor_id)] if walkable else [],
    )
