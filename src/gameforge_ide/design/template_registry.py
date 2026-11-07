"""Semantic Template Registry and Multi-Strategy Game Generation Engine (P0 Overhaul).

Replaces rigid template hijacking and falling-cube fallbacks with semantic capability matching,
two-stage suitability analysis, and explicit strategy selection (Adapt Template, Hybrid, Scratch).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .gds import CameraKind, Genre

logger = logging.getLogger(__name__)

CompleteJson = Callable[[str, str, dict], Optional[str]]


class Capability:
    GRID_2D = "grid_2d"
    TURN_BASED = "turn_based"
    BOARD_GAME = "board_game"
    REAL_TIME = "real_time"
    PHYSICS_CHARACTER = "physics_character"
    COMBAT = "combat"
    SHOOTING = "shooting"
    PUZZLE_LOGIC = "puzzle_logic"
    UI_DRIVEN = "ui_driven"
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"
    FIXED_CAMERA = "fixed_camera"
    TOP_DOWN = "top_down"
    JUMPING = "jumping"
    COLLECTIBLES = "collectibles"
    ENEMIES = "enemies"
    CARD_DECK = "card_deck"
    VEHICLE_PHYSICS = "vehicle_physics"
    WAVE_SPAWNER = "wave_spawner"
    CONSTRAINT_SOLVER = "constraint_solver"
    PIECE_MOVEMENT = "piece_movement"
    CHECKMATE_LOGIC = "checkmate_logic"


class GenerationStrategy(str, Enum):
    ADAPT_TEMPLATE = "adapt_template"  # Approach A: >= 80% overlap, 0 conflicts
    HYBRID = "hybrid"                  # Approach B: 40-79% overlap, custom C++ logic added
    SCRATCH = "scratch"                # Approach C: < 40% overlap or conflicting constraints (e.g. Sudoku, Chess, Tetris)


@dataclass(frozen=True)
class TemplateDefinition:
    id: str
    title: str
    genre: Genre
    camera: CameraKind
    capabilities: Set[str]
    forbidden_capabilities: Set[str]
    description: str
    preset_key: Optional[str] = None


@dataclass
class CapabilityProfile:
    detected_genre: Genre
    required_capabilities: Set[str] = field(default_factory=set)
    forbidden_capabilities: Set[str] = field(default_factory=set)
    keywords_matched: List[str] = field(default_factory=list)
    title_hint: Optional[str] = None


@dataclass
class CandidateEvaluation:
    template: TemplateDefinition
    overlap_score: float
    has_conflict: bool
    conflict_reasons: List[str] = field(default_factory=list)
    matched_capabilities: Set[str] = field(default_factory=set)
    missing_capabilities: Set[str] = field(default_factory=set)


@dataclass
class StrategyDecision:
    strategy: GenerationStrategy
    template: Optional[TemplateDefinition]
    suitability_score: float
    profile: CapabilityProfile
    reasons: List[str]
    evaluations: List[CandidateEvaluation]
    suggested_architecture: Dict[str, Any] = field(default_factory=dict)


CANONICAL_TEMPLATES: List[TemplateDefinition] = [
    TemplateDefinition(
        id="platformer_3d",
        title="3D Platformer",
        genre=Genre.PLATFORMER,
        camera=CameraKind.THIRD_PERSON,
        capabilities={
            Capability.PHYSICS_CHARACTER,
            Capability.REAL_TIME,
            Capability.THIRD_PERSON,
            Capability.JUMPING,
            Capability.COLLECTIBLES,
        },
        forbidden_capabilities={
            Capability.PUZZLE_LOGIC,
            Capability.TURN_BASED,
            Capability.BOARD_GAME,
            Capability.CARD_DECK,
            Capability.CONSTRAINT_SOLVER,
        },
        description="3D obstacle course with running, jumping, floating platforms, and collectibles.",
        preset_key="platformer",
    ),
    TemplateDefinition(
        id="tactical_fps",
        title="Tactical FPS / Arena Combat",
        genre=Genre.ARENA_COMBAT,
        camera=CameraKind.FIRST_PERSON,
        capabilities={
            Capability.PHYSICS_CHARACTER,
            Capability.REAL_TIME,
            Capability.FIRST_PERSON,
            Capability.COMBAT,
            Capability.SHOOTING,
            Capability.ENEMIES,
        },
        forbidden_capabilities={
            Capability.TURN_BASED,
            Capability.BOARD_GAME,
            Capability.PUZZLE_LOGIC,
            Capability.CARD_DECK,
            Capability.CONSTRAINT_SOLVER,
        },
        description="First-person tactical combat arena with firearms, bot enemies, and weapon fire.",
        preset_key="arena_combat",
    ),
    TemplateDefinition(
        id="top_down_shooter",
        title="Top-Down Shooter",
        genre=Genre.TOP_DOWN_SHOOTER,
        camera=CameraKind.TOP_DOWN,
        capabilities={
            Capability.TOP_DOWN,
            Capability.REAL_TIME,
            Capability.COMBAT,
            Capability.SHOOTING,
            Capability.ENEMIES,
            Capability.WAVE_SPAWNER,
        },
        forbidden_capabilities={
            Capability.TURN_BASED,
            Capability.BOARD_GAME,
            Capability.PUZZLE_LOGIC,
            Capability.CARD_DECK,
        },
        description="Top-down shooter with projectile mechanics, wave spawners, and enemy hordes.",
        preset_key="top_down_shooter",
    ),
    TemplateDefinition(
        id="turn_based_grid_board",
        title="Turn-Based Grid Board",
        genre=Genre.GRID_BOARD,
        camera=CameraKind.FIXED_BOARD,
        capabilities={
            Capability.GRID_2D,
            Capability.TURN_BASED,
            Capability.BOARD_GAME,
            Capability.FIXED_CAMERA,
        },
        forbidden_capabilities={
            Capability.PHYSICS_CHARACTER,
            Capability.COMBAT,
            Capability.SHOOTING,
            Capability.JUMPING,
            Capability.VEHICLE_PHYSICS,
            Capability.PUZZLE_LOGIC,
            Capability.CONSTRAINT_SOLVER,
            Capability.REAL_TIME,
            Capability.PIECE_MOVEMENT,
        },
        description="Turn-based grid board game for two or more players (e.g. Tic-Tac-Toe, Connect Four, Gomoku).",
        preset_key="tic_tac_toe",
    ),
    TemplateDefinition(
        id="card_battler",
        title="Card Battler",
        genre=Genre.CARD_BATTLER,
        camera=CameraKind.FIXED_BOARD,
        capabilities={
            Capability.CARD_DECK,
            Capability.TURN_BASED,
            Capability.FIXED_CAMERA,
            Capability.UI_DRIVEN,
        },
        forbidden_capabilities={
            Capability.PHYSICS_CHARACTER,
            Capability.JUMPING,
            Capability.SHOOTING,
            Capability.VEHICLE_PHYSICS,
        },
        description="Turn-based card match game with deck play and UI interaction.",
        preset_key="card_battler",
    ),
    TemplateDefinition(
        id="relic_hunt",
        title="Relic Hunt Adventure",
        genre=Genre.ACTION_ADVENTURE,
        camera=CameraKind.THIRD_PERSON,
        capabilities={
            Capability.PHYSICS_CHARACTER,
            Capability.REAL_TIME,
            Capability.THIRD_PERSON,
            Capability.COLLECTIBLES,
        },
        forbidden_capabilities={
            Capability.TURN_BASED,
            Capability.BOARD_GAME,
            Capability.CARD_DECK,
            Capability.PUZZLE_LOGIC,
        },
        description="Third-person open adventure with relic exploration and environment navigation.",
        preset_key="relic_hunt",
    ),
]


class SemanticTemplateRegistry:
    """Classifies templates and capabilities, matching user prompts to the correct generation strategy."""

    def __init__(self, templates: Optional[List[TemplateDefinition]] = None):
        self.templates = templates or list(CANONICAL_TEMPLATES)

    def analyze_prompt(self, prompt: str) -> CapabilityProfile:
        text = prompt.lower().strip()

        # Title hint extraction
        m_title = re.search(r'\b(?:called|named|titled)\s+["\']?([^"\',.!?\n]+)["\']?', prompt, re.I)
        title_hint = m_title.group(1).strip() if m_title else None

        req: Set[str] = set()
        forbid: Set[str] = set()
        matched: List[str] = []

        # 1. Specialized Logic Puzzles & Discrete Games
        if re.search(r"\bsudoku\b", text):
            matched.append("sudoku")
            req.update({
                Capability.GRID_2D,
                Capability.PUZZLE_LOGIC,
                Capability.UI_DRIVEN,
                Capability.FIXED_CAMERA,
                Capability.CONSTRAINT_SOLVER,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.COMBAT,
                Capability.SHOOTING,
                Capability.JUMPING,
                Capability.ENEMIES,
                Capability.WAVE_SPAWNER,
                Capability.VEHICLE_PHYSICS,
                Capability.BOARD_GAME,
                Capability.TURN_BASED,
            })
            return CapabilityProfile(
                detected_genre=Genre.PUZZLE,
                required_capabilities=req,
                forbidden_capabilities=forbid,
                keywords_matched=matched,
                title_hint=title_hint or "Sudoku",
            )

        if re.search(r"\btetris\b", text):
            matched.append("tetris")
            req.update({
                Capability.GRID_2D,
                Capability.REAL_TIME,
                Capability.PUZZLE_LOGIC,
                Capability.FIXED_CAMERA,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.COMBAT,
                Capability.SHOOTING,
                Capability.ENEMIES,
                Capability.VEHICLE_PHYSICS,
                Capability.BOARD_GAME,
                Capability.TURN_BASED,
            })
            return CapabilityProfile(
                detected_genre=Genre.PUZZLE,
                required_capabilities=req,
                forbidden_capabilities=forbid,
                keywords_matched=matched,
                title_hint=title_hint or "Tetris",
            )

        is_snake_and_ladders = bool(re.search(r"\bsnakes?\s*(?:and|&)\s*ladders?\b|\bchutes\s*(?:and|&)\s*ladders?\b", text))
        if re.search(r"\bsnake\b", text) and not is_snake_and_ladders:
            matched.append("snake")
            req.update({
                Capability.GRID_2D,
                Capability.REAL_TIME,
                Capability.FIXED_CAMERA,
                Capability.PUZZLE_LOGIC,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.COMBAT,
                Capability.SHOOTING,
                Capability.VEHICLE_PHYSICS,
                Capability.BOARD_GAME,
                Capability.TURN_BASED,
            })
            return CapabilityProfile(
                detected_genre=Genre.PUZZLE,
                required_capabilities=req,
                forbidden_capabilities=forbid,
                keywords_matched=matched,
                title_hint=title_hint or "Snake",
            )

        if re.search(r"\bchess\b", text):
            matched.append("chess")
            req.update({
                Capability.GRID_2D,
                Capability.TURN_BASED,
                Capability.BOARD_GAME,
                Capability.FIXED_CAMERA,
                Capability.PIECE_MOVEMENT,
                Capability.CHECKMATE_LOGIC,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.COMBAT,
                Capability.SHOOTING,
                Capability.JUMPING,
                Capability.ENEMIES,
                Capability.VEHICLE_PHYSICS,
                Capability.REAL_TIME,
            })
            return CapabilityProfile(
                detected_genre=Genre.GRID_BOARD,
                required_capabilities=req,
                forbidden_capabilities=forbid,
                keywords_matched=matched,
                title_hint=title_hint or "Chess",
            )

        # 2. General Capability Detection
        is_top_down = bool(re.search(r"\b(?:top[\s\-]down|twin[\s\-]stick)\b", text))

        if re.search(r"\b(?:platformer|obstacle\s+course|parkour|jump(?:ing)?)\b", text):
            matched.append("platformer")
            req.update({
                Capability.PHYSICS_CHARACTER,
                Capability.REAL_TIME,
                Capability.THIRD_PERSON,
                Capability.JUMPING,
            })
            forbid.update({
                Capability.BOARD_GAME,
                Capability.CARD_DECK,
                Capability.PUZZLE_LOGIC,
                Capability.CONSTRAINT_SOLVER,
            })

        if is_top_down:
            matched.append("top_down")
            req.update({
                Capability.TOP_DOWN,
                Capability.REAL_TIME,
                Capability.COMBAT,
                Capability.SHOOTING,
            })
            forbid.update({
                Capability.FIRST_PERSON,
                Capability.TURN_BASED,
                Capability.BOARD_GAME,
                Capability.CARD_DECK,
            })
        elif re.search(r"\b(?:fps|first[\s\-]person|shooter|gun|rifle|counter[\s\-]strike)\b", text):
            matched.append("fps")
            req.update({
                Capability.PHYSICS_CHARACTER,
                Capability.REAL_TIME,
                Capability.FIRST_PERSON,
                Capability.COMBAT,
                Capability.SHOOTING,
            })
            forbid.update({
                Capability.TOP_DOWN,
                Capability.TURN_BASED,
                Capability.BOARD_GAME,
                Capability.CARD_DECK,
                Capability.PUZZLE_LOGIC,
            })

        if re.search(r"\b(?:racing|car|vehicle|drive|driving)\b", text):
            matched.append("racing")
            req.update({
                Capability.VEHICLE_PHYSICS,
                Capability.REAL_TIME,
                Capability.THIRD_PERSON,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.JUMPING,
                Capability.COLLECTIBLES,
                Capability.TURN_BASED,
                Capability.BOARD_GAME,
                Capability.CARD_DECK,
                Capability.PUZZLE_LOGIC,
            })

        if re.search(r"\b(?:tower\s+defense|defend\s+the\s+base)\b", text):
            matched.append("tower_defense")
            req.update({
                Capability.TOP_DOWN,
                Capability.REAL_TIME,
                Capability.WAVE_SPAWNER,
                Capability.GRID_2D,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.JUMPING,
            })

        if re.search(r"\b(?:card|cards|deck|deckbuilder|battler)\b", text):
            matched.append("card")
            req.update({
                Capability.CARD_DECK,
                Capability.TURN_BASED,
                Capability.FIXED_CAMERA,
                Capability.UI_DRIVEN,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.JUMPING,
                Capability.SHOOTING,
                Capability.VEHICLE_PHYSICS,
            })

        if re.search(r"\b(?:tic[\s\-]tac[\s\-]toe|connect\s+four|gomoku|board\s+game|snakes?\s*(?:and|&)\s*ladders?|chutes\s*(?:and|&)\s*ladders?|ludo|parcheesi|monopoly|checkers|draughts|dice\s+board(?:\s+game)?|roll\s+and\s+move)\b", text):
            matched.append("board_game")
            req.update({
                Capability.GRID_2D,
                Capability.TURN_BASED,
                Capability.BOARD_GAME,
                Capability.FIXED_CAMERA,
            })
            forbid.update({
                Capability.PHYSICS_CHARACTER,
                Capability.COMBAT,
                Capability.SHOOTING,
                Capability.JUMPING,
                Capability.VEHICLE_PHYSICS,
            })

        # Fallback to action adventure or custom if no strong genre matched
        if not req:
            req.update({Capability.PHYSICS_CHARACTER, Capability.REAL_TIME, Capability.THIRD_PERSON})
            detected_genre = Genre.ACTION_ADVENTURE
        elif Capability.PUZZLE_LOGIC in req:
            detected_genre = Genre.PUZZLE
        elif Capability.BOARD_GAME in req:
            detected_genre = Genre.GRID_BOARD
        elif Capability.CARD_DECK in req:
            detected_genre = Genre.CARD_BATTLER
        elif Capability.FIRST_PERSON in req and Capability.SHOOTING in req:
            detected_genre = Genre.ARENA_COMBAT
        elif Capability.TOP_DOWN in req and Capability.SHOOTING in req:
            detected_genre = Genre.TOP_DOWN_SHOOTER
        elif Capability.JUMPING in req:
            detected_genre = Genre.PLATFORMER
        else:
            detected_genre = Genre.CUSTOM

        return CapabilityProfile(
            detected_genre=detected_genre,
            required_capabilities=req,
            forbidden_capabilities=forbid,
            keywords_matched=matched,
            title_hint=title_hint,
        )

    def evaluate_strategy(self, prompt: str) -> StrategyDecision:
        profile = self.analyze_prompt(prompt)
        evaluations: List[CandidateEvaluation] = []

        for tmpl in self.templates:
            conflict_reasons: List[str] = []

            # Check 1: Template has capability forbidden by the user's request
            conflicts_in_template = tmpl.capabilities & profile.forbidden_capabilities
            if conflicts_in_template:
                conflict_reasons.append(
                    f"Template '{tmpl.title}' includes forbidden capabilities: {sorted(conflicts_in_template)}"
                )

            # Check 2: Template forbids capability required by the user's request
            conflicts_in_req = tmpl.forbidden_capabilities & profile.required_capabilities
            if conflicts_in_req:
                conflict_reasons.append(
                    f"Template '{tmpl.title}' explicitly forbids required capabilities: {sorted(conflicts_in_req)}"
                )

            has_conflict = len(conflict_reasons) > 0
            matched = tmpl.capabilities & profile.required_capabilities
            missing = profile.required_capabilities - tmpl.capabilities

            if has_conflict:
                overlap_score = 0.0
            else:
                total_req = max(1, len(profile.required_capabilities))
                overlap_score = round(len(matched) / total_req, 3)

            evaluations.append(
                CandidateEvaluation(
                    template=tmpl,
                    overlap_score=overlap_score,
                    has_conflict=has_conflict,
                    conflict_reasons=conflict_reasons,
                    matched_capabilities=matched,
                    missing_capabilities=missing,
                )
            )

        # Sort evaluations by score descending
        evaluations.sort(key=lambda e: e.overlap_score, reverse=True)
        best = evaluations[0] if evaluations else None

        # Decision logic:
        # Strategy A (ADAPT_TEMPLATE): overlap >= 0.80 and no conflicts
        # Strategy B (HYBRID): 0.40 <= overlap < 0.80 and no conflicts
        # Strategy C (SCRATCH): overlap < 0.40 or all candidates have conflicts
        reasons: List[str] = []

        if best and not best.has_conflict and best.overlap_score >= 0.80:
            strategy = GenerationStrategy.ADAPT_TEMPLATE
            reasons.append(
                f"Selected '{best.template.title}' (Approach A: Adapt Template) with "
                f"{int(best.overlap_score * 100)}% capability overlap and zero conflicts."
            )
            suggested_arch = {
                "method": "template_adaptation",
                "template_id": best.template.id,
                "genre": best.template.genre,
                "camera": best.template.camera,
                "preset_key": best.template.preset_key,
            }
            return StrategyDecision(
                strategy=strategy,
                template=best.template,
                suitability_score=best.overlap_score,
                profile=profile,
                reasons=reasons,
                evaluations=evaluations,
                suggested_architecture=suggested_arch,
            )

        if best and not best.has_conflict and best.overlap_score >= 0.40:
            strategy = GenerationStrategy.HYBRID
            reasons.append(
                f"Selected '{best.template.title}' (Approach B: Hybrid Generation) with "
                f"{int(best.overlap_score * 100)}% capability overlap. Requires custom rules for "
                f"missing capabilities: {sorted(best.missing_capabilities)}."
            )
            suggested_arch = {
                "method": "hybrid_generation",
                "base_template_id": best.template.id,
                "genre": profile.detected_genre,
                "camera": best.template.camera,
                "custom_capabilities": list(best.missing_capabilities),
            }
            return StrategyDecision(
                strategy=strategy,
                template=best.template,
                suitability_score=best.overlap_score,
                profile=profile,
                reasons=reasons,
                evaluations=evaluations,
                suggested_architecture=suggested_arch,
            )

        # Strategy C: Generate from Scratch
        strategy = GenerationStrategy.SCRATCH
        if best and best.has_conflict:
            reasons.append(
                f"All existing templates conflict with prompt constraints (e.g. {best.conflict_reasons[0]}). "
                f"Selecting Approach C: Generate from Scratch."
            )
        else:
            reasons.append(
                "No existing template matches the required capabilities (< 40% overlap). "
                "Selecting Approach C: Generate from Scratch."
            )

        # Construct game-specific scratch architecture
        suggested_arch = self._synthesize_scratch_architecture(profile)

        return StrategyDecision(
            strategy=strategy,
            template=None,
            suitability_score=0.0,
            profile=profile,
            reasons=reasons,
            evaluations=evaluations,
            suggested_architecture=suggested_arch,
        )

    def evaluate_strategy_with_model(
        self,
        prompt: str,
        complete_json: Optional[CompleteJson] = None,
        model: Optional[str] = None,
    ) -> StrategyDecision:
        """Uses LLM to evaluate the generation strategy and decide whether to adapt a template, create hybrid, or build from scratch."""
        if complete_json is not None:
            templates_summary = "\n".join(
                f"- ID: '{t.id}' | Title: {t.title} | Genre: {t.genre.value} | Camera: {t.camera.value}\n"
                f"  Capabilities: {', '.join(sorted(t.capabilities))}\n"
                f"  Forbidden: {', '.join(sorted(t.forbidden_capabilities))}\n"
                f"  Description: {t.description}"
                for t in self.templates
            )
            system = (
                "You are GameForge's Principal Game Systems Architect.\n"
                "Your mission is to evaluate the user's natural-language game request and choose the optimal implementation strategy.\n\n"
                "AVAILABLE TEMPLATES IN ENGINE:\n"
                f"{templates_summary}\n\n"
                "STRATEGY DEFINITIONS:\n"
                "1. 'adapt_template': An existing template is an exact match (>=80% overlap) for the gameplay mechanics with zero conflicting constraints.\n"
                "2. 'hybrid': An existing template provides the base movement/camera (40-79% overlap), but requires custom C++ logic for new mechanics.\n"
                "3. 'scratch': NONE of the templates match (e.g. Sudoku, Chess, Tetris, Minesweeper, Card games with custom logic, RTS, Tycoon, custom logic games).\n\n"
                "CRITICAL ARCHITECTURAL CONSTRAINTS:\n"
                "- NEVER adapt a 3D platformer or combat shooter for a discrete board game, logic puzzle, or Sudoku!\n"
                "- For Sudoku: you MUST select strategy='scratch' (or 'puzzle_grid') so that it is built with dedicated 9x9 grid data structures, number pad, and solver without falling cubes, obstacles, or character combat.\n"
                "- Output strictly valid JSON conforming to the schema."
            )
            schema = {
                "type": "object",
                "properties": {
                    "strategy": {"type": "string", "enum": ["adapt_template", "hybrid", "scratch"]},
                    "template_id": {"type": "string"},
                    "genre": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "target_classes": {"type": "array", "items": {"type": "string"}},
                    "custom_mechanics": {"type": "object"},
                    "plan_steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "target_files": {"type": "array", "items": {"type": "string"}},
                                "verification": {"type": "string"}
                            },
                            "required": ["title", "description", "target_files", "verification"]
                        }
                    }
                },
                "required": ["strategy", "reasoning"]
            }
            try:
                raw = complete_json(system, prompt, schema)
                if raw:
                    data = json.loads(raw)
                    strat_str = data.get("strategy", "").lower()
                    if strat_str in ("adapt_template", "hybrid", "scratch"):
                        strategy = GenerationStrategy(strat_str)
                        tmpl_id = data.get("template_id")
                        tmpl = next((t for t in self.templates if t.id == tmpl_id), None)
                        profile = self.analyze_prompt(prompt)
                        if data.get("genre"):
                            try:
                                profile.detected_genre = Genre(data["genre"])
                            except Exception:
                                pass
                        suggested_arch = {
                            "method": f"llm_{strat_str}",
                            "template_id": tmpl_id,
                            "genre": profile.detected_genre,
                            "target_classes": data.get("target_classes") or ["CustomGameMode"],
                            "mechanics": data.get("custom_mechanics") or {},
                            "llm_plan_steps": data.get("plan_steps") or [],
                        }
                        if strategy == GenerationStrategy.SCRATCH:
                            scratch_arch = self._synthesize_scratch_architecture(profile)
                            scratch_arch.update(suggested_arch)
                            suggested_arch = scratch_arch

                        return StrategyDecision(
                            strategy=strategy,
                            template=tmpl,
                            suitability_score=1.0 if strategy == GenerationStrategy.ADAPT_TEMPLATE else (0.6 if strategy == GenerationStrategy.HYBRID else 0.2),
                            profile=profile,
                            reasons=[f"[LLM Decision]: {data.get('reasoning', '')}"],
                            evaluations=[],
                            suggested_architecture=suggested_arch,
                        )
            except Exception as exc:
                logger.warning("LLM strategy evaluation failed, using deterministic evaluation: %s", exc)

        return self.evaluate_strategy(prompt)

    def _synthesize_scratch_architecture(self, profile: CapabilityProfile) -> Dict[str, Any]:
        """Provides concrete, genre-appropriate C++ and UI architecture for games generated from scratch."""
        if "sudoku" in profile.keywords_matched:
            return {
                "method": "scratch_generation",
                "genre": Genre.PUZZLE,
                "camera": CameraKind.FIXED_BOARD,
                "plan_kind": "scratch_puzzle",
                "target_classes": [
                    "ASudokuGameMode",
                    "USudokuGameInstance",
                    "USudokuGridManager",
                    "FSudokuSolver",
                ],
                "target_widgets": [
                    "WSudokuGrid",
                    "WNumberPad",
                    "WCellButton",
                    "WSudokuHUD",
                ],
                "source_files": [
                    "Source/MyGame/SudokuGameMode.h",
                    "Source/MyGame/SudokuGameMode.cpp",
                    "Source/MyGame/SudokuGameInstance.h",
                    "Source/MyGame/SudokuGameInstance.cpp",
                    "Source/MyGame/SudokuGridManager.h",
                    "Source/MyGame/SudokuGridManager.cpp",
                ],
                "mechanics": {
                    "grid_size": 9,
                    "subgrid_size": 3,
                    "rule_set": "Standard Sudoku (no repeated digits in rows, columns, or 3x3 boxes)",
                },
                "win_condition": "board.solved == true",
                "lose_condition": None,
            }

        if "chess" in profile.keywords_matched:
            return {
                "method": "scratch_generation",
                "genre": Genre.GRID_BOARD,
                "camera": CameraKind.FIXED_BOARD,
                "plan_kind": "scratch_board",
                "target_classes": [
                    "AChessGameMode",
                    "AChessBoardManager",
                    "AChessPiece",
                    "FChessMoveValidator",
                ],
                "target_widgets": [
                    "WChessHUD",
                    "WTurnIndicator",
                ],
                "source_files": [
                    "Source/MyGame/ChessGameMode.h",
                    "Source/MyGame/ChessGameMode.cpp",
                    "Source/MyGame/ChessBoardManager.h",
                    "Source/MyGame/ChessBoardManager.cpp",
                ],
                "win_condition": "board.checkmate == true",
                "lose_condition": None,
            }

        if "tetris" in profile.keywords_matched:
            return {
                "method": "scratch_generation",
                "genre": Genre.PUZZLE,
                "camera": CameraKind.FIXED_BOARD,
                "plan_kind": "scratch_falling_blocks",
                "target_classes": [
                    "ATetrisGameMode",
                    "UTetrisGridManager",
                    "ATetrominoSpawner",
                ],
                "target_widgets": [
                    "WTetrisHUD",
                    "WScoreBoard",
                ],
                "source_files": [
                    "Source/MyGame/TetrisGameMode.h",
                    "Source/MyGame/TetrisGameMode.cpp",
                    "Source/MyGame/TetrisGridManager.h",
                    "Source/MyGame/TetrisGridManager.cpp",
                ],
                "win_condition": "score >= 1000",
                "lose_condition": "grid.top_out == true",
            }

        if "snake" in profile.keywords_matched:
            return {
                "method": "scratch_generation",
                "genre": Genre.PUZZLE,
                "camera": CameraKind.FIXED_BOARD,
                "plan_kind": "scratch_snake",
                "target_classes": [
                    "ASnakeGameMode",
                    "ASnakePawn",
                    "AFoodSpawner",
                ],
                "target_widgets": [
                    "WSnakeHUD",
                ],
                "source_files": [
                    "Source/MyGame/SnakeGameMode.h",
                    "Source/MyGame/SnakeGameMode.cpp",
                ],
                "win_condition": "score >= 50",
                "lose_condition": "snake.self_collision == true",
            }

        if profile.detected_genre == Genre.PUZZLE:
            return {
                "method": "scratch_generation",
                "genre": Genre.PUZZLE,
                "camera": CameraKind.FIXED_BOARD,
                "plan_kind": "scratch_puzzle",
                "target_classes": [
                    "APuzzleGameMode",
                    "UPuzzleGridManager",
                ],
                "target_widgets": [
                    "WPuzzleHUD",
                ],
                "source_files": [
                    "Source/MyGame/PuzzleGameMode.h",
                    "Source/MyGame/PuzzleGameMode.cpp",
                ],
                "win_condition": "puzzle.solved == true",
                "lose_condition": None,
            }

        # Default scratch architecture
        return {
            "method": "scratch_generation",
            "genre": profile.detected_genre,
            "camera": CameraKind.THIRD_PERSON,
            "plan_kind": "scratch_custom",
            "target_classes": [
                "ACustomGameMode",
                "ACustomPlayerController",
                "ACustomGameState",
            ],
            "target_widgets": [
                "WCustomHUD",
            ],
            "source_files": [
                "Source/MyGame/CustomGameMode.h",
                "Source/MyGame/CustomGameMode.cpp",
            ],
            "win_condition": "game.won == true",
            "lose_condition": "game.lost == true",
        }


# Global registry instance
default_registry = SemanticTemplateRegistry()
