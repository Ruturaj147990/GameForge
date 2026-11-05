"""Unit tests for prompt classification, intent analysis, and anti-hijacking (WI-1.6 / P1 / P9)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from src.gameforge_ide.design.gds import CameraKind, EntityKind, Genre
from src.gameforge_ide.design.intent import (
    IntentType,
    classify_prompt_intent,
    detect_genre_intent,
    extract_gameplay_mechanics,
    is_game_creation_request,
    normalize_prompt,
    strip_conversational_prefixes,
)
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds


def test_normalize_prompt_and_typos():
    """Verify common typos and punctuation are normalized."""
    assert "build" in normalize_prompt("buid a platformer")
    assert "platformer" in normalize_prompt("make a platfromer")
    assert "roguelike" in normalize_prompt("create a rouguelike game")
    assert "game" in normalize_prompt("make a gaem")


def test_strip_conversational_prefixes():
    """Verify conversational pleasantries are stripped cleanly."""
    assert strip_conversational_prefixes("hello, can you make a game") == "make a game"
    assert strip_conversational_prefixes("Hey please create a 3d platformer") == "create a 3d platformer"
    assert strip_conversational_prefixes("Hi! I want a racing game") == "I want a racing game"


def test_is_game_creation_request_archetypes():
    """Verify standard game creation requests are identified."""
    assert is_game_creation_request("create a 3d platformer with 10 coins")
    assert is_game_creation_request("make a top-down shooter")
    assert is_game_creation_request("build an arena combat game")
    assert is_game_creation_request("make a snake and ladders game")
    assert is_game_creation_request("author a dungeon crawler")
    assert is_game_creation_request("develop an endless runner")
    assert is_game_creation_request("tic tac toe")
    assert is_game_creation_request("chess")
    assert is_game_creation_request("connect four")


def test_is_game_creation_request_non_creation_filtered():
    """Verify questions, bug reports, and conversational greetings are not treated as creation."""
    assert not is_game_creation_request("hello there")
    assert not is_game_creation_request("who are you?")
    assert not is_game_creation_request("what is the difference between GAS and blueprints?")
    assert not is_game_creation_request("how does the character jump in Unreal Engine?")
    assert not is_game_creation_request("fix the compile error in PlayerCharacter.cpp")
    assert not is_game_creation_request("debug null pointer in weapon component")
    assert not is_game_creation_request("can you explain the game mode lifecycle?")


def test_detect_genre_intent_dominant_over_subordinate():
    """Verify primary genre is not hijacked by secondary feature keywords."""
    # Subordinate 'chess' or 'tiles' should not override platformer
    assert detect_genre_intent("a 3d platformer game with giant floating chess tiles") == Genre.PLATFORMER
    assert detect_genre_intent("arena combat with card collecting mini-game") == Genre.ARENA_COMBAT
    assert detect_genre_intent("top-down shooter on a grid board arena") == Genre.TOP_DOWN_SHOOTER
    assert detect_genre_intent("dungeon crawler with platforming obstacles") == Genre.DUNGEON_CRAWLER


def test_classify_prompt_intent():
    """Verify multi-class intent result returns accurate IntentType."""
    res_conv = classify_prompt_intent("hi, good morning!")
    assert res_conv.intent == IntentType.CONVERSATIONAL
    assert not res_conv.is_creation

    res_info = classify_prompt_intent("how does the enhanced input system work in UE 5.7?")
    assert res_info.intent == IntentType.INFORMATIONAL
    assert not res_info.is_creation

    res_debug = classify_prompt_intent("fix the syntax error in Source/Game/Hero.cpp")
    assert res_debug.intent == IntentType.CODE_OR_DEBUG
    assert not res_debug.is_creation

    res_create = classify_prompt_intent("create a fast-paced arena combat game with sword and shield")
    assert res_create.intent == IntentType.GAME_CREATION
    assert res_create.is_creation
    assert res_create.genre == Genre.ARENA_COMBAT
    assert "shield" in res_create.mechanics or "sword" in res_create.mechanics


def test_extract_gameplay_mechanics():
    """Verify recognized gameplay mechanics are extracted from prompt text."""
    mechanics = extract_gameplay_mechanics("A ninja platformer with double-jump, dash, and wall-jump")
    assert "dash" in mechanics
    assert "double-jump" in mechanics or "double jump" in mechanics
    assert "wall-jump" in mechanics or "walljump" in mechanics


def test_prevent_template_hijacking_on_creative_prompt():
    """Verify creative prompt with model provided generates model draft without preset hijacking."""
    mock_complete = MagicMock(return_value=json.dumps({
        "title": "Neon Infiltrator",
        "genre": "custom",
        "camera": "first_person",
        "pitch": "Sneak through a neon cyberpunk facility hacking terminals",
        "entities": [
            {"kind": "guard", "count": 3, "note": "patrol bots"},
            {"kind": "pickup", "count": 5, "note": "data cores"},
        ],
        "win": [{"type": "collect_all", "target": 5}],
    }))

    res = prompt_to_gds(
        "A cyberpunk stealth game where you infiltrate a neon lab and hack data cores",
        complete_json=mock_complete,
        allow_model=True,
    )
    assert res.status == "OK"
    assert res.path == "model"
    assert res.gds is not None
    assert res.gds.meta.title == "Neon Infiltrator"
    assert mock_complete.call_count == 1
