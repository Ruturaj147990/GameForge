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
from .gds import CameraKind, EntityKind, GameDesignSpec, Genre
from .prompt_analysis import PromptBrief, analyze_prompt, brief_for_model, brief_to_draft, reconcile_draft
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

DRAFT_SYSTEM_PROMPT = """You are a senior game designer. Turn the user's game idea into ONE JSON object that matches the given schema
exactly. The game is built automatically from your JSON, so everything the user asked for must be in it.

Fidelity rules (most important):
- Keep every concrete detail from the prompt: the setting, the named enemies, the named collectibles, hazards, counts,
  time limits, lives, score targets and the stated camera. Never replace them with generic defaults.
- Put the user's own name for each thing in the entity "note" (e.g. "Zombie", "Golden Relic", "Lava pool") and add a
  tag "label:<Name>"; optionally a tag "color:#RRGGBB" that fits it (zombies green, lava orange, gems cyan).
- Use the counts the user gave. If none is given choose fun counts: pickups 6-12, enemies 4-10, hazards 2-5.
- title: the name the user gave, otherwise a short evocative title built from the prompt (not "Custom Game").
- pitch: one sentence describing the game in the user's words.

Genre guidance:
- grid_board: board games on a grid - tic-tac-toe, chess, checkers, connect four, gomoku, snakes and ladders.
- platformer: jumping across platforms / obstacle courses / parkour (camera third_person or side_scroller).
- arena_combat: fighting enemies or waves in an arena; survival against hordes.
- top_down_shooter: shooting enemies from a top-down view.
- card_battler: card / deck games.
- exploration: open areas to explore, find things, discover landmarks.
- dungeon_crawler: rooms and corridors, dungeons, heists, stealth inside buildings.
- action_adventure: quests with NPCs.
- puzzle: logic puzzles.
- custom: only when nothing above fits.

Entities (kind values): player, pickup, checkpoint, goal, hazard, enemy, ranged_enemy, spawner, guard, npc, door,
switch, moving_platform, landmark, prop. Counts 1-50. Enemies that shoot, cast or throw are ranged_enemy.
Include a spawner (props: wave_count, enemies_per_wave) for wave/horde games.

win: 1-3 of collect_all, reach_goal, defeat_all, survive_seconds (set "seconds"), score_at_least (set "target"),
board_win, match_win. Any listed condition wins, so "collect everything and then reach the exit" is collect_all +
reach_goal (the exit is locked until everything is collected).
lose: health_zero, timer_runs_out (set "seconds"), fall_off, caught_by_guard, board_loss, match_loss; [] if the player
cannot lose.
custom_rules: at most 3 short player-facing briefing sentences for flavour the lists cannot express. Usually [].
questions: [] unless the idea is truly impossible to interpret.
Output JSON only - no markdown, no comments."""

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
            _mark_preset(gds, explicit_preset_id, prompt)
            return PromptToGdsResult(status="OK", gds=gds, path="preset")
        except Exception as exc:
            logger.exception("Explicit preset %s failed", explicit_preset_id)
            return PromptToGdsResult(
                status="ERROR",
                path="none",
                errors=[f"Explicit preset {explicit_preset_id!r} failed: {exc}"],
            )

    brief = analyze_prompt(prompt)
    have_model = bool(allow_model and complete_json is not None)

    # 1. Preset fast path: only for plain requests ("make tic-tac-toe", "an arena game") that state nothing the preset
    #    would throw away. A prompt with a setting, named enemies/collectibles, hazards or numbers used to be collapsed
    #    into the bare preset ("arena game on a volcano with demons" -> grey Arena Combat with generic enemies).
    best_preset = _match_preset_keyword(prompt)
    if best_preset is not None and _brief_is_plain(brief, best_preset):
        overrides = extract_preset_overrides(best_preset, prompt)
        title = overrides.pop("title", None)
        try:
            gds = PRESETS[best_preset](title=title, **overrides)
            _mark_preset(gds, best_preset, prompt)
            return PromptToGdsResult(status="OK", gds=gds, path="preset")
        except Exception as exc:
            logger.warning("Preset creation failed for %s: %s", best_preset, exc)

    # 2. Strategy evaluation (uses model evaluation when callback is available)
    if have_model:
        decision = default_registry.evaluate_strategy_with_model(
            prompt, complete_json=complete_json, model=model
        )
    else:
        decision = default_registry.evaluate_strategy(prompt)

    facts = brief_for_model(brief)

    # 3. Scratch generation path: discrete logic puzzles and custom games with a dedicated architecture.
    #    A model sometimes labels ordinary action games "scratch"; the scratch prompt forbids action mechanics, so
    #    only board/puzzle-like requests take this path.
    scratch_ok = decision.strategy == GenerationStrategy.SCRATCH and (
        brief.is_board_like
        or decision.profile.detected_genre in (Genre.GRID_BOARD, Genre.PUZZLE, Genre.CARD_BATTLER)
        or any(k in decision.profile.keywords_matched for k in ("sudoku", "chess", "tetris", "snake", "racing"))
    )
    if scratch_ok:
        deterministic_supported = any(
            k in decision.profile.keywords_matched
            for k in ("sudoku", "chess", "tetris", "snake")
        ) or decision.profile.title_hint in ("Sudoku", "Chess", "Tetris", "Snake")
        if have_model:
            scratch_system_prompt = (
                f"{DRAFT_SYSTEM_PROMPT}\n\n"
                f"Architecture Strategy: SCRATCH GENERATION ({decision.profile.detected_genre.value})\n"
                f"Target Classes: {', '.join(decision.suggested_architecture.get('target_classes', []))}\n"
                f"DO NOT adapt platformer or shooter mechanics. Generate clean puzzle/board logic."
                + (f"\n\n{facts}" if facts else "")
            )
            preloaded = getattr(decision, "draft_preloaded", None)
            draft, attempts, errs = _draft_with_repair(complete_json, scratch_system_prompt, prompt, preloaded)
            if draft is not None:
                try:
                    if draft.architecture is None:
                        draft = draft.model_copy(update={"architecture": decision.suggested_architecture})
                    gds = expand_draft(draft, source_prompt=prompt)
                    gds.meta.generator = _model_generator(model)
                    return PromptToGdsResult(status="OK", gds=gds, path="model", model=model, attempts=attempts, errors=errs)
                except Exception as exc:
                    errs.append(f"Scratch draft expansion failed: {exc}")
            logger.info("Scratch model draft unusable (%s); using deterministic fallback", errs[-1:] or "no output")
        if deterministic_supported:
            gds = _build_scratch_gds(prompt, decision)
            return PromptToGdsResult(
                status="OK", gds=gds, path="preset", model=None, attempts=1 if have_model else 0,
                errors=(["The model did not return a valid scratch-game design; a deterministic game-specific "
                         "fallback was used."] if have_model else []),
            )
        # No dedicated deterministic architecture: build the closest playable game from the prompt's facts.
        return _offline_result(prompt, brief, model, note="no dedicated architecture for this game type; built the "
                                                         "closest playable design from the prompt")

    # 4. Model path for Template Adaptation or Hybrid
    if have_model:
        system_prompt = DRAFT_SYSTEM_PROMPT + (f"\n\n{facts}" if facts else "")
        preloaded = getattr(decision, "draft_preloaded", None)
        draft, attempts, errors = _draft_with_repair(complete_json, system_prompt, prompt, preloaded)

        if draft is not None:
            draft, fixes = reconcile_draft(draft, brief)
            if fixes:
                logger.info("Draft reconciled with prompt facts: %s", "; ".join(fixes))
            try:
                gds = expand_draft(draft, source_prompt=prompt)
                gds.meta.generator = _model_generator(model)
            except Exception as exc:
                errors.append(f"Draft expansion failed: {exc}")
                # The model draft could not be expanded; the prompt's own facts still make a playable game.
                return _offline_result(prompt, brief, model, errors=errors,
                                       note="model draft could not be expanded; built from the prompt's facts")

            model_questions = [q for q in (getattr(draft, "questions", None) or []) if q]
            stated_facts = [ln for ln in brief.summary_lines() if not ln.startswith(("title:", "genre:"))]
            if model_questions and not stated_facts:
                return PromptToGdsResult(
                    status="NEEDS_INPUT", gds=gds, questions=model_questions, path="model", model=model,
                    attempts=attempts, errors=errors,
                )
            return PromptToGdsResult(status="OK", gds=gds, path="model", model=model, attempts=attempts,
                                     errors=errors + [f"reconciled: {f}" for f in fixes])

        # Model output unusable after the repair round-trip: fall back to the deterministic brief instead of
        # asking the user to pick a preset.
        return _offline_result(prompt, brief, model, errors=errors,
                               note="model output was invalid; built from the prompt's facts")

    # 5. No model available: deterministic design from the prompt's facts.
    return _offline_result(prompt, brief, model)


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────────────────

