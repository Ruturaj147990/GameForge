"""Deterministic expansion of a DesignDraft into a full GameDesignSpec (P1 WI-1.4).

Binding modifiers use the syntax Key:modifier with modifiers negate, swizzle and swizzle_negate.
P5 maps them to UInputModifierNegate and UInputModifierSwizzleAxis(YXZ).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..pipeline.spec_from_prompt import _pascal
from .events_catalog import DEFAULT_MODULE, MODULE_EVENTS
from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .gds import (
    ArchitectureSpec,
    Acceptance,
    AddStat,
    AllOf,
    ArtDirection,
    AudioSpec,
    CameraKind,
    Condition,
    CountAtLeast,
    CustomCode,
    Effect,
    Message,
    EndGame,
    EntityKind,
    EntitySpec,
    EventOccurred,
    EventRef,
    FeedbackSpec,
    GameDesignSpec,
    Genre,
    Goals,
    HudElement,
    InputActionSpec,
    InputSpec,
    LayoutKind,
    LevelSpec,
    Meta,
    Overview,
    Placement,
    Progression,
    RuleSpec,
    ScenarioRef,
    Scene,
    ScoreSpec,
    StatCompare,
    TechSpec,
    TimerElapsed,
    UISpec,
    Vec2,
    Biome,
    IntroSpec,
    PresentationSpec,
)


class ExpandError(RuntimeError):
    """Raised when a draft cannot be deterministically expanded into a GameDesignSpec."""
    def __init__(self, message: str, question: Optional[str] = None):
        super().__init__(message)
        self.question = question


LEVEL_SIZES: Dict[str, Tuple[float, float]] = {
    "small": (60.0, 60.0),
    "medium": (150.0, 150.0),
    "large": (400.0, 400.0),
}

IA_MOVE = InputActionSpec(
    action_id="IA_Move",
    value_type="axis2d",
    bindings=["W", "S:negate", "A:swizzle_negate", "D:swizzle"],
    purpose="Move forward/backward and left/right",
)
IA_LOOK = InputActionSpec(
    action_id="IA_Look",
    value_type="axis2d",
    bindings=["Mouse2D"],
    purpose="Camera orientation",
)
IA_JUMP = InputActionSpec(
    action_id="IA_Jump",
    value_type="bool",
    bindings=["SpaceBar"],
    purpose="Jump",
)
IA_INTERACT = InputActionSpec(
    action_id="IA_Interact",
    value_type="bool",
    bindings=["E"],
    purpose="Interact with world object",
)
IA_ATTACK = InputActionSpec(
    action_id="IA_Attack",
    value_type="bool",
    bindings=["LeftMouseButton"],
    purpose="Primary attack",
)
IA_FIRE = InputActionSpec(
    action_id="IA_Fire",
    value_type="bool",
    bindings=["LeftMouseButton"],
    purpose="Fire projectile",
)
IA_SELECT = InputActionSpec(
    action_id="IA_Select",
    value_type="bool",
    bindings=["LeftMouseButton"],
    purpose="Select board tile or card",
)
IA_END_TURN = InputActionSpec(
    action_id="IA_EndTurn",
    value_type="bool",
    bindings=["E"],
    purpose="End player turn",
)
IA_RESTART = InputActionSpec(
    action_id="IA_Restart",
    value_type="bool",
    bindings=["R"],
    purpose="Restart session",
)


GENRE_TEMPLATES: Dict[Genre, Dict[str, Any]] = {
    Genre.GRID_BOARD: {
        "layout": LayoutKind.BOARD,
        "camera": CameraKind.FIXED_BOARD,
        "actions": [IA_SELECT],
        "always_entities": [(EntityKind.BOARD, 1, "board")],
    },
    Genre.PLATFORMER: {
        "layout": LayoutKind.COURSE,
        "camera": CameraKind.THIRD_PERSON,
        "actions": [IA_MOVE, IA_LOOK, IA_JUMP],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start")],
    },
    Genre.ARENA_COMBAT: {
        "layout": LayoutKind.ARENA,
        "camera": CameraKind.TOP_DOWN,
        "actions": [IA_MOVE, IA_LOOK, IA_ATTACK, IA_JUMP, IA_RESTART],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start"), (EntityKind.SPAWNER, 1, "scatter")],
    },
    Genre.CARD_BATTLER: {
        "layout": LayoutKind.LANES,
        "camera": CameraKind.FIXED_BOARD,
        "actions": [IA_SELECT, IA_END_TURN],
        "always_entities": [(EntityKind.CARD_TABLE, 1, "board")],
    },
    Genre.EXPLORATION: {
        "layout": LayoutKind.OPEN_WORLD,
        "camera": CameraKind.THIRD_PERSON,
        "actions": [IA_MOVE, IA_LOOK, IA_JUMP, IA_INTERACT],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start")],
    },
    Genre.ACTION_ADVENTURE: {
        "layout": LayoutKind.OPEN_WORLD,
        "camera": CameraKind.THIRD_PERSON,
        "actions": [IA_MOVE, IA_LOOK, IA_JUMP, IA_INTERACT],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start")],
    },
    Genre.TOP_DOWN_SHOOTER: {
        "layout": LayoutKind.ARENA,
        "camera": CameraKind.TOP_DOWN,
        "actions": [IA_MOVE, IA_LOOK, IA_FIRE, IA_JUMP],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start"), (EntityKind.SPAWNER, 1, "scatter")],
    },
    Genre.DUNGEON_CRAWLER: {
        "layout": LayoutKind.ROOMS,
        "camera": CameraKind.THIRD_PERSON,
        "actions": [IA_MOVE, IA_LOOK, IA_JUMP, IA_INTERACT, IA_ATTACK],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start")],
    },
    Genre.PUZZLE: {
        "layout": LayoutKind.BOARD,
        "camera": CameraKind.FIXED_BOARD,
        "actions": [IA_SELECT],
        "always_entities": [(EntityKind.BOARD, 1, "board")],
    },
    Genre.CUSTOM: {
        "layout": LayoutKind.ARENA,
        "camera": CameraKind.THIRD_PERSON,
        "actions": [IA_MOVE, IA_LOOK, IA_JUMP, IA_INTERACT],
        "always_entities": [(EntityKind.PLAYER, 1, "player_start")],
    },
}

FEEDBACK_CATALOG = [
    ("pickup.collected", "vfx.sparkle_burst", "sfx.pickup_chime"),
    ("player.damaged", "vfx.hit_flash", "sfx.impact"),
    ("enemy.killed", "vfx.poof", "sfx.defeat"),
    ("game.won", "vfx.confetti", "sfx.fanfare"),
    ("checkpoint.reached", "vfx.ring", "sfx.chime_low"),
]

KIT_DEFAULT_PROPS: Dict[EntityKind, Dict[str, Any]] = {
    EntityKind.PLAYER: {
        "move_speed": 600.0,
        "jump_velocity": 600.0,
        "max_health": 100.0,
        "attack_mode": "melee",
    },
    EntityKind.PICKUP: {
        "value": 1,
        "respawns": False,
        "respawn_seconds": 10.0,
    },
    EntityKind.CHECKPOINT: {
        "activate_once": True,
    },
    EntityKind.GOAL: {
        "required_value": 0.0,
    },
    EntityKind.HAZARD: {
        "damage_per_second": 20.0,
        "instant_kill": False,
        "shape_extent": 100.0,
    },
    EntityKind.ENEMY: {
        "attack_damage": 15.0,
        "attack_range": 180.0,
        "attack_cooldown": 1.0,
        "move_speed": 350.0,
        "aggro_range": 800.0,
        "max_health": 50.0,
    },
    EntityKind.RANGED_ENEMY: {
        "attack_damage": 10.0,
        "attack_range": 900.0,
        "attack_cooldown": 1.5,
        "move_speed": 280.0,
        "aggro_range": 1200.0,
        "projectile_speed": 1500.0,
        "max_health": 35.0,
    },
    EntityKind.SPAWNER: {
        "enemy_entity_id": "enemy",
        "wave_count": 3,
        "enemies_per_wave": 4,
        "seconds_between_waves": 5.0,
        "spawn_radius": 400.0,
    },
    EntityKind.GUARD: {
        "patrol_radius": 1000.0,
        "aggro_radius": 600.0,
        "move_speed": 300.0,
    },
    EntityKind.NPC: {
        "objective_id": "main_quest",
        "objective_title": "Main Quest",
        "objective_target": 1,
        "talk_on_overlap": True,
    },
    EntityKind.DOOR: {
        "required_value": 1.0,
        "open_seconds": 1.0,
    },
    EntityKind.SWITCH: {
        "target_tag": "",
        "toggle": True,
    },
    EntityKind.MOVING_PLATFORM: {
        "end_offset_z": 300.0,
        "seconds": 3.0,
        "pause_seconds": 1.0,
    },
    EntityKind.LANDMARK: {
        "discover_radius": 500.0,
    },
    EntityKind.PROP: {
        "mesh_path": "/Engine/BasicShapes/Cube.Cube",
        "scale_x": 1.0,
        "scale_y": 1.0,
        "scale_z": 1.0,
    },
    EntityKind.BOARD: {
        "board_size": 3,
        "win_length": 3,
        "gravity": False,
        "vs_ai": True,
        "ai_level": "random",
        "cell_size_cm": 120.0,
    },
    EntityKind.CARD_TABLE: {
        "deck_size": 20,
        "hand_size": 4,
        "energy_per_turn": 3,
    },
}

_CSG_PROP_RECIPES = {
    "crate", "barrel", "rock", "pillar", "fence",
    "tree", "stylized_tree", "bush", "torch", "chest", "altar",
}


def _extract_note_props(kind: EntityKind, note: str) -> Dict[str, Any]:
    """Parse custom user entity parameters and tags from draft entity note."""
    props: Dict[str, Any] = {}
    if not note:
        return props

    note_lower = note.lower()

    # CSG Procedural Prop Recipes
    for recipe in _CSG_PROP_RECIPES:
        if recipe in note_lower:
            props["recipe"] = "stylized_tree" if recipe == "tree" else recipe
            break

    # Parse key-value parameters: "speed: 400", "health: 120", "damage: 25"
    kv_matches = re.findall(r"([a-z_]+)\s*[:=]\s*(\d+(?:\.\d+)?)", note_lower)
    for k, v in kv_matches:
        num_val = float(v) if "." in v else int(v)
        if k in ("speed", "move_speed", "player_speed"):
            props["move_speed"] = float(num_val)
        elif k in ("health", "hp", "max_health", "player_max_health"):
            props["max_health"] = float(num_val)
        elif k in ("damage", "attack_damage"):
            props["attack_damage"] = float(num_val)
        elif k in ("value", "score", "points"):
            props["value"] = int(num_val)
        elif k in ("extent", "radius", "size"):
            props["shape_extent"] = float(num_val)

    return props


# GDS/legacy aliases -> canonical kit parameter names. Model drafts and presets use both spellings; the kit param
# models are extra="forbid", so an alias or an unknown key used to fail validation of the whole design.
PROP_ALIASES: Dict[str, str] = {
    "player_speed": "move_speed", "speed": "move_speed", "walk_speed": "move_speed",
    "player_max_health": "max_health", "health": "max_health", "hp": "max_health",
    "player_attack_damage": "attack_damage", "damage": "attack_damage",
    "player_attack_range": "attack_range", "range": "attack_range",
    "player_attack_cooldown": "attack_cooldown", "cooldown": "attack_cooldown",
    "jump": "jump_velocity", "jump_height": "jump_velocity",
    "enemy_count": "enemies_per_wave", "waves": "wave_count",
    "points": "value", "score": "value",
    "radius": "shape_extent", "size": "shape_extent", "extent": "shape_extent",
    "dps": "damage_per_second",
}

DIFFICULTY_SCALE = {"easy": 0.7, "normal": 1.0, "hard": 1.4}


def _field_bounds(field_info: Any) -> Tuple[Optional[float], Optional[float]]:
    lo = hi = None
    for meta in getattr(field_info, "metadata", []) or []:
        for attr, is_lo in (("ge", True), ("gt", True), ("le", False), ("lt", False)):
            val = getattr(meta, attr, None)
            if isinstance(val, (int, float)):
                if is_lo:
                    lo = float(val)
                else:
                    hi = float(val)
    return lo, hi


def sanitize_props(module_id: str, props: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Map aliases, drop keys the kit module does not accept and clamp numbers into the module's ranges.

    Returns (clean_props, notes). Never raises: a design should not fail because a model wrote ``"speed": 9000``.
    """
    notes: List[str] = []
    try:
        from ..kit.registry import KIT, _ensure_modules_loaded
        _ensure_modules_loaded()
        mod = KIT.get(module_id)
    except Exception:
        mod = None
    if mod is None:
        return dict(props), notes
    fields = mod.params_model.model_fields
    clean: Dict[str, Any] = {}
    for key, val in (props or {}).items():
        k = key if key in fields else PROP_ALIASES.get(key, key)
        if k not in fields:
            notes.append(f"{module_id}: dropped unsupported property {key!r}")
            continue
        if k in clean and key != k:
            continue  # canonical spelling wins over an alias
        lo, hi = _field_bounds(fields[k])
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            if isinstance(val, str) and lo is not None:
                try:
                    val = float(val)
                except ValueError:
                    notes.append(f"{module_id}: dropped non-numeric {key!r}")
                    continue
            else:
                clean[k] = val
                continue
        num = float(val)
        if lo is not None and num < lo:
            notes.append(f"{module_id}: {k} raised to {lo}")
            num = lo
        if hi is not None and num > hi:
            notes.append(f"{module_id}: {k} lowered to {hi}")
            num = hi
        ann = getattr(fields[k], "annotation", None)
        clean[k] = int(round(num)) if ann in (int, Optional[int]) or "int" in str(ann) and "float" not in str(ann) else num
    # Final guard: drop whatever the model still rejects.
    for _ in range(len(clean) + 1):
        try:
            mod.params_model.model_validate(clean)
            break
        except Exception as exc:
            errs = getattr(exc, "errors", lambda: [])()
            bad = {str(e.get("loc", [""])[0]) for e in errs if e.get("loc")}
            if not bad:
                clean = {}
                break
            for b in bad:
                clean.pop(b, None)
                notes.append(f"{module_id}: dropped invalid {b!r}")
    return clean, notes


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = fallback
    return slug[:30]


