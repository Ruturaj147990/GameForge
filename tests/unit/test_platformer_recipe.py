"""Unit tests for the platformer recipe parameter validation and source generation."""

import pytest
from tests.fixtures.legacy_recipes.platformer.recipe import PlatformerParams, generate
from src.gameforge_ide.pipeline.spec_from_prompt import match_prompt, is_game_creation_request


def test_platformer_default_params_valid():
    p = PlatformerParams()
    p.validate()
    assert p.project_name == "Platformer"
    assert p.collectible_target == 5
    assert p.difficulty == "normal"
    assert p.player_speed == 600.0
    assert p.jump_velocity == 650.0
    assert p.gravity_scale == 1.2
    assert p.air_control == 0.35
    assert p.kill_z == -500.0


def test_platformer_invalid_project_name():
    with pytest.raises(ValueError, match="project_name must be PascalCase"):
        PlatformerParams(project_name="invalid_name").validate()

    with pytest.raises(ValueError, match="project_name must be PascalCase"):
        PlatformerParams(project_name="123Platformer").validate()


def test_platformer_invalid_collectible_target():
    with pytest.raises(ValueError, match="collectible_target must be between 1 and 50"):
        PlatformerParams(collectible_target=0).validate()

    with pytest.raises(ValueError, match="collectible_target must be between 1 and 50"):
        PlatformerParams(collectible_target=100).validate()


def test_platformer_invalid_difficulty():
    with pytest.raises(ValueError, match="difficulty must be easy\\|normal\\|hard"):
        PlatformerParams(difficulty="impossible").validate()


def test_platformer_invalid_movement_params():
    with pytest.raises(ValueError, match="player_speed must be between 100 and 2000"):
        PlatformerParams(player_speed=50.0).validate()

    with pytest.raises(ValueError, match="jump_velocity must be between 200 and 1500"):
        PlatformerParams(jump_velocity=100.0).validate()

    with pytest.raises(ValueError, match="gravity_scale must be between 0.1 and 5.0"):
        PlatformerParams(gravity_scale=0.0).validate()

    with pytest.raises(ValueError, match="air_control must be between 0.0 and 1.0"):
        PlatformerParams(air_control=1.5).validate()


def test_platformer_source_generation():
    p = PlatformerParams(project_name="SkyJump", display_title="Sky Jump 3D", collectible_target=7)
    sources = generate(p)

    expected_files = [
        "Source/SkyJump/GFPlatformerConfig.h",
        "Source/SkyJump/GFPlatformerCollectible.h",
        "Source/SkyJump/GFPlatformerCollectible.cpp",
        "Source/SkyJump/GFPlatformerCheckpoint.h",
        "Source/SkyJump/GFPlatformerCheckpoint.cpp",
        "Source/SkyJump/GFPlatformerGoal.h",
        "Source/SkyJump/GFPlatformerGoal.cpp",
        "Source/SkyJump/GFPlatformerCharacter.h",
        "Source/SkyJump/GFPlatformerCharacter.cpp",
        "Source/SkyJump/GFPlatformerHUD.h",
        "Source/SkyJump/GFPlatformerHUD.cpp",
        "Source/SkyJump/GFPlatformerGameMode.h",
        "Source/SkyJump/GFPlatformerGameMode.cpp",
        "Source/SkyJump/GFPlatformerTests.cpp",
    ]
    for fn in expected_files:
        assert fn in sources, f"Missing expected generated file: {fn}"

    config_content = sources["Source/SkyJump/GFPlatformerConfig.h"]
    assert "Sky Jump 3D" in config_content
    assert "CollectibleTarget = 7;" in config_content

    hud_cpp = sources["Source/SkyJump/GFPlatformerHUD.cpp"]
    assert "AGFPlatformerHUD::DrawHUD" in hud_cpp
    assert "COINS:" in hud_cpp
    assert "CHECKPOINT:" in hud_cpp


def test_platformer_prompt_matching():
    spec = match_prompt("make me a 3d platformer game with 8 coins")
    assert spec.matched
    assert spec.recipe_id == "platformer"
    assert spec.params.collectible_target == 8
    assert is_game_creation_request("create a platformer jumping game")
