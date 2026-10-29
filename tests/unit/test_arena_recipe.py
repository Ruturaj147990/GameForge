"""Unit tests for the arena_combat recipe parameter validation and source generation."""

import pytest
from src.gameforge_ide.recipes.arena_combat.recipe import ArenaCombatParams, generate
from src.gameforge_ide.pipeline.spec_from_prompt import match_prompt, is_game_creation_request


def test_arena_combat_default_params_valid():
    p = ArenaCombatParams()
    p.validate()
    assert p.project_name == "ArenaCombat"
    assert p.display_title == "Arena Combat"
    assert p.difficulty == "normal"
    assert p.wave_count == 3
    assert p.enemies_per_wave == 4
    assert p.player_max_health == 100.0
    assert p.player_attack_damage == 35.0
    assert p.player_attack_range == 250.0
    assert p.player_attack_cooldown == 0.4
    assert p.enemy_max_health == 50.0
    assert p.enemy_attack_damage == 15.0
    assert p.enemy_attack_range == 120.0
    assert p.enemy_attack_cooldown == 1.0
    assert p.enemy_speed == 350.0


def test_arena_combat_invalid_project_name():
    with pytest.raises(ValueError, match="project_name must be PascalCase"):
        ArenaCombatParams(project_name="invalid_arena").validate()

    with pytest.raises(ValueError, match="project_name must be PascalCase"):
        ArenaCombatParams(project_name="123Arena").validate()


def test_arena_combat_invalid_wave_params():
    with pytest.raises(ValueError, match="wave_count must be between 1 and 20"):
        ArenaCombatParams(wave_count=0).validate()

    with pytest.raises(ValueError, match="wave_count must be between 1 and 20"):
        ArenaCombatParams(wave_count=25).validate()

    with pytest.raises(ValueError, match="enemies_per_wave must be between 1 and 50"):
        ArenaCombatParams(enemies_per_wave=0).validate()


def test_arena_combat_invalid_difficulty():
    with pytest.raises(ValueError, match="difficulty must be easy\\|normal\\|hard"):
        ArenaCombatParams(difficulty="extreme").validate()


def test_arena_combat_invalid_combat_params():
    with pytest.raises(ValueError, match="player_max_health must be between 10 and 1000"):
        ArenaCombatParams(player_max_health=5.0).validate()

    with pytest.raises(ValueError, match="player_attack_damage must be between 5 and 500"):
        ArenaCombatParams(player_attack_damage=2.0).validate()

    with pytest.raises(ValueError, match="player_attack_range must be between 50 and 1000"):
        ArenaCombatParams(player_attack_range=20.0).validate()

    with pytest.raises(ValueError, match="player_attack_cooldown must be between 0.05 and 5.0"):
        ArenaCombatParams(player_attack_cooldown=0.01).validate()

    with pytest.raises(ValueError, match="enemy_speed must be between 50 and 1200"):
        ArenaCombatParams(enemy_speed=2000.0).validate()


def test_arena_combat_source_generation():
    p = ArenaCombatParams(project_name="GladiatorArena", display_title="Gladiator Arena", wave_count=5, enemies_per_wave=6)
    sources = generate(p)

    expected_files = [
        "Source/GladiatorArena/GFArenaConfig.h",
        "Source/GladiatorArena/GFArenaCharacter.h",
        "Source/GladiatorArena/GFArenaCharacter.cpp",
        "Source/GladiatorArena/GFArenaAIController.h",
        "Source/GladiatorArena/GFArenaAIController.cpp",
        "Source/GladiatorArena/GFArenaEnemy.h",
        "Source/GladiatorArena/GFArenaEnemy.cpp",
        "Source/GladiatorArena/GFArenaHUD.h",
        "Source/GladiatorArena/GFArenaHUD.cpp",
        "Source/GladiatorArena/GFArenaGameMode.h",
        "Source/GladiatorArena/GFArenaGameMode.cpp",
        "Source/GladiatorArena/GFArenaTests.cpp",
    ]
    for fn in expected_files:
        assert fn in sources, f"Missing expected generated file: {fn}"

    config_content = sources["Source/GladiatorArena/GFArenaConfig.h"]
    assert "Gladiator Arena" in config_content
    assert "WaveCount = 5;" in config_content
    assert "EnemiesPerWave = 6;" in config_content

    hud_cpp = sources["Source/GladiatorArena/GFArenaHUD.cpp"]
    assert "AGFArenaHUD::DrawHUD" in hud_cpp
    assert "HEALTH:" in hud_cpp
    assert "WAVE:" in hud_cpp
    assert "SCORE:" in hud_cpp

    gamemode_cpp = sources["Source/GladiatorArena/GFArenaGameMode.cpp"]
    assert "GF_ARENA_SELFTEST PASS" in gamemode_cpp
    assert "MoveToActor" in sources["Source/GladiatorArena/GFArenaAIController.cpp"]


def test_arena_combat_prompt_matching():
    spec = match_prompt("create an arena combat game with 4 waves and 5 enemies per wave")
    assert spec.matched
    assert spec.recipe_id == "arena_combat"
    assert spec.params.wave_count == 4
    assert spec.params.enemies_per_wave == 5
    assert is_game_creation_request("make an action arena game")
