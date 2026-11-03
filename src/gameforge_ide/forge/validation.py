"""Evidence and output validation for Forge pipeline stages (WI-3.5 / Phase 3 & 8).

Ensures pipeline stages do not falsely report DONE without verifying their actual outputs:
- design: verifies GDS has correct genre (not fallback), valid pitch, meaningful entities.
- assemble: verifies expected actors exist via read-back from Unreal (player, goal, main game actor).
- scenarios: verifies game-specific acceptance tests ran (not just generic Kit smoke tests).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ..design.gds import EntityKind, GameDesignSpec, Genre
from ..design.semantic_validate import semantic_validate_gds
from ..qa.game_spec_tests import generate_acceptance_tests

GENERIC_KIT_TESTS = {
    "smoke",
    "gameforge.kit",
    "countatleast",
    "nestinganddepth",
    "statoperators",
    "gameforge.kit.statoperators",
    "gameforge.kit.countatleast",
    "gameforge.kit.nestinganddepth",
}


def _is_generic_test(name: str) -> bool:
    """Determine if a test name represents a generic engine kit smoke test."""
    n = name.strip().lower()
    if n in GENERIC_KIT_TESTS or n == "smoke":
        return True
    if n.startswith("gameforge.kit") and not any(
        kw in n for kw in ("snake", "ladder", "jump", "combat", "pickup", "enemy", "shooter", "goal")
    ):
        return True
    return False


def validate_stage_output(
    stage_name: str,
    stage_result: Dict[str, Any],
    gds: Optional[GameDesignSpec] = None,
) -> Tuple[bool, List[str]]:
    """Validate that a pipeline stage produced legitimate verified output.

    Args:
        stage_name: Name or kind of the pipeline stage (e.g. 'design', 'assemble', 'scenarios').
        stage_result: Data dict produced by the step execution.
        gds: Optional GameDesignSpec for context and expectation matching.

    Returns:
        (passed, issues): Boolean pass flag and list of issue descriptions.
    """
    issues: List[str] = []
    s_norm = (stage_name or "").lower().strip()
    result = stage_result or {}

    overview = getattr(gds, "overview", None) if gds else None
    genre = getattr(overview, "genre", None)
    genre_val = (
        genre.value
        if isinstance(genre, Genre)
        else str(genre or result.get("params", {}).get("genre", "")).lower()
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 1. DESIGN / SPEC STAGE
    # ──────────────────────────────────────────────────────────────────────────
    if "design" in s_norm or "spec" in s_norm:
        if gds is None:
            # Check if GDS is in result
            gds_raw = result.get("gds") or result.get("spec")
            if isinstance(gds_raw, dict):
                try:
                    gds = GameDesignSpec.model_validate(gds_raw)
                    overview = getattr(gds, "overview", None)
                    genre_val = gds.overview.genre.value
                except Exception:
                    pass

        if gds is None and not result.get("params"):
            issues.append("Design stage produced neither a valid GDS nor design params")
            return (False, issues)

        # Check genre is not a fallback
        if result.get("fallback") is True or result.get("is_fallback") is True:
            issues.append("Design stage fell back to a default unverified fallback template")

        if not genre_val or genre_val in ("custom", "none", "unknown"):
            issues.append(f"GDS genre is invalid or unassigned: '{genre_val}'")

        # Check valid pitch
        pitch = (
            getattr(overview, "pitch", "")
            if overview
            else result.get("params", {}).get("pitch", "")
        )
        if not isinstance(pitch, str) or len(pitch.strip()) < 5:
            issues.append("GDS pitch is missing, empty, or too short")
        elif pitch.strip().lower() in ("todo", "placeholder", "game pitch", "n/a"):
            issues.append(f"GDS pitch is a placeholder: '{pitch}'")

        # Check meaningful entities
        entities = getattr(gds, "entities", []) if gds else []
        if gds and not entities:
            issues.append("GDS has no entities defined")
        elif gds:
            if genre_val == Genre.GRID_BOARD.value:
                if not any(getattr(e, "kind", None) in (EntityKind.BOARD, "board") for e in entities):
                    issues.append("Grid board design lacks required 'board' entity")
            elif genre_val == Genre.PLATFORMER.value:
                if not any(getattr(e, "kind", None) in (EntityKind.PLAYER, "player") for e in entities):
                    issues.append("Platformer design lacks required 'player' entity")
                if not any(getattr(e, "kind", None) in (EntityKind.PICKUP, "pickup") for e in entities):
                    issues.append("Platformer design lacks 'pickup' entities")
                if not any(getattr(e, "kind", None) in (EntityKind.GOAL, "goal") for e in entities):
                    issues.append("Platformer design lacks 'goal' entity")
            elif genre_val in (Genre.ARENA_COMBAT.value, Genre.TOP_DOWN_SHOOTER.value):
                if not any(getattr(e, "kind", None) in (EntityKind.PLAYER, "player") for e in entities):
                    issues.append("Combat/shooter design lacks required 'player' entity")
                if not any(
                    getattr(e, "kind", None) in (
                        EntityKind.ENEMY,
                        EntityKind.RANGED_ENEMY,
                        EntityKind.SPAWNER,
                        "enemy",
                        "ranged_enemy",
                        "spawner",
                    )
                    for e in entities
                ):
                    issues.append("Combat/shooter design lacks enemy or spawner entities")

        # Prompt semantic check if source prompt available
        prompt = getattr(getattr(gds, "meta", None), "source_prompt", "") or result.get("prompt", "")
        if gds and prompt:
            _, sem_issues = semantic_validate_gds(gds, prompt)
            issues.extend(sem_issues)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. ASSEMBLE STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "assemble" in s_norm:
        # Collect actor evidence from read_back_actors, spawned_actors, calls, or manifest
        actor_records: List[Union[Dict[str, Any], str]] = []
        if isinstance(result.get("read_back_actors"), list):
            actor_records.extend(result["read_back_actors"])
        if isinstance(result.get("spawned_actors"), dict):
            for lbl, act_data in result["spawned_actors"].items():
                if isinstance(act_data, dict):
                    actor_records.append(dict(act_data, label=lbl))
                else:
                    actor_records.append({"label": lbl})
        elif isinstance(result.get("spawned_actors"), list):
            actor_records.extend(result["spawned_actors"])
        elif isinstance(result.get("actors"), list):
            actor_records.extend(result["actors"])

        if "spawned_actors" in result and result.get("actors_count", 0) > 0 and not result.get("spawned_actors"):
            issues.append(f"Assemble failed: 0 of {result.get('actors_count')} planned actors were spawned by engine")

        calls = result.get("calls") or []
        for c in calls:
            if isinstance(c, dict):
                args = c.get("args") or {}
                actor_records.append({
                    "class": args.get("actor_class", ""),
                    "label": args.get("label", ""),
                    "name": args.get("name", ""),
                    "tag": args.get("tag", ""),
                    "purpose": c.get("purpose", ""),
                })

        # Tokenize actor records
        text_tokens: List[str] = []
        for rec in actor_records:
            if isinstance(rec, dict):
                text_tokens.extend([
                    str(rec.get("class", "")),
                    str(rec.get("actor_class", "")),
                    str(rec.get("label", "")),
                    str(rec.get("name", "")),
                    str(rec.get("tag", "")),
                    str(rec.get("purpose", "")),
                ])
                for t in rec.get("tags", []):
                    text_tokens.append(str(t))
            elif isinstance(rec, str):
                text_tokens.append(rec)

        all_actor_text = " ".join(text_tokens).lower()

        if not text_tokens and result.get("actors_count", 0) == 0 and not calls:
            issues.append("No Unreal actor read-back or spawn evidence found in assemble output")
            return (False, issues)

        # 1. Player check (at least player)
        has_player = (
            "player" in all_actor_text
            or "playerstart" in all_actor_text
            or "character" in all_actor_text
            or "pawn" in all_actor_text
            or "gf_player" in all_actor_text
        )
        if not has_player:
            issues.append("Expected 'player' actor missing from assemble read-back")

        # 2. Goal check (at least goal)
        has_goal = (
            "goal" in all_actor_text
            or "finish" in all_actor_text
            or "target" in all_actor_text
            or "win" in all_actor_text
            or "gf_goal" in all_actor_text
            or "checkpoint" in all_actor_text
        )
        if not has_goal:
            issues.append("Expected 'goal' actor missing from assemble read-back")

        # 3. Main game actor check
        if genre_val in (Genre.GRID_BOARD.value, "grid_board"):
            has_main = "board" in all_actor_text or "grid" in all_actor_text or "gameforgegridboard" in all_actor_text
            if not has_main:
                issues.append("Expected 'board' actor missing from grid board assemble read-back")
        elif genre_val in (Genre.CARD_BATTLER.value, "card_battler"):
            has_main = "card" in all_actor_text or "table" in all_actor_text or "gameforgecardtable" in all_actor_text
            if not has_main:
                issues.append("Expected 'card_table' actor missing from card battler assemble read-back")
        elif genre_val in (Genre.ARENA_COMBAT.value, Genre.TOP_DOWN_SHOOTER.value, "arena_combat", "top_down_shooter"):
            has_main = (
                "spawner" in all_actor_text
                or "enemy" in all_actor_text
                or "wave" in all_actor_text
                or "bot" in all_actor_text
            )
            if not has_main:
                issues.append(f"Expected enemy or spawner actor missing from {genre_val} assemble read-back")
        else:
            # Platformer / Action / Other: check for pickups or landmarks or platforms
            has_main = (
                "pickup" in all_actor_text
                or "platform" in all_actor_text
                or "landmark" in all_actor_text
                or "course" in all_actor_text
            )
            if not has_main:
                issues.append("Expected primary gameplay actor missing from assemble read-back")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. SCENARIOS / AUTOMATION STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif any(k in s_norm for k in ("scenario", "test", "automation", "smoke")):
        test_results = (
            result.get("results")
            or result.get("scenarios")
            or result.get("tests")
            or []
        )

        test_names: List[str] = []
        if isinstance(test_results, list):
            for t in test_results:
                if isinstance(t, dict):
                    name = t.get("scenario_id") or t.get("test_id") or t.get("name") or ""
                    test_names.append(name)
                    if t.get("passed") is False:
                        fails = t.get("failures") or ["test marked passed=False"]
                        issues.append(f"Scenario '{name}' failed: {'; '.join(str(f) for f in fails)}")
                elif isinstance(t, str):
                    test_names.append(t)

        if result.get("test_filter"):
            test_names.append(str(result["test_filter"]))

        if not test_names:
            issues.append("No scenario or test results found in stage output")
            return (False, issues)

        # Check that tests are not exclusively generic kit tests
        all_generic = all(_is_generic_test(name) for name in test_names if name)
        if all_generic and test_names:
            issues.append(
                f"Only generic Kit smoke tests ran ({test_names}); "
                f"game-specific acceptance tests were not executed"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # 4. OTHER STAGES (General fail-closed check)
    # ──────────────────────────────────────────────────────────────────────────
    else:
        if result.get("ok") is False:
            errors = result.get("errors") or ["Stage reported ok=False"]
            issues.extend([str(e) for e in errors])

    return (len(issues) == 0, issues)
