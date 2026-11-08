"""Orchestrates natural-language prompt -> GameDesignSpec via presets or model draft (P1 WI-1.6)."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Callable, Dict, List, Literal, Optional, Set

from pydantic import ValidationError

from .spec_from_prompt import is_game_creation_request
from .draft import DesignDraft, DraftLose, DraftWin
from .expand import ExpandError, expand_draft
from .gds import CameraKind, GameDesignSpec, Genre
from .presets import PRESETS, PRESET_KEYWORDS, extract_preset_overrides
from .template_registry import (
    GenerationStrategy,
    SemanticTemplateRegistry,
    StrategyDecision,
    default_registry,
)

logger = logging.getLogger(__name__)

CompleteJson = Callable[[str, str, dict], Optional[str]]

CUSTOM_DETAIL_KEYWORDS: Set[str] = {
    "relic", "relics", "guard", "guards", "laser", "lasers", "plasma", "alien", "aliens",
    "robot", "robots", "invader", "invaders", "zombie", "zombies", "vampire", "vampires",
    "drone", "drones", "ship", "ships", "spaceship", "spaceships", "core", "energy",
    "temple", "altar", "cage", "cages", "villager", "villagers", "chalice", "island", "islands",
    "dungeon", "dungeons", "boss", "bosses", "skeleton", "skeletons", "portal", "portals",
    "terminal", "terminals", "hack", "hacking", "bomb", "bombs", "defuse", "defusing",
    "counter-strike", "counter strike", "terrorist", "terrorists", "ct", "t", "swat",
    "police", "gun", "guns", "rifle", "rifles", "pistol", "pistols", "sniper", "grenade",
    "knife", "knives", "stealth", "infiltrate", "infiltration", "magic", "spell", "spells", "potion",
    "quest", "dialogue", "npc", "npcs", "hermit", "cursed", "loot", "treasure",
    "escape", "facility", "burning", "arctic", "desert", "crystal", "crystals", "sail",
    "pirate", "monsters", "slaying", "asteroid", "meteor", "mars", "space", "cyber",
    "defending", "defend", "survive", "survival", "bullet", "shooting", "shooter",
    "spooky", "haunted", "mansion", "ninja", "cyberpunk", "neon", "volcano", "lava",
    "ice", "snow", "underwater", "aquatic", "ocean", "cosmic", "galaxy", "gothic",
    "western", "cowboy", "samurai", "wizard", "witch", "speedrun", "endless", "runner",
    "racing", "racer", "flight", "glider", "glide", "gliding", "gravity", "stealthy", "tactical", "castle",
    "knight", "dragon", "dwarf", "elf", "sci-fi", "scifi", "futuristic", "post-apocalyptic",
    "apocalypse", "glitch", "arcade", "horror", "creepy", "shadow",
    # Core gameplay mechanics
    "dash", "grapple", "grappling", "hookshot", "jetpack", "slide", "sliding",
    "walljump", "wall-jump", "climb", "climbing", "swim", "swimming", "fly", "flying",
    "sprint", "sprinting", "crouch", "crouching", "sneak", "sneaking",
    "shield", "shields", "mana", "stamina", "skill", "skills", "ability", "abilities",
    "perk", "perks", "talent", "talents", "combo", "parry", "parrying", "dodge", "dodging",
    "roll", "rolling", "block", "blocking", "bow", "arrow", "arrows", "quiver",
    "sword", "swords", "blade", "axe", "hammer", "spear", "dagger",
    "inventory", "craft", "crafting", "forge", "shop", "merchant", "upgrade", "upgrades",
    "xp", "experience", "minion", "minions", "trap", "traps", "hazard", "riddle",
    "checkpoint", "timer", "countdown", "permadeath", "rogue", "roguelike", "roguelite",
}

DRAFT_SYSTEM_PROMPT = """You turn a game idea into a JSON object that matches the given schema exactly.
Rules:
- Choose the closest genre and camera. Prefer simple, playable designs a small team could build in a day.
Genre guidance:
- grid_board: for board games played on a grid — tic-tac-toe, chess, checkers, snakes and ladders, monopoly, ludo, connect four, draughts
- platformer: for 3D/2D obstacle course games with jumping and running
- arena_combat: for wave-based combat arenas
- top_down_shooter: for top-down shooting games
- card_battler: for card/deck games
- exploration: for open-world exploration
- dungeon_crawler: for dungeon room exploration
- puzzle: for logic puzzle games
- custom: for everything else

