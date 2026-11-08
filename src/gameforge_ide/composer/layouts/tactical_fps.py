"""Composer tactical FPS bomb-defusal layout (Counter-Strike style).

Provides an authentic tactical bomb-defusal map:
- Counter-Terrorist (CT) Spawn Base
- Terrorist (T) Spawn Base
- Bomb Site A (with Site A marker and AGameForgeBombSite actor)
- Bomb Site B (with Site B marker and AGameForgeBombSite actor)
- Mid corridor, Long A, and B routes with cover crates
- 5 Opposing combat bots deployed at tactical defensive positions
"""
from __future__ import annotations

import math
import random
from typing import Any, List, Tuple
from ..model import map_package_path, LevelPlan, OpCall, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = map_package_path(level_id)

    geometry_ops: List[OpCall] = []
    actors: List[PlacedActor] = []

    # 1. Main Ground / Floor (60m x 60m)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Map_Floor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                "location": {"x": 0.0, "y": 0.0, "z": -10.0},
                "scale": {"x": 60.0, "y": 60.0, "z": 0.2},
            },
            purpose="Spawn tactical ground floor",
        )
    )

    # 2. Outer Boundary Walls (Height 400cm, Thickness 100cm)
    wall_h = 400.0
    wall_thick = 100.0
    half_size = 3000.0
    # North (+Y)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_OuterWall_North",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 0.0, "y": half_size, "z": wall_h / 2.0},
                "scale": {"x": 60.0, "y": 1.0, "z": wall_h / 100.0},
            },
            purpose="Spawn north boundary wall",
        )
    )
    # South (-Y)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_OuterWall_South",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 0.0, "y": -half_size, "z": wall_h / 2.0},
                "scale": {"x": 60.0, "y": 1.0, "z": wall_h / 100.0},
            },
            purpose="Spawn south boundary wall",
        )
    )
    # East (+X)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_OuterWall_East",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": half_size, "y": 0.0, "z": wall_h / 2.0},
                "scale": {"x": 1.0, "y": 60.0, "z": wall_h / 100.0},
            },
            purpose="Spawn east boundary wall",
        )
    )
    # West (-X)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_OuterWall_West",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": -half_size, "y": 0.0, "z": wall_h / 2.0},
                "scale": {"x": 1.0, "y": 60.0, "z": wall_h / 100.0},
            },
            purpose="Spawn west boundary wall",
        )
    )

    # 3. Corridor Dividers (Creating Mid, Long A, and B apartments)
    # Divider 1: Separating Mid and Site A
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Divider_Mid_A",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 700.0, "y": 400.0, "z": 175.0},
                "scale": {"x": 1.0, "y": 30.0, "z": 3.5},
            },
            purpose="Spawn corridor wall separating Mid and Site A",
        )
    )
    # Divider 2: Separating Mid and Site B
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Divider_Mid_B",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": -700.0, "y": 400.0, "z": 175.0},
                "scale": {"x": 1.0, "y": 30.0, "z": 3.5},
            },
            purpose="Spawn corridor wall separating Mid and Site B",
        )
    )

    # 4. Bomb Site A Marker Platform (Orange)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_SiteA_Platform",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Orange",
                "location": {"x": 1500.0, "y": 1400.0, "z": 10.0},
                "scale": {"x": 8.0, "y": 8.0, "z": 0.3},
            },
            purpose="Spawn Bomb Site A zone marker",
        )
    )
    # 5. Bomb Site B Marker Platform (Green)
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_SiteB_Platform",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Green",
                "location": {"x": -1500.0, "y": 1400.0, "z": 10.0},
                "scale": {"x": 8.0, "y": 8.0, "z": 0.3},
            },
            purpose="Spawn Bomb Site B zone marker",
        )
    )

    # 6. Tactical Cover Crates at choke points
    crate_locations = [
        (1500.0, 1100.0), (1300.0, 1500.0),  # Site A cover
        (-1500.0, 1100.0), (-1300.0, 1500.0), # Site B cover
        (0.0, 200.0), (150.0, 600.0), (-150.0, 600.0), # Mid cover
        (1600.0, -400.0), (-1600.0, -400.0), # Long & Tunnels cover
        (400.0, -1200.0), (-400.0, -1200.0), # CT defense cover
    ]
    for idx, (cx, cy) in enumerate(crate_locations):
        geometry_ops.append(
            OpCall(
                op="spawn_actor",
                args={
                    "actor_class": "StaticMeshActor",
                    "label": f"GF_Tactical_Crate_{idx}",
                    "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                    "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                    "location": {"x": cx, "y": cy, "z": 75.0},
                    "scale": {"x": 1.5, "y": 1.5, "z": 1.5},
                },
                purpose=f"Spawn tactical cover crate {idx}",
            )
        )

    # 7. Bomb Site Interactive Actors
    actors.append(
        PlacedActor(
            actor_id="bombsite_a",
            runtime_class="/Script/GameForgeRuntime.GameForgeBombSite",
            location=(1500.0, 1400.0, 50.0),
            yaw=0.0,
            entity_id="bombsite_a",
            tags=["goal", "Goal", "GF_Goal", "Goal_1", "goal_1", "GF_Goal_1", "bombsite", "site_a", "objective", "GF_Owned", "bombsite_a"],
        )
    )
    actors.append(
        PlacedActor(
            actor_id="bombsite_b",
            runtime_class="/Script/GameForgeRuntime.GameForgeBombSite",
            location=(-1500.0, 1400.0, 50.0),
            yaw=0.0,
            entity_id="bombsite_b",
            tags=["goal", "Goal", "GF_Goal", "Goal_2", "goal_2", "GF_Goal_2", "bombsite", "site_b", "objective", "GF_Owned", "bombsite_b"],
        )
    )

    # 8. Five Opposing Terrorist Combat Bots (GameForgeEnemy)
    bot_configs = [
        ("bot_site_a", (1500.0, 1600.0, 50.0), 180.0, "Site A Defender"),
        ("bot_site_b", (-1500.0, 1600.0, 50.0), 180.0, "Site B Defender"),
        ("bot_mid", (0.0, 1200.0, 50.0), 180.0, "Mid Guard"),
        ("bot_long_a", (1800.0, 200.0, 50.0), 225.0, "Long A Patrol"),
        ("bot_tunnels", (-1800.0, 200.0, 50.0), 135.0, "B Tunnels Flanker"),
    ]
    for idx, (bot_id, loc, yaw, desc) in enumerate(bot_configs):
        actors.append(
            PlacedActor(
                actor_id=bot_id,
                runtime_class="/Script/GameForgeRuntime.GameForgeEnemy",
                location=loc,
                yaw=yaw,
                entity_id="enemy",
                tags=[
                    "enemy",
                    "Enemy",
                    f"Enemy_{idx + 1}",
                    f"enemy_{idx + 1}",
                    f"GF_enemy_{idx + 1}",
                    f"GF_Enemy_{idx + 1}",
                    bot_id,
                    "terrorist",
                    "combat",
                    "GF_Owned",
                ],
            )
        )

    # 9. Spawner for backup waves if wave rules apply
    actors.append(
        PlacedActor(
            actor_id="spawner_terrorist_reinforcements",
            runtime_class="/Script/GameForgeRuntime.GameForgeSpawner",
            location=(0.0, 2200.0, 50.0),
            yaw=180.0,
            entity_id="spawner",
            tags=["spawner", "enemy", "GF_Owned"],
        )
    )

    # Player starts at CT Base
    player_start = (0.0, -2200.0, 50.0)
    nav_extent = (3200.0, 3200.0, 500.0)

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        lighting="day",
        player_start=player_start,
        nav_bounds=((0.0, 0.0, 0.0), nav_extent),
        geometry_ops=geometry_ops,
        actors=actors,
    )