_BOARD_PRESETS = {"tic_tac_toe", "connect_four", "gomoku", "card_battler"}


def _is_board_preset(preset_id: str) -> bool:
    return preset_id in _BOARD_PRESETS


def _match_preset_keyword(prompt: str) -> Optional[str]:
    """Longest preset keyword matched on word boundaries (substring matching used to hijack prompts: "arena" inside
    "an arena-like volcano level", "board" inside "skateboard")."""
    text = " " + prompt.lower().replace("’", "'") + " "
    best, best_len = None, 0
    for preset_id, kws in PRESET_KEYWORDS.items():
        for kw in kws:
            if re.search(rf"(?<![\w-]){re.escape(kw)}(?![\w-])", text) and len(kw) > best_len:
                best, best_len = preset_id, len(kw)
    return best if best in PRESETS else None


def _brief_is_plain(brief: PromptBrief, preset_id: str) -> bool:
    """True when the prompt states nothing beyond what the preset already builds."""
    text = brief.prompt.lower()
    words = set(re.findall(r"\b[a-z0-9_-]+\b", text))
    for kw in PRESET_KEYWORDS.get(preset_id, []):
        if kw in text:
            words -= set(re.findall(r"\b[a-z0-9_-]+\b", kw))
    if words & CUSTOM_DETAIL_KEYWORDS:
        return False
    if _is_board_preset(preset_id):
        return True   # board/card presets carry their own rules; extra flavour text cannot be honoured anyway
    named_enemies = [e for e in brief.enemies if e.label not in ("Enemy", "Foe", "Minion")]
    named_items = [c for c in brief.collectibles if c.label not in ("Pickup", "Collectible", "Item", "Coin")]
    return not (named_enemies or named_items or brief.hazards or brief.theme or brief.has_guards or brief.has_npc
                or brief.survive_seconds or brief.time_limit_seconds or brief.score_target or brief.lives
                or brief.double_jump or (brief.camera_explicit and preset_id not in ("top_down_shooter",)))


