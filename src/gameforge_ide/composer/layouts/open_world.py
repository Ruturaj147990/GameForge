"""Composer open world layout (WI-6.3).

Open world level plan with landscape creation, biomes lighting rig,
scattered POIs, landmark, and far goal.
"""
from __future__ import annotations

import random
from typing import Any, List, Tuple
from ..model import LevelPlan, OpCall, PlacedActor
from ...backend.tools import biomes


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    biome_name = getattr(level, "biome", "forest")
    if biome_name not in biomes.BIOMES:
        biome_name = "forest"

    seed = getattr(level, "seed", rng.randint(1, 999999))
    size_m = getattr(level, "size_m", (200.0, 200.0))
    if hasattr(size_m, "x") and hasattr(size_m, "y"):
        size_m = (float(size_m.x), float(size_m.y))
    elif isinstance(size_m, (int, float)):
        size_m = (float(size_m), float(size_m))
    half_x_cm = (size_m[0] * 100.0) / 2.0
    half_y_cm = (size_m[1] * 100.0) / 2.0

    geometry_ops: List[OpCall] = []

    # Floor / ground plane: 100cm cube scaled to match open world area
    floor_scale_x = (half_x_cm * 2.0) / 100.0
    floor_scale_y = (half_y_cm * 2.0) / 100.0
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_OpenWorld_Ground",
                "location": {"x": 0.0, "y": 0.0, "z": -10.0},
                "scale": {"x": floor_scale_x, "y": floor_scale_y, "z": 0.2},
            },
            purpose="Spawn open world ground plane",
        )
    )

    # Lighting preset is recorded on LevelPlan and emitted by level_ops.py
    lighting_preset = getattr(level, "lighting", "day")

    # Player start near one edge
    player_start = (-half_x_cm * 0.75, 0.0, 100.0)

    # Goal near opposite edge
    goal_loc = (half_x_cm * 0.75, 0.0, 100.0)
    goal_actor = PlacedActor(
        actor_id="goal_0",
        entity_id="goal",
        runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
        location=goal_loc,
        yaw=0.0,
        tags=["GF_E_goal", "GF_Owned", "GF_Goal"],
        properties={},
    )

    # Landmark mid-way
    landmark_loc = (0.0, half_y_cm * 0.3, 100.0)
    landmark_actor = PlacedActor(
        actor_id="landmark_0",
        entity_id="landmark",
        runtime_class="/Script/GameForgeRuntime.GameForgeLandmark",
        location=landmark_loc,
        yaw=0.0,
        tags=["GF_E_landmark", "GF_Owned", "GF_Landmark"],
        properties={},
    )

    actors: List[PlacedActor] = [goal_actor, landmark_actor]

    center = (0.0, 0.0, 100.0)
    extent = (half_x_cm + 500.0, half_y_cm + 500.0, 1000.0)

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=(size_m[0] > 400.0),
        player_start=player_start,
        nav_bounds=(center, extent),
        geometry_ops=geometry_ops,
        actors=actors,
        lighting=lighting_preset,
        nav_checks=[("player_start", "landmark_0"), ("landmark_0", "goal_0")],
    )
