"""Composer lanes layout (WI-6.3).

Lanes level plan for card battlers and lane combat.
The card table actor manages lanes and card interaction.
"""
from __future__ import annotations

import random
from typing import Any
from ..model import LevelPlan, OpCall, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    # Match card table entity from GDS to avoid duplicate unplaced entity scattering
    table_ent = None
    if hasattr(gds, "entities") and gds.entities:
        for ent in gds.entities:
            k = str(getattr(ent, "kind", ""))
            m = str(getattr(ent, "module", ""))
            eid = str(getattr(ent, "entity_id", ""))
            if (
                k in ("card_table", "cards", "lanes", "table")
                or m in ("kit.card_table", "kit.lanes")
                or eid in ("card_table", "cards")
            ):
                table_ent = ent
                break

    if table_ent:
        table_entity_id = table_ent.entity_id
        actor_id = f"{table_ent.entity_id}_0" if not table_ent.entity_id.endswith("_0") else table_ent.entity_id
        tags = [f"GF_E_{table_entity_id}", "GF_Owned", "GF_CardTable"]
        props = dict(getattr(table_ent, "props", {}) or {})
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