def _mark_preset(gds: GameDesignSpec, preset_id: str, prompt: str) -> None:
    """Presets are the only designs the legacy recipe builders reproduce faithfully; mark them so routing knows."""
    try:
        gds.meta.generator = f"preset:{preset_id}"
        if prompt and not gds.meta.source_prompt:
            gds.meta.source_prompt = prompt[:4000]
    except Exception:
        pass


def _model_generator(model: Optional[str]) -> str:
    tag = re.sub(r"[^\w.:\-/]", "_", model or "unknown")[:80] or "unknown"
    return f"model:{tag}"


def _draft_with_repair(
    complete_json: CompleteJson, system_prompt: str, prompt: str, preloaded: Optional[Dict[str, Any]],
) -> "tuple[Optional[DesignDraft], int, List[str]]":
    """One model call plus exactly one repair round-trip. Returns (draft or None, attempts, errors)."""
    schema = DesignDraft.model_json_schema()
    errors: List[str] = []
    attempts = 1
    raw_json = json.dumps(preloaded) if preloaded is not None else complete_json(system_prompt, prompt, schema)
    if raw_json is None:
        return None, attempts, ["Initial model call failed (transport error or no response)"]
    try:
        data = preloaded if preloaded is not None else _loads_lenient(raw_json)
        if not isinstance(data, dict):
            raise ValueError(f"Output is not a JSON object (got {type(data).__name__})")
        return DesignDraft.model_validate(_coerce_draft(data)), attempts, errors
    except Exception as exc:
        err_str = str(exc)
        errors.append(f"Attempt 1 validation error: {err_str[:500]}")
    attempts += 1
    repair_prompt = (
        f"{prompt}\n\nPrevious output:\n{str(raw_json)[:6000]}\n\n"
        f"Validation errors:\n{err_str[:1500]}\n\n"
        "Fix the errors above and return only the corrected JSON object matching the schema."
    )
    repair_raw = complete_json(system_prompt, repair_prompt, schema)
    if repair_raw is None:
        errors.append("Repair call failed (transport error or no response)")
        return None, attempts, errors
    try:
        data2 = _loads_lenient(repair_raw)
        if not isinstance(data2, dict):
            raise ValueError(f"Repaired output is not a JSON object (got {type(data2).__name__})")
        return DesignDraft.model_validate(_coerce_draft(data2)), attempts, errors
    except Exception as exc2:
        errors.append(f"Attempt 2 validation error: {str(exc2)[:500]}")
        return None, attempts, errors


def _loads_lenient(raw: str) -> Any:
    """json.loads that tolerates markdown fences and prose around the object (common with small local models)."""
    try:
        return json.loads(raw)
    except Exception:
        pass
    text = str(raw).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    return json.loads(text)


