"""Unit tests for Composer level ops generation and layout verification (Phase 6)."""
from __future__ import annotations

import random
import pytest

from src.gameforge_ide.composer.model import LevelPlan, PlacedActor
from src.gameforge_ide.composer.level_ops import (
    plan_to_op_calls,
    verify_placed_actor_transforms,
)
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.composer.layouts.board import plan_level as plan_board_level
from src.gameforge_ide.design.presets import preset_tic_tac_toe, preset_platformer
from src.gameforge_ide.design.gds import Genre, LayoutKind


def test_plan_to_op_calls_basic():
    """Verify standard level plan generates valid op sequence starting with new_level."""
    plan = LevelPlan(
        level_id="level_1",
        map_path="/Game/Maps/Level_1",
        player_start=(0.0, -300.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=[],
        actors=[],
        lighting="day",
        nav_checks=[],
    )
    ops = plan_to_op_calls(plan)
    assert len(ops) >= 3
    assert ops[0].op == "new_level"
    assert ops[0].args["level_path"] == "/Game/Maps/Level_1"
    assert ops[-1].op == "save_all"

    # Exactly one PlayerStart emitted
    player_starts = [o for o in ops if o.op == "spawn_actor" and o.args.get("actor_class") == "PlayerStart"]
    assert len(player_starts) == 1
    assert player_starts[0].args["label"] == "GF_PlayerStart"


def test_no_duplicate_player_start():
    """Verify that if plan.actors already has a PlayerStart, duplicate is not emitted."""
    custom_start = PlacedActor(
        actor_id="GF_PlayerStart",
        runtime_class="PlayerStart",
        location=(100.0, 200.0, 50.0),
        yaw=90.0,
        tags=["GF_Owned"],
    )
    plan = LevelPlan(
        level_id="level_1",
        map_path="/Game/Maps/Level_1",
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=[],
        actors=[custom_start],
        lighting="indoor",
        nav_checks=[],
    )
    ops = plan_to_op_calls(plan)
    player_starts = [o for o in ops if o.op == "spawn_actor" and o.args.get("actor_class") == "PlayerStart"]
    assert len(player_starts) == 1
    assert player_starts[0].args["label"] == "GF_PlayerStart"
    assert player_starts[0].args["location"]["x"] == 100.0


def test_board_layout_skips_navmesh():
    """Verify grid board games with no AI or nav checks omit NavMeshBounds and nav_rebuild."""
    board_actor = PlacedActor(
        actor_id="board_0",
        entity_id="board",
        runtime_class="/Script/GameForgeRuntime.GameForgeGridBoard",
        location=(0.0, 0.0, 50.0),
        tags=["GF_Board", "GF_Owned"],
    )
    plan = LevelPlan(
        level_id="level_1",
        map_path="/Game/Maps/Level_1",
        player_start=(0.0, -300.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=[],
        actors=[board_actor],
        lighting="indoor",
        nav_checks=[],
    )
    ops = plan_to_op_calls(plan)
    op_names = [o.op for o in ops]
    assert "nav_rebuild" not in op_names
    assert not any(o.op == "spawn_actor" and o.args.get("actor_class") == "NavMeshBoundsVolume" for o in ops)


def test_platformer_layout_includes_navmesh():
    """Verify non-board layouts retain NavMeshBoundsVolume and nav_rebuild."""
    gds = preset_platformer()
    comp = compose(gds)
    level = comp.levels[0]
    ops = plan_to_op_calls(level)
    op_names = [o.op for o in ops]
    assert "nav_rebuild" in op_names
    assert any(o.op == "spawn_actor" and o.args.get("actor_class") == "NavMeshBoundsVolume" for o in ops)


def test_verify_placed_actor_transforms():
    """Verify actor transform read-back check flags discrepancies beyond tolerance."""
    actor = PlacedActor(
        actor_id="test_board",
        runtime_class="/Script/GameForgeRuntime.GameForgeGridBoard",
        location=(340.0, 710.0, 430.0),
    )
    plan = LevelPlan(
        level_id="level_1",
        map_path="/Game/Maps/Level_1",
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        actors=[actor],
    )

    # Discrepancy case: actual location is at (0, 0, 50)
    actual_records = {
        "test_board": {
            "location": {"x": 0.0, "y": 0.0, "z": 50.0},
        }
    }
    warnings = verify_placed_actor_transforms(plan, actual_records, tolerance_cm=50.0)
    assert len(warnings) == 1
    assert "location mismatch" in warnings[0]
    assert "340.0" in warnings[0]
    assert "710.0" in warnings[0]

    # Matching case: actual location within tolerance
    matching_records = {
        "test_board": {
            "location": {"x": 340.5, "y": 709.8, "z": 430.2},
        }
    }
    no_warnings = verify_placed_actor_transforms(plan, matching_records, tolerance_cm=50.0)
    assert len(no_warnings) == 0


def test_board_layout_populates_properties_and_spacing():
    """Verify board layout extracts properties from GDS and provides player clearance."""
    gds = preset_tic_tac_toe()
    # Configure custom 8x8 board
    board_ent = gds.entities[0]
    board_ent.entity_id = "custom_board"
    board_ent.props["board_size"] = 8
    board_ent.props["cell_size_cm"] = 150.0
    board_ent.props["win_length"] = 5
    board_ent.props["gravity"] = True

    comp = compose(gds)
    level = comp.levels[0]

    # Board actor should match entity_id and have populated properties
    assert len(level.actors) == 1
    board_actor = level.actors[0]
    assert board_actor.entity_id == "custom_board"
    assert board_actor.actor_id == "custom_board_0"
    assert board_actor.properties["BoardSize"] == 8
    assert board_actor.properties["WinLength"] == 5
    assert board_actor.properties["bGravity"] is True
    assert board_actor.properties["CellSizeCm"] == 150.0

    # Player start should provide clearance based on board size (8 * 150 / 2 = 600 + 200 = 800cm)
    assert level.player_start[1] <= -800.0


def test_compose_layout_detection_for_genres():
    """Verify fallback layout detection maps grid_board, card_battler, and puzzle properly."""
    # Test preset tic tac toe uses board layout
    gds_ttt = preset_tic_tac_toe()
    comp_ttt = compose(gds_ttt)
    assert comp_ttt.levels[0].map_path == "/Game/Maps/Level_1"
    assert any("GridBoard" in a.runtime_class for a in comp_ttt.levels[0].actors)