- If the idea involves jumping across platforms, courses, or parkour (e.g. floating stone platforms, temple ruins course), ALWAYS use genre=platformer with camera=third_person or camera=first_person.
- For turn-based board games with dice, tokens, snakes/ladders, or grid tiles, ALWAYS use genre=grid_board with camera=fixed_board and players>=2.
- For first-person shooters or tactical combat, use camera=first_person with enemies, combat spawner, weapons, and clear win condition.

- entities: list what the player meets (pickups, enemies, guards, npcs, doors, hazards, checkpoints, goal). Counts must be small (1-20).
- win: 1-3 conditions the game can check (collect_all, reach_goal, defeat_all, survive_seconds, score_at_least, board_win, match_win).
- lose: conditions such as health_zero or timer_runs_out. Use [] if the player cannot lose.
- custom_rules: at most 3 short sentences for mechanics the lists above cannot express. Leave empty when possible.
- questions: only if the idea is ambiguous in a way that changes the game (max 3).
- title: short, no quotes. Output JSON only."""

PRESET_TITLES = [
    "Tic-Tac-Toe",
    "Connect Four",
    "Gomoku",
    "Snakes and Ladders",
    "3D Platformer",
    "Arena Combat",
    "Card Battler",
    "Procedural World",
    "Top-Down Shooter",
    "Relic Hunt",
]


@dataclass
class PromptToGdsResult:
    status: Literal["OK", "NEEDS_INPUT", "UNSUPPORTED", "ERROR"]
    gds: Optional[GameDesignSpec] = None
    questions: List[str] = field(default_factory=list)
    suggested_patches: List[Dict[str, Any]] = field(default_factory=list)
    path: Literal["preset", "model", "none"] = "none"
    model: Optional[str] = None
    attempts: int = 0
    errors: List[str] = field(default_factory=list)


def _build_scratch_gds(prompt: str, decision: StrategyDecision) -> GameDesignSpec:
    """Synthesizes a clean, tailored GameDesignSpec directly for scratch-generated games (e.g. Sudoku, Chess, Tetris, Snake)."""
    arch = decision.suggested_architecture
    profile = decision.profile
    title = profile.title_hint or (
        "Sudoku" if "sudoku" in profile.keywords_matched else
        "Chess" if "chess" in profile.keywords_matched else
        "Tetris" if "tetris" in profile.keywords_matched else
        "Snake" if "snake" in profile.keywords_matched else
        "Puzzle Game" if profile.detected_genre == Genre.PUZZLE else
        "Custom Game"
    )
    custom_rules = [
        f"Architecture: {arch.get('plan_kind', 'scratch')}",
        f"Target classes: {', '.join(arch.get('target_classes', [])[:4])}",
    ]
    if "mechanics" in arch and isinstance(arch["mechanics"], dict):
        for k, v in list(arch["mechanics"].items())[:2]:
            custom_rules.append(f"{k}: {v}")

    win_list = [DraftWin(type="board_win")]
    lose_list = []
    if arch.get("lose_condition"):
        lose_list = [DraftLose(type="timer_runs_out", seconds=300)]

    draft = DesignDraft(
        title=title,
        genre=arch.get("genre", Genre.PUZZLE),
        camera=arch.get("camera", CameraKind.FIXED_BOARD),
        pitch=prompt,
        entities=[],
        win=win_list,
        lose=lose_list,
        custom_rules=custom_rules[:3],
        architecture=arch,
    )
    gds = expand_draft(draft)
    gds.meta.generator = "fallback:scratch"
    return gds


def prompt_to_gds(
    prompt: str,
    complete_json: Optional[CompleteJson] = None,
    model: Optional[str] = None,
    allow_model: bool = True,
) -> PromptToGdsResult:
    """Orchestrates turning a prompt into a GameDesignSpec.

    1. Checks if prompt is a game creation request (otherwise UNSUPPORTED).
    2. Uses SemanticTemplateRegistry to evaluate strategy (Adapt Template, Hybrid, Scratch).
    3. For Scratch games (Sudoku, Chess, Tetris, Snake), constructs dedicated architecture
       and forbids incompatible templates (no falling cubes, no platformer obstacles).
    4. For Adapt Template, customizes template properties from the start via model or preset.
    5. Runs error repair and falls back safely without amnesia or hallucination.
    """
    if not is_game_creation_request(prompt):
        return PromptToGdsResult(
            status="UNSUPPORTED",
            errors=["Prompt is not a game creation request"],
            path="none",
        )

    # 0. Explicit preset selector: preset:<id>
    explicit_preset_id: Optional[str] = None
    match = re.match(
        r"^\s*preset\s*:\s*([a-z0-9_]+)(?:\s+.*)?$",
        prompt,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = match.group(1).lower()
        alias_map = {
            "3d_platformer": "platformer",
            "snakes_and_ladders": "snake_and_ladders",
            "grid_board_game": "tic_tac_toe",
            "card_game": "card_battler",
            "arena": "arena_combat",
        }
        candidate = alias_map.get(candidate, candidate)
        if candidate in PRESETS:
            explicit_preset_id = candidate

    if explicit_preset_id is not None:
        overrides = extract_preset_overrides(explicit_preset_id, prompt)
        title = overrides.pop("title", None)
        try:
            gds = PRESETS[explicit_preset_id](title=title, **overrides)
            return PromptToGdsResult(status="OK", gds=gds, path="preset")
        except Exception as exc:
            logger.exception("Explicit preset %s failed", explicit_preset_id)
            return PromptToGdsResult(
                status="ERROR",
                path="none",
                errors=[f"Explicit preset {explicit_preset_id!r} failed: {exc}"],
            )

    # 1. Preset / Fast Template path: keyword match (only for direct preset requests without custom narrative/mechanics)
    text = " " + prompt.lower().replace("’", "'").replace("'", "'") + " "
    words = set(re.findall(r"\b\w+\b", text))
    preset_words = {w for kws in PRESET_KEYWORDS.values() for kw in kws for w in kw.split()}
    stop_words = {
        "a", "an", "the", "in", "on", "at", "to", "for", "with", "and", "or", "of", "is", "are",
        "you", "where", "game", "make", "create", "build", "called", "named", "titled", "against",
        "friend", "ai", "easy", "medium", "hard", "vs", "versus", "i", "want", "please",
    }
    override_words = {
        "coin", "coins", "pickups", "pickup", "collectibles", "collectible", "gems", "gem",
        "points", "point", "stars", "star", "ring", "rings", "target", "targets", "waves",
        "wave", "health", "hp", "seed", "size", "board", "grid", "rows", "columns",
    }
    m_title = re.search(r'\b(?:called|named|titled)\s+["\']?([^"\',.!?\n]+)["\']?', prompt, re.I)
    title_words = set(re.findall(r"\b\w+\b", m_title.group(1).lower())) if m_title else set()

    custom_words = {
        w
        for w in (words - preset_words - stop_words - override_words - title_words)
        if not w.isdigit()
    }
    has_custom_detail = bool(words.intersection(CUSTOM_DETAIL_KEYWORDS)) or len(custom_words) >= 1

    best_preset: Optional[str] = None
    best_kw: str = ""
    if not (allow_model and complete_json is not None and has_custom_detail):
        for preset_id, kws in PRESET_KEYWORDS.items():
            for kw in kws:
                if kw in text and len(kw) > len(best_kw):
                    best_preset = preset_id
                    best_kw = kw

        if best_preset is not None and best_preset in PRESETS:
            overrides = extract_preset_overrides(best_preset, prompt)
            title = overrides.pop("title", None)
            try:
                gds = PRESETS[best_preset](title=title, **overrides)
                return PromptToGdsResult(
                    status="OK",
                    gds=gds,
                    path="preset",
                )
            except Exception as exc:
                logger.warning("Preset creation failed for %s: %s", best_preset, exc)

    # 2. Strategy evaluation (uses model evaluation when callback is available)
    if allow_model and complete_json is not None:
        decision = default_registry.evaluate_strategy_with_model(
            prompt, complete_json=complete_json, model=model
        )
    else:
        decision = default_registry.evaluate_strategy(prompt)

    # 3. Scratch generation path: discrete logic puzzles and custom games
    if decision.strategy == GenerationStrategy.SCRATCH:
        if allow_model and complete_json is not None:
            # Let the LLM design custom rules/draft from the start with scratch architecture guidance
            scratch_system_prompt = (
                f"{DRAFT_SYSTEM_PROMPT}\n\n"
                f"Architecture Strategy: SCRATCH GENERATION ({decision.profile.detected_genre.value})\n"
                f"Target Classes: {', '.join(decision.suggested_architecture.get('target_classes', []))}\n"
                f"DO NOT adapt platformer or shooter mechanics. Generate clean puzzle/board logic."
            )
            schema = DesignDraft.model_json_schema()
            data_scratch = getattr(decision, "draft_preloaded", None)
            if data_scratch is not None:
                raw_json = json.dumps(data_scratch)
            else:
                raw_json = complete_json(scratch_system_prompt, prompt, schema)
            if raw_json is not None:
                try:
                    data = data_scratch if data_scratch is not None else json.loads(raw_json)
                    if isinstance(data, dict):
                        draft = DesignDraft.model_validate(data)
                        gds = expand_draft(draft)
                        gds.meta.generator = f"model:{model}"
                        return PromptToGdsResult(status="OK", gds=gds, path="model", model=model, attempts=1)
                except Exception as exc:
                    logger.info("Scratch model draft failed validation; attempting one repair: %s", exc)
                    # One repair round-trip (same policy as the template path) before falling
                    # back to the deterministic scratch architecture.
                    if data_scratch is None:
                        repair_prompt = (
                            f"{prompt}\n\nPrevious output:\n{raw_json[:6000]}\n\n"
                            f"Validation errors:\n{str(exc)[:1500]}\n\n"
                            "Fix the errors and return only the corrected JSON object matching the schema."
                        )
                        try:
                            repair_raw = complete_json(scratch_system_prompt, repair_prompt, schema)
                            if repair_raw:
                                data2 = json.loads(repair_raw)
                                if isinstance(data2, dict):
                                    draft = DesignDraft.model_validate(data2)
                                    gds = expand_draft(draft)
                                    gds.meta.generator = f"model:{model}"
                                    return PromptToGdsResult(status="OK", gds=gds, path="model", model=model, attempts=2)
                        except Exception as exc2:
                            logger.info("Scratch draft repair failed, using deterministic scratch architecture: %s", exc2)

        # Verified scratch architecture synthesis fallback
        deterministic_supported = any(
            k in decision.profile.keywords_matched
            for k in ("sudoku", "chess", "tetris", "snake")
        ) or decision.profile.title_hint in ("Sudoku", "Chess", "Tetris", "Snake")
        if not deterministic_supported and not (allow_model and complete_json is not None):
            preset_list = ", ".join(PRESET_TITLES)
            return PromptToGdsResult(
                status="NEEDS_INPUT",
                questions=[f"Which kind of game is this closest to: {preset_list}?"],
                path="none",
                model=model,
                errors=["No model available to synthesize custom scratch architecture."],
            )

        gds = _build_scratch_gds(prompt, decision)
        fallback_errors = []
        if allow_model and complete_json is not None:
            fallback_errors.append(
                "The model did not return a valid scratch-game design; a deterministic "
                "game-specific fallback was used."
            )
        return PromptToGdsResult(
            status="OK",
            gds=gds,
            path="preset",
            model=None,
            attempts=1 if allow_model and complete_json is not None else 0,
            errors=fallback_errors,
        )

    # 4. Model path for Template Adaptation or Hybrid
    if allow_model and complete_json is not None:
        schema = DesignDraft.model_json_schema()
        attempts = 0
        errors: List[str] = []

        # Attempt 1
        attempts += 1
        draft: Optional[DesignDraft] = None
        data_init = getattr(decision, "draft_preloaded", None)
        if data_init is not None:
            raw_json = json.dumps(data_init)
        else:
            raw_json = complete_json(DRAFT_SYSTEM_PROMPT, prompt, schema)

        if raw_json is not None:
            try:
                data = data_init if data_init is not None else json.loads(raw_json)
                if isinstance(data, dict):
                    draft = DesignDraft.model_validate(data)
                else:
                    raise ValueError(f"Output is not a JSON object (got {type(data).__name__})")
            except Exception as exc:
                err_str = str(exc)
                errors.append(f"Attempt 1 validation error: {err_str}")

                # Repair attempt (exactly one repair call)
                attempts += 1
                repair_prompt = (
                    f"{prompt}\n\n"
                    f"Previous output:\n{raw_json}\n\n"
                    f"Validation errors:\n{err_str[:1500]}\n\n"
                    f"Please fix the errors above and return the corrected JSON object matching the schema only."
                )
                repair_raw = complete_json(DRAFT_SYSTEM_PROMPT, repair_prompt, schema)
                if repair_raw is not None:
                    try:
                        data2 = json.loads(repair_raw)
                        if isinstance(data2, dict):
                            draft = DesignDraft.model_validate(data2)
                        else:
                            raise ValueError(f"Repaired output is not a JSON object (got {type(data2).__name__})")
                    except Exception as exc2:
                        errors.append(f"Attempt 2 validation error: {exc2}")
                else:
                    errors.append("Repair call failed (transport error or no response)")
        else:
            errors.append("Initial model call failed (transport error or no response)")

        if draft is not None:
            try:
                gds = expand_draft(draft)
                gds.meta.generator = f"model:{model}"
            except Exception as exc:
                errors.append(f"Draft expansion failed: {exc}")
                return PromptToGdsResult(
                    status="NEEDS_INPUT",
                    questions=[f"Could not construct a valid game specification: {exc}. Please clarify the game rules."],
                    path="model",
                    model=model,
                    attempts=attempts,
                    errors=errors,
                )

            if draft.questions:
                return PromptToGdsResult(
                    status="NEEDS_INPUT",
                    gds=gds,
                    questions=list(draft.questions),
                    path="model",
                    model=model,
                    attempts=attempts,
                    errors=errors,
                )

            return PromptToGdsResult(
                status="OK",
                gds=gds,
                path="model",
                model=model,
                attempts=attempts,
                errors=errors,
            )

        # Still invalid after repair or transport failed
        if attempts > 1 or errors:
            return PromptToGdsResult(
                status="NEEDS_INPUT",
                questions=[
                    "Could not generate a valid game design from this prompt. "
                    "Could you clarify the genre, primary goal, and win condition?"
                ],
                path="model",
                model=model,
                attempts=attempts,
                errors=errors,
            )

    # 4. No model available
    preset_list = ", ".join(PRESET_TITLES)
    return PromptToGdsResult(
        status="NEEDS_INPUT",
        questions=[f"Which kind of game is this closest to: {preset_list}?"],
        path="none",
        model=model,
    )
