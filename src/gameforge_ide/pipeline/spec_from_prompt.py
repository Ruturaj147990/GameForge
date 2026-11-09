"""Natural-language prompt -> Game Spec (recipe + validated parameters).

Re-exports the canonical specification matcher from `gameforge_ide.design.spec_from_prompt`
so all callers share a single authoritative implementation.
"""
from __future__ import annotations

from ..design.spec_from_prompt import (
    RECIPES,
    SPEC_SCHEMA,
    GameSpec,
    RecipeEntry,
    _pascal,
    expand_game_flags,
    is_game_creation_request,
    match_prompt,
    refine_with_model,
    spec_from_prompt,
)

__all__ = [
    "GameSpec",
    "RECIPES",
    "RecipeEntry",
    "SPEC_SCHEMA",
    "_pascal",
    "expand_game_flags",
    "is_game_creation_request",
    "match_prompt",
    "refine_with_model",
    "spec_from_prompt",
]
