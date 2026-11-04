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

    # Check 2: First-person shooter / FPS vs First-person platformer vs frame-rate (60 fps)
    is_frame_rate = bool(re.search(r"\b\d+\s*fps\b", p_lower))
    is_fp_platformer = bool(re.search(r"\bfirst[- ]person\s+(?:platformer|platform|obstacle|parkour|runner)\b", p_lower))
    is_fps_shooter = (
        (bool(re.search(r"\bfirst[- ]person\s+shooter\b", p_lower))
         or bool(re.search(r"\b(?:tactical|competitive|military|arena)?\s*fps\b(?!\s*(?:cap|limit|lock|target|drop|rate|frame))", p_lower))
         or (("first person" in p_lower or "first-person" in p_lower) and any(w in p_lower for w in ("shooter", "rifle", "gun", "guns", "weapons", "sniper", "deathmatch"))))
        and not is_frame_rate
        and not is_fp_platformer
    )

    if is_fps_shooter:
        if genre_val in (Genre.PLATFORMER.value, Genre.GRID_BOARD.value, "platformer", "grid_board"):
            issues.append(
                f"Prompt specifies first-person/FPS game, but genre is '{genre_val}', "
                f"which cannot be platformer or grid_board"
            )
    elif ("first person" in p_lower or "first-person" in p_lower) and not is_frame_rate:
        # First person cannot be a grid board game
        if genre_val in (Genre.GRID_BOARD.value, "grid_board"):
            issues.append(
                f"Prompt specifies first-person game, but genre is '{genre_val}', which cannot be grid_board"
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
        # Check if the user explicitly requested a pure parkour / no collectibles platformer
        no_collectibles_requested = bool(
            re.search(r"\b(?:no\s+(?:collectibles?|coins?|pickups?|items?|gems?)|pure\s+(?:platformer|parkour)|speedrun)\b", p_lower)
        )
        if not has_pickup and not no_collectibles_requested:
            issues.append("Platformer GDS must include at least one 'pickup' entity")
        if not has_goal:
            issues.append("Platformer GDS must include a 'goal' entity")

    # Check 4: shooter / combat prompt
    if ("shooter" in p_lower or "arena combat" in p_lower) and not is_fps_shooter:
        allowed_shooter_genres = (
            Genre.ARENA_COMBAT.value,
            Genre.TOP_DOWN_SHOOTER.value,
            Genre.ACTION_ADVENTURE.value,
            Genre.DUNGEON_CRAWLER.value,
            Genre.EXPLORATION.value,
            Genre.PUZZLE.value,
            Genre.CUSTOM.value,
            "arena_combat",
            "top_down_shooter",
            "action_adventure",
            "dungeon_crawler",
            "exploration",
            "puzzle",
            "custom",
        )
        if genre_val not in allowed_shooter_genres:
            issues.append(
                f"Prompt specifies shooter/combat game, but genre is '{genre_val}'"
            )

    # Check 5: Card game / Deck battler prompt
    if any(k in p_lower for k in ("card battler", "card game", "deck builder", "deckbuilder", "card battle")):
        if genre_val in (Genre.PLATFORMER.value, Genre.GRID_BOARD.value, "platformer", "grid_board"):
            issues.append(
                f"Prompt specifies card battler/deck building game, but genre is '{genre_val}' "
                f"(expected '{Genre.CARD_BATTLER.value}')"
            )

    # Check 6: Board game prompt
    if any(k in p_lower for k in ("tic tac toe", "tic-tac-toe", "connect four", "connect 4", "gomoku", "five in a row")):
        if genre_val != Genre.GRID_BOARD.value and genre_val != "grid_board":
            issues.append(
                f"Prompt specifies grid board game, but genre is '{genre_val}' "
                f"(expected '{Genre.GRID_BOARD.value}')"
            )

    # 2. Entity expectations for Genre
    if genre_val in (Genre.GRID_BOARD.value, "grid_board"):
        if not any(getattr(e, "kind", None) in (EntityKind.BOARD, "board") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'board' entity")
    elif genre_val in (Genre.PLATFORMER.value, "platformer"):
        if not any(getattr(e, "kind", None) in (EntityKind.PLAYER, "player") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'player' entity")
    elif genre_val in (Genre.ARENA_COMBAT.value, Genre.TOP_DOWN_SHOOTER.value, "arena_combat", "top_down_shooter"):
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
    elif genre_val in (Genre.CARD_BATTLER.value, "card_battler"):
        if not any(getattr(e, "kind", None) in (EntityKind.CARD_TABLE, "card_table") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'card_table' entity")
    elif genre_val in (
        Genre.ACTION_ADVENTURE.value,
        Genre.DUNGEON_CRAWLER.value,
        Genre.EXPLORATION.value,
        "action_adventure",
        "dungeon_crawler",
        "exploration",
    ):
        if not any(getattr(e, "kind", None) in (EntityKind.PLAYER, "player") for e in entities):
            issues.append(f"Genre '{genre_val}' requires a 'player' entity")

    # 3. Win/Lose conditions sense for Genre
    goals = getattr(gds, "goals", None)
    if goals is not None and not getattr(goals, "sandbox", False):
        win_conds = getattr(goals, "win", []) or []
        if not win_conds:
            issues.append("Non-sandbox game must specify at least one win condition")

    return (len(issues) == 0, issues)
