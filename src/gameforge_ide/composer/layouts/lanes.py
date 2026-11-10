"""Composer lanes layout (WI-6.3).

Supports both:
1. Card Battler 3-lane duel table when `kit.card_match` / `card_table` is present.
2. Multi-lane Tower Defense map when Tower Defense / lane defense is requested, spawning
   3 distinct creep lanes, buildable tower pads, autonomous defense turrets, enemy wave spawner,
   and a defendable home base goal.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List
from ..model import map_package_path, LevelPlan, OpCall, PlacedActor
from ...kit.registry import get_module


def _map_entity_props(ent: Any, module_id: str) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    if not ent or not getattr(ent, "props", None):
        return props
    raw = ent.props if isinstance(ent.props, dict) else ent.props.model_dump()
    try:
        mod = get_module(module_id)
        for gds_k, ue_k in mod.property_map.items():
            if gds_k in raw and raw[gds_k] is not None:
                props[ue_k] = raw[gds_k]
            elif ue_k in raw and raw[ue_k] is not None:
                props[ue_k] = raw[ue_k]
    except KeyError:
        pass
    for k, v in raw.items():
        if k[:1].isupper() and v is not None:
            props.setdefault(k, v)
    return props


def _plan_tower_defense_lanes(level_id: str, map_path: str, level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    """Build a genuine 3-lane Tower Defense battlefield."""
    geometry_ops: List[OpCall] = [
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_TD_Floor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                "location": {"x": 0.0, "y": 0.0, "z": -10.0},
                "scale": {"x": 56.0, "y": 36.0, "z": 0.2},
            },
            purpose="Spawn tower defense battlefield floor",
        ),
        # Lane divider walls separating North, Center, and South creep lanes
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Lane_Divider_North",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 0.0, "y": 500.0, "z": 60.0},
                "scale": {"x": 32.0, "y": 0.8, "z": 1.2},
            },
            purpose="Spawn north lane divider barrier",
        ),
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Lane_Divider_South",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 0.0, "y": -500.0, "z": 60.0},
                "scale": {"x": 32.0, "y": 0.8, "z": 1.2},
            },
            purpose="Spawn south lane divider barrier",
        ),
        # Defendable Base platform on the West side (-X)
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Goal_BasePad",
                "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Orange",
                "location": {"x": -2200.0, "y": 0.0, "z": 10.0},
                "scale": {"x": 5.0, "y": 5.0, "z": 0.3},
            },
            purpose="Spawn defendable home base pad",
        ),
        # Enemy Spawn Portal on the East side (+X)
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Start_CreepPortal",
                "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_DarkGray",
                "location": {"x": 2200.0, "y": 0.0, "z": 10.0},
                "scale": {"x": 5.0, "y": 5.0, "z": 0.3},
            },
            purpose="Spawn enemy wave portal pad",
        ),
    ]

    # 6 Tower Build Pads along the lanes
    tower_pad_coords = [
        (-900.0, 500.0),
        (300.0, 500.0),
        (-900.0, -500.0),
        (300.0, -500.0),
        (-1500.0, 900.0),
        (-1500.0, -900.0),
    ]
    actors: List[PlacedActor] = []
    for idx, (tx, ty) in enumerate(tower_pad_coords):
        geometry_ops.append(
            OpCall(
                op="spawn_actor",
                args={
                    "actor_class": "StaticMeshActor",
                    "label": f"GF_Platform_TowerPad_{idx}",
                    "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
                    "location": {"x": tx, "y": ty, "z": 130.0},
                    "scale": {"x": 2.2, "y": 2.2, "z": 0.4},
                },
                purpose=f"Spawn elevated tower build pad {idx}",
            )
        )
        if idx < 4:
            actors.append(
                PlacedActor(
                    actor_id=f"defense_turret_{idx}",
                    entity_id=None,
                    runtime_class="/Script/GameForgeRuntime.GameForgeEnemy",
                    location=(tx, ty, 190.0),
                    yaw=0.0,
                    tags=["GF_Owned", "turret", "friendly_tower", f"Turret_{idx + 1}"],
                    properties={
                        "TeamId": 0,
                        "bStationaryTurret": True,
                        "bRanged": True,
                        "MoveSpeed": 0.0,
                        "AttackRange": 1400.0,
                        "AttackDamage": float(
                            next(
                                (
                                    (getattr(e, "props", {}) or {}).get("attack_damage", 25.0)
                                    for e in getattr(gds, "entities", [])
                                    if "turret" in str(getattr(e, "tags", []))
                                ),
                                25.0,
                            )
                        ),
                        "AttackCooldown": 0.8,
                    },
                )
            )

    goal_ent = next((e for e in getattr(gds, "entities", []) if str(getattr(e, "kind", "")) == "goal" or getattr(e, "module", "") == "kit.goal"), None)
    goal_id = goal_ent.entity_id if goal_ent else "goal"
    actors.append(
        PlacedActor(
            actor_id=f"{goal_id}_0",
            entity_id=goal_id,
            runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
            location=(-2200.0, 0.0, 80.0),
            yaw=0.0,
            tags=[f"GF_E_{goal_id}", "GF_Owned", "GF_Goal", "goal", "Goal", "Goal_1", "goal_0", "base_core"],
            properties=_map_entity_props(goal_ent, "kit.goal"),
        )
    )

    spawner_ent = next((e for e in getattr(gds, "entities", []) if str(getattr(e, "kind", "")) == "spawner" or getattr(e, "module", "") == "kit.spawner"), None)
    spawner_id = spawner_ent.entity_id if spawner_ent else "spawner"
    actors.append(
        PlacedActor(
            actor_id=f"{spawner_id}_0",
            entity_id=spawner_id,
            runtime_class="/Script/GameForgeRuntime.GameForgeSpawner",
            location=(2200.0, 0.0, 80.0),
            yaw=180.0,
            tags=[f"GF_E_{spawner_id}", "GF_Owned", "GF_Spawner", "spawner", "Spawner", "Spawner_1"],
            properties=_map_entity_props(spawner_ent, "kit.spawner"),
        )
    )

    lighting_val = getattr(getattr(level, "lighting", "day"), "value", getattr(level, "lighting", "day"))
    if lighting_val not in ("day", "dusk", "night", "indoor"):
        lighting_val = "day"

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(-1800.0, 0.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (2800.0, 1800.0, 500.0)),
        geometry_ops=geometry_ops,
        actors=actors,
        lighting=lighting_val,
        nav_checks=[("player_start", f"{goal_id}_0")],
    )


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = map_package_path(level_id)

    # Check if this level is a Tower Defense game rather than a Card Battler
    layout_params = getattr(level, "layout_params", {}) or {}
    meta_title = getattr(getattr(gds, "meta", None), "title", "") or ""
    meta_prompt = getattr(getattr(gds, "meta", None), "source_prompt", "") or ""
    pitch = getattr(getattr(gds, "overview", None), "pitch", "") or ""
    genre_str = str(getattr(getattr(getattr(gds, "overview", None), "genre", ""), "value", getattr(getattr(gds, "overview", None), "genre", ""))).lower()
    text_corpus = f"{meta_title} {meta_prompt} {pitch}".lower()

    table_ent = None
    if hasattr(gds, "entities") and gds.entities:
        for ent in gds.entities:
            k = str(getattr(ent, "kind", ""))
            m = str(getattr(ent, "module", ""))
            eid = str(getattr(ent, "entity_id", ""))
            if (
                k in ("card_table", "cards", "lanes", "table")
                or m in ("kit.card_match", "kit.card_table", "kit.lanes")
                or eid in ("card_table", "cards")
            ):
                table_ent = ent
                break

    is_tower_defense = (
        layout_params.get("lane_mode") == "tower_defense"
        or "tower defense" in text_corpus
        or "tower_defense" in text_corpus
        or "defend the base" in text_corpus
        or "turret" in text_corpus
        or "moba" in text_corpus
        or "lane defense" in text_corpus
        or genre_str in ("arena_combat", "top_down_shooter")
        or (table_ent is None and genre_str != "card_battler" and any(
            str(getattr(e, "kind", "")) in ("spawner", "enemy", "ranged_enemy") for e in getattr(gds, "entities", [])
        ))
    )

    if is_tower_defense:
        return _plan_tower_defense_lanes(level_id, map_path, level, gds, rng)

    if table_ent:
        table_entity_id = table_ent.entity_id
        actor_id = f"{table_ent.entity_id}_0" if not table_ent.entity_id.endswith("_0") else table_ent.entity_id
        tags = [f"GF_E_{table_entity_id}", "GF_Owned", "GF_CardTable"]
        props = _map_entity_props(table_ent, "kit.card_match")
    else:
        table_entity_id = "card_table"
        actor_id = "card_table_0"
        tags = ["GF_E_card_table", "GF_Owned", "GF_CardTable"]
        props = {}

    card_table = PlacedActor(
        actor_id=actor_id,
        entity_id=table_entity_id,
        runtime_class="/Script/GameForgeRuntime.GameForgeCardTable",
        location=(0.0, 0.0, 50.0),
        yaw=0.0,
        tags=tags,
        properties=props,
    )

    geometry_ops = [
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Lanes_Floor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                "location": {"x": 0.0, "y": 0.0, "z": -10.0},
                "scale": {"x": 40.0, "y": 40.0, "z": 0.2},
            },
            purpose="Spawn card battler arena floor",
        )
    ]

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(0.0, -300.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=geometry_ops,
        actors=[card_table],
        lighting="indoor",
        nav_checks=[],
    )
