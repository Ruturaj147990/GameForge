"""Semantic validation for GameDesignSpec (GDS) against user prompt and genre conventions."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .gds import EntityKind, GameDesignSpec, Genre


def semantic_validate_gds(
    gds: GameDesignSpec, original_prompt: str
) -> Tuple[bool, List[str]]:
    """Validate that GDS semantics match user intent and genre conventions.

    Args:
        gds: The GameDesignSpec object to validate.
        original_prompt: The raw user prompt used to create or request the game.

    Returns:
        (valid, list_of_issues): Tuple of boolean pass flag and list of issue messages.
    """
    issues: List[str] = []
    p_lower = (original_prompt or "").strip().lower()

    overview = getattr(gds, "overview", None)
    genre = getattr(overview, "genre", None)
    genre_val = genre.value if isinstance(genre, Genre) else str(genre or "").lower()

    entities = getattr(gds, "entities", []) or []

    # 1. Intent keyword checks in prompt
    # Check 1: "snake" AND "ladder"
    if "snake" in p_lower and "ladder" in p_lower:
        if genre_val != Genre.GRID_BOARD.value:
            issues.append(
                f"Prompt specifies 'snake' and 'ladder' game, but genre is '{genre_val}' "
                f"(expected '{Genre.GRID_BOARD.value}')"
            )
        has_board = any(
            getattr(e, "kind", None) in (EntityKind.BOARD, "board")
            for e in entities
        )
        if not has_board:
            issues.append(
                "Prompt specifies 'snake' and 'ladder' game, but entities lack required 'board' entity"
            )

    # Check 2: "fps" or "first person"
    is_fps = bool(re.search(r"\bfps\b", p_lower)) or "first person" in p_lower or "first-person" in p_lower
    if is_fps:
        if genre_val in (Genre.PLATFORMER.value, Genre.GRID_BOARD.value, "platformer", "grid_board"):
            issues.append(
                f"Prompt specifies first-person/FPS game, but genre is '{genre_val}', "
                f"which cannot be platformer or grid_board"
            )

    # Check 3: "platformer"
    if "platformer" in p_lower or "platform game" in p_lower:
        if genre_val not in (Genre.PLATFORMER.value, "platformer"):
            issues.append(
                f"Prompt specifies platformer game, but genre is '{genre_val}' "
                f"(expected '{Genre.PLATFORMER.value}')"
            )
        has_pickup = any(
            getattr(e, "kind", None) in (EntityKind.PICKUP, "pickup")
            for e in entities
        )
        has_goal = any(
            getattr(e, "kind", None) in (EntityKind.GOAL, "goal")
            for e in entities
        )
        if not has_pickup:
            issues.append("Platformer GDS must include at least one 'pickup' entity")
        if not has_goal:
            issues.append("Platformer GDS must include a 'goal' entity")

    # Check 4: shooter / combat prompt
    if ("shooter" in p_lower or "arena combat" in p_lower) and not is_fps:
        if genre_val not in (
            Genre.ARENA_COMBAT.value,
            Genre.TOP_DOWN_SHOOTER.value,
            Genre.ACTION_ADVENTURE.value,
            "arena_combat",
            "top_down_shooter",
            "action_adventure",
        ):
            issues.append(
                f"Prompt specifies shooter/combat game, but genre is '{genre_val}'"
            )

    # 2. Entity expectations for Genre
    if genre_val == Genre.GRID_BOARD.value:
        if not any(getattr(e, "kind", None) in (EntityKind.BOARD, "board") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'board' entity")
    elif genre_val == Genre.PLATFORMER.value:
        if not any(getattr(e, "kind", None) in (EntityKind.PLAYER, "player") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'player' entity")
    elif genre_val in (Genre.ARENA_COMBAT.value, Genre.TOP_DOWN_SHOOTER.value):
        if not any(getattr(e, "kind", None) in (EntityKind.PLAYER, "player") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'player' entity")
        has_enemy = any(
            getattr(e, "kind", None) in (
                EntityKind.ENEMY,
                EntityKind.RANGED_ENEMY,
                EntityKind.SPAWNER,
                "enemy",
                "ranged_enemy",
                "spawner",
            )
            for e in entities
        )
        if not has_enemy:
            issues.append(f"Genre '{genre_val}' requires an enemy or spawner entity")
    elif genre_val == Genre.CARD_BATTLER.value:
        if not any(getattr(e, "kind", None) in (EntityKind.CARD_TABLE, "card_table") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'card_table' entity")

    # 3. Win/Lose conditions sense for Genre
    goals = getattr(gds, "goals", None)
    if goals is not None and not getattr(goals, "sandbox", False):
        win_conds = getattr(goals, "win", []) or []
        if not win_conds:
            issues.append("Non-sandbox game must specify at least one win condition")

    return (len(issues) == 0, issues)
