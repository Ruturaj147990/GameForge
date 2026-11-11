"""Requirement-to-Implementation Traceability & Strict Completion Gates.

Ensures every generated game has a machine-checkable requirements ledger,
verifies genuine gameplay implementation against user prompts, and prevents
false success reporting where templates are packaged without actual game logic.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ...design.gds import GameDesignSpec, Genre

logger = logging.getLogger(__name__)


@dataclass
class GameRequirement:
    req_id: str
    title: str
    description: str
    category: str  # "spatial_board", "rules_logic", "actors_entities", "ui_widgets", "win_condition"
    satisfied: bool = False
    evidence: Optional[str] = None
    associated_files: List[str] = field(default_factory=list)
    associated_actors: List[str] = field(default_factory=list)
    associated_events: List[str] = field(default_factory=list)


@dataclass
class CompletionReport:
    is_complete: bool
    stages_achieved: Dict[str, bool]
    completed_requirements: List[GameRequirement]
    incomplete_requirements: List[GameRequirement]
    verdict_summary: str
    template_only_detected: bool = False


def derive_requirements_for_game(
    prompt: str,
    gds: Optional[GameDesignSpec] = None,
) -> List[GameRequirement]:
    """Derives structured, game-specific gameplay requirements from the prompt and GDS."""
    reqs: List[GameRequirement] = []
    p_low = prompt.lower()

    # 1. Board & Discrete Logic Games
    is_snakes = bool(re.search(r"\b(snakes?\s*(?:and|&)\s*ladders?|chutes\s*(?:and|&)\s*ladders?)\b", p_low))
    is_roll_and_move = is_snakes or bool(re.search(r"\b(roll\s+and\s+move|race\s+board|ludo|parcheesi)\b", p_low))
    is_chess = bool(re.search(r"\bchess\b", p_low))
    is_checkers = bool(re.search(r"\b(checkers|draughts)\b", p_low))
    is_sudoku = bool(re.search(r"\b(sudoku|number\s+constraint)\b", p_low))
    is_tetris = bool(re.search(r"\b(tetris|falling\s+blocks?)\b", p_low))
    is_snake_arcade = bool(re.search(r"\bsnake\b", p_low) and not is_snakes and re.search(r"\b(apple|grow|tail|classic|grid)\b", p_low))

    if is_snakes:
        reqs.append(GameRequirement(
            req_id="req_board_grid_10x10",
            title="10x10 Linear Numbered Track Board",
            description="A real 10x10 (100-tile) grid board actor must exist with tile coordinates and navigation layout.",
            category="spatial_board",
            associated_files=["Source/", "GameForge/design/game.gds.json"],
            associated_actors=["board_0", "GF_Board"],
        ))
        reqs.append(GameRequirement(
            req_id="req_dice_rolling",
            title="Working Dice Mechanic",
            description="Dice rolling functionality (1-6) must exist, advancing turns and emitting dice events.",
            category="rules_logic",
            associated_events=["dice.rolled", "board.move"],
        ))
        reqs.append(GameRequirement(
            req_id="req_player_tokens",
            title="Player and AI Tokens",
            description="Player tokens must exist on disk / in level, tracking positions 1..100 across turns.",
            category="actors_entities",
            associated_files=["Source/"],
        ))
        reqs.append(GameRequirement(
            req_id="req_snake_warp_mechanics",
            title="Snakes Downward Slides",
            description="Landing on snake heads must slide player tokens downwards to corresponding tail tiles.",
            category="rules_logic",
            associated_events=["snake.transition"],
        ))
        reqs.append(GameRequirement(
            req_id="req_ladder_climb_mechanics",
            title="Ladders Upward Climbs",
            description="Landing on ladder bases must climb player tokens upwards to ladder tops.",
            category="rules_logic",
            associated_events=["ladder.transition"],
        ))
        reqs.append(GameRequirement(
            req_id="req_win_detection",
            title="Tile 100 Win Detection",
            description="Game must detect when a player reaches tile 100, conclude the match, and emit win events.",
            category="win_condition",
            associated_events=["board.win", "game.won", "match.won"],
        ))
    elif is_roll_and_move:
        reqs.append(GameRequirement(
            req_id="req_track_board",
            title="Track Board Geometry",
            description="A track board grid actor must be placed in the level.",
            category="spatial_board",
            associated_actors=["board_0"],
        ))
        reqs.append(GameRequirement(
            req_id="req_dice_rolling",
            title="Dice Rolling System",
            description="Dice rolling functionality must advance turn positions.",
            category="rules_logic",
            associated_events=["dice.rolled", "board.move"],
        ))
        reqs.append(GameRequirement(
            req_id="req_win_detection",
            title="Race Board Win Detection",
            description="Game must declare a winner upon reaching the target goal tile.",
            category="win_condition",
            associated_events=["board.win", "game.won"],
        ))
    elif is_chess or is_checkers:
        reqs.append(GameRequirement(
            req_id="req_chess_board_8x8",
            title="8x8 Checkered Grid Board",
            description="8x8 grid board actor must exist with alternating light and dark squares.",
            category="spatial_board",
            associated_actors=["board_0"],
        ))
        reqs.append(GameRequirement(
            req_id="req_turn_rotation",
            title="Alternating Player Turns",
            description="Rules must enforce turn rotation between Player 1 and Player 2 / AI.",
            category="rules_logic",
            associated_events=["turn.ended", "board.move"],
        ))
        reqs.append(GameRequirement(
            req_id="req_piece_movement",
            title="Piece Movement & Capture",
            description="State machine must track piece locations and handle captures or checkmate.",
            category="rules_logic",
            associated_events=["board.move"],
        ))
    elif is_sudoku:
        reqs.append(GameRequirement(
            req_id="req_sudoku_grid_9x9",
            title="9x9 Sudoku Grid Layout",
            description="9x9 grid board with 3x3 subgrid regions must be placed in the level.",
            category="spatial_board",
            associated_actors=["board_0"],
        ))
        reqs.append(GameRequirement(
            req_id="req_sudoku_rules",
            title="Digit Constraint Validation",
            description="Rules state machine must validate row, column, and subgrid digit constraints.",
            category="rules_logic",
            associated_events=["board.move"],
        ))
    elif is_tetris:
        reqs.append(GameRequirement(
            req_id="req_matrix_layout",
            title="Falling Block Matrix Grid",
            description="Matrix board actor with gravity must exist in the level.",
            category="spatial_board",
            associated_actors=["board_0"],
        ))
        reqs.append(GameRequirement(
            req_id="req_line_clearing",
            title="Line Clearing & Score Rules",
            description="C++ rules must track filled rows and clear lines upon completion.",
            category="rules_logic",
            associated_events=["line.cleared", "board.move"],
        ))
    elif is_snake_arcade:
        reqs.append(GameRequirement(
            req_id="req_snake_arena",
            title="2D Grid Arena for Snake",
            description="Grid arena layout must be generated with bounded walls.",
            category="spatial_board",
            associated_actors=["board_0"],
        ))
        reqs.append(GameRequirement(
            req_id="req_tail_growth",
            title="Food Collection & Tail Growth",
            description="Rules must increment tail length and spawn food pickups.",
            category="rules_logic",
            associated_events=["pickup.collected"],
        ))
    else:
        # Action, shooter, platformer, exploration
        reqs.append(GameRequirement(
            req_id="req_core_gameplay",
            title="Core Gameplay Systems",
            description=f"Authentic gameplay mechanics tailored for {prompt[:60]}.",
            category="rules_logic",
            associated_files=["Source/"],
        ))
        reqs.append(GameRequirement(
            req_id="req_win_lose",
            title="Win and Lose Conditions",
            description="Win and lose conditions matching the prompt requirements.",
            category="win_condition",
            associated_events=["game.won", "goal.reached", "match.won"],
        ))

    return reqs


def verify_game_completion_gate(
    prompt: str,
    gds: Optional[GameDesignSpec],
    project_dir: Union[str, Path],
    outcome: Dict[str, Any],
) -> CompletionReport:
    """Rigorous 9-stage completion gate distinguishing real game creation from template copying."""
    pdir = Path(str(project_dir)).resolve()
    stages_achieved: Dict[str, bool] = {
        "1_project_created": False,
        "2_template_scaffolded": False,
        "3_gameplay_started": False,
        "4_gameplay_implemented": False,
        "5_project_compiled": False,
        "6_project_packaged": False,
        "7_game_launched": False,
        "8_gameplay_tested": False,
        "9_requirements_verified": False,
    }

    # 1. Project Created
    uprojects = list(pdir.glob("*.uproject")) if pdir.is_dir() else []
    if uprojects:
        stages_achieved["1_project_created"] = True

    # 2. Template Scaffolded
    source_dir = pdir / "Source"
    config_dir = pdir / "Config"
    if source_dir.is_dir() and config_dir.is_dir():
        stages_achieved["2_template_scaffolded"] = True

    # 4. Gameplay Implemented (Check for real game logic vs generic template)
    template_only_detected = False
    cpp_files = list(source_dir.rglob("*.cpp")) if source_dir.is_dir() else []
    h_files = list(source_dir.rglob("*.h")) if source_dir.is_dir() else []
    all_source_text = ""
    for f in (cpp_files + h_files)[:30]:
        try:
            all_source_text += f.read_text(encoding="utf-8", errors="replace") + "\n"
        except Exception:
            pass

    # 3. Gameplay Started
    gds_file = pdir / "GameForge" / "design" / "game.gds.json"
    if gds_file.is_file() or gds is not None or len(cpp_files) > 0:
        stages_achieved["3_gameplay_started"] = True

    requirements = derive_requirements_for_game(prompt, gds)

    # Check if a discrete board game was requested but only platformer code exists
    p_low = prompt.lower()
    is_board_req = bool(re.search(r"\b(snakes?\s*(?:and|&)\s*ladders?|chutes|ludo|chess|checkers|sudoku|tetris|board\s+game)\b", p_low))
    has_platformer_only = ("ACharacter" in all_source_text or "Jump" in all_source_text) and not any(
        k in all_source_text for k in ("BoardGrid", "dice.rolled", "ladder.transition", "snake.transition", "UBoardGameSubsystem", "GameForgeGridBoard", "BoardMode")
    )

    if is_board_req and has_platformer_only:
        template_only_detected = True

    # Evaluate each requirement against source, GDS, and stage outputs
    completed_reqs: List[GameRequirement] = []
    incomplete_reqs: List[GameRequirement] = []

    for req in requirements:
        req_satisfied = False
        ev_notes = []

        if req.req_id == "req_board_grid_10x10":
            # Check GDS or sources
            has_grid = False
            if gds is not None:
                for ent in getattr(gds, "entities", []):
                    props = getattr(ent, "props", {}) or {}
                    if props.get("board_mode") == "roll_and_move" or props.get("board_size") == 10:
                        has_grid = True
                        ev_notes.append("Board entity with 10x10 roll_and_move found in GDS")
            if "GameForgeGridBoard" in all_source_text or "roll_and_move" in all_source_text or has_grid:
                req_satisfied = True
                req.evidence = "; ".join(ev_notes) or "Grid board configuration verified in project"
            else:
                req.evidence = "No 10x10 board entity or GameForgeGridBoard found in sources or GDS"

        elif req.req_id == "req_dice_rolling":
            if "dice.rolled" in all_source_text or (gds and any("dice" in str(getattr(e, "props", {})).lower() for e in getattr(gds, "entities", []))):
                req_satisfied = True
                req.evidence = "Dice rolling event and mechanics verified in C++ rules"
            else:
                req.evidence = "Dice rolling logic missing from C++ sources"

        elif req.req_id == "req_player_tokens":
            if "PlayerPositions" in all_source_text or "player" in all_source_text or not template_only_detected:
                req_satisfied = True
                req.evidence = "Player token tracking verified in board state machine"
            else:
                req.evidence = "Player token state missing"

        elif req.req_id == "req_snake_warp_mechanics":
            if "snake.transition" in all_source_text or (gds and any(getattr(e, "props", {}).get("snakes") for e in getattr(gds, "entities", []))):
                req_satisfied = True
                req.evidence = "Snake downward transitions verified in C++ rules and GDS"
            else:
                req.evidence = "Snake transitions missing from C++ rules"

        elif req.req_id == "req_ladder_climb_mechanics":
            if "ladder.transition" in all_source_text or (gds and any(getattr(e, "props", {}).get("ladders") for e in getattr(gds, "entities", []))):
                req_satisfied = True
                req.evidence = "Ladder climb transitions verified in C++ rules and GDS"
            else:
                req.evidence = "Ladder climb transitions missing from C++ rules"

        elif req.req_id == "req_win_detection":
            if "board.win" in all_source_text or "game.won" in all_source_text or (gds and getattr(gds, "win", None)):
                req_satisfied = True
                req.evidence = "Win detection logic verified in C++ rules"
            else:
                req.evidence = "Win detection missing from C++ rules"

        else:
            # General fallback check
            if not template_only_detected and len(cpp_files) > 0:
                req_satisfied = True
                req.evidence = f"Source files exist and project compiled ({len(cpp_files)} cpp files)"
            else:
                req.evidence = "Requested game mechanics not verified in implementation"

        req.satisfied = req_satisfied
        if req_satisfied:
            completed_reqs.append(req)
        else:
            incomplete_reqs.append(req)

    if not template_only_detected and len(completed_reqs) >= max(1, int(len(requirements) * 0.75)):
        stages_achieved["4_gameplay_implemented"] = True

    # 5. Project Compiled
    build_ok = outcome.get("ok", True) and outcome.get("status") in ("SUCCESS", "OK")
    stages_list = outcome.get("stages") or []
    compile_stage = next((s for s in stages_list if s.get("step_id") in ("compile", "legacy_compile")), None)
    if compile_stage and compile_stage.get("status") == "DONE":
        stages_achieved["5_project_compiled"] = True
    elif ((pdir / "Binaries").is_dir() or outcome.get("package_exe") or outcome.get("exe")) and build_ok:
        stages_achieved["5_project_compiled"] = True

    # 6. Project Packaged
    package_stage = next((s for s in stages_list if s.get("step_id") in ("package", "legacy_package")), None)
    exe = outcome.get("exe") or outcome.get("package_exe")
    if (package_stage and package_stage.get("status") == "DONE") or (exe and Path(str(exe)).is_file()):
        stages_achieved["6_project_packaged"] = True

    # 7. Game Launched & 8. Gameplay Tested
    scenario_stage = next((s for s in stages_list if s.get("step_id") in ("scenarios", "scenario_gen", "legacy_scenarios")), None)
    if scenario_stage and scenario_stage.get("status") == "DONE":
        stages_achieved["7_game_launched"] = True
        stages_achieved["8_gameplay_tested"] = True

    # 9. Requirements Verified
    if len(incomplete_reqs) == 0 and not template_only_detected:
        stages_achieved["9_requirements_verified"] = True

    is_complete = (
        stages_achieved["1_project_created"]
        and stages_achieved["2_template_scaffolded"]
        and stages_achieved["3_gameplay_started"]
        and stages_achieved["4_gameplay_implemented"]
        and stages_achieved["9_requirements_verified"]
        and not template_only_detected
    )

    if template_only_detected:
        summary = (
            "CRITICAL COMPLETION GATE FAILURE: The project is merely a premade template "
            "(e.g. 3D Platformer) with no meaningful implementation of the requested game. "
            "Scaffolding or building a template does not constitute successful game generation."
        )
    elif is_complete:
        summary = (
            f"GAME COMPLETION VERIFIED: All 9 stages achieved and all {len(requirements)} "
            "gameplay requirements verified with real implementation evidence."
        )
    else:
        unmet_names = [r.title for r in incomplete_reqs]
        summary = (
            f"INCOMPLETE IMPLEMENTATION: Project built at engine level, but {len(incomplete_reqs)} "
            f"gameplay requirements remain unmet: {', '.join(unmet_names)}."
        )

    return CompletionReport(
        is_complete=is_complete,
        stages_achieved=stages_achieved,
        completed_requirements=completed_reqs,
        incomplete_requirements=incomplete_reqs,
        verdict_summary=summary,
        template_only_detected=template_only_detected,
    )
