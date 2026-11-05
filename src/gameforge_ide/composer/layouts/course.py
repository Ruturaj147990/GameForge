"""Composer platformer course layout (WI-6.3).

Generates linear platforming courses along +X with ballistic reachability
validation for jumps, start pad, goal pad, and intermediate checkpoints.
"""
from __future__ import annotations

import math
import random
from typing import Any, List, Optional, Tuple
from ..model import LevelPlan, OpCall, PlacedActor


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
        # At apex height, player still traverses horizontal distance move_speed * t_apex
        apex_gap = 0.85 * move_speed * t_apex
        return False, max_allowable_h, max(150.0, apex_gap)

    # Fall time from apex to (max_h - height_delta_cm)
    fall_dist = max(0.0, max_h - height_delta_cm)
    t_fall = math.sqrt((2.0 * fall_dist) / g_acc)
    t_air = t_apex + t_fall
    max_allowable_gap = 0.85 * move_speed * t_air

    is_reachable = gap_cm <= max_allowable_gap
    return is_reachable, max_allowable_h, max_allowable_gap


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    # Extract physics properties from player or defaults
    move_speed = 600.0
    jump_velocity = 650.0
    gravity_scale = 1.2
    if hasattr(gds, "entities"):
        for ent in gds.entities:
            if ent.kind in ("player", "character", "hero") or ent.entity_id == "player":
                move_speed = float(ent.props.get("move_speed", ent.props.get("player_speed", 600.0)))
                jump_velocity = float(ent.props.get("jump_velocity", 650.0))
                gravity_scale = float(ent.props.get("gravity_scale", 1.2))

    geometry_ops: List[OpCall] = []
    actors: List[PlacedActor] = []

    # Number of platforms: ensure enough platforms for all pickups + checkpoint + goal
    pickup_requests: List[Tuple[str, int]] = []
    if hasattr(gds, "entities"):
        for ent in gds.entities:
            if (
                ent.kind in ("pickup", "collectible")
                or "pickup" in ent.entity_id.lower()
                or getattr(ent, "module", "") == "kit.pickup"
            ):
                c = int(getattr(ent, "count", None) or ent.props.get("count", 3))
                pickup_requests.append((ent.entity_id, c))
    if not pickup_requests:
        pickup_requests = [("pickups", 3)]
    total_pickups = sum(c for _, c in pickup_requests)
    num_platforms = max(7, total_pickups + 4)

    # 1. Start pad at origin
    start_pos = (0.0, 0.0, 0.0)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Platform_Start",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                "location": {"x": 0.0, "y": 0.0, "z": -25.0},
                "scale": {"x": 4.0, "y": 4.0, "z": 0.5},
            },
            purpose="Spawn start platform",
        )
    )

    current_x = 0.0
    current_z = 0.0
    platform_tops: List[Tuple[float, float, float]] = [start_pos]

    for i in range(1, num_platforms):
        # Generate reachable gap (250 - 450 cm) and step (-100 to +120 cm)
        gap = rng.uniform(260.0, 420.0)
        h_delta = rng.uniform(-80.0, 110.0)

        # Enforce walkable slope <= 35.0 degrees between consecutive platforms
        max_walkable_h = gap * math.tan(math.radians(35.0))
        if abs(h_delta) > max_walkable_h:
            h_delta = math.copysign(max_walkable_h, h_delta)

        # Validate with ballistic formula
        reachable, max_h, max_g = validate_jump_reachability(
            gap, h_delta, move_speed, jump_velocity, gravity_scale
        )
        if not reachable:
            # Clamp to safe bounds
            h_delta = min(h_delta, max_h)
            gap = max(150.0, min(gap, max_g))
            max_walkable_h = gap * math.tan(math.radians(35.0))
            if abs(h_delta) > max_walkable_h:
                h_delta = math.copysign(max_walkable_h, h_delta)

        # Clamp current_z to prevent dropping into KillZ (-500) or excessive climbing
        target_z = max(-200.0, min(800.0, current_z + h_delta))
        dz_target = target_z - current_z
        if abs(dz_target) > max_walkable_h:
            target_z = current_z + math.copysign(max_walkable_h, dz_target)
        current_z = target_z
        current_x += gap
        platform_tops.append((current_x, 0.0, current_z))

        # Choose distinct material for goal platform vs intermediate platforms
        is_goal_platform = (i == num_platforms - 1)
        plat_material = (
            "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Orange"
            if is_goal_platform
            else "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray"
        )

        # Spawn platform: 300x300cm cube, top at current_z
        geometry_ops.append(
            OpCall(
                op="spawn_actor",
                args={
                    "actor_class": "StaticMeshActor",
                    "label": f"GF_Platform_{i}",
                    "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                    "material": plat_material,
                    "location": {"x": current_x, "y": 0.0, "z": current_z - 25.0},
                    "scale": {"x": 3.0, "y": 3.0, "z": 0.5},
                },
                purpose=f"Spawn platform {i}",
            )
        )

        # Spawn connecting stone walkway ramp between consecutive platforms for continuous traversal & NavMesh
        prev_x, _, prev_z = platform_tops[i - 1]
        mid_x = (prev_x + current_x) / 2.0
        mid_z = (prev_z + current_z) / 2.0 - 25.0
        dx = current_x - prev_x
        dz = current_z - prev_z
        span = math.hypot(dx, dz)
        raw_pitch = math.degrees(math.atan2(dz, dx)) if dx != 0.0 else 0.0
        # Clamp pitch to safe walkable slope (<= 35 degrees) ensuring unbroken NavMesh generation
        pitch_deg = max(-35.0, min(35.0, raw_pitch))

        geometry_ops.append(
            OpCall(
                op="spawn_actor",
                args={
                    "actor_class": "StaticMeshActor",
                    "label": f"GF_Walkway_{i}",
                    "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                    "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                    "location": {"x": mid_x, "y": 0.0, "z": mid_z},
                    "rotation": {"pitch": round(pitch_deg, 2), "yaw": 0.0, "roll": 0.0},
                    "scale": {"x": max(1.0, round(span / 100.0, 2)), "y": 1.5, "z": 0.5},
                },
                purpose=f"Spawn stone walkway ramp connecting platform {i-1} to {i}",
            )
        )

    # Spawn safety floor beneath course span to prevent unrecoverable void fall
    course_length = current_x + 1000.0
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Course_SafetyFloor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": current_x / 2.0, "y": 0.0, "z": -450.0},
                "scale": {"x": max(10.0, course_length / 100.0), "y": 20.0, "z": 0.2},
            },
            purpose="Spawn course safety floor to prevent void fall",
        )
    )

    # Goal pad on the last platform
    last_pos = platform_tops[-1]
    goal_actor = PlacedActor(
        actor_id="goal_0",
        entity_id="goal",
        runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
        location=(last_pos[0], last_pos[1], last_pos[2] + 50.0),
        yaw=0.0,
        tags=[
            "GF_E_goal",
            "GF_Owned",
            "GF_Goal",
            "goal",
            "Goal",
            "Goal_1",
            "goal_1",
            "GF_Goal_1",
            "GF_goal_1",
            "goal_0",
        ],
        properties={},
    )
    actors.append(goal_actor)

    # Checkpoint on middle platform
    mid_idx = len(platform_tops) // 2
    mid_pos = platform_tops[mid_idx]
    cp_actor = PlacedActor(
        actor_id="cp_0",
        entity_id="checkpoint",
        runtime_class="/Script/GameForgeRuntime.GameForgeCheckpoint",
        location=(mid_pos[0], mid_pos[1], mid_pos[2] + 50.0),
        yaw=0.0,
        tags=[
            "GF_E_checkpoint",
            "GF_Owned",
            "GF_Checkpoint",
            "checkpoint",
            "Checkpoint",
            "Checkpoint_1",
            "checkpoint_1",
            "GF_Checkpoint_1",
            "GF_checkpoint_1",
            "cp_0",
        ],
        properties={},
    )
    actors.append(cp_actor)

    # Distribute pickups across available platforms
    available_indices = [idx for idx in range(1, len(platform_tops) - 1) if idx != mid_idx]
    pick_idx = 0
    for entity_id, count in pickup_requests:
        for c_i in range(count):
            if pick_idx >= len(available_indices):
                break
            idx = available_indices[pick_idx]
            pos = platform_tops[idx]
            pickup_actor = PlacedActor(
                actor_id=f"{entity_id}_{c_i}",
                entity_id=entity_id,
                runtime_class="/Script/GameForgeRuntime.GameForgePickup",
                location=(pos[0], pos[1], pos[2] + 60.0),
                yaw=0.0,
                tags=[
                    f"GF_E_{entity_id}",
                    "GF_Owned",
                    "pickup",
                    "Pickup",
                    f"GF_Pickup_{c_i + 1}",
                    f"GF_pickup_{c_i + 1}",
                    f"Pickup_{c_i + 1}",
                    f"pickup_{c_i + 1}",
                    f"{entity_id}_{c_i}",
                ],
                properties={},
            )
            actors.append(pickup_actor)
            pick_idx += 1

    nav_center = (current_x / 2.0, 0.0, current_z / 2.0)
    nav_extent = (current_x / 2.0 + 500.0, 800.0, 1500.0)

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=(nav_center, nav_extent),
        geometry_ops=geometry_ops,
        actors=actors,
        lighting=getattr(level, "lighting", "day"),
        nav_checks=[("player_start", "goal_0")],
    )
