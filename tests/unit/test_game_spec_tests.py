"""Unit tests for GDS-driven game-specific test generation, semantic validation, and stage output evidence verification."""

from __future__ import annotations

import pytest

from src.gameforge_ide.design.gds import (
    CameraKind,
    EntityKind,
    EntitySpec,
    GameDesignSpec,
    Genre,
    Goals,
    LevelSpec,
    Meta,
    Overview,
    Placement,
    Scene,
    Vec2,
)
from src.gameforge_ide.design.presets import preset_arena_combat, preset_platformer, preset_tic_tac_toe
from src.gameforge_ide.design.semantic_validate import semantic_validate_gds
from src.gameforge_ide.forge.validation import validate_stage_output
from src.gameforge_ide.qa.game_spec_tests import (
    AcceptanceTestSpec,
    acceptance_tests_to_scenarios,
    generate_acceptance_tests,
)
from src.gameforge_ide.qa.scenario import Scenario


def _make_snakes_and_ladders_gds() -> GameDesignSpec:
    """Helper to create a valid Snake and Ladders GameDesignSpec."""
    gds = preset_tic_tac_toe(title="Snakes and Ladders")
    gds.meta.source_prompt = "Make a snakes and ladders board game with 100 cells"
    gds.overview.pitch = "Classic 100-cell board game with snakes and ladders"
    for e in gds.entities:
        if e.kind == EntityKind.BOARD:
            e.props["cell_count"] = 100
            e.props["snakes"] = [16, 6, 47, 26, 49, 11]
            e.props["ladders"] = [1, 38, 4, 14, 9, 31]
    return gds


# ─────────────────────────────────────────────────────────────────────────────
# 1. Acceptance Test Generation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_acceptance_tests_snakes_and_ladders():
    """Verify snake and ladders GDS generates all 8 concrete test assertions."""
    gds = _make_snakes_and_ladders_gds()
    tests = generate_acceptance_tests(gds)

    assert len(tests) >= 8
    test_ids = {t.test_id for t in tests}

    expected_tests = {
        "board_structure_valid",
        "dice_outcomes_valid",
        "player_token_movement",
        "snake_transition",
        "ladder_transition",
        "win_condition",
        "overshoot_handling",
        "turn_progression",
    }
    assert expected_tests.issubset(test_ids), f"Missing tests: {expected_tests - test_ids}"

    # Detailed assertion checks
    board_test = next(t for t in tests if t.test_id == "board_structure_valid")
    assert "100 cells" in board_test.description
    assert any("100" in a for a in board_test.assertions)

    dice_test = next(t for t in tests if t.test_id == "dice_outcomes_valid")
    assert "1-6" in dice_test.description
    assert any("1" in a and "6" in a for a in dice_test.assertions)

    snake_test = next(t for t in tests if t.test_id == "snake_transition")
    assert "snake head" in snake_test.description
    assert any("tail" in a for a in snake_test.assertions)

    ladder_test = next(t for t in tests if t.test_id == "ladder_transition")
    assert "ladder bottom" in ladder_test.description
    assert any("top" in a for a in ladder_test.assertions)

    win_test = next(t for t in tests if t.test_id == "win_condition")
    assert "cell 100" in win_test.description or "100" in win_test.description
    assert any("game.won" in a for a in win_test.assertions)

    overshoot_test = next(t for t in tests if t.test_id == "overshoot_handling")
    assert "past cell 100" in overshoot_test.description

    turn_test = next(t for t in tests if t.test_id == "turn_progression")
    assert "alternate" in turn_test.description


def test_generate_acceptance_tests_platformer():
    """Verify platformer GDS produces jump, collect, goal, and win tests."""
    gds = preset_platformer(collectible_target=7)
    tests = generate_acceptance_tests(gds)

    test_ids = {t.test_id for t in tests}
    assert "player_can_jump" in test_ids
    assert "collectibles_exist" in test_ids
    assert "goal_exists" in test_ids
    assert "win_on_collect_all" in test_ids

    jump_test = next(t for t in tests if t.test_id == "player_can_jump")
    assert "space" in jump_test.description.lower()
    assert "airborne" in jump_test.description.lower()

    col_test = next(t for t in tests if t.test_id == "collectibles_exist")
    assert col_test.params.get("pickup_count") == 7

    win_test = next(t for t in tests if t.test_id == "win_on_collect_all")
    assert "game.won" in win_test.description or any("game.won" in a for a in win_test.assertions)


