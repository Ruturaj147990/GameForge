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
        lose_conds = getattr(goals, "lose", []) or []
        if not win_conds:
            issues.append("Non-sandbox game must specify at least one win condition")

        # Check pickup count sufficiency for count_at_least win conditions
        for cond in win_conds:
            if getattr(cond, "kind", "") == "count_at_least" and getattr(cond, "event", "") == "kit.pickup/collected":
                required_n = getattr(cond, "n", 0)
                total_pickups = sum(
                    getattr(e, "count", 1)
                    for e in entities
                    if getattr(e, "kind", None) in (EntityKind.PICKUP, "pickup")
                )
                has_spawner = any(
                    getattr(e, "kind", None) in (EntityKind.SPAWNER, "spawner")
                    for e in entities
                )
                if required_n > total_pickups and not has_spawner:
                    issues.append(
                        f"Win condition requires collecting {required_n} pickups, but level only contains {total_pickups} pickups with no spawner"
                    )

        # Check for contradictory win and lose conditions
        def _get_atomic_conditions(cond_list):
            atomics = []
            for c in cond_list:
                k = getattr(c, "kind", "")
                if k in ("all", "any"):
                    atomics.extend(_get_atomic_conditions(getattr(c, "items", [])))
                else:
                    atomics.append(c)
            return atomics

        win_atomics = _get_atomic_conditions(win_conds)
        lose_atomics = _get_atomic_conditions(lose_conds)

        for w in win_atomics:
            w_kind = getattr(w, "kind", "")
            for l in lose_atomics:
                l_kind = getattr(l, "kind", "")
                if w_kind == "stat" and l_kind == "stat":
                    w_stat = getattr(w, "stat", "")
                    l_stat = getattr(l, "stat", "")
                    if w_stat == l_stat:
                        w_op = getattr(w, "op", "")
                        w_val = getattr(w, "value", 0.0)
                        l_op = getattr(l, "op", "")
                        l_val = getattr(l, "value", 0.0)
                        # Identical condition for both win and lose
                        if w_op == l_op and w_val == l_val:
                            issues.append(f"Contradictory win and lose conditions: both trigger when '{w_stat} {w_op} {w_val}'")
                        # Score-based contradiction where initial value triggers loss immediately
                        if w_stat == "game.score":
                            if w_op in (">=", ">") and w_val > 0 and l_op in ("<=", "<") and l_val >= 0:
                                issues.append(
                                    f"Contradictory goals: win requires '{w_stat} {w_op} {w_val}', but lose triggers on initial/zero score '{w_stat} {l_op} {l_val}'"
                                )
                            elif w_op in (">=", ">") and l_op in (">=", ">") and l_val <= w_val:
                                issues.append(
                                    f"Contradictory goals: lose condition '{l_stat} {l_op} {l_val}' triggers before win condition '{w_stat} {w_op} {w_val}' can be reached"
                                )
                        # Health-based contradiction (e.g. winning on player death)
                        if w_stat == "player.health":
                            if w_op in ("<=", "<", "==") and w_val <= 0:
                                issues.append("Contradictory win condition: player wins when player.health <= 0")
                elif w_kind == "event" and l_kind == "event":
                    if getattr(w, "event", "") == getattr(l, "event", "") and getattr(w, "source", None) == getattr(l, "source", None):
                        issues.append(f"Contradictory win and lose conditions: both trigger on event '{getattr(w, 'event', '')}'")

    # 4. Negative prompt constraints validation
    if bool(re.search(r"\b(?:no|without|zero)\s+(?:enemies|enemy|monsters?|hostiles?|combat|opponents?|bad\s+guys?)\b", p_lower)) or "peaceful" in p_lower:
        has_enemy = any(
            getattr(e, "kind", None) in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY, EntityKind.SPAWNER, "enemy", "ranged_enemy", "spawner")
            for e in entities
        )
        if has_enemy:
            issues.append("Prompt explicitly requested 'no enemies', but GDS contains enemy or spawner entities")

    if bool(re.search(r"\b(?:no|without)\s+(?:guns?|weapons?|rifles?|pistols?|firearms?|shooting)\b", p_lower)):
        for e in entities:
            if getattr(e, "kind", None) in (EntityKind.PLAYER, "player"):
                props = getattr(e, "props", {}) or {}
                if isinstance(props, dict):
                    if props.get("attack_mode") == "projectile" or props.get("weapons"):
                        issues.append("Prompt explicitly requested 'no guns/weapons', but player entity is configured with projectile weapons")

    if bool(re.search(r"\b(?:no|without)\s+(?:timer|time\s+limit|countdown)\b", p_lower)):
        goals = getattr(gds, "goals", None)
        lose_conds = getattr(goals, "lose", []) if goals else []
        for c in lose_conds:
            if getattr(c, "kind", "") == "timer":
                issues.append("Prompt explicitly requested 'no timer', but GDS contains a timer loss condition")

    # 5. Mechanics and Input Consistency
    input_spec = getattr(gds, "input", None)
    if input_spec and getattr(input_spec, "actions", None):
        action_ids = {getattr(a, "action_id", "") for a in input_spec.actions}
        camera_val = getattr(getattr(gds, "overview", None), "camera", None)
        camera_str = camera_val.value if hasattr(camera_val, "value") else str(camera_val or "")
        if camera_str in ("first_person", "third_person") and "IA_Move" not in action_ids:
            issues.append(f"Camera perspective '{camera_str}' requires 'IA_Move' action in input configuration")

    # 6. Entity property sanity bounds
    for e in entities:
        props = getattr(e, "props", {}) or {}
        if isinstance(props, dict):
            if "jump_velocity" in props and float(props["jump_velocity"]) < 0:
                issues.append(f"Entity '{e.entity_id}' has negative jump_velocity ({props['jump_velocity']})")
            if "speed" in props and float(props["speed"]) <= 0:
                issues.append(f"Entity '{e.entity_id}' has non-positive speed ({props['speed']})")

    return (len(issues) == 0, issues)
