"""Composer board layout (WI-6.3).

Grid board level plan for turn-based grid games (Tic-Tac-Toe, Connect Four,
Snakes and Ladders, etc.).
The board actor dynamically builds its grid cells.
"""
from __future__ import annotations

import random
from typing import Any, Dict
from ..model import map_package_path, LevelPlan, OpCall, PlacedActor


def plan_level(level: Any, gds: Any, rng: random.Random) -> LevelPlan:
    level_id = getattr(level, "level_id", "level_1")
    map_path = map_package_path(level_id)

    # Find matching board entity from GDS entities
    board_ent = None
    if hasattr(gds, "entities") and gds.entities:
        for ent in gds.entities:
            k = getattr(ent, "kind", "")
            m = getattr(ent, "module", "")
            if (
                k in ("board", "grid", "grid_board", "tictactoe", "connect_four", "gomoku", "snakes_and_ladders")
                or m in ("kit.grid_board", "kit.board")
            ):
                board_ent = ent
                break

    # Match entity_id and actor_id to prevent duplicate unplaced entity scattering
    if board_ent:
        board_entity_id = board_ent.entity_id
        actor_id = f"{board_ent.entity_id}_0" if not board_ent.entity_id.endswith("_0") else board_ent.entity_id
        tags = [f"GF_E_{board_entity_id}", "GF_Owned", "GF_Board"]
    else:
        board_entity_id = "board"
        actor_id = "board_0"
        tags = ["GF_E_board", "GF_Owned", "GF_Board"]

    # Extract properties from board entity
    props: Dict[str, Any] = {}
    board_size = 3
    cell_size_cm = 120.0
    loc = (0.0, 0.0, 50.0)

    if board_ent and hasattr(board_ent, "props") and board_ent.props:
        eprops = board_ent.props
        if "board_size" in eprops:
            board_size = int(eprops["board_size"])
            props["BoardSize"] = board_size
        if "win_length" in eprops:
            props["WinLength"] = int(eprops["win_length"])
        if "gravity" in eprops:
            props["bGravity"] = bool(eprops["gravity"])
        if "vs_ai" in eprops:
            props["bVsAI"] = bool(eprops["vs_ai"])
        if "ai_level" in eprops:
            props["AILevel"] = str(eprops["ai_level"])
        if "cell_size_cm" in eprops:
            cell_size_cm = float(eprops["cell_size_cm"])
            props["CellSizeCm"] = cell_size_cm
        for custom_key in ("snakes", "ladders", "snakes_and_ladders"):
            if custom_key in eprops:
                props[custom_key] = eprops[custom_key]
        if "location" in eprops:
            loc_val = eprops["location"]
            if isinstance(loc_val, (list, tuple)) and len(loc_val) == 3:
                loc = (float(loc_val[0]), float(loc_val[1]), float(loc_val[2]))

    board_actor = PlacedActor(
        actor_id=actor_id,
        entity_id=board_entity_id,
        runtime_class="/Script/GameForgeRuntime.GameForgeGridBoard",
        location=loc,
        yaw=0.0,
        tags=tags,
        properties=props,
    )

    # Provide enough space for player away from the board edge
    board_extent_y = (board_size * cell_size_cm) / 2.0
    player_y = loc[1] - max(300.0, board_extent_y + 200.0)
    extent_xy = max(1000.0, board_size * cell_size_cm + 500.0)

    # Spawn solid floor for player and board
    floor_extent = max(2000.0, extent_xy * 2.0)
    floor_scale = floor_extent / 100.0
    geometry_ops = [
        OpCall(
            op="spawn_actor",
            args={
                "actor_class": "StaticMeshActor",
                "label": "GF_Board_Floor",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                "material": "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
                "location": {"x": loc[0], "y": loc[1], "z": -10.0},
                "scale": {"x": floor_scale, "y": floor_scale, "z": 0.2},
            },
            purpose="Spawn board room ground floor",
        )
    ]

    return LevelPlan(
        level_id=level_id,
        map_path=map_path,
        partitioned=False,
        player_start=(loc[0], player_y, 100.0),
        nav_bounds=((loc[0], loc[1], 100.0), (extent_xy, extent_xy, 500.0)),
        geometry_ops=geometry_ops,
        actors=[board_actor],
        lighting="indoor",
        nav_checks=[],
    )