def test_generate_acceptance_tests_combat_and_shooter():
    """Verify arena combat / shooter GDS generates enemy spawn, combat, defeat all, and health tests."""
    gds = preset_arena_combat()
    tests = generate_acceptance_tests(gds)

    test_ids = {t.test_id for t in tests}
    assert "enemies_spawn" in test_ids
    assert "combat_damages_enemies" in test_ids
    assert "win_on_defeat_all" in test_ids
    assert "player_health_decreases" in test_ids


def test_acceptance_tests_to_scenarios():
    """Verify acceptance test specs convert cleanly into valid executable Scenarios."""
    gds = preset_platformer()
    tests = generate_acceptance_tests(gds)
    scenarios = acceptance_tests_to_scenarios(tests)

    assert len(scenarios) == len(tests)
    for sc in scenarios:
        assert isinstance(sc, Scenario)
        assert sc.schema_ == "scenario/1"
        assert len(sc.steps) >= 1
        assert len(sc.expect) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. Semantic GDS Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_validate_snake_and_ladders():
    """Verify semantic_validate_gds correctly validates snake and ladders intent."""
    gds = _make_snakes_and_ladders_gds()

    # Valid case: prompt specifies snake and ladders, GDS has grid_board and board entity
    valid, issues = semantic_validate_gds(gds, "A 3D snake and ladder game for family")
    assert valid is True
    assert len(issues) == 0

    # Invalid case 1: prompt specifies snake and ladders, but GDS is platformer
    platformer_gds = preset_platformer()
    valid, issues = semantic_validate_gds(platformer_gds, "make a snake and ladder board game")
    assert valid is False
    assert any("genre is 'platformer'" in i and "grid_board" in i for i in issues)

    # Invalid case 2: prompt specifies snake and ladders, but entities missing board
    gds_no_board = _make_snakes_and_ladders_gds()
    object.__setattr__(gds_no_board, "entities", [e for e in gds_no_board.entities if e.kind != EntityKind.BOARD])
    valid, issues = semantic_validate_gds(gds_no_board, "snake and ladder game")
    assert valid is False
    assert any("board" in i for i in issues)


def test_semantic_validate_fps_keyword():
    """Verify FPS/first-person keyword rejects platformer or grid_board."""
    platformer_gds = preset_platformer()
    valid, issues = semantic_validate_gds(platformer_gds, "make a first person shooter with rifles")
    assert valid is False
    assert any("first-person/FPS" in i or "incompatible" in i for i in issues)

    grid_gds = preset_tic_tac_toe()
    valid, issues = semantic_validate_gds(grid_gds, "make a competitive tactical fps game")
    assert valid is False
    assert any("cannot be platformer or grid_board" in i for i in issues)


def test_semantic_validate_platformer():
    """Verify platformer intent requires platformer genre with pickup and goal entities."""
    # When genre matches and has pickup & goal -> pass
    plat_gds = preset_platformer()
    valid, issues = semantic_validate_gds(plat_gds, "create a 3D platformer adventure")
    assert valid is True
    assert len(issues) == 0

    # When prompt specifies platformer but genre is grid_board -> fail
    grid_gds = preset_tic_tac_toe()
    valid, issues = semantic_validate_gds(grid_gds, "a challenging jump platformer")
    assert valid is False
    assert any("platformer" in i.lower() for i in issues)

    # When platformer is missing goal entity -> fail
    plat_gds_no_goal = preset_platformer()
    object.__setattr__(plat_gds_no_goal, "entities", [e for e in plat_gds_no_goal.entities if e.kind != EntityKind.GOAL])
    valid, issues = semantic_validate_gds(plat_gds_no_goal, "platformer game")
    assert valid is False
    assert any("goal" in i.lower() for i in issues)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pipeline Stage Evidence Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_stage_output_design():
    """Verify design stage evidence validation."""
    gds = preset_platformer()

    # Passing design output
    valid_result = {"params": {"genre": "platformer", "pitch": "Valid platformer pitch"}}
    passed, issues = validate_stage_output("design", valid_result, gds)
    assert passed is True
    assert len(issues) == 0

    # Failing design: fallback template used
    fallback_result = {"fallback": True, "params": {"genre": "Action", "pitch": "TODO"}}
    passed, issues = validate_stage_output("design", fallback_result, gds)
    assert passed is False
    assert any("fallback" in i.lower() for i in issues)

    # Failing design: empty pitch
    bad_pitch_gds = preset_platformer()
    bad_pitch_gds.overview.pitch = ""
    passed, issues = validate_stage_output("design", {"params": {"genre": "platformer"}}, bad_pitch_gds)
    assert passed is False
    assert any("pitch" in i.lower() for i in issues)


