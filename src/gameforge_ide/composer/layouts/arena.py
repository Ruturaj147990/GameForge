"""Composer arena layout (WI-6.3).

Walled combat arena layout with floor, perimeter walls, cover blocks,
and ring-shaped spawn points around a central player spawn.
"""
from __future__ import annotations

import math
import random
from typing import Any, List, Tuple
from ..model import LevelPlan, OpCall, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    size_m = getattr(level, "size_m", (60.0, 60.0))
    if hasattr(size_m, "x") and hasattr(size_m, "y"):
        size_m = (float(size_m.x), float(size_m.y))
    elif isinstance(size_m, (int, float)):
        size_m = (float(size_m), float(size_m))
    half_x_cm = (size_m[0] * 100.0) / 2.0
    half_y_cm = (size_m[1] * 100.0) / 2.0

    geometry_ops: List[OpCall] = []

    # 1. Floor: 100cm cube scaled to (2*half_x/100, 2*half_y/100, 0.1)
    floor_scale_x = (half_x_cm * 2.0) / 100.0
    floor_scale_y = (half_y_cm * 2.0) / 100.0
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Arena_Floor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                "location": {"x": 0.0, "y": 0.0, "z": -5.0},
                "scale": {"x": floor_scale_x, "y": floor_scale_y, "z": 0.1},
            },
            purpose="Spawn arena floor",
        )
    )

    # 2. Four perimeter walls (height 300cm, thickness 50cm)
    wall_h = 300.0
    wall_thick = 50.0
    # North wall (+X)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Wall_North",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": half_x_cm + wall_thick / 2.0, "y": 0.0, "z": wall_h / 2.0},
                "scale": {"x": wall_thick / 100.0, "y": floor_scale_y, "z": wall_h / 100.0},
            },
            purpose="Spawn north wall",
        )
    )
    # South wall (-X)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Wall_South",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": -half_x_cm - wall_thick / 2.0, "y": 0.0, "z": wall_h / 2.0},
                "scale": {"x": wall_thick / 100.0, "y": floor_scale_y, "z": wall_h / 100.0},
            },
            purpose="Spawn south wall",
        )
    )
    # East wall (+Y)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Wall_East",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 0.0, "y": half_y_cm + wall_thick / 2.0, "z": wall_h / 2.0},
                "scale": {"x": floor_scale_x, "y": wall_thick / 100.0, "z": wall_h / 100.0},
            },
            purpose="Spawn east wall",
        )
    )
    # West wall (-Y)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Wall_West",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 0.0, "y": -half_y_cm - wall_thick / 2.0, "z": wall_h / 2.0},
                "scale": {"x": floor_scale_x, "y": wall_thick / 100.0, "z": wall_h / 100.0},
            },
            purpose="Spawn west wall",
        )
    )

    # 3. Cover blocks: 4-6 blocks, >= 600cm apart, >= 800cm from origin
    num_cover = rng.randint(4, 6)
    cover_locs: List[Tuple[float, float]] = []
    for i in range(num_cover):
        for _ in range(40):
            cx = rng.uniform(-half_x_cm * 0.7, half_x_cm * 0.7)
            cy = rng.uniform(-half_y_cm * 0.7, half_y_cm * 0.7)
            if math.hypot(cx, cy) < 800.0:
                continue
            if any(math.hypot(cx - ox, cy - oy) < 600.0 for ox, oy in cover_locs):
                continue
            cover_locs.append((cx, cy))
            geometry_ops.append(
                OpCall(
                    op="spawn_actor",
                    args={
                        "actor_class": "StaticMeshActor",
                        "label": f"GF_Cover_{i}",
                        "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                        "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                        "location": {"x": cx, "y": cy, "z": 100.0},
                        "scale": {"x": 2.0, "y": 2.0, "z": 2.0},
                    },
                    purpose=f"Spawn cover block {i}",
                )
            )
            break

    nav_extent = (half_x_cm + 200.0, half_y_cm + 200.0, 500.0)

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), nav_extent),
        geometry_ops=geometry_ops,
        actors=[],
        lighting=getattr(level, "lighting", "day"),
        nav_checks=[],
    )
