"""Composer layout registry (WI-6.3).

Maps layout names to their plan_level(level, gds, rng) generators.
"""
from __future__ import annotations

from typing import Any, Callable, Dict
import random

from . import arena, board, course, lanes, open_world, rooms, tactical_fps
from ..model import LevelPlan

LAYOUTS: Dict[str, Callable[[Any, Any, random.Random], LevelPlan]] = {
    "board": board.plan_level,
    "arena": arena.plan_level,
    "course": course.plan_level,
    "rooms": rooms.plan_level,
    "open_world": open_world.plan_level,
    "lanes": lanes.plan_level,
    "tactical_fps": tactical_fps.plan_level,
}

LAYOUT_ALIASES: Dict[str, str] = {
    "platformer": "course",
    "dungeon": "rooms",
    "dungeon_crawler": "rooms",
    "fps": "tactical_fps",
    "tactical": "tactical_fps",
    "grid_board": "board",
    "card_battler": "lanes",
    "card": "lanes",
    "moba": "lanes",
    "open": "open_world",
}


def get_layout_generator(name: str) -> Callable[[Any, Any, random.Random], LevelPlan]:
    """Retrieve layout generator function with robust alias resolution."""
    normalized = str(name).strip().lower()
    target = LAYOUT_ALIASES.get(normalized, normalized)
    if target in LAYOUTS:
        return LAYOUTS[target]
    raise KeyError(f"Unknown layout: {name!r}. Supported layouts: {sorted(LAYOUTS.keys())}")


__all__ = [
    "LAYOUTS",
    "LAYOUT_ALIASES",
    "arena",
    "board",
    "course",
    "get_layout_generator",
    "lanes",
    "open_world",
    "rooms",
    "tactical_fps",
]
