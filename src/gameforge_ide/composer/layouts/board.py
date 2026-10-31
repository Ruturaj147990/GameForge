"""Composer board layout (WI-6.3).

Grid board level plan for turn-based grid games (Tic-Tac-Toe, Connect Four, etc.).
The board actor dynamically builds its grid cells.
"""
from __future__ import annotations

import random
from typing import Any
from ..model import LevelPlan, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = f"/Game/Maps/{level_id.capitalize()}"

    board_actor = PlacedActor(
        actor_id="board_0",
        entity_id="board",
        runtime_class="/Script/GameForgeRuntime.GameForgeGridBoard",
        location=(0.0, 0.0, 50.0),
        yaw=0.0,
        tags=["GF_E_board", "GF_Owned", "GF_Board"],
        properties={},
    )

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(0.0, -300.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=[],
        actors=[board_actor],
        lighting="indoor",
        nav_checks=[],
    )
