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
