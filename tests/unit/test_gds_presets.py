"""Unit tests for GDS presets (P1 WI-1.5)."""
from __future__ import annotations

from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.presets import (
    PRESETS,
    PRESET_KEYWORDS,
    extract_preset_overrides,
    preset_arena_combat,
    preset_card_battler,
    preset_connect_four,
    preset_gomoku,
    preset_platformer,
    preset_procedural_world,
    preset_tic_tac_toe,
)


def test_every_preset_creates_valid_gds():
    for name, factory in PRESETS.items():
        gds = factory()
        assert isinstance(gds, GameDesignSpec), f"Preset {name} did not return GameDesignSpec"
        # Validate round-trip
        reloaded = GameDesignSpec.model_validate_json(gds.to_json())
        assert reloaded == gds


def test_preset_tic_tac_toe_props():
    gds = preset_tic_tac_toe()
    board = next((e for e in gds.entities if e.entity_id == "board"), None)
    assert board is not None
    assert board.props["board_size"] == 3
    assert board.props["win_length"] == 3
    assert board.props["vs_ai"] is True


def test_preset_connect_four_props():
    gds = preset_connect_four()
    board = next((e for e in gds.entities if e.entity_id == "board"), None)
    assert board is not None
    assert board.props["board_size"] == 7
    assert board.props["gravity"] is True


def test_preset_platformer_overrides():
    overrides = extract_preset_overrides("platformer", "Create a 3d platformer with 12 collectibles")
    assert overrides.get("collectible_target") == 12
    gds = preset_platformer(**overrides)
    pickups = next((e for e in gds.entities if e.entity_id == "pickups"), None)
    assert pickups is not None
    assert pickups.count == 12


def test_preset_arena_combat_overrides():
    overrides = extract_preset_overrides("arena_combat", "Make an arena combat game with 5 waves of 8 enemies")
    assert overrides.get("wave_count") == 5
    assert overrides.get("enemies_per_wave") == 8
    gds = preset_arena_combat(**overrides)
    spawner = next((e for e in gds.entities if e.entity_id == "spawner"), None)
    assert spawner is not None
    assert spawner.props["wave_count"] == 5
    assert spawner.props["enemies_per_wave"] == 8


def test_preset_procedural_world_overrides():
    overrides = extract_preset_overrides("procedural_world", "Generate a procedural mountain landscape with seed 4242")
    assert overrides.get("terrain_type") == "Mountains"
    assert overrides.get("seed") == 4242
    gds = preset_procedural_world(**overrides)
    lvl = gds.scene.levels[0]
    assert lvl.layout_params["terrain_type"] == "Mountains"
    assert lvl.seed == 4242
