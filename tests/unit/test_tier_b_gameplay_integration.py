"""Unit tests for Tier B Gameplay Integration (Agent 2 - P1).

Verifies that Tier B pure logic game engines (Sudoku, Chess, Racing, Tetris,
Snake, Tower Defense, Roguelike, Zombie Survival) are connected across:
- kit/rules.py: GAME_TYPE_LAYOUT_MAP and GAME_TYPE_REQUIRED_MODULES
- design/intent.py: Prompt intent & genre classification
- design/template_registry.py: Strategy analysis & scratch architecture synthesis
- design/expand.py: Authoritative layout and required module resolution
- composer/compose.py: Composition with feature checks
"""
import pytest

from src.gameforge_ide.kit.rules import (
    GAME_TYPE_LAYOUT_MAP,
    GAME_TYPE_REQUIRED_MODULES,
    get_layout_for_game_type,
    get_required_modules_for_game_type,
    check_composition_features,
)
from src.gameforge_ide.design.gds import Genre, LayoutKind, CameraKind
from src.gameforge_ide.design.draft import DesignDraft, DraftWin, DraftLose
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.design.intent import classify_prompt_intent, detect_genre_intent, is_game_creation_request
from src.gameforge_ide.design.template_registry import default_registry, GenerationStrategy
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.composer.model import CompositionError


def test_tier_b_registry_mappings():
    """Verify all 8 Tier B game types have authoritative layout and module mappings."""
    expected_mappings = {
        "sudoku": ("board", ["kit.grid_board"]),
        "chess": ("board", ["kit.grid_board"]),
        "tetris": ("board", ["kit.grid_board"]),
        "snake": ("board", ["kit.grid_board"]),
        "racing": ("course", ["kit.player_character", "kit.goal"]),
        "tower_defense": ("lanes", ["kit.spawner", "kit.goal"]),
        "roguelike": ("rooms", ["kit.player_character", "kit.enemy_melee", "kit.door"]),
        "zombie_survival": ("arena", ["kit.player_character", "kit.enemy_melee", "kit.spawner"]),
    }
    for gt, (expected_layout, expected_mods) in expected_mappings.items():
        assert get_layout_for_game_type(gt) == expected_layout
        mods = get_required_modules_for_game_type(gt)
        for m in expected_mods:
            assert m in mods, f"Module {m} missing from {gt}"


def test_tier_b_intent_classification():
    """Verify natural language prompts for Tier B games are classified as creation requests with correct genres."""
    test_cases = [
        ("create a sudoku puzzle game", Genre.PUZZLE),
        ("make a chess game for two players", Genre.GRID_BOARD),
        ("build a tetris block puzzle", Genre.PUZZLE),
        ("develop a classic snake game", Genre.PUZZLE),
        ("create a high speed racing game", Genre.PLATFORMER),
        ("build a tower defense game defending the base", Genre.TOP_DOWN_SHOOTER),
        ("make a roguelike dungeon crawl", Genre.DUNGEON_CRAWLER),
        ("create a zombie survival arena", Genre.ARENA_COMBAT),
    ]
    for prompt, expected_genre in test_cases:
        assert is_game_creation_request(prompt) is True
        result = classify_prompt_intent(prompt)
        assert result.is_creation is True
        assert result.genre == expected_genre, f"Expected {expected_genre} for '{prompt}', got {result.genre}"


def test_tier_b_scratch_architectures():
    """Verify semantic template registry synthesizes dedicated scratch architectures."""
    tier_b_prompts = [
        ("racing", "scratch_racing", "ARaceGameMode"),
        ("tower defense", "scratch_tower_defense", "ATowerDefenseGameMode"),
        ("roguelike", "scratch_roguelike", "ARoguelikeGameMode"),
        ("zombie survival", "scratch_zombie_survival", "AZombieSurvivalGameMode"),
    ]
    for prompt, expected_plan_kind, expected_class in tier_b_prompts:
        profile = default_registry.analyze_prompt(prompt)
        arch = default_registry._synthesize_scratch_architecture(profile)
        assert arch.get("plan_kind") == expected_plan_kind
        assert expected_class in arch.get("target_classes", [])


def test_tier_b_draft_expansion_and_composition():
    """Verify expanding drafts for Tier B games resolves correct layouts and modules."""
    # Test Sudoku draft expansion
    sudoku_draft = DesignDraft(
        title="Sudoku Challenge",
        genre=Genre.PUZZLE,
        camera=CameraKind.FIXED_BOARD,
        pitch="Play classic 9x9 sudoku",
        entities=[],
        win=[DraftWin(type="board_win")],
        lose=[],
    )
    gds = expand_draft(sudoku_draft)
    assert gds.scene.levels[0].layout == LayoutKind.BOARD
    assert any(e.module == "kit.grid_board" for e in gds.entities)

    # Test Racing draft expansion
    racing_draft = DesignDraft(
        title="Formula Racing",
        genre=Genre.PLATFORMER,
        camera=CameraKind.THIRD_PERSON,
        pitch="High speed racing course",
        entities=[],
        win=[DraftWin(type="reach_goal")],
        lose=[DraftLose(type="timer_runs_out", seconds=120)],
    )
    gds_race = expand_draft(racing_draft)
    assert gds_race.scene.levels[0].layout == LayoutKind.COURSE
    assert any(e.module == "kit.player_character" for e in gds_race.entities)
    assert any(e.module == "kit.goal" for e in gds_race.entities)

    # Compose both GDS specs and verify composition passes
    comp_sudoku = compose(gds)
    assert len(comp_sudoku.levels) == 1
    assert any("board" in a.tags or a.entity_id == "board" for a in comp_sudoku.levels[0].actors)

    comp_race = compose(gds_race)
    assert len(comp_race.levels) == 1
    assert any("goal" in a.tags or a.entity_id == "goal" for a in comp_race.levels[0].actors)
