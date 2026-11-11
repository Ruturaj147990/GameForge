"""Permanent Evaluation Benchmark for Semantic Template Suitability & Strategy Selection (Part 2.5).

Verifies that diverse game genres are correctly mapped to:
- Strategy A (ADAPT_TEMPLATE) for high-overlap canonical genres (Platformer, Tactical FPS, Card Battler)
- Strategy B (HYBRID) for mixed requirements (Top-Down Roguelike Shooter, Tower Defense)
- Strategy C (SCRATCH) for distinct discrete games and logic puzzles (Sudoku, Chess, Tetris, Snake)
Guarantees that no puzzle game is ever matched to combat, platformers, or falling cubes.
"""
from __future__ import annotations

import pytest
from src.gameforge_ide.design.gds import Genre, CameraKind
from src.gameforge_ide.design.template_registry import (
    Capability,
    GenerationStrategy,
    SemanticTemplateRegistry,
    default_registry,
)


@pytest.fixture
def registry() -> SemanticTemplateRegistry:
    return default_registry


def test_sudoku_maps_to_scratch_and_never_combat_or_platformer(registry: SemanticTemplateRegistry):
    prompt = "Create a 9x9 Sudoku puzzle game with number input and row/column validation"
    decision = registry.evaluate_strategy(prompt)

    # Strategy assertion
    assert decision.strategy == GenerationStrategy.SCRATCH, f"Expected SCRATCH for Sudoku, got {decision.strategy}"
    assert decision.template is None
    assert decision.profile.detected_genre == Genre.PUZZLE

    # Architectural assertions
    arch = decision.suggested_architecture
    assert arch["plan_kind"] == "scratch_puzzle"
    assert "UGridPuzzleSubsystem" in arch["target_classes"]
    assert "ASudokuGameMode" in arch["target_classes"]
    assert any("Grid" in w for w in arch["target_widgets"])

    # Incompatibility assertions: check that ALL combat and platformer templates were strictly rejected
    for ev in decision.evaluations:
        if ev.template.id in ("platformer_3d", "tactical_fps", "arena_combat", "top_down_shooter"):
            assert ev.has_conflict is True, f"Template {ev.template.id} should have conflicted with Sudoku"
            assert ev.overlap_score == 0.0, f"Template {ev.template.id} score should be 0.0"


def test_chess_maps_to_scratch_and_never_platformer(registry: SemanticTemplateRegistry):
    prompt = "Build a 2-player turn-based Chess game on an 8x8 board with piece movement rules"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.SCRATCH
    assert decision.profile.detected_genre == Genre.GRID_BOARD
    arch = decision.suggested_architecture
    assert arch["plan_kind"] == "scratch_board"
    assert "UBoardGameSubsystem" in arch["target_classes"]

    # Verify platformer and combat conflict
    for ev in decision.evaluations:
        if ev.template.id in ("platformer_3d", "tactical_fps"):
            assert ev.has_conflict is True


def test_tetris_maps_to_scratch_puzzle(registry: SemanticTemplateRegistry):
    prompt = "Make a classic Tetris game with falling tetrominoes and line clearing"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.SCRATCH
    assert decision.profile.detected_genre == Genre.PUZZLE
    arch = decision.suggested_architecture
    assert arch["plan_kind"] == "scratch_falling_blocks"
    assert "UGridPuzzleSubsystem" in arch["target_classes"]

    # Verify platformer was rejected
    for ev in decision.evaluations:
        if ev.template.id == "platformer_3d":
            assert ev.has_conflict is True


def test_snake_maps_to_scratch_puzzle(registry: SemanticTemplateRegistry):
    prompt = "Make a retro 2D Snake game where eating apples grows your tail"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.SCRATCH
    assert decision.profile.detected_genre == Genre.PUZZLE
    arch = decision.suggested_architecture
    assert arch["plan_kind"] == "scratch_snake"
    assert "ASnakeGameMode" in arch["target_classes"]


def test_3d_platformer_maps_to_adapt_template(registry: SemanticTemplateRegistry):
    prompt = "Create a 3D platformer with double jump, obstacle course, and floating gold coin collectibles"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.ADAPT_TEMPLATE
    assert decision.template is not None
    assert decision.template.id == "platformer_3d"
    assert decision.suitability_score >= 0.80
    assert len(decision.reasons) > 0


def test_tactical_fps_maps_to_adapt_template(registry: SemanticTemplateRegistry):
    prompt = "Build a tactical first-person shooter with rifle shooting, enemy combat bots, and bomb defusal"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.ADAPT_TEMPLATE
    assert decision.template is not None
    assert decision.template.id == "tactical_fps"
    assert decision.suitability_score >= 0.80


def test_top_down_shooter_maps_to_adapt_template(registry: SemanticTemplateRegistry):
    prompt = "Create a top-down shooter with twin-stick controls, weapon fire, and wave-based enemy hordes"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy in (GenerationStrategy.ADAPT_TEMPLATE, GenerationStrategy.HYBRID)
    assert decision.template is not None
    assert decision.template.id == "top_down_shooter"
    assert decision.suitability_score >= 0.60


def test_card_battler_maps_to_adapt_template(registry: SemanticTemplateRegistry):
    prompt = "Make a turn-based card battler game with deck matching and custom UI cards"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.ADAPT_TEMPLATE
    assert decision.template is not None
    assert decision.template.id == "card_battler"
    assert decision.suitability_score >= 0.80


def test_tower_defense_maps_to_hybrid_or_scratch(registry: SemanticTemplateRegistry):
    prompt = "Build a tower defense game where players place towers on a grid to defend against enemy waves"
    decision = registry.evaluate_strategy(prompt)

    # Tower defense has wave spawner, top down, grid, but no physics character jumping
    assert decision.strategy in (GenerationStrategy.HYBRID, GenerationStrategy.SCRATCH)
    for ev in decision.evaluations:
        if ev.template.id == "platformer_3d":
            assert ev.has_conflict is True


def test_racing_game_maps_to_scratch(registry: SemanticTemplateRegistry):
    prompt = "Make a fast-paced 3D car racing game with vehicle physics and lap times"
    decision = registry.evaluate_strategy(prompt)

    # No vehicle template in canonical templates -> SCRATCH
    assert decision.strategy == GenerationStrategy.SCRATCH
    assert Capability.VEHICLE_PHYSICS in decision.profile.required_capabilities


def test_snakes_and_ladders_maps_to_scratch_and_never_platformer(registry: SemanticTemplateRegistry):
    prompt = "Create a Snake and Ladders game"
    decision = registry.evaluate_strategy(prompt)

    assert decision.strategy == GenerationStrategy.SCRATCH, f"Expected SCRATCH for Snake and Ladders, got {decision.strategy}"
    assert decision.template is None
    assert decision.profile.detected_genre == Genre.GRID_BOARD
    arch = decision.suggested_architecture
    assert arch["plan_kind"] == "scratch_board"
    assert "UBoardGameSubsystem" in arch["target_classes"]
    assert "ASnakesAndLaddersGameMode" in arch["target_classes"]
    assert arch["mechanics"].get("grid_size") == 10
    assert arch["mechanics"].get("dice_sides") == 6

    # Critical requirement: platformer, combat, and FPS templates MUST strictly conflict
    for ev in decision.evaluations:
        if ev.template.id in ("platformer_3d", "tactical_fps", "arena_combat", "top_down_shooter", "card_battler"):
            assert ev.has_conflict is True, f"Template {ev.template.id} should have conflicted with Snake and Ladders"
            assert ev.overlap_score == 0.0, f"Template {ev.template.id} score should be 0.0"