def _plural(word: str) -> str:
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _tag_value(tags: List[str], key: str) -> Optional[str]:
    for t in tags or []:
        if isinstance(t, str) and t.startswith(key + ":"):
            return t.split(":", 1)[1].strip() or None
    return None


def _hex_ok(code: Optional[str]) -> bool:
    return bool(code) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", code or ""))


def expand_draft(draft: DesignDraft, source_prompt: Optional[str] = None) -> GameDesignSpec:
    """Deterministically expand a DesignDraft into a validated GameDesignSpec.

    ``source_prompt`` is the user's full prompt (the draft pitch is capped at 280 characters); it is stored in
    ``meta.source_prompt`` and drives the art direction when the draft leaves it at defaults.
    """
    from ..kit.rules import get_layout_for_game_type, get_required_modules_for_game_type, GAME_TYPE_LAYOUT_MAP
    proj_name = _pascal(draft.title)
    tmpl = GENRE_TEMPLATES.get(draft.genre, GENRE_TEMPLATES[Genre.CUSTOM])
    layout = tmpl["layout"]

    # Check for specific game type hints to resolve authoritative layout
    pitch_title = f"{draft.title} {draft.pitch}".lower()
    game_type_hint = ""
    for gt in GAME_TYPE_LAYOUT_MAP:
        if gt in pitch_title or gt.replace("_", " ") in pitch_title:
            try:
                resolved_l = get_layout_for_game_type(gt)
                for lk in LayoutKind:
                    if lk.value == resolved_l:
                        layout = lk
                        game_type_hint = gt
                        break
                if game_type_hint:
                    break
            except KeyError:
                pass

    size_key = draft.level_size
    # Crowded designs get room to breathe: 30+ scattered things in a 60 m square overlapped and spawned in walls.
    if size_key == "small" and sum(de.count for de in draft.entities) > 30:
        size_key = "medium"
    size_w, size_h = LEVEL_SIZES.get(size_key, LEVEL_SIZES["small"])

    # Stable per-design seed: every game used to get seed 2026 and therefore the identical level layout.
    import hashlib
    seed = int(hashlib.sha256(f"{draft.title}|{source_prompt or draft.pitch}".encode("utf-8")).hexdigest()[:7], 16) % (2**31 - 1)

    # 1. Level & Scene
    level = LevelSpec(
        level_id="level_1",
        layout=layout,
        size_m=Vec2(x=size_w, y=size_h),
        biome=draft.biome,
        lighting=draft.lighting,
        seed=seed,
    )
    scene = Scene(levels=[level], start_level="level_1")

    # 2. Collect Entities
    # Start with always-added entities for the genre
    existing_kinds: Set[EntityKind] = set()
    raw_entities: List[Tuple[EntityKind, int, str, Dict[str, Any], List[str], str]] = []

    for kind, count, slot_or_strat in tmpl["always_entities"]:
        existing_kinds.add(kind)
        raw_entities.append((kind, count, slot_or_strat, {}, [], ""))

    # Add entities from draft, preserving user entity properties and tags
    for de in draft.entities:
        if de.kind in (EntityKind.PLAYER, EntityKind.BOARD, EntityKind.CARD_TABLE, EntityKind.SPAWNER) and de.kind in existing_kinds:
            # Merge props onto existing mandatory entity if user provided custom parameters
            idx = next(i for i, (k, _, _, _, _, _) in enumerate(raw_entities) if k == de.kind)
            cur_k, cur_cnt, cur_strat, cur_props, cur_tags, cur_note = raw_entities[idx]
            merged_props = dict(cur_props)
            merged_props.update(_extract_note_props(de.kind, de.note))
            merged_props.update(de.props)
            raw_entities[idx] = (cur_k, cur_cnt, cur_strat, merged_props, list(set(cur_tags + de.tags)), de.note or cur_note)
            continue

        existing_kinds.add(de.kind)
        slot_or_strat = "scatter"
        if de.kind == EntityKind.GOAL:
            slot_or_strat = "goal"
        elif de.kind == EntityKind.LANDMARK:
            slot_or_strat = "landmark"

        custom_props = _extract_note_props(de.kind, de.note)
        custom_props.update(de.props)
        raw_entities.append((de.kind, de.count, slot_or_strat, custom_props, list(de.tags), de.note))

    # Check Win & Lose conditions to see if additional entities must be injected
    has_spawner = any(k == EntityKind.SPAWNER for k, _, _, _, _, _ in raw_entities)
    has_enemy = any(k in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY) for k, _, _, _, _, _ in raw_entities)
    has_pickup = any(k == EntityKind.PICKUP for k, _, _, _, _, _ in raw_entities)
    has_goal = any(k == EntityKind.GOAL for k, _, _, _, _, _ in raw_entities)
    has_guard = any(k == EntityKind.GUARD for k, _, _, _, _, _ in raw_entities)
    has_board = any(k == EntityKind.BOARD for k, _, _, _, _, _ in raw_entities)
    has_card = any(k == EntityKind.CARD_TABLE for k, _, _, _, _, _ in raw_entities)
    has_player = any(k == EntityKind.PLAYER for k, _, _, _, _, _ in raw_entities)

    # If required game type modules imply entities not yet present, add them
    if game_type_hint:
        req_mods = get_required_modules_for_game_type(game_type_hint)
        if "kit.grid_board" in req_mods and not has_board:
            raw_entities.append((EntityKind.BOARD, 1, "board", {}, [], ""))
            has_board = True
        if "kit.goal" in req_mods and not has_goal:
            raw_entities.append((EntityKind.GOAL, 1, "goal", {}, [], ""))
            has_goal = True
        if "kit.player_character" in req_mods and not has_player:
            raw_entities.append((EntityKind.PLAYER, 1, "player_start", {}, [], ""))
            has_player = True

    for w in draft.win:
        if w.type == "collect_all" and not has_pickup:
            raw_entities.append((EntityKind.PICKUP, w.target or 5, "scatter", {}, [], ""))
            has_pickup = True
        elif w.type == "reach_goal" and not has_goal:
            raw_entities.append((EntityKind.GOAL, 1, "goal", {}, [], ""))
            has_goal = True
        elif w.type == "defeat_all" and not has_enemy and not has_spawner:
            raw_entities.append((EntityKind.ENEMY, w.target or 5, "scatter", {}, [], ""))
            has_enemy = True
        elif w.type == "board_win" and not has_board:
            raw_entities.append((EntityKind.BOARD, 1, "board", {}, [], ""))
            has_board = True
        elif w.type == "match_win" and not has_card:
            raw_entities.append((EntityKind.CARD_TABLE, 1, "board", {}, [], ""))
            has_card = True

    for l in draft.lose:
        if l.type == "caught_by_guard" and not has_guard:
            raw_entities.append((EntityKind.GUARD, 1, "scatter", {}, [], ""))
            has_guard = True
        elif l.type == "board_loss" and not has_board:
            raw_entities.append((EntityKind.BOARD, 1, "board", {}, [], ""))
            has_board = True
        elif l.type == "match_loss" and not has_card:
            raw_entities.append((EntityKind.CARD_TABLE, 1, "board", {}, [], ""))
            has_card = True
        elif l.type in ("fall_off", "health_zero") and not has_player:
            raw_entities.append((EntityKind.PLAYER, 1, "player_start", {}, [], ""))
            has_player = True

    # Platformers: a fall used to end the whole game ("health_zero" with no lives). Give the classic three lives
    # unless the design says otherwise; deaths respawn at the last checkpoint.
    if draft.genre == Genre.PLATFORMER and any(l.type in ("health_zero", "fall_off") for l in draft.lose):
        for idx, (k, c, st, pr, tg, nt) in enumerate(raw_entities):
            if k == EntityKind.PLAYER and not pr.get("lives"):
                raw_entities[idx] = (k, c, st, {**pr, "lives": 3}, tg, nt)

    # Build EntitySpec instances with deduplicated entity_ids and validated default properties
    entities: List[EntitySpec] = []
    used_ids: Set[str] = set()

    diff_scale = DIFFICULTY_SCALE.get(draft.difficulty, 1.0)
    sanitize_notes: List[str] = []
    for kind, count, placement_strat, user_props, user_tags, note_str in raw_entities:
        label = _tag_value(user_tags, "label") or (note_str.strip() if note_str and len(note_str) <= 30 else "")
        if label and kind not in (EntityKind.PLAYER, EntityKind.BOARD, EntityKind.CARD_TABLE, EntityKind.SPAWNER):
            noun = _slug(label, kind.value)
            base_id = _plural(noun) if count > 1 else noun
        else:
            noun = kind.value
            base_id = _plural(noun) if count > 1 else noun
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", base_id):
            base_id = kind.value
        candidate_id = base_id
        suffix = 2
        while candidate_id in used_ids:
            candidate_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(candidate_id)

        if placement_strat in ("player_start", "goal", "board", "landmark"):
            placement = Placement(strategy="slot", slot=placement_strat)
        else:
            placement = Placement(strategy="scatter")

        # Merge kit default properties with custom user properties
        final_props = dict(KIT_DEFAULT_PROPS.get(kind, {}))
        if kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY) and diff_scale != 1.0:
            for key in ("attack_damage", "max_health"):
                if key in final_props:
                    final_props[key] = round(float(final_props[key]) * diff_scale, 1)
        if kind == EntityKind.BOARD:
            draft_text = f"{draft.title} {getattr(draft, 'pitch', '')} {getattr(draft, 'core_mechanic', '')}".lower()
            if "sudoku" in draft_text or draft.genre == Genre.PUZZLE:
                final_props["board_size"] = 9
                final_props["win_length"] = 9
                final_props["vs_ai"] = False
                final_props["cell_size_cm"] = 80.0
            elif any(k in draft_text for k in ("chess", "checkers", "draughts")):
                final_props["board_size"] = 8
                final_props["win_length"] = 8
                final_props["cell_size_cm"] = 100.0
            elif any(k in draft_text for k in ("connect four", "connect 4", "connect_four", "four in a row")):
                final_props["board_size"] = 7
                final_props["win_length"] = 4
                final_props["gravity"] = True
        if kind == EntityKind.PICKUP and "objective_id" not in user_props:
            final_props["objective_id"] = candidate_id
        if kind == EntityKind.PLAYER and "attack_mode" not in user_props and (
                draft.genre == Genre.TOP_DOWN_SHOOTER or draft.camera == CameraKind.FIRST_PERSON):
            final_props["attack_mode"] = "projectile"   # shooters used to get the melee default
        if kind == EntityKind.PLAYER and draft.genre == Genre.PLATFORMER:
            final_props.setdefault("air_control", 0.45)
            final_props["jump_velocity"] = max(float(final_props.get("jump_velocity", 600.0)), 700.0)
        final_props.update(user_props)
        module_id = DEFAULT_MODULE[kind.value]
        final_props, notes = sanitize_props(module_id, final_props)
        sanitize_notes.extend(notes)

        tags = ["GF_Owned"]
        for t in user_tags:
            if isinstance(t, str) and t not in tags and len(tags) < 8 and len(t) <= 64:
                tags.append(t)
        if label and not _tag_value(tags, "label") and len(tags) < 8:
            tags.append(f"label:{label}"[:64])

        entities.append(
            EntitySpec(
                entity_id=candidate_id,
                kind=kind,
                module=module_id,
                level_id="level_1",
                count=count,
                placement=placement,
                props=final_props,
                tags=tags,
            )
        )

    # Map entity lookups
    pickup_ents = [e for e in entities if e.kind == EntityKind.PICKUP]
    pickup_ent = pickup_ents[0] if pickup_ents else None
    enemy_ent = next((e for e in entities if e.kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY)), None)

    # A spawner must spawn an enemy entity that exists in this design. The default "enemy" id rarely matched the
    # expanded id ("enemies", "zombies"), so waves spawned nameless default enemies with none of the design's stats.
    for sp in [e for e in entities if e.kind == EntityKind.SPAWNER]:
        target = sp.props.get("enemy_entity_id")
        if not any(e.entity_id == target for e in entities):
            if enemy_ent is None:
                enemy_ent = EntitySpec(
                    entity_id="enemies" if "enemies" not in {e.entity_id for e in entities} else "wave_enemies",
                    kind=EntityKind.ENEMY, module=DEFAULT_MODULE["enemy"], level_id="level_1",
                    count=max(1, int(sp.props.get("enemies_per_wave", 4))),
                    placement=Placement(strategy="scatter"),
                    props=sanitize_props("kit.enemy_melee", {
                        **KIT_DEFAULT_PROPS[EntityKind.ENEMY],
                        "attack_damage": round(15.0 * diff_scale, 1), "max_health": round(50.0 * diff_scale, 1)})[0],
                    tags=["GF_Owned", "spawned_by_spawner"],
                )
                entities.append(enemy_ent)
            sp.props = {**sp.props, "enemy_entity_id": enemy_ent.entity_id}
        if diff_scale != 1.0 and "enemies_per_wave" in sp.props:
            sp.props = {**sp.props, "enemies_per_wave": max(1, min(50, int(round(int(sp.props["enemies_per_wave"]) * diff_scale))))}

    # 3. Rules & Goals
    rules: List[RuleSpec] = []
    rule_idx = 1

    # Rules always added: score on pickup / enemy kill
    if pickup_ent:
        rules.append(
            RuleSpec(
                rule_id=f"rule_{rule_idx}",
                when=EventRef(event="pickup.collected"),
                effects=[AddStat(stat="game.score", delta=10.0)],
                description="Award points on pickup",
            )
        )
        rule_idx += 1

    if enemy_ent:
        enemy_effects: List[Effect] = [AddStat(stat="game.score", delta=25.0)]
        # Track enemy kill remaining stat if defeat_all without spawner is in win conditions
        if any(w.type == "defeat_all" for w in draft.win) and not has_spawner:
            enemy_effects.append(AddStat(stat=f"entity.{enemy_ent.entity_id}.remaining", delta=-1.0))

        rules.append(
            RuleSpec(
                rule_id=f"rule_{rule_idx}",
                when=EventRef(event="enemy.killed"),
                effects=enemy_effects,
                description="Award points and update enemy count on defeat",
            )
        )
        rule_idx += 1

    # "Collect everything AND reach the exit": win conditions are OR-ed at runtime, so reaching the goal used to win
    # without collecting anything. Lock the goal behind the pickup total instead and win on reaching it.
    win_types = [w.type for w in draft.win]
    goal_ent = next((e for e in entities if e.kind == EntityKind.GOAL), None)
    effective_wins = list(draft.win)
    if "collect_all" in win_types and "reach_goal" in win_types and goal_ent is not None and pickup_ents:
        total = sum(e.count for e in pickup_ents)
        if len(pickup_ents) == 1:
            stat = f"entity.{pickup_ents[0].entity_id}.collected"
        else:
            # several collectible kinds: count them all in one counter
            stat = "game.counter.collected"
            rules.append(RuleSpec(rule_id="count_collected", when=EventRef(event="pickup.collected"),
                                  effects=[AddStat(stat=stat, delta=1.0)], description="Count every collectible"))
        goal_ent.props = {**goal_ent.props, "required_stat": stat, "required_value": float(total)}
        effective_wins = [w for w in draft.win if w.type != "collect_all"]

    # Win conditions
    win_conds: List[Condition] = []
    has_timer_win = False
    for w in effective_wins:
        if w.type == "collect_all":
            # "Collect all" means every pickup placed; a model-supplied target smaller than the placed count made
            # the game end early, a larger one made it unwinnable.
            total_pickups = sum(e.count for e in pickup_ents) or 5
            win_conds.append(CountAtLeast(event="pickup.collected", n=total_pickups))
        elif w.type == "reach_goal":
            win_conds.append(EventOccurred(event="goal.reached"))
        elif w.type == "defeat_all":
            if has_spawner:
                waves = w.target or 3
                win_conds.append(
                    AllOf(
                        items=[
                            EventOccurred(event="wave.cleared"),
                            StatCompare(stat="game.counter.waves_cleared", op=">=", value=float(waves)),
                        ]
                    )
                )
                rules.append(
                    RuleSpec(
                        rule_id=f"rule_{rule_idx}",
                        when=EventRef(event="wave.cleared"),
                        effects=[AddStat(stat="game.counter.waves_cleared", delta=1.0)],
                        description="Increment cleared wave count",
                    )
                )
                rule_idx += 1
            else:
                target_enemy = enemy_ent.entity_id if enemy_ent else "enemies"
                win_conds.append(StatCompare(stat=f"entity.{target_enemy}.remaining", op="<=", value=0.0))
        elif w.type == "survive_seconds":
            win_conds.append(TimerElapsed(seconds=float(w.seconds or w.target or 60)))
            has_timer_win = True
        elif w.type == "score_at_least":
            win_conds.append(StatCompare(stat="game.score", op=">=", value=float(w.target or 100)))
        elif w.type == "board_win":
            win_conds.append(EventOccurred(event="board.win"))
        elif w.type == "match_win":
            win_conds.append(EventOccurred(event="match.won"))

    # Lose conditions
    lose_conds: List[Condition] = []
    for l in draft.lose:
        if l.type == "health_zero":
            player_ent = next((e for e in entities if e.kind == EntityKind.PLAYER), None)
            lives = int(player_ent.props.get("lives", 0) or 0) if player_ent else 0
            if lives > 0:
                # With lives, death respawns the player; the game is lost when the last life is used.
                lose_conds.append(StatCompare(stat="player.lives", op="<=", value=0.0))
            else:
                lose_conds.append(StatCompare(stat="player.health", op="<=", value=0.0))
        elif l.type == "timer_runs_out":
            if not has_timer_win:
                lose_conds.append(TimerElapsed(seconds=float(l.seconds or l.target or 60)))
        elif l.type == "fall_off":
            lose_conds.append(EventOccurred(event="player.died"))
        elif l.type == "board_loss":
            # Handled via rule: on board.win with ai_won -> end_game lose
            rules.append(
                RuleSpec(
                    rule_id=f"rule_{rule_idx}",
                    when=EventRef(event="board.win"),
                    conditions=[StatCompare(stat="game.counter.ai_won", op=">=", value=1.0)],
                    effects=[EndGame(outcome="lose")],
                    description="AI victory triggers loss",
                )
            )
            rule_idx += 1
        elif l.type == "match_loss":
            lose_conds.append(EventOccurred(event="match.lost"))
        elif l.type == "caught_by_guard":
            lose_conds.append(EventOccurred(event="guard.spotted_player"))

    # Custom rules from the draft are free text. They used to become empty CustomCode handlers, i.e. generated C++
    # classes that compiled (or failed to compile) and did nothing. They are shown to the player as briefing lines
    # instead; mechanics that matter are expressed with the typed entities/conditions above.
    briefings = [] if draft.architecture else [
        re.sub(r'["\\\r\n]+', " ", cr).strip() for cr in draft.custom_rules
    ]
    briefings = [b for b in briefings if len(b) >= 3]
    if briefings:
        rules.append(
            RuleSpec(
                rule_id="briefing",
                when=EventRef(event="game.started"),
                effects=[Message(text=briefings[0][:80], seconds=6.0)],
                description=("Briefing: " + " / ".join(briefings))[:200],
            )
        )

    # 4. Input - Ensure comprehensive camera orientation, movement and jump bindings
    actions = list(tmpl.get("actions", [IA_MOVE, IA_LOOK]))
    action_ids = {a.action_id for a in actions}

    # Bindings for 3D and dynamic cameras
    if draft.camera in (CameraKind.FIRST_PERSON, CameraKind.THIRD_PERSON):
        if IA_MOVE.action_id not in action_ids:
            actions.append(IA_MOVE)
            action_ids.add(IA_MOVE.action_id)
        if IA_LOOK.action_id not in action_ids:
            actions.append(IA_LOOK)
            action_ids.add(IA_LOOK.action_id)
        if IA_JUMP.action_id not in action_ids:
            actions.append(IA_JUMP)
            action_ids.add(IA_JUMP.action_id)

    elif draft.camera == CameraKind.SIDE_SCROLLER:
        if IA_MOVE.action_id not in action_ids:
            actions.append(IA_MOVE)
            action_ids.add(IA_MOVE.action_id)
        if IA_JUMP.action_id not in action_ids:
            actions.append(IA_JUMP)
            action_ids.add(IA_JUMP.action_id)

    elif draft.camera == CameraKind.TOP_DOWN:
        if IA_MOVE.action_id not in action_ids:
            actions.append(IA_MOVE)
            action_ids.add(IA_MOVE.action_id)
        if IA_LOOK.action_id not in action_ids:
            actions.append(IA_LOOK)
            action_ids.add(IA_LOOK.action_id)

    # Combat action injection
    has_combat_elements = has_enemy or has_spawner or any(
        getattr(e, "kind", None) in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY, EntityKind.SPAWNER)
        for e in entities
    ) or any(
        "shoot" in cr.lower() or "attack" in cr.lower() or "gun" in cr.lower() or "weapon" in cr.lower()
        for cr in draft.custom_rules
    )

    if has_combat_elements:
        if IA_FIRE.action_id not in action_ids and IA_ATTACK.action_id not in action_ids:
            if draft.camera in (CameraKind.FIRST_PERSON, CameraKind.TOP_DOWN):
                actions.append(IA_FIRE)
            else:
                actions.append(IA_ATTACK)
            action_ids.add(actions[-1].action_id)

    input_spec = InputSpec(actions=actions)

    # 5. UI & HUD
    hud_elements: List[HudElement] = []
    if any(e.kind == EntityKind.PLAYER for e in entities):
        hud_elements.append(HudElement(element_id="hud_health", kind="bar", binds="player.health", label="Health"))
    for i, pe in enumerate(pickup_ents[:3]):
        plabel = _tag_value(pe.tags, "label") or "Pickups"
        hud_elements.append(HudElement(element_id=f"hud_pickups{'' if i == 0 else '_' + str(i + 1)}", kind="counter",
                                       binds=f"entity.{pe.entity_id}.collected",
                                       label=(_plural(plabel) if not plabel.endswith("s") else plabel)[:30]))
    if any(w.type == "defeat_all" for w in draft.win) and enemy_ent and not has_spawner:
        elabel = _tag_value(enemy_ent.tags, "label") or "Enemies"
        hud_elements.append(HudElement(element_id="hud_enemies", kind="counter",
                                       binds=f"entity.{enemy_ent.entity_id}.remaining",
                                       label=f"{_plural(elabel) if not elabel.endswith('s') else elabel} left"[:30]))
    if has_spawner:
        hud_elements.append(HudElement(element_id="hud_waves", kind="counter",
                                       binds="game.counter.waves_cleared", label="Waves cleared"))
    if any(e.kind == EntityKind.PLAYER and int(e.props.get("lives", 0) or 0) > 0 for e in entities):
        hud_elements.append(HudElement(element_id="hud_lives", kind="counter", binds="player.lives", label="Lives"))
    if any(isinstance(c, TimerElapsed) for c in win_conds + lose_conds):
        hud_elements.append(HudElement(element_id="hud_timer", kind="timer", binds="game.time_s", label="Time"))
    hud_elements.append(HudElement(element_id="hud_score", kind="counter", binds="game.score", label="Score"))

    ui_spec = UISpec(hud=hud_elements, main_menu=True, pause_menu=True, end_screen=True)

    # 6. Feedback rows (only for events declared by modules/rules)
    game_events = {"game.started", "game.won", "game.lost", "game.restarted", "game.paused", "game.resumed"}
    allowed_events = set(game_events)
    for e in entities:
        if e.module in MODULE_EVENTS:
            allowed_events.update(MODULE_EVENTS[e.module])
    for r in rules:
        for eff in r.effects:
            if hasattr(eff, "event"):
                allowed_events.add(eff.event)

    feedback: List[FeedbackSpec] = []
    pickup_label = _tag_value(pickup_ent.tags, "label") if pickup_ent else None
    enemy_label = _tag_value(enemy_ent.tags, "label") if enemy_ent else None
    messages = {
        "pickup.collected": f"+1 {pickup_label}" if pickup_label else None,
        "enemy.killed": f"{enemy_label} defeated!" if enemy_label else None,
        "wave.cleared": "Wave cleared!",
        "landmark.discovered": "Landmark discovered",
        "door.opened": "Door opened",
    }
    shakes = {"player.damaged": 0.35, "enemy.killed": 0.15}
    for ev, vfx, sfx in FEEDBACK_CATALOG + [("wave.cleared", "vfx.ring", "sfx.fanfare"),
                                            ("landmark.discovered", "vfx.magic_trail", "sfx.chime_low"),
                                            ("door.opened", None, "sfx.chime_low")]:
        if ev in allowed_events and not any(f.on.event == ev for f in feedback):
            msg = messages.get(ev)
            feedback.append(FeedbackSpec(on=EventRef(event=ev), vfx=vfx, sfx=sfx,
                                         camera_shake=shakes.get(ev, 0.0),
                                         ui_message=msg[:60] if msg else None))

    # 7. Acceptance Scenarios
    scenarios: List[ScenarioRef] = []
    # A real jump course is not navmesh-connected, so the walking autopilot cannot prove its win conditions;
    # those scenarios are advisory (the smoke test and lose scenarios still gate the build).
    jump_course = draft.genre == Genre.PLATFORMER and draft.difficulty != "easy"
    for i, _ in enumerate(win_conds):
        scenarios.append(ScenarioRef(scenario_id=f"win_{i+1}", derived_from=f"goals.win[{i}]", must_pass=not jump_course))
    for i, _ in enumerate(lose_conds):
        scenarios.append(ScenarioRef(scenario_id=f"lose_{i+1}", derived_from=f"goals.lose[{i}]", must_pass=True))
    scenarios.append(ScenarioRef(scenario_id="smoke", derived_from="smoke", must_pass=True))

    goals = Goals(win=win_conds, lose=lose_conds, score=ScoreSpec(stat="game.score"), sandbox=False)
    acceptance = Acceptance(scenarios=scenarios)

    # 8. Meta, Overview, Art, Audio, Tech
    full_prompt = (source_prompt or draft.pitch or "").strip()
    meta = Meta(
        project_name=proj_name,
        title=re.sub(r'["\\\r\n]+', " ", draft.title).strip()[:60] or proj_name,
        source_prompt=full_prompt[:4000],
        generator="user",
    )
    # Art direction from the prompt's setting (palette, material theme, ambience). Previously every game got the
    # same four default colours and no ambience regardless of "volcano", "neon city" or "haunted graveyard".
    theme_id, palette, ambience, music = None, None, "none", draft.music_mood
    try:
        from .prompt_analysis import analyze_prompt, THEMES
        brief = analyze_prompt(f"{full_prompt} {draft.title}")
        theme_id = brief.theme
        if theme_id is None:
            theme_id = {Biome.FOREST: "forest", Biome.DESERT: "desert", Biome.ISLAND: "island",
                        Biome.MOUNTAIN: "castle", Biome.DUNGEON: "dungeon", Biome.INDOOR: "cyber"}.get(draft.biome)
        if theme_id:
            palette = list(THEMES[theme_id]["palette"])
            ambience = THEMES[theme_id]["ambience"]
            if music == "none":
                music = THEMES[theme_id]["music"]
    except Exception:
        pass
    players = 1
    for e in entities:
        if "players" in e.props:
            try:
                p_val = int(e.props["players"])
                if p_val >= 2:
                    players = p_val
                    break
            except (ValueError, TypeError):
                pass
    if players == 1 and draft.genre == Genre.GRID_BOARD:
        players = 2

    overview = Overview(
        genre=draft.genre,
        pitch=draft.pitch,
        camera=draft.camera,
        players=players,
        session_minutes=10,
    )
    art_kwargs: Dict[str, Any] = {}
    if palette:
        art_kwargs["palette"] = palette
    art = ArtDirection(
        style=draft.art_style,
        material_theme=theme_id or "default",
        character_source="mannequin",
        placeholder_ok=False,
        **art_kwargs,
    )
    audio = AudioSpec(
        music_mood=music if music in ("none", "calm", "tense", "heroic", "playful") else "none",
        ambience=ambience if ambience in ("none", "wind", "forest", "dungeon", "city") else "none",
        sfx_set="soft" if draft.art_style == "toon" else "default",
    )
    tech = TechSpec(
        target_fps=60,
        max_frame_ms=16.6,
        max_package_mb=400,
        multiplayer="none",
    )
    progression = Progression(difficulty=draft.difficulty, difficulty_params={"scale": diff_scale})

    try:
        arch_spec = None
        if getattr(draft, "architecture", None):
            try:
                arch_spec = ArchitectureSpec.model_validate(draft.architecture)
            except Exception:
                pass

        spec = GameDesignSpec(
            meta=meta,
            overview=overview,
            scene=scene,
            entities=entities,
            input=input_spec,
            rules=rules,
            progression=progression,
            goals=goals,
            feedback=feedback,
            ui=ui_spec,
            art=art,
            audio=audio,
            tech=tech,
            acceptance=acceptance,
            architecture=arch_spec,
        )
        return spec
    except Exception as exc:
        raise ExpandError(
            f"Draft expansion failed cross-validation: {exc}",
            question="Could not expand draft into a valid game specification. Please clarify the game rules.",
        ) from exc
