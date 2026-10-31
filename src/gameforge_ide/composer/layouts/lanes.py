"""Composer lanes layout (WI-6.3).

Lanes level plan for card battlers and lane combat.
The card table actor manages lanes and card interaction.
"""
from __future__ import annotations

import random
from typing import Any
from ..model import LevelPlan, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    card_table = PlacedActor(
        actor_id="cards_0",
        entity_id="cards",
        runtime_class="/Script/GameForgeRuntime.GameForgeCardTable",
        location=(0.0, 0.0, 50.0),
        yaw=0.0,
        tags=["GF_E_cards", "GF_Owned", "GF_CardTable"],
        properties={},
    )

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(0.0, -300.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=[],
        actors=[card_table],
        lighting="indoor",
        nav_checks=[],
    )
