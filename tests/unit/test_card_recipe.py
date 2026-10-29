"""Unit tests for the card_battler recipe parameter validation and source generation."""

import pytest
from src.gameforge_ide.recipes.card_battler.recipe import CardBattlerParams, generate
from src.gameforge_ide.pipeline.spec_from_prompt import match_prompt, is_game_creation_request


def test_card_battler_default_params_valid():
    p = CardBattlerParams()
    p.validate()
    assert p.project_name == "CardBattler"
    assert p.display_title == "Card Battler"
    assert p.difficulty == "normal"
    assert p.player_base_health == 30
    assert p.opponent_base_health == 30
    assert p.starting_hand_size == 4
    assert p.max_hand_size == 7
    assert p.base_energy_per_turn == 3
    assert p.lane_count == 3


def test_card_battler_invalid_project_name():
    with pytest.raises(ValueError, match="project_name must be PascalCase"):
        CardBattlerParams(project_name="invalid_card_game").validate()

    with pytest.raises(ValueError, match="project_name must be PascalCase"):
        CardBattlerParams(project_name="123CardGame").validate()


def test_card_battler_invalid_health_params():
    with pytest.raises(ValueError, match="player_base_health must be between 5 and 200"):
        CardBattlerParams(player_base_health=0).validate()

    with pytest.raises(ValueError, match="opponent_base_health must be between 5 and 200"):
        CardBattlerParams(opponent_base_health=500).validate()


def test_card_battler_invalid_hand_and_energy():
    with pytest.raises(ValueError, match="starting_hand_size must be between 1 and 10"):
        CardBattlerParams(starting_hand_size=0).validate()

    with pytest.raises(ValueError, match="base_energy_per_turn must be between 1 and 10"):
        CardBattlerParams(base_energy_per_turn=0).validate()


def test_card_battler_source_generation():
    p = CardBattlerParams(project_name="LaneBattler", display_title="Lane Battler", player_base_health=25)
    sources = generate(p)

    expected_files = [
        "Source/LaneBattler/GFCardConfig.h",
        "Source/LaneBattler/GFCardTypes.h",
        "Source/LaneBattler/GFCardStateComponent.h",
        "Source/LaneBattler/GFCardStateComponent.cpp",
        "Source/LaneBattler/GFCardOpponentAI.h",
        "Source/LaneBattler/GFCardOpponentAI.cpp",
        "Source/LaneBattler/GFCardGameMode.h",
        "Source/LaneBattler/GFCardGameMode.cpp",
        "Source/LaneBattler/GFCardHUD.h",
        "Source/LaneBattler/GFCardHUD.cpp",
        "Source/LaneBattler/GFCardTests.cpp",
    ]
    for fn in expected_files:
        assert fn in sources, f"Missing expected generated file: {fn}"

    config_content = sources["Source/LaneBattler/GFCardConfig.h"]
    assert "Lane Battler" in config_content
    assert "PlayerBaseHealth = 25;" in config_content
    assert "LaneCount = 3;" in config_content

    state_cpp = sources["Source/LaneBattler/GFCardStateComponent.cpp"]
    assert "ResolveLaneCombat" in state_cpp
    assert "CanPlayCard" in state_cpp
    assert "PlayCard" in state_cpp

    hud_cpp = sources["Source/LaneBattler/GFCardHUD.cpp"]
    assert "AGFCardHUD::DrawHUD" in hud_cpp
    assert "PLAYER BASE:" in hud_cpp
    assert "OPPONENT BASE:" in hud_cpp
    assert "LANE" in hud_cpp


def test_card_battler_prompt_matching():
    spec = match_prompt("create a card battler game with 40 health")
    assert spec.matched
    assert spec.recipe_id == "card_battler"
    assert spec.params.player_base_health == 40
    assert spec.params.opponent_base_health == 40
    assert is_game_creation_request("make a deck builder card game")
