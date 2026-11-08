"""Composer arena layout (WI-6.3).

Walled combat arena layout with floor, perimeter walls, cover blocks,
and ring-shaped spawn points around a central player spawn.
"""
from __future__ import annotations

import math
import random
from typing import Any, List, Tuple
from ..model import map_package_path, LevelPlan, OpCall, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = map_package_path(level_id)

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

    # 3. Cover: a mix of crates, pillars and low walls (all identical 2 m cubes before), more of it in bigger arenas.
    area_scale = max(1.0, (half_x_cm * half_y_cm) / (3000.0 * 3000.0))
    num_cover = int(rng.randint(6, 9) * min(3.0, area_scale))
    cover_locs: List[Tuple[float, float]] = []
    kinds = (
        ("Cube", (2.0, 2.0, 1.6), 0.0),        # crate stack
        ("Cylinder", (1.6, 1.6, 3.0), 0.0),    # pillar
        ("Cube", (4.0, 0.6, 1.2), None),       # low wall, random yaw
        ("Cube", (1.2, 1.2, 1.0), 0.0),        # small crate
    )
    for i in range(num_cover):
        for _ in range(40):
            cx = rng.uniform(-half_x_cm * 0.75, half_x_cm * 0.75)
            cy = rng.uniform(-half_y_cm * 0.75, half_y_cm * 0.75)
            if math.hypot(cx, cy) < 800.0:
                continue
            if any(math.hypot(cx - ox, cy - oy) < 650.0 for ox, oy in cover_locs):
                continue
            cover_locs.append((cx, cy))
            shape, (sx, sy, sz), yaw = kinds[rng.randrange(len(kinds))]
            yaw = rng.choice((0.0, 45.0, 90.0, 135.0)) if yaw is None else yaw
            geometry_ops.append(
                OpCall(
                    op="spawn_actor",
                    args={
                        "actor_class": "StaticMeshActor",
                        "label": f"GF_Cover_{i}",
                        "static_mesh": f"/Engine/BasicShapes/{shape}.{shape}",
                        "location": {"x": round(cx, 1), "y": round(cy, 1), "z": round(sz * 50.0, 1)},
                        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                        "scale": {"x": sx, "y": sy, "z": sz},
                    },
                    purpose=f"Spawn cover {i} ({shape.lower()})",
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