def test_validate_stage_output_assemble():
    """Verify assemble stage checks player, goal, and main game actors from read-back."""
    gds = _make_snakes_and_ladders_gds()

    # Passing case: read-back contains player, goal, and board
    pass_assemble = {
        "read_back_actors": [
            {"label": "PlayerStart_1", "class": "PlayerStart"},
            {"label": "GoalTrigger_1", "class": "GameForgeGoal"},
            {"label": "GridBoard_1", "class": "GameForgeGridBoard"},
        ]
    }
    passed, issues = validate_stage_output("assemble", pass_assemble, gds)
    assert passed is True
    assert len(issues) == 0

    # Failing case: missing goal actor
    missing_goal = {
        "read_back_actors": [
            {"label": "PlayerStart_1", "class": "PlayerStart"},
            {"label": "GridBoard_1", "class": "GameForgeGridBoard"},
        ]
    }
    passed, issues = validate_stage_output("assemble", missing_goal, gds)
    assert passed is False
    assert any("goal" in i.lower() for i in issues)

    # Failing case: missing player actor
    missing_player = {
        "read_back_actors": [
            {"label": "GoalTrigger_1", "class": "GameForgeGoal"},
            {"label": "GridBoard_1", "class": "GameForgeGridBoard"},
        ]
    }
    passed, issues = validate_stage_output("assemble", missing_player, gds)
    assert passed is False
    assert any("player" in i.lower() for i in issues)

    # Failing case: missing main board actor
    missing_board = {
        "read_back_actors": [
            {"label": "PlayerStart_1", "class": "PlayerStart"},
            {"label": "GoalTrigger_1", "class": "GameForgeGoal"},
        ]
    }
    passed, issues = validate_stage_output("assemble", missing_board, gds)
    assert passed is False
    assert any("board" in i.lower() for i in issues)


def test_validate_stage_output_scenarios():
    """Verify scenarios stage checks that game-specific tests ran and not just generic smoke."""
    gds = preset_platformer()

    # Passing case: game-specific platformer scenarios ran and passed
    pass_scenarios = {
        "results": [
            {"scenario_id": "player_can_jump", "passed": True},
            {"scenario_id": "collectibles_exist", "passed": True},
            {"scenario_id": "win_on_collect_all", "passed": True},
        ]
    }
    passed, issues = validate_stage_output("scenarios", pass_scenarios, gds)
    assert passed is True
    assert len(issues) == 0

    # Failing case: ONLY generic smoke ran
    only_smoke = {
        "results": [
            {"scenario_id": "smoke", "passed": True},
        ]
    }
    passed, issues = validate_stage_output("scenarios", only_smoke, gds)
    assert passed is False
    assert any("generic" in i.lower() for i in issues)

    # Failing case: a scenario failed
    failed_test = {
        "results": [
            {"scenario_id": "player_can_jump", "passed": False, "failures": ["Jump velocity zero"]},
        ]
    }
    passed, issues = validate_stage_output("scenarios", failed_test, gds)
    assert passed is False
    assert any("failed" in i.lower() for i in issues)

    # Failing case: empty results
    empty_res = {"results": []}
    passed, issues = validate_stage_output("scenarios", empty_res, gds)
    assert passed is False
    assert any("no scenario or test results" in i.lower() for i in issues)


def test_validate_stage_output_automation():
    """Verify automation stage accepts successful Unreal Editor C++ Kit automation tests."""
    # Passing case: Kit C++ automation tests passed
    automation_data = {
        "exit_code": 0,
        "filter": "GameForge.Kit",
        "found": True,
        "failed": 0,
        "succeeded": 3,
        "tests": [
            {"name": "GameForge.Kit.Rules.CountAtLeast", "state": "Success"},
            {"name": "GameForge.Kit.Rules.NestingAndDepth", "state": "Success"},
            {"name": "GameForge.Kit.Rules.StatOperators", "state": "Success"},
        ],
    }
    passed, issues = validate_stage_output("automation", automation_data)
    assert passed is True
    assert len(issues) == 0

    # Failing case: C++ automation test failed
    failing_automation = {
        "exit_code": 1,
        "filter": "GameForge.Kit",
        "found": True,
        "failed": 1,
        "succeeded": 2,
        "tests": [
            {"name": "GameForge.Kit.Rules.CountAtLeast", "state": "Fail", "errors": ["Assertion failed"]},
            {"name": "GameForge.Kit.Rules.StatOperators", "state": "Success"},
        ],
    }
    passed, issues = validate_stage_output("automation", failing_automation)
    assert passed is False
    assert any("failed" in i.lower() for i in issues)
