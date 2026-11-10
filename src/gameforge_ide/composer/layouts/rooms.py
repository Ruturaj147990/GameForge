"""Composer dungeon rooms layout (WI-6.3).

Generates interconnected modular rooms and corridors using dungeon_layout
generator on a 400cm grid with floors, perimeter walls, and point lights.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple
from ..model import map_package_path, LevelPlan, OpCall, PlacedActor
from ...backend.tools import dungeon_layout


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = map_package_path(level_id)

    seed = getattr(level, "seed", rng.randint(1, 999999))
    num_rooms = rng.randint(4, 7)

    dungeon = dungeon_layout.generate(seed, num_rooms)
    grid_cm = 400.0
    placements = dungeon_layout.kit_placements(dungeon["cells"], grid=grid_cm)

    geometry_ops: List[OpCall] = []

    # Spawn floors and walls with correct centering and authoritative meshes
    for i, piece in enumerate(placements):
        loc = piece["location"]
        yaw = float(piece["yaw"])
        p_type = piece["piece"]
        if p_type == "Floor":
            # Center cube on grid cell [x*grid, (x+1)*grid] x [y*grid, (y+1)*grid]
            floor_cx = loc[0] + grid_cm / 2.0
            floor_cy = loc[1] + grid_cm / 2.0
            geometry_ops.append(
                OpCall(
                    op="spawn_actor",
                    args={
                        "actor_class": "StaticMeshActor",
                        "label": f"GF_Dungeon_Floor_{i}",
                        "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                        "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                        "location": {"x": floor_cx, "y": floor_cy, "z": -10.0},
                        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                        "scale": {"x": 4.0, "y": 4.0, "z": 0.2},
                    },
                    purpose=f"Spawn dungeon floor piece {i}",
                )
            )
        elif p_type == "Wall":
            # Wall piece runs along local +X; center is at local grid/2 rotated by yaw
            rad = math.radians(yaw)
            wall_cx = loc[0] + (grid_cm / 2.0) * math.cos(rad)
            wall_cy = loc[1] + (grid_cm / 2.0) * math.sin(rad)
            geometry_ops.append(
                OpCall(
                    op="spawn_actor",
                    args={
                        "actor_class": "StaticMeshActor",
                        "label": f"GF_Dungeon_Wall_{i}",
                        "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                        "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                        "location": {"x": wall_cx, "y": wall_cy, "z": 150.0},
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
    goal_ent = next((e for e in getattr(gds, "entities", []) if str(getattr(e, "kind", "")) in ("goal", "exit") or getattr(e, "module", "") == "kit.goal"), None)
    goal_id = goal_ent.entity_id if goal_ent is not None else "goal"
    goal_props: Dict[str, Any] = {}
    if goal_ent is not None and getattr(goal_ent, "props", None):
        gp = goal_ent.props if isinstance(goal_ent.props, dict) else goal_ent.props.model_dump()
        if "required_stat" in gp:
            goal_props["RequiredStat"] = gp["required_stat"]
            goal_props["RequiredValue"] = float(gp.get("required_value", 0.0) or 0.0)

    goal_actor = PlacedActor(
        actor_id=f"{goal_id}_0",
        entity_id=goal_id,
        runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
        location=(goal_x, goal_y, 100.0),
        yaw=0.0,
        tags=[
            f"GF_E_{goal_id}",
            "GF_Owned",
            "GF_Goal",
            "goal",
            "Goal",
            "Goal_1",
            "goal_1",
            "GF_Goal_1",
            "GF_goal_1",
            f"{goal_id}_0",
        ],
        properties=goal_props,
    )

    actors: List[PlacedActor] = [goal_actor]

    # Boss enemy placed in final room guarding the goal
    boss_ent = next(
        (
            e for e in getattr(gds, "entities", [])
            if str(getattr(e.kind, "value", e.kind)) == "enemy"
            and (
                getattr(e, "properties", {}).get("bIsBoss")
                or getattr(e, "props", {}).get("bIsBoss")
                or "boss" in (getattr(e, "tags", []) or [])
                or "boss" in getattr(e, "entity_id", "").lower()
            )
        ),
        None,
    )
    if boss_ent is not None:
        boss_props = dict(getattr(boss_ent, "properties", {}) or getattr(boss_ent, "props", {}) or {})
        boss_props.setdefault("bIsBoss", True)
        boss_props.setdefault("BossName", getattr(boss_ent, "entity_id", "BossEnemy").replace("_", " ").title())
        boss_props.setdefault("BossPhase", 1)
        bx = (last_room.x + last_room.w / 2.0) * grid_cm
        by = (last_room.y + last_room.h / 2.0) * grid_cm
        actors.append(
            PlacedActor(
                actor_id=f"{boss_ent.entity_id}_0",
                entity_id=boss_ent.entity_id,
                runtime_class="/Script/GameForgeRuntime.GameForgeEnemy",
                location=(round(bx, 1), round(by, 1), 100.0),
                yaw=180.0,
                tags=[f"GF_E_{boss_ent.entity_id}", "GF_Owned", "enemy", "boss", "Boss", f"{boss_ent.entity_id}_0"],
                properties=boss_props,
            )
        )
        # When boss guards the room, place the goal slightly behind the boss near the far wall
        goal_actor.location = (round(bx, 1), round(by + 250.0, 1), 100.0)

    # Key pickups distributed across intermediate rooms (between room 1 and last_room)
    key_ent = next(
        (
            e for e in getattr(gds, "entities", [])
            if str(getattr(e.kind, "value", e.kind)) == "pickup"
            and (
                "key" in getattr(e, "entity_id", "").lower()
                or "key" in (getattr(e, "tags", []) or [])
            )
        ),
        None,
    )
    if key_ent is not None and len(rooms) >= 3:
        key_count = int(getattr(key_ent, "count", 1) or getattr(key_ent, "props", {}).get("count", 1) or 1)
        intermediate_rooms = rooms[1:-1]
        for k_idx in range(key_count):
            target_rm = intermediate_rooms[k_idx % len(intermediate_rooms)]
            kx = (target_rm.x + target_rm.w / 2.0) * grid_cm + ((k_idx // len(intermediate_rooms)) * 120.0)
            ky = (target_rm.y + target_rm.h / 2.0) * grid_cm + ((k_idx // len(intermediate_rooms)) * 120.0)
            k_props = dict(getattr(key_ent, "properties", {}) or getattr(key_ent, "props", {}) or {})
            actors.append(
                PlacedActor(
                    actor_id=f"{key_ent.entity_id}_{k_idx}",
                    entity_id=key_ent.entity_id,
                    runtime_class="/Script/GameForgeRuntime.GameForgePickup",
                    location=(round(kx, 1), round(ky, 1), 75.0),
                    yaw=0.0,
                    tags=[f"GF_E_{key_ent.entity_id}", "GF_Owned", "pickup", "key", f"{key_ent.entity_id}_{k_idx}"],
                    properties=k_props,
                )
            )

    # Place doors and switches in intermediate rooms when requested in GDS
    if hasattr(gds, "entities") and len(rooms) >= 3:
        mid_room = rooms[len(rooms) // 2]
        mx = (mid_room.x + mid_room.w / 2.0) * grid_cm
        my = (mid_room.y + mid_room.h / 2.0) * grid_cm
        door_ent = next((e for e in gds.entities if str(getattr(e.kind, "value", e.kind)) == "door"), None)
        if door_ent is not None:
            door_props = dict(getattr(door_ent, "properties", {}) or getattr(door_ent, "props", {}) or {})
            if key_ent is not None:
                door_props.setdefault("RequiredStat", "game.counter.keys_collected")
                door_props.setdefault("RequiredValue", float(key_count))
            door_x = (last_room.x) * grid_cm if boss_ent is not None else mx
            door_y = (last_room.y + last_room.h / 2.0) * grid_cm if boss_ent is not None else my
            actors.append(PlacedActor(
                actor_id=f"{door_ent.entity_id}_0",
                entity_id=door_ent.entity_id,
                runtime_class="/Script/GameForgeRuntime.GameForgeDoor",
                location=(round(door_x, 1), round(door_y, 1), 100.0),
                yaw=0.0,
                tags=[f"GF_E_{door_ent.entity_id}", "GF_Owned", "door", "Door", f"{door_ent.entity_id}_0"],
                properties=door_props,
            ))
        sw_ent = next((e for e in gds.entities if str(getattr(e.kind, "value", e.kind)) == "switch"), None)
        if sw_ent is not None and int(getattr(sw_ent, "count", 1) or 1) == 1:
            r1 = rooms[1]
            sx = (r1.x + r1.w / 2.0) * grid_cm
            sy = (r1.y + r1.h / 2.0) * grid_cm
            sw_props = dict(getattr(sw_ent, "properties", {}) or getattr(sw_ent, "props", {}) or {})
            actors.append(PlacedActor(
                actor_id=f"{sw_ent.entity_id}_0",
                entity_id=sw_ent.entity_id,
                runtime_class="/Script/GameForgeRuntime.GameForgeSwitch",
                location=(round(sx, 1), round(sy, 1), 100.0),
                yaw=0.0,
                tags=[f"GF_E_{sw_ent.entity_id}", "GF_Owned", "switch", "Switch", f"{sw_ent.entity_id}_0"],
                properties=sw_props,
            ))

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

    # Spawn dungeon safety floor covering all rooms and corridors
    geometry_ops.append(
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Dungeon_SafetyFloor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": center[0], "y": center[1], "z": -25.0},
                "scale": {"x": max(10.0, (extent[0] * 2.0) / 100.0), "y": max(10.0, (extent[1] * 2.0) / 100.0), "z": 0.2},
            },
            purpose="Spawn dungeon safety floor preventing void fall",
        )
    )

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=player_start,
        nav_bounds=(center, extent),
        geometry_ops=geometry_ops,
        actors=actors,
        lighting="indoor",
        nav_checks=[("player_start", f"{goal_id}_0")],
    )
