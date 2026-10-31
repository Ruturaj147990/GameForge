"""Composer dungeon rooms layout (WI-6.3).

Generates interconnected modular rooms and corridors using dungeon_layout
generator on a 400cm grid with floors, perimeter walls, and point lights.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple
from ..model import LevelPlan, OpCall, PlacedActor
from ...backend.tools import dungeon_layout


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    seed = getattr(level, "seed", rng.randint(1, 999999))
    num_rooms = rng.randint(4, 7)

    dungeon = dungeon_layout.generate(seed, num_rooms)
    grid_cm = 400.0
    placements = dungeon_layout.kit_placements(dungeon["cells"], grid=grid_cm)

    geometry_ops: List[OpCall] = []

    # Spawn floors and walls
    for i, piece in enumerate(placements):
        loc = piece["location"]
        yaw = piece["yaw"]
        p_type = piece["piece"]
        if p_type == "Floor":
            geometry_ops.append(
                OpCall(
                    op="spawn_actor",
                    args={
                        "actor_class": "StaticMeshActor",
                        "label": f"GF_Dungeon_Floor_{i}",
                        "location": {"x": loc[0], "y": loc[1], "z": -10.0},
                        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                        "scale": {"x": 4.0, "y": 4.0, "z": 0.2},
                    },
                    purpose=f"Spawn dungeon floor piece {i}",
                )
            )
        elif p_type == "Wall":
            geometry_ops.append(
                OpCall(
                    op="spawn_actor",
                    args={
                        "actor_class": "StaticMeshActor",
                        "label": f"GF_Dungeon_Wall_{i}",
                        "location": {"x": loc[0], "y": loc[1], "z": 150.0},
                        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                        "scale": {"x": 4.0, "y": 0.5, "z": 3.0},
                    },
                    purpose=f"Spawn dungeon wall piece {i}",
                )
            )

    # Rooms info
    rooms = dungeon["rooms"]
    first_room = rooms[0]
    last_room = rooms[-1]

    # Player start in first room center
    p_start_x = (first_room.x + first_room.w / 2.0) * grid_cm
    p_start_y = (first_room.y + first_room.h / 2.0) * grid_cm
    player_start = (p_start_x, p_start_y, 100.0)

    # Goal in last room center
    goal_x = (last_room.x + last_room.w / 2.0) * grid_cm
    goal_y = (last_room.y + last_room.h / 2.0) * grid_cm
    goal_actor = PlacedActor(
        actor_id="goal_0",
        entity_id="goal",
        runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
        location=(goal_x, goal_y, 100.0),
        yaw=0.0,
        tags=["GF_E_goal", "GF_Owned", "GF_Goal"],
        properties={},
    )

    actors: List[PlacedActor] = [goal_actor]

    # Spawn PointLights in room centres (WI-6.4: indoor preset: intensity 5000, attenuation 1500cm)
    for r_idx, rm in enumerate(rooms):
        rx = (rm.x + rm.w / 2.0) * grid_cm
        ry = (rm.y + rm.h / 2.0) * grid_cm
        geometry_ops.append(
            OpCall(
                op="spawn_actor",
                args={
                    "actor_class": "PointLight",
                    "label": f"GF_Room_Light_{r_idx}",
                    "location": {"x": rx, "y": ry, "z": 250.0},
                },
                purpose=f"Spawn room point light {r_idx}",
            )
        )

    # Nav bounds covering all cells
    all_x = [c[0] * grid_cm for c in dungeon["cells"]]
    all_y = [c[1] * grid_cm for c in dungeon["cells"]]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    center = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, 150.0)
    extent = ((max_x - min_x) / 2.0 + 400.0, (max_y - min_y) / 2.0 + 400.0, 500.0)

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=player_start,
        nav_bounds=(center, extent),
        geometry_ops=geometry_ops,
        actors=actors,
        lighting="indoor",
        nav_checks=[("player_start", "goal_0")],
    )
