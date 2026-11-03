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
    g_acc = gravity_scale * 980.0  # cm/s^2
    t_apex = jump_velocity / g_acc
    max_h = (jump_velocity ** 2) / (2.0 * g_acc)

    max_allowable_h = 0.8 * max_h
    if height_delta_cm > max_allowable_h:
        return False, max_allowable_h, 0.0

    # Fall time from apex to (max_h - height_delta_cm)
    fall_dist = max_h - height_delta_cm
    t_fall = math.sqrt((2.0 * fall_dist) / g_acc)
    t_air = t_apex + t_fall
    max_allowable_gap = 0.8 * move_speed * t_air

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
    num_pickups = 3
    pickup_entity_id = "pickups"
    if hasattr(gds, "entities"):
        for ent in gds.entities:
            if (
                ent.kind in ("pickup", "collectible")
                or "pickup" in ent.entity_id.lower()
                or getattr(ent, "module", "") == "kit.pickup"
            ):
                c = getattr(ent, "count", None) or ent.props.get("count", 3)
                num_pickups = max(num_pickups, int(c))
                pickup_entity_id = ent.entity_id
    num_platforms = max(7, num_pickups + 4)

    # 1. Start pad at origin
    start_pos = (0.0, 0.0, 0.0)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Platform_Start",
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

        # Validate with ballistic formula
        reachable, max_h, max_g = validate_jump_reachability(
            gap, h_delta, move_speed, jump_velocity, gravity_scale
        )
        if not reachable:
            # Clamp to safe bounds
            h_delta = min(h_delta, max_h * 0.9)
            gap = min(gap, max_g * 0.85)

        current_x += gap
        current_z += h_delta
        platform_tops.append((current_x, 0.0, current_z))

        # Spawn platform: 300x300cm cube, top at current_z
        geometry_ops.append(
            OpCall(
                op="spawn_actor",
                args={
                    "actor_class": "StaticMeshActor",
                    "label": f"GF_Platform_{i}",
                    "location": {"x": current_x, "y": 0.0, "z": current_z - 25.0},
                    "scale": {"x": 3.0, "y": 3.0, "z": 0.5},
                },
                purpose=f"Spawn platform {i}",
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
        tags=["GF_E_goal", "GF_Owned", "GF_Goal"],
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
        tags=["GF_E_checkpoint", "GF_Owned", "GF_Checkpoint"],
        properties={},
    )
    actors.append(cp_actor)

    # Distribute pickups across available platforms
    available_indices = [idx for idx in range(1, len(platform_tops) - 1) if idx != mid_idx]
    for p_i in range(min(num_pickups, len(available_indices))):
        idx = available_indices[p_i]
        pos = platform_tops[idx]
        pickup_actor = PlacedActor(
            actor_id=f"pickup_{p_i}",
            entity_id=pickup_entity_id,
            runtime_class="/Script/GameForgeRuntime.GameForgePickup",
            location=(pos[0], pos[1], pos[2] + 60.0),
            yaw=0.0,
            tags=[f"GF_E_{pickup_entity_id}", "GF_Owned", f"GF_Pickup_{p_i + 1}"],
            properties={},
        )
        actors.append(pickup_actor)

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
