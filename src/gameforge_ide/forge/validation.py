"""Evidence and output validation for Forge pipeline stages (WI-3.5 / Phase 3 & 8).

Ensures pipeline stages do not falsely report DONE without verifying their actual outputs:
- design: verifies GDS has correct genre (not fallback), valid pitch, meaningful entities.
- assemble: verifies expected actors exist via read-back from Unreal (player, goal, main game actor).
- scenarios: verifies game-specific acceptance tests ran (not just generic Kit smoke tests).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
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
        kw in n for kw in ("jump", "combat", "pickup", "enemy", "shooter", "goal", "board", "card", "race", "stealth", "puzzle", "quest", "switch", "hazard", "win", "lose")
    ):
        return True
    return False


def validate_stage_output(
    stage_name: str,
    stage_result: Dict[str, Any],
    gds: Optional[GameDesignSpec] = None,
    project_dir: Optional[Union[Path, str]] = None,
    artifacts: Optional[Sequence[Any]] = None,
) -> Tuple[bool, List[str]]:
    """Validate that a pipeline stage produced legitimate verified output.

    Args:
        stage_name: Name or kind of the pipeline stage (e.g. 'design', 'assemble', 'scenarios').
        stage_result: Data dict produced by the step execution.
        gds: Optional GameDesignSpec for context and expectation matching.
        project_dir: Optional project directory to verify on-disk artifacts and files.
        artifacts: Optional sequence of declared artifacts (ArtifactRef or dicts).

    Returns:
        (passed, issues): Boolean pass flag and list of issue descriptions.
    """
    issues: List[str] = []
    s_norm = (stage_name or "").lower().strip()
    result = stage_result or {}
    pdir = Path(project_dir).resolve() if project_dir else (Path(result.get("project_dir")).resolve() if result.get("project_dir") else None)

    if gds is None and pdir:
        gds_file = pdir / "GameForge" / "design" / "game.gds.json"
        if gds_file.is_file():
            try:
                import json
                gds_raw = json.loads(gds_file.read_text(encoding="utf-8"))
                gds = GameDesignSpec.model_validate(gds_raw)
            except Exception:
                pass

    overview = getattr(gds, "overview", None) if gds else None
    genre = getattr(overview, "genre", None)
    genre_val = (
        genre.value
        if isinstance(genre, Genre)
        else str(genre or result.get("params", {}).get("genre", "") or result.get("genre", "") or result.get("recipe", "")).lower()
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

        if gds is None and not result.get("params") and not result.get("recipe"):
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
            else result.get("params", {}).get("pitch", "") or result.get("pitch", "") or (f"Recipe design for {result.get('recipe')}" if result.get("recipe") else "")
        )
        if not pitch:
            p_name = result.get("params", {}).get("display_title") or result.get("params", {}).get("project_name") or (pdir.name if pdir else "")
            p_genre = result.get("params", {}).get("genre") or genre_val or "game"
            if p_name:
                pitch = f"{p_name} — dynamic {p_genre} specification"
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

        # Strict on-disk GDS artifact verification
        if pdir is not None:
            gds_on_disk = pdir / "GameForge" / "design" / "game.gds.json"
            if gds_on_disk.is_file() and gds_on_disk.stat().st_size == 0:
                issues.append(f"GameDesignSpec file '{gds_on_disk}' exists but is empty (0 bytes)")
        if "gds_path" in result and result["gds_path"]:
            gp = Path(result["gds_path"])
            if not gp.is_absolute() and pdir is not None:
                gp = pdir / gp
            if not gp.is_file():
                issues.append(f"Design GDS file '{result['gds_path']}' does not exist on disk")
            elif gp.stat().st_size == 0:
                issues.append(f"Design GDS file '{result['gds_path']}' is empty (0 bytes)")

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

        # 2. Goal / Objective check
        # For platformers, a physical goal/checkpoint actor is expected.
        # For combat / shooter / FPS games, enemies, spawners, bomb sites, and objectives are the targets.
        # For grid board games, card battlers, and puzzles, the board or table actor itself is the primary objective container.
        has_goal = any(
            k in all_actor_text
            for k in ("goal", "finish", "target", "win", "gf_goal", "checkpoint", "landmark", "relic", "switch", "door", "zone", "npc")
        )
        is_combat = (
            genre_val in (
                Genre.ARENA_COMBAT.value,
                Genre.TOP_DOWN_SHOOTER.value,
                "arena_combat",
                "top_down_shooter",
                "fps",
                "tactical_fps",
                "shooter",
                "combat",
            )
            or any(k in all_actor_text for k in ("bombsite", "site_a", "site_b", "tactical", "terrorist"))
        )
        if is_combat:
            has_goal = has_goal or any(
                k in all_actor_text
                for k in ("enemy", "spawner", "bot", "site", "bomb", "bombsite", "objective", "wave", "hazard", "boss", "guard")
            )

        is_board_or_table = (
            genre_val in (
                Genre.GRID_BOARD.value,
                Genre.CARD_BATTLER.value,
                "grid_board",
                "card_battler",
                "board",
                "puzzle",
            )
            or any(k in all_actor_text for k in ("board", "grid", "gameforgegridboard", "card_table", "gameforgecardtable"))
        )
        if is_board_or_table:
            has_goal = has_goal or any(
                k in all_actor_text
                for k in ("board", "grid", "gameforgegridboard", "card_table", "gameforgecardtable", "table")
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
        elif genre_val in (
            Genre.ARENA_COMBAT.value,
            Genre.TOP_DOWN_SHOOTER.value,
            "arena_combat",
            "top_down_shooter",
            "fps",
            "tactical_fps",
            "shooter",
            "combat",
        ) or is_combat:
            has_main = any(
                k in all_actor_text
                for k in ("spawner", "enemy", "wave", "bot", "guard", "site", "bomb", "bombsite")
            )
            if not has_main:
                issues.append(f"Expected enemy, spawner, or objective actor missing from {genre_val or 'combat'} assemble read-back")
        else:
            # Platformer / Action / Other: check for pickups or landmarks or platforms or board
            has_main = (
                "pickup" in all_actor_text
                or "platform" in all_actor_text
                or "landmark" in all_actor_text
                or "course" in all_actor_text
                or "board" in all_actor_text
                or "grid" in all_actor_text
                or "table" in all_actor_text
                or "switch" in all_actor_text
                or "door" in all_actor_text
                or "checkpoint" in all_actor_text
                or "zone" in all_actor_text
                or "npc" in all_actor_text
                or "hazard" in all_actor_text
                or "mover" in all_actor_text
                or is_combat
            )
            if not has_main:
                issues.append("Expected primary gameplay actor missing from assemble read-back")

        # Strict on-disk level manifest and level file validation
        if "manifest_path" in result and result["manifest_path"]:
            mp = Path(result["manifest_path"])
            if not mp.is_absolute() and pdir is not None:
                mp = pdir / mp
            if not mp.is_file():
                issues.append(f"Assemble manifest file '{result['manifest_path']}' does not exist on disk")
            elif mp.stat().st_size == 0:
                issues.append(f"Assemble manifest file '{result['manifest_path']}' is empty (0 bytes)")
        if "level_file" in result and result["level_file"]:
            lf = Path(result["level_file"])
            if not lf.is_absolute() and pdir is not None:
                lf = pdir / lf
            if not lf.is_file():
                issues.append(f"Assemble level file '{result['level_file']}' does not exist on disk")
            elif lf.stat().st_size == 0:
                issues.append(f"Assemble level file '{result['level_file']}' is empty (0 bytes)")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. SCENARIO_GEN STAGE (QA Scenario Generation)
    # ──────────────────────────────────────────────────────────────────────────
    elif s_norm == "scenario_gen" or (
        any(k in s_norm for k in ("scenario", "design"))
        and "scenarios" in result
        and "results" not in result
        and ("out_dir" in result or all(isinstance(x, dict) and "passed" not in x for x in (result.get("scenarios") or []) if isinstance(x, dict)))
        and "params" not in result
    ):
        scs = result.get("scenarios") or []
        count = result.get("count", len(scs))
        if count == 0 and not scs:
            issues.append("Scenario generation produced no QA scenarios")
        if pdir is not None and count > 0:
            candidate_dirs = [
                pdir / "GameForge" / "scenarios",
                pdir / "Saved" / "GameForge" / "evidence" / "scenarios",
            ]
            if result.get("out_dir"):
                od = Path(str(result["out_dir"]))
                candidate_dirs.insert(0, od if od.is_absolute() else (pdir / od))
            if not any(d.is_dir() for d in candidate_dirs):
                issues.append(
                    f"Scenario output directory not found on disk (checked {[str(d) for d in candidate_dirs]})"
                )

    # ──────────────────────────────────────────────────────────────────────────
    # 3b. SCENARIOS STAGE (Packaged QA Acceptance Scenarios)
    # ──────────────────────────────────────────────────────────────────────────
    elif any(k in s_norm for k in ("scenario", "acceptance")) and s_norm != "scenario_gen":
        test_results = (
            result.get("results")
            or result.get("scenarios")
            or []
        )

        test_names: List[str] = []
        if isinstance(test_results, list):
            for t in test_results:
                if isinstance(t, dict):
                    name = (
                        t.get("scenario_id")
                        or t.get("test_id")
                        or t.get("id")
                        or t.get("name")
                        or ""
                    )
                    test_names.append(name)
                    if t.get("passed") is False:
                        fails = t.get("failures") or ["test marked passed=False"]
                        issues.append(f"Scenario '{name}' failed: {'; '.join(str(f) for f in fails)}")
                elif isinstance(t, str):
                    test_names.append(t)

        if not test_names:
            issues.append("No scenario or test results found in stage output")
            return (False, issues)

        # For QA scenario runs, check that tests are not exclusively generic kit smoke
        all_generic = all(_is_generic_test(name) for name in test_names if name)
        if all_generic and test_names:
            issues.append(
                f"Only generic Kit smoke tests ran ({test_names}); "
                f"game-specific acceptance tests were not executed"
            )

        # Strict on-disk scenario report verification
        if "report_file" in result and result["report_file"]:
            rf = Path(result["report_file"])
            if not rf.is_absolute() and pdir is not None:
                rf = pdir / rf
            if not rf.is_file():
                issues.append(f"Scenario report file '{result['report_file']}' does not exist on disk")
            elif rf.stat().st_size == 0:
                issues.append(f"Scenario report file '{result['report_file']}' is empty (0 bytes)")

    # ──────────────────────────────────────────────────────────────────────────
    # 3b. AUTOMATION STAGE (Unreal Editor C++ Automation Tests)
    # ──────────────────────────────────────────────────────────────────────────
    elif any(k in s_norm for k in ("automation", "smoke", "test")):
        test_results = (
            result.get("tests")
            or result.get("results")
            or []
        )

        test_names: List[str] = []
        if isinstance(test_results, list):
            for t in test_results:
                if isinstance(t, dict):
                    name = t.get("name") or t.get("test_id") or ""
                    test_names.append(name)
                    state = t.get("state")
                    if (state and state != "Success") or t.get("passed") is False:
                        fails = t.get("errors") or t.get("failures") or ["test marked failed"]
                        issues.append(f"Automation test '{name}' failed: {'; '.join(str(f) for f in fails)}")
                elif isinstance(t, str):
                    test_names.append(t)

        if result.get("test_filter"):
            test_names.append(str(result["test_filter"]))

        if not test_names and not result.get("found"):
            issues.append("No automation test results found in stage output")
            return (False, issues)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. SCAFFOLD STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "scaffold" in s_norm:
        if pdir is not None:
            if not pdir.is_dir():
                issues.append(f"Scaffold project directory '{pdir}' does not exist on disk")
            else:
                uprojects = [p for p in pdir.glob("*.uproject") if p.is_file()]
                if not uprojects:
                    issues.append(f"Scaffold failed: no .uproject file exists in '{pdir}'")
                else:
                    for up in uprojects:
                        if up.stat().st_size == 0:
                            issues.append(f"Scaffold produced empty .uproject file '{up.name}' (0 bytes)")
        elif not result.get("uproject") and not result.get("project_name"):
            issues.append("Scaffold outcome missing project identification (uproject/project_name)")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. CODEGEN / SOURCES STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif any(k in s_norm for k in ("codegen", "source")):
        files = result.get("files") or []
        tasks_count = result.get("codegen_tasks", 0)
        if not files and tasks_count == 0 and not result.get("written_files"):
            issues.append("Codegen stage produced no source or header files")
        elif pdir is not None and files:
            # Verify at least one declared source file exists on disk
            any_exist = False
            for f in files:
                pf = Path(f)
                if pf.is_absolute():
                    f_path = pf
                elif pf.is_file() and pf.stat().st_size > 0:
                    f_path = pf
                else:
                    f_path = pdir / pf
                if f_path.is_file() and f_path.stat().st_size > 0:
                    any_exist = True
                    break
            if not any_exist and len(files) > 0:
                issues.append(f"None of the {len(files)} generated source files exist on disk in '{pdir}'")

    # ──────────────────────────────────────────────────────────────────────────
    # 6. BUILD / BUILD_EDITOR STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "build" in s_norm:
        exit_code = result.get("exit_code")
        if exit_code is not None and exit_code != 0:
            issues.append(f"Build failed with non-zero exit code: {exit_code}")
        err_val = result.get("errors")
        if isinstance(err_val, int) and err_val > 0:
            issues.append(f"Build reported {err_val} compilation error(s)")
        elif isinstance(err_val, list) and len(err_val) > 0:
            issues.append(f"Build reported compilation errors: {err_val[:3]}")

    # ──────────────────────────────────────────────────────────────────────────
    # 7. CONTENT STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "content" in s_norm:
        artifacts_count = result.get("artifacts_count", 0)
        installed = result.get("installed_packs") or []
        cook_dirs = result.get("cook_dirs") or []
        if artifacts_count == 0 and not installed and not cook_dirs:
            issues.append("Content stage produced neither installed template packs nor configured assets")
        if pdir is not None:
            if cook_dirs:
                dg_ini = pdir / "Config" / "DefaultGame.ini"
                if dg_ini.is_file() and dg_ini.stat().st_size == 0:
                    issues.append(f"Config/DefaultGame.ini in '{pdir}' is empty (0 bytes)")
            # Asset integrity and mock asset contamination audit (Mandate 4)
            content_dir = pdir / "Content"
            if content_dir.is_dir():
                from ..unreal.asset_integrity import validate_content_directory
                c_valid, c_issues, _ = validate_content_directory(content_dir)
                if not c_valid:
                    issues.extend(c_issues)

    # ──────────────────────────────────────────────────────────────────────────
    # 8. PACKAGE STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "package" in s_norm:
        exe_path = result.get("exe") or result.get("package_dir")
        if exe_path:
            ep = Path(exe_path)
            if not ep.is_absolute() and pdir is not None:
                ep = pdir / ep

            # CRITICAL DEF-308 REJECTION: Raw executable in Binaries/Win64 is NEVER proof of packaging
            norm_path = ep.as_posix().lower()
            if "binaries" in norm_path and "packaged" not in norm_path:
                issues.append(
                    f"REJECTED: Raw executable '{exe_path}' in Binaries/Win64 is not proof of a packaged game. "
                    f"Valid packaged staging structure in Packaged/Windows/ is strictly required."
                )
            elif ep.suffix.lower() == ".exe":
                if not ep.is_file():
                    issues.append(f"Packaged executable '{exe_path}' does not exist on disk")
                elif ep.stat().st_size == 0:
                    issues.append(f"Packaged executable '{exe_path}' is an empty file (0 bytes)")
            elif ep.is_dir():
                if not any(ep.iterdir()):
                    issues.append(f"Package directory '{exe_path}' is empty")
            elif not ep.exists():
                issues.append(f"Packaged path '{exe_path}' does not exist on disk")
        elif pdir is not None:
            # Check for candidate exe strictly in Packaged/ or package_* dirs (NEVER Binaries/Win64)
            exes = [
                e for e in (
                    list(pdir.glob("Packaged/**/*.exe")) +
                    list(pdir.glob("package_dev/**/*.exe")) +
                    list(pdir.glob("package_ship/**/*.exe"))
                )
                if e.is_file() and e.stat().st_size > 0 and not e.name.lower().endswith("crashreportclient.exe")
            ]
            if not exes:
                issues.append("Package stage produced no packaged executable on disk in Packaged/")
        else:
            issues.append("Package stage outcome missing executable path ('exe')")

    # ──────────────────────────────────────────────────────────────────────────
    # 9. REVIEW STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "review" in s_norm:
        mesh_audit = result.get("mesh_audit") or {}
        if not mesh_audit:
            issues.append("Review stage missing mesh audit outcome")
        elif not mesh_audit.get("passed", False) and mesh_audit.get("placeholder_components", 0) > 0:
            issues.append(
                f"Review mesh audit failed: {mesh_audit.get('placeholder_components')} "
                f"placeholder component(s) remain in level"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # 10. REPORT STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "report" in s_norm:
        rep = result.get("report_path")
        if not rep:
            issues.append("Report stage outcome missing 'report_path'")
        else:
            rp = Path(rep)
            if not rp.is_absolute() and pdir is not None:
                rp = pdir / rp
            if not rp.is_file():
                issues.append(f"Pipeline report file '{rep}' does not exist on disk")
            elif rp.stat().st_size == 0:
                issues.append(f"Pipeline report file '{rep}' is empty (0 bytes)")
            else:
                try:
                    if rp.suffix.lower() == ".json":
                        json.loads(rp.read_text(encoding="utf-8", errors="replace"))
                except Exception as exc:
                    issues.append(f"Pipeline report JSON file '{rep}' is corrupt: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # 11. TOOL_CALL STAGE
    # ──────────────────────────────────────────────────────────────────────────
    elif "tool_call" in s_norm:
        out_data = result.get("output")
        if isinstance(out_data, dict):
            if out_data.get("status") in ("ERROR", "FAILED"):
                issues.append(f"Tool execution failed: {out_data.get('error') or out_data.get('message')}")
            if out_data.get("exit_code", 0) != 0:
                issues.append(f"Tool exited with non-zero code {out_data.get('exit_code')}")

    # ──────────────────────────────────────────────────────────────────────────
    # 12. GENERAL FAIL-CLOSED CHECK
    # ──────────────────────────────────────────────────────────────────────────
    else:
        if result.get("ok") is False:
            errors = result.get("errors") or ["Stage reported ok=False"]
            issues.extend([str(e) for e in errors])

    # ──────────────────────────────────────────────────────────────────────────
    # 13. DECLARED ARTIFACTS VERIFICATION
    # ──────────────────────────────────────────────────────────────────────────
    if artifacts:
        for a in artifacts:
            path_str = a.get("path") if isinstance(a, dict) else getattr(a, "path", None)
            if path_str:
                ap = Path(path_str)
                if not ap.is_absolute():
                    if pdir is not None:
                        ap = pdir / ap
                    else:
                        ap = ap.resolve()
                if not ap.exists():
                    issues.append(f"Declared artifact file '{path_str}' does not exist on disk")
                elif ap.is_file() and ap.stat().st_size == 0:
                    issues.append(f"Declared artifact file '{path_str}' is empty (0 bytes)")
                elif ap.is_dir() and not any(ap.iterdir()):
                    issues.append(f"Declared artifact directory '{path_str}' is empty")

    return (len(issues) == 0, issues)