_VALID_WINS = {"collect_all", "reach_goal", "defeat_all", "survive_seconds", "score_at_least", "board_win", "match_win"}
_VALID_LOSES = {"health_zero", "timer_runs_out", "fall_off", "board_loss", "match_loss", "caught_by_guard"}
_KIND_SYNONYMS = {
    "coin": "pickup", "collectible": "pickup", "item": "pickup", "gem": "pickup", "relic": "pickup", "key": "pickup",
    "monster": "enemy", "zombie": "enemy", "melee_enemy": "enemy", "boss": "enemy", "archer": "ranged_enemy",
    "shooter": "ranged_enemy", "turret": "ranged_enemy", "trap": "hazard", "spike": "hazard", "lava": "hazard",
    "exit": "goal", "portal": "goal", "flag": "goal", "finish": "goal", "villager": "npc", "quest_giver": "npc",
    "platform": "moving_platform", "wave_spawner": "spawner", "enemy_spawner": "spawner", "lever": "switch",
    "button": "switch", "gate": "door", "statue": "landmark", "tower": "landmark", "decoration": "prop",
}


def _coerce_draft(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalises the most common small-model schema slips before validation (they used to burn the one repair
    attempt): extra keys, entity kind synonyms, counts out of range, over-long strings, win/lose given as strings."""
    allowed = set(DesignDraft.model_fields)
    out = {k: v for k, v in data.items() if k in allowed}
    for key, limit in (("title", 60), ("pitch", 280)):
        if isinstance(out.get(key), str):
            out[key] = re.sub(r'["\\\r\n]+', " ", out[key]).strip()[:limit]
    ents = []
    for e in out.get("entities") or []:
        if not isinstance(e, dict):
            continue
        kind = str(e.get("kind", "")).strip().lower().replace("-", "_").replace(" ", "_")
        kind = _KIND_SYNONYMS.get(kind, _KIND_SYNONYMS.get(kind.rstrip("s"), kind))
        if kind not in {k.value for k in EntityKind}:
            continue
        try:
            count = int(e.get("count", 1) or 1)
        except (TypeError, ValueError):
            count = 1
        ents.append({
            "kind": kind, "count": max(1, min(50, count)),
            "note": str(e.get("note", "") or "")[:60],
            "props": e.get("props") if isinstance(e.get("props"), dict) else {},
            "tags": [str(t)[:40] for t in (e.get("tags") or []) if isinstance(t, (str, int, float))][:6],
        })
    out["entities"] = ents[:12]

    def _conds(items: Any, valid: set) -> List[Dict[str, Any]]:
        res = []
        for w in items or []:
            if isinstance(w, str):
                w = {"type": w}
            if not isinstance(w, dict):
                continue
            t = str(w.get("type", "")).strip().lower().replace("-", "_").replace(" ", "_")
            if t not in valid:
                continue
            item: Dict[str, Any] = {"type": t}
            for num_key, lo, hi in (("target", 0, 10000), ("seconds", 1, 3600)):
                if w.get(num_key) is not None:
                    try:
                        item[num_key] = max(lo, min(hi, int(float(w[num_key]))))
                    except (TypeError, ValueError):
                        pass
            if valid is _VALID_WINS and item.get("target") == 0:
                item.pop("target")
            res.append(item)
        return res[:3]

    out["win"] = _conds(out.get("win"), _VALID_WINS) or [{"type": "reach_goal"}]
    out["lose"] = _conds(out.get("lose"), _VALID_LOSES)
    for key in ("custom_rules", "questions"):
        if isinstance(out.get(key), list):
            out[key] = [str(x)[:200] for x in out[key] if x][:3]
    for key, allowed_vals, default in (("difficulty", ("easy", "normal", "hard"), "normal"),
                                       ("art_style", ("stylized", "realistic", "low_poly", "toon"), "stylized"),
                                       ("music_mood", ("none", "calm", "tense", "heroic", "playful"), "none"),
                                       ("level_size", ("small", "medium", "large"), "small")):
        if key in out and str(out[key]).lower() not in allowed_vals:
            out[key] = default
        elif key in out:
            out[key] = str(out[key]).lower()
    return out


def _offline_result(
    prompt: str, brief: PromptBrief, model: Optional[str], errors: Optional[List[str]] = None, note: Optional[str] = None,
) -> PromptToGdsResult:
    """Build the game from the deterministic prompt brief (no model involvement)."""
    errs = list(errors or [])
    try:
        draft = brief_to_draft(brief)
        gds = expand_draft(draft, source_prompt=prompt)
        gds.meta.generator = "fallback:prompt"
        if note:
            errs.append(note)
        if brief.unsupported:
            errs.append("not supported, approximated: " + "; ".join(brief.unsupported))
        return PromptToGdsResult(status="OK", gds=gds, path="preset", model=model, attempts=0, errors=errs)
    except Exception as exc:
        logger.exception("Offline prompt brief could not be expanded")
        errs.append(f"Offline design failed: {exc}")
        preset_list = ", ".join(PRESET_TITLES)
        return PromptToGdsResult(
            status="NEEDS_INPUT",
            questions=[f"Which kind of game is this closest to: {preset_list}?"],
            path="none", model=model, errors=errs,
        )
