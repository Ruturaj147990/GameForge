"""Unit & Regression tests for AI Intent, Spec from Prompt, Presets, and Semantic Validation.

Covers:
- DEF-088: Conversational and informational prompt hijacking eliminated.
- DEF-089: Template hijacking on custom mechanics & narrative eliminated.
- DEF-090: Missing modern genres, typos, and colloquialisms comprehensively supported.
- DEF-091: Semantic validation false rejections eliminated on frame rates (60 fps) and emergent gameplay.
- DEF-092: Dedicated design/intent.py and design/spec_from_prompt.py architecture.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from src.gameforge_ide.design.gds import EntityKind, Genre
from src.gameforge_ide.design.intent import (
    IntentType,
    classify_prompt_intent,
    detect_genre_intent,
    extract_gameplay_mechanics,
    is_game_creation_request,
    normalize_prompt,
    strip_conversational_prefixes,
)
from src.gameforge_ide.design.presets import (
    PRESETS,
    PRESET_KEYWORDS,
    extract_preset_overrides,
    preset_platformer,
    preset_tic_tac_toe,
)
from src.gameforge_ide.design.prompt_to_gds import (
    PRESET_TITLES,
    PromptToGdsResult,
    prompt_to_gds,
)
from src.gameforge_ide.design.semantic_validate import semantic_validate_gds
from src.gameforge_ide.design.spec_from_prompt import (
    expand_game_flags,
    match_prompt,
)


# =============================================================================
# DEF-088: Conversational and Informational Prompt Hijacking
# =============================================================================

@pytest.mark.parametrize(
    "conversational_prompt",
    [
        "Hello!",
        "Hey there",
        "Good morning",
        "Who are you?",
        "What is GameForge?",
        "What can you do?",
        "Thank you so much!",
        "Thanks for your help",
        "Could you explain how to make a platformer?",
        "Can you tell me what a platformer game is?",
        "Hey, what is a platformer game?",
        "Hello, who made this platformer game?",
        "Hey, how do I make a platformer in unreal?",
        "Do you know any good platformer games?",
        "Can you explain card battler mechanics?",
        "Tell me about roguelike games",
        "What's the difference between Gomoku and Tic-Tac-Toe?",
    ],
)
def test_conversational_and_informational_prompts_not_game_creation(conversational_prompt: str):
    """Verify that conversational greetings and informational questions are not parsed as game creation."""
    assert is_game_creation_request(conversational_prompt) is False
    res = prompt_to_gds(conversational_prompt)
    assert res.status == "UNSUPPORTED"
    assert res.path == "none"

    result = classify_prompt_intent(conversational_prompt)
    assert result.is_creation is False
    assert result.intent in (IntentType.CONVERSATIONAL, IntentType.INFORMATIONAL, IntentType.UNKNOWN)


# =============================================================================
# DEF-089: Template Hijacking on Custom Mechanics and Narrative
# =============================================================================

@pytest.mark.parametrize(
    "mechanic_prompt",
    [
        "create a platformer with dash",
        "create a platformer with grapple",
        "make an arena combat with shields",
        "create a card battler with mana",
        "make a platformer with climbing",
        "make a platformer with jetpack",
        "make a platformer with walljump",
        "make a platformer with sprint",
        "make a platformer with gliding",
        "make an arena combat with parry and dodge",
    ],
)
def test_template_hijacking_mechanics_route_to_model(mechanic_prompt: str):
    """Verify that prompts specifying custom mechanics are not coerced into rigid presets."""
    valid_draft = {
        "title": "Custom Mechanics Game",
        "genre": "platformer",
        "camera": "third_person",
        "pitch": mechanic_prompt,
        "entities": [{"kind": "player", "count": 1}, {"kind": "pickup", "count": 5}],
        "win": [{"type": "reach_goal"}],
        "lose": [{"type": "fall_off"}],
    }
    mock_complete = MagicMock(return_value=json.dumps(valid_draft))
    res = prompt_to_gds(mechanic_prompt, complete_json=mock_complete, allow_model=True)
    assert res.path == "model"
    assert res.status == "OK"
    assert mock_complete.called is True


def test_pure_preset_requests_still_use_preset_path():
    """Verify that pure standard preset requests without custom mechanics continue to use the fast preset path."""
    mock_complete = MagicMock()
    res = prompt_to_gds(
        "make a 3d platformer with 8 coins called Sky Hop",
        complete_json=mock_complete,
        allow_model=True,
    )
    assert res.status == "OK"
    assert res.path == "preset"
    assert mock_complete.called is False


# =============================================================================
# DEF-090: Missing Modern Game Genres, Typos, and Colloquialisms
# =============================================================================

@pytest.mark.parametrize(
    "prompt_with_typo",
    [
        "buid a platformer",
        "biuld a platformer",
        "crte a platformer",
        "creaet a platformer",
        "mak a platformer",
        "mkae a platformer",
        "make a rouguelike",
        "make a tower defence",
    ],
)
def test_typos_in_create_verbs_and_genres(prompt_with_typo: str):
    """Verify that common typographical errors in verbs or genres are properly recognized."""
    assert is_game_creation_request(prompt_with_typo) is True


@pytest.mark.parametrize(
    "novel_genre_prompt",
    [
        "make an autobattler",
        "make a bullet hell",
        "make a shmup",
        "make a souls-like",
        "make a deckbuilder",
        "make a battle royale",
        "make a moba",
        "create an arpg",
        "make a hack and slash",
        "make a beat em up",
        "make a visual novel",
        "make an idle clicker",
        "make a roguelite",
    ],
)
def test_modern_novel_genres_recognized(novel_genre_prompt: str):
    """Verify that modern and indie game genres are accurately recognized as game creation requests."""
    assert is_game_creation_request(novel_genre_prompt) is True


def test_preset_keywords_and_titles_contain_top_down_shooter_and_relic_hunt():
    """Verify top_down_shooter and relic_hunt are fully registered in PRESET_KEYWORDS and PRESET_TITLES."""
    assert "top_down_shooter" in PRESET_KEYWORDS
    assert "relic_hunt" in PRESET_KEYWORDS
    assert "Top-Down Shooter" in PRESET_TITLES
    assert "Relic Hunt" in PRESET_TITLES

    overrides = extract_preset_overrides("top_down_shooter", "create a top-down shooter with 5 waves of 6 enemies")
    assert overrides.get("wave_count") == 5
    assert overrides.get("enemies_per_wave") == 6


# =============================================================================
# DEF-091: Semantic Validation False Rejections on Emergent Designs & Frame Rates
# =============================================================================

def test_semantic_validate_frame_rate_not_confused_with_fps_shooter():
    """Verify that specifying 60 fps or 120 fps is not misclassified as a first-person shooter mismatch."""
    plat = preset_platformer()
    valid, issues = semantic_validate_gds(plat, "A 3D platformer running smoothly at 60 fps")
    assert valid is True
    assert len(issues) == 0

    valid, issues = semantic_validate_gds(plat, "A 3D platformer targeting 120 fps")
    assert valid is True
    assert len(issues) == 0


def test_semantic_validate_first_person_platformer_allowed():
    """Verify that first-person platformers are recognized as a valid platformer genre."""
    plat = preset_platformer()
    valid, issues = semantic_validate_gds(plat, "A first person platformer obstacle course")
    assert valid is True
    assert len(issues) == 0


def test_semantic_validate_emergent_platformer_without_pickups():
    """Verify that pure platformers or speedruns with no collectibles are permitted without pickups."""
    plat_no_pickups = preset_platformer()
    object.__setattr__(
        plat_no_pickups,
        "entities",
        [e for e in plat_no_pickups.entities if e.kind != EntityKind.PICKUP],
    )
    valid, issues = semantic_validate_gds(
        plat_no_pickups,
        "A pure parkour platformer with no collectibles, just reach the summit",
    )
    assert valid is True
    assert len(issues) == 0

    # Without explicit prompt exemption, missing pickups should still fail
    valid_unexempt, issues_unexempt = semantic_validate_gds(
        plat_no_pickups,
        "create a standard 3D platformer",
    )
    assert valid_unexempt is False
    assert any("pickup" in i for i in issues_unexempt)


def test_semantic_validate_shooter_novel_genres():
    """Verify that shooter mechanics are allowed in dungeon crawlers and custom genres."""
    plat = preset_platformer()
    object.__setattr__(plat.overview, "genre", Genre.DUNGEON_CRAWLER)
    # Add an enemy so entity requirements pass
    valid, issues = semantic_validate_gds(plat, "A dungeon crawler shooter with bows and crossbows")
    assert valid is True
    assert len(issues) == 0


# =============================================================================
# DEF-092: Architectural Intent Module & Design Spec Bridge
# =============================================================================

def test_intent_module_capabilities():
    """Verify IntentType classification, mechanics extraction, and genre detection."""
    result = classify_prompt_intent("create a fast-paced platformer with dash and walljump")
    assert result.intent == IntentType.GAME_CREATION
    assert result.is_creation is True
    assert result.genre == Genre.PLATFORMER
    assert "dash" in result.mechanics
    assert any("walljump" in m or "wall-jump" in m for m in result.mechanics)

    # Mutation intent
    result_mut = classify_prompt_intent("increase player jump height in my game")
    assert result_mut.intent == IntentType.GAME_MUTATION

    # Debug intent
    result_debug = classify_prompt_intent("fix the null pointer compiler error in LevelOps.cpp")
    assert result_debug.intent == IntentType.CODE_OR_DEBUG


def test_design_spec_from_prompt_bridge():
    """Verify src/gameforge_ide/design/spec_from_prompt.py exposes standard pipeline tools."""
    spec = match_prompt("tic tac toe")
    assert spec.matched is True
    assert spec.recipe_id == "grid_board_game"

    flags_expanded = expand_game_flags("gomoku --size 9 --win 4")
    assert "9x9" in flags_expanded
    assert "4 in a row" in flags_expanded
