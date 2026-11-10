"""Semantic Template Registry and Multi-Strategy Game Generation Engine.

Evaluates capability overlap between arbitrary user prompts and engine foundations,
selects the optimal generation strategy (Adapt Template, Hybrid, Scratch), and
synthesizes a prompt-specific C++ & UI architecture specification so every generated
game genuinely implements the user's requested mechanics, systems, and entities.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

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
    STEALTH_AI = "stealth_ai"
    INTERACTIVE_SWITCHES = "interactive_switches"
    RESOURCE_DRAIN = "resource_drain"
    MULTI_WEAPON = "multi_weapon"


class GenerationStrategy(str, Enum):
    ADAPT_TEMPLATE = "adapt_template"
    HYBRID = "hybrid"
    SCRATCH = "scratch"


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
    draft_preloaded: Optional[Dict[str, Any]] = None


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
        description="3D traversal foundation with character movement, jumping, platforms, and collectibles.",
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
        description="First-person tactical combat foundation with projectile weapons and hostile AI.",
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
        description="Top-down combat foundation with projectile aiming and wave spawners.",
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
        description="Turn-based grid board foundation for alignment and token movement rules.",
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
        description="Turn-based card match foundation with lane deployment and deck management.",
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
        description="Third-person exploration and adventure foundation with quests and world interaction.",
        preset_key="relic_hunt",
    ),
]


def _pascal_ident(text: str, default: str = "DynamicGame") -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", text or "")
    out = "".join(t[:1].upper() + t[1:] for t in tokens if t)
    if not out or not out[0].isalpha():
        return default
    return out[:24]


class SemanticTemplateRegistry:
    """Classifies templates and capabilities, matching user prompts to the optimal generation strategy
    and synthesizing prompt-specific C++ & UI architecture extensions."""

    def __init__(self, templates: Optional[List[TemplateDefinition]] = None):
        self.templates = templates or list(CANONICAL_TEMPLATES)

    def analyze_prompt(self, prompt: str) -> CapabilityProfile:
        text = prompt.lower().strip()

        m_title = re.search(r'\b(?:called|named|titled)\s+["\']?([^"\',.!?\n]+)["\']?', prompt, re.I)
        title_hint = m_title.group(1).strip() if m_title else None

        req: Set[str] = set()
        forbid: Set[str] = set()
        matched: List[str] = []

        # 1. Constraint-Satisfaction & Grid Logic Archetypes
        if re.search(r"\b(sudoku|number\s+constraint|constraint\s+grid)\b", text):
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
                title_hint=title_hint or "Constraint Grid",
            )

        if re.search(r"\b(minesweeper|mine\s+deduction|hidden\s+mine)\b", text):
            matched.append("minesweeper")
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
                Capability.VEHICLE_PHYSICS,
                Capability.TURN_BASED,
            })
            return CapabilityProfile(
                detected_genre=Genre.PUZZLE,
                required_capabilities=req,
                forbidden_capabilities=forbid,
                keywords_matched=matched,
                title_hint=title_hint or "Deduction Grid",
            )

        if re.search(r"\b(tetris|falling\s+blocks?|tetromino)\b", text):
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
                title_hint=title_hint or "Block Matrix",
            )

        is_roll_and_move = bool(re.search(r"\b(snakes?\s*(?:and|&)\s*ladders?|chutes\s*(?:and|&)\s*ladders?|roll\s+and\s+move)\b", text))
        if re.search(r"\bsnake\b", text) and not is_roll_and_move and re.search(r"\b(grid|grow|apple|food|tail|arcade)\b", text):
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
                title_hint=title_hint or "Grid Trail",
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
                title_hint=title_hint or "Tactical Chess",
            )

        if re.search(r"\b(?:checkers|draughts)\b", text):
            matched.append("checkers")
            req.update({
                Capability.GRID_2D,
                Capability.TURN_BASED,
                Capability.BOARD_GAME,
                Capability.FIXED_CAMERA,
                Capability.PIECE_MOVEMENT,
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
                title_hint=title_hint or "Capture Checkers",
            )

        # 2. General Spatial & Gameplay Capability Decomposition
        is_top_down = bool(re.search(r"\b(?:top[\s\-]down|twin[\s\-]stick|isometric|overhead)\b", text))

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
        elif re.search(r"\b(?:fps|first[\s\-]person|shooter|gun|rifle|pistol|shotgun|blaster|railgun)\b", text):
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

        if re.search(r"\b(?:racing|car|vehicle|drive|driving|hoverbike|speedway|circuit|kart)\b", text):
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

        if re.search(r"\b(?:tower\s+defense|defend\s+the\s+(?:base|core|nexus|crystal)|lane\s+defense|turret\s+defense)\b", text):
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

        if re.search(r"\b(?:tic[\s\-]tac[\s\-]toe|connect\s+four|gomoku|board\s+game|roll\s+and\s+move|linear\s+board|dice\s+board(?:\s+game)?)\b", text):
            matched.append("board_game")
            if is_roll_and_move:
                matched.append("roll_and_move")
            elif re.search(r"\b(?:ludo|parcheesi)\b", text):
                matched.append("ludo")
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

        if re.search(r"\b(?:roguelike|roguelite|dungeon\s+crawler)\b", text):
            matched.append("roguelike")
            req.update({
                Capability.PHYSICS_CHARACTER,
                Capability.REAL_TIME,
                Capability.THIRD_PERSON,
                Capability.COMBAT,
                Capability.ENEMIES,
            })

        if re.search(r"\b(?:wave\s+survival|horde\s+survival|survival\s+arena|horde\s+mode)\b", text):
            matched.append("wave_survival")
            req.update({
                Capability.PHYSICS_CHARACTER,
                Capability.REAL_TIME,
                Capability.THIRD_PERSON,
                Capability.COMBAT,
                Capability.ENEMIES,
                Capability.WAVE_SPAWNER,
            })

        # Additional fine-grained capabilities requested in the prompt
        if re.search(r"\b(stealth|sneak|infiltrat|undetected|patrol(?:ling)?\s+guards?)\b", text):
            matched.append("stealth")
            req.add(Capability.STEALTH_AI)
        if re.search(r"\b(hack|terminal|console|switch|lever|relay|brazier|unlock)\b", text):
            matched.append("interactive_switches")
            req.add(Capability.INTERACTIVE_SWITCHES)
        if re.search(r"\b(oxygen|air\s+supply|radiation|heat|overheat|battery\s+drain)\b", text):
            matched.append("resource_drain")
            req.add(Capability.RESOURCE_DRAIN)

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

    def _synthesize_architecture_for_prompt(
        self,
        prompt: str,
        profile: CapabilityProfile,
        strategy: GenerationStrategy,
        template: Optional[TemplateDefinition],
    ) -> Dict[str, Any]:
        """Synthesize a rich, prompt-tailored C++ & UI architecture specification for any strategy."""
        from .prompt_analysis import analyze_prompt

        brief = analyze_prompt(prompt)
        title_pascal = _pascal_ident(brief.title or profile.title_hint or "DynamicGame")

        custom_caps: List[str] = []
        for m in brief.mechanics:
            if m not in custom_caps:
                custom_caps.append(m)
        if brief.double_jump and "double_jump" not in custom_caps:
            custom_caps.append("double_jump")
        if brief.sprint and "sprint_boost" not in custom_caps:
            custom_caps.append("sprint_boost")
        if brief.switches and "interactive_switches" not in custom_caps:
            custom_caps.append("interactive_switches")
        if brief.has_guards and "stealth_detection" not in custom_caps:
            custom_caps.append("stealth_detection")
        if brief.waves and "wave_progression" not in custom_caps:
            custom_caps.append("wave_progression")
        if brief.laps and "checkpoint_lap_tracker" not in custom_caps:
            custom_caps.append("checkpoint_lap_tracker")
        if brief.weapons and len(brief.weapons) > 1 and "multi_weapon_loadout" not in custom_caps:
            custom_caps.append("multi_weapon_loadout")

        mechanics_dict: Dict[str, Any] = {}
        if brief.weapons:
            mechanics_dict["weapons"] = list(brief.weapons)
        if brief.mechanics:
            mechanics_dict["active_mechanics"] = list(brief.mechanics)
        if brief.waves:
            mechanics_dict["wave_count"] = brief.waves
        if brief.laps:
            mechanics_dict["lap_count"] = brief.laps
            mechanics_dict["checkpoint_count"] = brief.checkpoints or 4
        if brief.survive_seconds:
            mechanics_dict["survive_seconds"] = brief.survive_seconds
        if brief.time_limit_seconds:
            mechanics_dict["time_limit_seconds"] = brief.time_limit_seconds
        if brief.score_target:
            mechanics_dict["score_target"] = brief.score_target
        if brief.enemies:
            mechanics_dict["primary_enemy"] = brief.enemies[0].label
        if brief.collectibles:
            mechanics_dict["primary_collectible"] = brief.collectibles[0].label
        if brief.switches:
            mechanics_dict["interactive_object"] = brief.switches[0].label

        # Determine plan_kind and target classes dynamically
        subtype = brief.game_subtype or ""
        if subtype in ("sudoku", "minesweeper") or (
            profile.detected_genre == Genre.PUZZLE and subtype not in ("tetris", "snake")
        ):
            plan_kind = "scratch_puzzle"
            mechanics_dict.setdefault("grid_size", 9)
            if subtype == "sudoku":
                mechanics_dict.setdefault("subgrid_size", 3)
        elif subtype in ("chess", "checkers"):
            plan_kind = "scratch_board"
            mechanics_dict.setdefault("grid_size", 8)
        elif subtype == "tetris":
            plan_kind = "scratch_falling_blocks"
            mechanics_dict.setdefault("grid_size", 10)
        elif subtype == "snake":
            plan_kind = "scratch_snake"
            mechanics_dict.setdefault("grid_size", 15)
        elif subtype in ("roll_and_move", "ludo"):
            plan_kind = "scratch_board"
            mechanics_dict.setdefault("grid_size", 10 if subtype == "roll_and_move" else 15)
            mechanics_dict.setdefault("dice_sides", 6)
        elif subtype == "racing" or "racing" in profile.keywords_matched:
            plan_kind = "scratch_racing"
            mechanics_dict.setdefault("lap_count", brief.laps or 3)
            mechanics_dict.setdefault("checkpoint_count", brief.checkpoints or 4)
        elif subtype == "tower_defense" or "tower_defense" in profile.keywords_matched:
            plan_kind = "scratch_tower_defense"
            mechanics_dict.setdefault("starting_gold", 250)
            mechanics_dict.setdefault("base_health", 100.0)
        elif subtype == "roguelike" or "roguelike" in profile.keywords_matched:
            plan_kind = "scratch_roguelike"
            mechanics_dict.setdefault("room_count", 6)
            mechanics_dict.setdefault("has_boss", True)
        elif strategy == GenerationStrategy.HYBRID:
            plan_kind = f"hybrid_{profile.detected_genre.value}"
        elif strategy == GenerationStrategy.ADAPT_TEMPLATE:
            plan_kind = f"extended_{template.id if template else profile.detected_genre.value}"
        else:
            plan_kind = f"scratch_{profile.detected_genre.value}"

        target_classes = [
            f"A{title_pascal}GameMode",
            f"U{title_pascal}GameplayRule",
            f"A{title_pascal}PlayerController",
        ]
        if profile.detected_genre == Genre.PUZZLE or subtype in ("sudoku", "tetris", "minesweeper", "puzzle", "scratch_puzzle"):
            target_classes.append("UGridPuzzleSubsystem")
        elif profile.detected_genre == Genre.GRID_BOARD or brief.is_board_like or subtype in ("chess", "checkers", "board", "roll_and_move", "scratch_board"):
            target_classes.append("UBoardGameSubsystem")
        elif brief.laps or subtype == "racing":
            target_classes.append("URacingCircuitSubsystem")
        elif brief.has_guards or "stealth" in custom_caps or "stealth_detection" in custom_caps:
            target_classes.append("UStealthInfiltrationSubsystem")
        elif brief.weapons or "multi_weapon_loadout" in custom_caps:
            target_classes.append("UWeaponInventorySubsystem")
        elif "bomb_site" in custom_caps or "defuse_bomb" in custom_caps or subtype == "tactical_fps":
            target_classes.append("UTacticalBombObjectiveSubsystem")
        elif brief.enemies:
            target_classes.append("UArenaCombatSubsystem")
        elif brief.switches:
            target_classes.append("UObjectiveInteractionSubsystem")
        elif "quest" in custom_caps or brief.has_npc:
            target_classes.append("UQuestProgressionSubsystem")

        target_widgets = [
            f"W{title_pascal}HUD",
            f"W{title_pascal}ObjectiveTracker",
        ]
        if profile.detected_genre in (Genre.PUZZLE, Genre.GRID_BOARD) or brief.is_board_like:
            target_widgets.append(f"W{title_pascal}Grid")
        source_files = [
            f"Source/{title_pascal}/{title_pascal}GameMode.h",
            f"Source/{title_pascal}/{title_pascal}GameMode.cpp",
            f"Source/{title_pascal}/{title_pascal}GameplayRule.h",
            f"Source/{title_pascal}/{title_pascal}GameplayRule.cpp",
        ]

        method_str = {
            GenerationStrategy.ADAPT_TEMPLATE: "template_adaptation",
            GenerationStrategy.HYBRID: "hybrid_generation",
            GenerationStrategy.SCRATCH: "scratch_generation",
        }[strategy]

        arch: Dict[str, Any] = {
            "method": method_str,
            "plan_kind": plan_kind,
            "genre": brief.genre or profile.detected_genre,
            "camera": brief.camera or (template.camera if template else CameraKind.THIRD_PERSON),
            "target_classes": target_classes,
            "target_widgets": target_widgets,
            "source_files": source_files,
            "custom_capabilities": custom_caps,
            "mechanics": mechanics_dict,
        }
        if template is not None:
            arch["template_id"] = template.id
            arch["base_template_id"] = template.id
            arch["preset_key"] = template.preset_key
        return arch

    def evaluate_strategy(self, prompt: str) -> StrategyDecision:
        profile = self.analyze_prompt(prompt)
        evaluations: List[CandidateEvaluation] = []

        for tmpl in self.templates:
            conflict_reasons: List[str] = []

            conflicts_in_template = tmpl.capabilities & profile.forbidden_capabilities
            if conflicts_in_template:
                conflict_reasons.append(
                    f"Template '{tmpl.title}' includes forbidden capabilities: {sorted(conflicts_in_template)}"
                )

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

        evaluations.sort(key=lambda e: e.overlap_score, reverse=True)
        best = evaluations[0] if evaluations else None
        reasons: List[str] = []

        if best and not best.has_conflict and best.overlap_score >= 0.80:
            strategy = GenerationStrategy.ADAPT_TEMPLATE
            reasons.append(
                f"Selected '{best.template.title}' (Approach A: Extend & Adapt Template) with "
                f"{int(best.overlap_score * 100)}% capability overlap and zero conflicts."
            )
            suggested_arch = self._synthesize_architecture_for_prompt(prompt, profile, strategy, best.template)
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
                f"{int(best.overlap_score * 100)}% capability overlap. Synthesizing custom subsystems for: "
                f"{sorted(best.missing_capabilities)}."
            )
            suggested_arch = self._synthesize_architecture_for_prompt(prompt, profile, strategy, best.template)
            for cap in sorted(best.missing_capabilities):
                if cap not in suggested_arch["custom_capabilities"]:
                    suggested_arch["custom_capabilities"].append(cap)
            return StrategyDecision(
                strategy=strategy,
                template=best.template,
                suitability_score=best.overlap_score,
                profile=profile,
                reasons=reasons,
                evaluations=evaluations,
                suggested_architecture=suggested_arch,
            )

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

        suggested_arch = self._synthesize_architecture_for_prompt(prompt, profile, strategy, None)

        return StrategyDecision(
            strategy=strategy,
            template=None,
            suitability_score=0.0,
            profile=profile,
            reasons=reasons,
            evaluations=evaluations,
            suggested_architecture=suggested_arch,
        )

    def _synthesize_scratch_architecture(self, profile: CapabilityProfile) -> Dict[str, Any]:
        """Synthesize a dedicated scratch architecture from a CapabilityProfile."""
        title = profile.title_hint or ""
        if profile.keywords_matched:
            title = profile.keywords_matched[0]
        arch = self._synthesize_architecture_for_prompt(title, profile, GenerationStrategy.SCRATCH, None)
        if "racing" in profile.keywords_matched or "racing" in title.lower():
            arch["plan_kind"] = "scratch_racing"
            arch["target_classes"] = ["ARaceGameMode", "URaceGameplayRule", "ARacePlayerController", "URaceLapTracker"]
        elif "tower_defense" in profile.keywords_matched or "tower" in title.lower():
            arch["plan_kind"] = "scratch_tower_defense"
            arch["target_classes"] = ["ATowerDefenseGameMode", "UTowerDefenseGameplayRule", "ATowerDefensePlayerController", "UTowerPlacementManager"]
        elif "roguelike" in profile.keywords_matched or "roguelike" in title.lower():
            arch["plan_kind"] = "scratch_roguelike"
            arch["target_classes"] = ["ARoguelikeGameMode", "URoguelikeGameplayRule", "ARoguelikePlayerController", "URoomGenerator"]
        elif "wave_survival" in profile.keywords_matched or "survival" in title.lower() or "horde" in title.lower():
            arch["plan_kind"] = "scratch_wave_survival"
            arch["target_classes"] = ["AWaveSurvivalGameMode", "UWaveSurvivalGameplayRule", "AWaveSurvivalPlayerController", "AWaveSpawner"]
        elif "stealth" in profile.keywords_matched or "stealth" in title.lower() or "heist" in title.lower():
            arch["plan_kind"] = "scratch_stealth"
            arch["target_classes"] = ["AStealthGameMode", "UStealthGameplayRule", "AStealthPlayerController", "UStealthInfiltrationSubsystem"]
        return arch

    def evaluate_strategy_with_model(
        self,
        prompt: str,
        complete_json: Optional[CompleteJson] = None,
        model: Optional[str] = None,
    ) -> StrategyDecision:
        """Use LLM to evaluate the generation strategy and enrich with deterministic architecture synthesis."""
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
                "Evaluate the user's natural-language game request and choose the optimal implementation strategy.\n\n"
                "AVAILABLE ENGINE FOUNDATIONS:\n"
                f"{templates_summary}\n\n"
                "STRATEGY DEFINITIONS:\n"
                "1. 'adapt_template': A foundation matches the spatial/camera mode (>=80% overlap) and will be extended with custom rules, entities, and C++ subsystems.\n"
                "2. 'hybrid': A foundation provides base movement/camera (40-79% overlap) and is combined with custom C++ subsystems for novel mechanics.\n"
                "3. 'scratch': None of the foundations match (e.g., constraint puzzles, tactical chess/checkers, falling blocks, racing circuits, tower defense).\n\n"
                "CRITICAL ARCHITECTURAL CONSTRAINTS:\n"
                "- NEVER adapt a 3D platformer or combat shooter for a discrete board game or logic puzzle.\n"
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
                                "verification": {"type": "string"},
                            },
                            "required": ["title", "description", "target_files", "verification"],
                        },
                    },
                },
                "required": ["strategy", "reasoning"],
            }
            try:
                raw = complete_json(system, prompt, schema)
                if raw:
                    text = str(raw).strip()
                    if text.startswith("```"):
                        text = text.strip("`")
                        text = text[4:] if text.lower().startswith("json") else text
                    start, end = text.find("{"), text.rfind("}")
                    data = json.loads(text[start:end + 1] if start >= 0 and end > start else text)
                    strat_str = str(data.get("strategy", "") or "").lower() if isinstance(data, dict) else ""
                    if not strat_str and isinstance(data, dict):
                        det_decision = self.evaluate_strategy(prompt)
                        if "title" in data and "genre" in data and ("win" in data or "entities" in data):
                            det_decision.draft_preloaded = data
                        return det_decision
                    if strat_str in ("adapt_template", "hybrid", "scratch"):
                        strategy = GenerationStrategy(strat_str)
                        tmpl_id = data.get("template_id")
                        tmpl = next((t for t in self.templates if t.id == tmpl_id), None)
                        profile = self.analyze_prompt(prompt)
                        if strategy in (GenerationStrategy.ADAPT_TEMPLATE, GenerationStrategy.HYBRID):
                            if tmpl is None:
                                raise ValueError(f"LLM selected unknown template_id: {tmpl_id!r}")
                            if (tmpl.capabilities & profile.forbidden_capabilities) or (
                                tmpl.forbidden_capabilities & profile.required_capabilities
                            ):
                                raise ValueError(
                                    f"LLM selected incompatible template {tmpl.id!r} for the request."
                                )
                        if data.get("genre"):
                            try:
                                profile.detected_genre = Genre(data["genre"])
                            except Exception:
                                pass
                        suggested_arch = self._synthesize_architecture_for_prompt(prompt, profile, strategy, tmpl)
                        suggested_arch["method"] = f"llm_{strat_str}"
                        if data.get("target_classes"):
                            suggested_arch["target_classes"] = data["target_classes"]
                        if isinstance(data.get("custom_mechanics"), dict):
                            suggested_arch["mechanics"] = {**suggested_arch.get("mechanics", {}), **data["custom_mechanics"]}
                        if data.get("plan_steps"):
                            suggested_arch["llm_plan_steps"] = data["plan_steps"]

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


default_registry = SemanticTemplateRegistry()

__all__ = [
    "CANONICAL_TEMPLATES",
    "CandidateEvaluation",
    "Capability",
    "CapabilityProfile",
    "GenerationStrategy",
    "SemanticTemplateRegistry",
    "StrategyDecision",
    "TemplateDefinition",
    "default_registry",
]
