"""Natural-language prompt -> Game Spec (Design package re-export and bridge).

Provides unified access to:
- is_game_creation_request
- match_prompt
- expand_game_flags
- RecipeEntry, RECIPES, GameSpec
- Parameter regexes (_TARGET, _DIFF, _NAME, _WAVES, _ENEMIES, _HP, _SEED, _DENSITY, _SIZE, _WIN, _pascal, etc.)
"""
from __future__ import annotations

from src.gameforge_ide.pipeline.spec_from_prompt import (
    RECIPES,
    GameSpec,
    RecipeEntry,
    _AI_EASY,
    _AI_MED,
    _COLOR_WORDS,
    _CREATE,
    _CREATE_GAME,
    _DENSITY,
    _DIFF,
    _ENEMIES,
    _FLAG,
    _GAME_WORD,
    _HOTSEAT,
    _HP,
    _NAME,
    _NOUN_GAME,
    _SEED,
    _SIZE,
    _TARGET,
    _WAVES,
    _WIN,
    _pascal,
    expand_game_flags,
    is_game_creation_request,
    match_prompt,
)

__all__ = [
    "RECIPES",
    "GameSpec",
    "RecipeEntry",
    "is_game_creation_request",
    "match_prompt",
    "expand_game_flags",
    "_CREATE",
    "_GAME_WORD",
    "_CREATE_GAME",
    "_NOUN_GAME",
    "_SEED",
    "_DENSITY",
    "_SIZE",
    "_WIN",
    "_TARGET",
    "_WAVES",
    "_ENEMIES",
    "_HP",
    "_NAME",
    "_HOTSEAT",
    "_AI_EASY",
    "_AI_MED",
    "_DIFF",
    "_COLOR_WORDS",
    "_pascal",
    "_FLAG",
]
