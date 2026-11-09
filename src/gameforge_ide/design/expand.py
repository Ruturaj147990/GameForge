"""Deterministic expansion of a DesignDraft into a full GameDesignSpec (P1 WI-1.4).

Binding modifiers use the syntax Key:modifier with modifiers negate, swizzle and swizzle_negate.
P5 maps them to UInputModifierNegate and UInputModifierSwizzleAxis(YXZ).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

def _pascal(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "Game")
    out = "".join(w[:1].upper() + w[1:] for w in words) or "Game"
    if not out[0].isalpha():
        out = "G" + out
    return (out if len(out) >= 2 else out + "Game")[:31]
from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .events_catalog import DEFAULT_MODULE, MODULE_EVENTS
from .gds import (
    Acceptance,
    AddStat,
    AllOf,
    ArchitectureSpec,
    ArtDirection,
    AudioSpec,
    Biome,
    CameraKind,
    Condition,
    CountAtLeast,
    CustomCode,
    Effect,
    Emit,
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
    Message,
    Overview,
    PhaseSpec,
    Placement,
    Progression,
    RuleSpec,
    ScenarioRef,
    Scene,
    ScoreSpec,
    SetStat,
    Spawn,
    StatCompare,
    TechSpec,
    TimerElapsed,
    UISpec,
    Vec2,
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
IA_DASH = InputActionSpec(
    action_id="IA_Dash",
    value_type="bool",
    bindings=["LeftShift"],
    purpose="Quick forward burst dash",
)
IA_SPRINT = InputActionSpec(
    action_id="IA_Sprint",
    value_type="bool",
    bindings=["LeftShift"],
    purpose="Sprint faster",
)
IA_ROLL_DICE = InputActionSpec(
    action_id="IA_RollDice",
    value_type="bool",
    bindings=["SpaceBar"],
    purpose="Roll dice on board",
)
IA_WEAPON_1 = InputActionSpec(
    action_id="IA_Weapon1",
    value_type="bool",
    bindings=["One"],
    purpose="Equip weapon slot 1",
)
IA_WEAPON_2 = InputActionSpec(
    action_id="IA_Weapon2",
    value_type="bool",
    bindings=["Two"],
    purpose="Equip weapon slot 2",
)
IA_WEAPON_3 = InputActionSpec(
    action_id="IA_Weapon3",
    value_type="bool",
    bindings=["Three"],
    purpose="Equip weapon slot 3",
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
        "board_mode": "n_in_a_row",
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
    EntityKind.BOMB_SITE: {
        "plant_seconds": 3.0,
        "defuse_seconds": 5.0,
        "fuse_seconds": 35.0,
    },
}

_CSG_PROP_RECIPES = {
    "crate", "barrel", "rock", "pillar", "fence",
    "tree", "stylized_tree", "bush", "torch", "chest", "altar",
    "crystal", "arch", "console", "turret_base",
}


def _extract_note_props(kind: EntityKind, note: str) -> Dict[str, Any]:
    """Parse custom user entity parameters and tags from draft entity note."""
    props: Dict[str, Any] = {}
    if not note:
        return props

    note_lower = note.lower()

    for recipe in _CSG_PROP_RECIPES:
        if recipe in note_lower:
            props["recipe"] = "stylized_tree" if recipe == "tree" else recipe
            break

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
    "mode": "board_mode", "snakes_count": "snakes", "ladders_count": "ladders",
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
    """Map aliases, drop keys the kit module does not accept and clamp numbers into the module's ranges."""
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
            continue
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


def _compile_custom_rules(
    custom_rules: List[str],
    architecture: Optional[Dict[str, Any]],
    allowed_events: Set[str],
    enemy_ent: Optional[EntitySpec],
    pickup_ent: Optional[EntitySpec],
    start_idx: int,
) -> List[RuleSpec]:
    """Compile natural-language custom_rules and architecture into executable RuleSpec items and C++ subsystems."""
    out: List[RuleSpec] = []

    cleaned_rules = [re.sub(r'["\\\r\n]+', " ", cr).strip() for cr in (custom_rules or []) if cr and cr.strip()]
    cleaned_rules = [cr for cr in cleaned_rules if len(cr) >= 3]

    user_facing_rules = [
        cr for cr in cleaned_rules
        if not cr.lower().startswith(("architecture:", "target classes:"))
    ]
    if user_facing_rules:
        out.append(
            RuleSpec(
                rule_id="briefing",
                when=EventRef(event="game.started"),
                effects=[Message(text=user_facing_rules[0][:80], seconds=6.0)],
                description=("Briefing: " + " / ".join(user_facing_rules))[:200],
            )
        )

    for i, cr in enumerate(user_facing_rules):
        low = cr.lower()

        # 1. Determine trigger event from open-vocabulary rule description
        ev = "game.started"
        if any(k in low for k in ("enemy dies", "enemy is killed", "on kill", "defeat", "killed", "slain", "destroy")) and "enemy.killed" in allowed_events:
            ev = "enemy.killed"
        elif any(k in low for k in ("on pickup", "collect", "coin", "item", "relic", "gather", "grab", "salvage", "core", "crystal", "gem")) and "pickup.collected" in allowed_events:
            ev = "pickup.collected"
        elif any(k in low for k in ("takes damage", "on damage", "low health", "hit", "damaged", "hurt")) and "player.damaged" in allowed_events:
            ev = "player.damaged"
        elif any(k in low for k in ("wave clear", "every wave", "wave ends", "after wave")) and "wave.cleared" in allowed_events:
            ev = "wave.cleared"
        elif any(k in low for k in ("lap", "complete a lap")) and "lap.completed" in allowed_events:
            ev = "lap.completed"
        elif any(k in low for k in ("checkpoint", "split")) and "checkpoint.reached" in allowed_events:
            ev = "checkpoint.reached"
        elif any(k in low for k in ("jump", "double jump", "airborne")) and "player.jumped" in allowed_events:
            ev = "player.jumped"
        elif any(k in low for k in ("dash", "dodge", "boost")) and "player.dashed" in allowed_events:
            ev = "player.dashed"
        elif any(k in low for k in ("switch", "terminal", "console", "button", "lever", "hack", "activate")) and "switch.toggled" in allowed_events:
            ev = "switch.toggled"
        elif any(k in low for k in ("door", "gate", "unlock")) and "door.opened" in allowed_events:
            ev = "door.opened"
        elif any(k in low for k in ("spotted", "detected", "seen by guard")) and "guard.spotted_player" in allowed_events:
            ev = "guard.spotted_player"
        elif any(k in low for k in ("hazard", "lava", "acid", "trap", "radiation")) and "hazard.touched" in allowed_events:
            ev = "hazard.touched"

        # 2. Extract conditions
        conds: List[Condition] = []
        if "low health" in low or "health <" in low or "health below" in low:
            m_thresh = re.search(r"health\s*(?:<|<=|below|under)\s*(\d+)", low)
            thresh = float(m_thresh.group(1)) if m_thresh else 35.0
            conds.append(StatCompare(stat="player.health", op="<=", value=max(1.0, min(500.0, thresh))))
        elif "score >=" in low or "score reaches" in low or "at least" in low and "score" in low:
            m_sc = re.search(r"(\d+)", low)
            if m_sc:
                conds.append(StatCompare(stat="game.score", op=">=", value=float(m_sc.group(1))))

        m_sec = re.search(r"\b(?:every|after)\s+(\d+)\s*(?:seconds?|secs?|s)\b", low)
        if m_sec:
            sec_val = max(1.0, min(3600.0, float(m_sec.group(1))))
            conds.append(TimerElapsed(seconds=sec_val))

        m_every_kill = re.search(r"\bevery\s+(\d+)\s+(?:kills?|enemies|defeats?)\b", low)
        if m_every_kill and "enemy.killed" in allowed_events:
            conds.append(CountAtLeast(event="enemy.killed", n=max(1, int(m_every_kill.group(1)))))

        # 3. Extract effects
        effects: List[Effect] = []
        m_num = re.search(r"([+-]?\d+(?:\.\d+)?)", low)
        num_val = abs(float(m_num.group(1))) if m_num else 25.0
        is_drain = any(k in low for k in ("drain", "lose", "subtract", "reduce", "cost", "consume", "decay", "damage"))

        if any(k in low for k in ("heal", "restore health", "gain health", "extra health", "+hp", "regenerate health")):
            effects.append(AddStat(stat="player.health", delta=min(200.0, max(5.0, num_val))))
        elif any(k in low for k in ("oxygen", "air supply")):
            delta = -min(50.0, max(1.0, num_val)) if is_drain else min(100.0, max(5.0, num_val))
            effects.append(AddStat(stat="player.oxygen", delta=delta))
        elif any(k in low for k in ("shield", "armor", "barrier")):
            delta = -min(50.0, max(5.0, num_val)) if is_drain else min(100.0, max(10.0, num_val))
            effects.append(AddStat(stat="player.shield", delta=delta))
        elif any(k in low for k in ("mana", "arcane", "spell energy")):
            delta = -min(50.0, max(5.0, num_val)) if is_drain else min(100.0, max(10.0, num_val))
            effects.append(AddStat(stat="player.mana", delta=delta))
        elif any(k in low for k in ("stamina", "endurance", "energy")):
            delta = -min(50.0, max(5.0, num_val)) if is_drain else min(100.0, max(10.0, num_val))
            effects.append(AddStat(stat="player.stamina", delta=delta))
        elif any(k in low for k in ("ammo", "ammunition", "bullets", "shells")):
            delta = -min(50.0, max(1.0, num_val)) if is_drain else min(100.0, max(5.0, num_val))
            effects.append(AddStat(stat="player.ammo", delta=delta))
        elif any(k in low for k in ("gold", "credits", "currency", "bounty", "scrap")):
            delta = -min(500.0, max(1.0, num_val)) if is_drain else min(500.0, max(5.0, num_val))
            effects.append(AddStat(stat="game.gold", delta=delta))
        elif any(k in low for k in ("speed", "move faster", "haste", "accelerate")):
            effects.append(AddStat(stat="player.speed", delta=min(400.0, max(25.0, num_val))))
        elif any(k in low for k in ("lives", "extra life", "1up")):
            effects.append(AddStat(stat="player.lives", delta=1.0))

        if any(k in low for k in ("score", "points", "bonus", "combo")):
            effects.append(AddStat(stat="game.score", delta=min(1000.0, max(5.0, num_val))))

        if any(k in low for k in ("spawn", "reinforcement", "ambush", "summon")) and enemy_ent is not None:
            effects.append(Spawn(entity_id=enemy_ent.entity_id, count=max(1, min(10, int(num_val) if num_val <= 10 else 2))))
        elif any(k in low for k in ("drop", "reward item")) and pickup_ent is not None:
            effects.append(Spawn(entity_id=pickup_ent.entity_id, count=1))

        if any(k in low for k in ("instant win", "win the game", "triggers victory")) and "lose" not in low:
            effects.append(EndGame(outcome="win"))
        elif any(k in low for k in ("instant death", "lose the game", "game over", "mission failed")):
            effects.append(EndGame(outcome="lose"))

        if not effects:
            effects.append(AddStat(stat="game.score", delta=15.0))

        out.append(
            RuleSpec(
                rule_id=f"custom_rule_{i + 1}",
                when=EventRef(event=ev),
                conditions=conds[:4],
                effects=effects[:4],
                description=cr[:200],
            )
        )

    # Synthesize C++ subsystem code whenever architecture defines custom mechanics/classes OR custom rules are present
    arch_dict = dict(architecture) if isinstance(architecture, dict) else {}
    has_custom_mechanics = bool(
        arch_dict.get("custom_capabilities")
        or arch_dict.get("mechanics")
        or arch_dict.get("target_classes")
        or arch_dict.get("method", "").startswith(("scratch", "hybrid", "llm_scratch", "llm_hybrid"))
        or user_facing_rules
    )
    if has_custom_mechanics:
        target_classes = arch_dict.get("target_classes") or []
        plan_kind = str(arch_dict.get("plan_kind") or arch_dict.get("method") or "dynamic_gameplay")
        raw_cls = str(target_classes[0]) if target_classes else "DynamicGameplayRule"
        clean_cls = re.sub(r"[^A-Za-z0-9]", "", raw_cls.lstrip("AUF"))
        if not clean_cls or not clean_cls[0].isupper():
            clean_cls = "DynamicGameplay"
        if not clean_cls.endswith("Rule"):
            clean_cls = f"{clean_cls[:28]}Rule"
        desc = f"Architecture state machine ({plan_kind}): {', '.join(str(c) for c in target_classes[:3]) or clean_cls}"
        from ..composer.codegen import synthesize_cpp_bodies_for_architecture
        on_event_cpp, tick_cpp = synthesize_cpp_bodies_for_architecture(arch_dict, cleaned_rules)
        if on_event_cpp.strip() or tick_cpp.strip():
            out.append(
                RuleSpec(
                    rule_id="architecture_codegen",
                    when=EventRef(event="game.started"),
                    effects=[
                        CustomCode(
                            description=desc[:400],
                            handler_name=clean_cls,
                            on_event_body=on_event_cpp[:8000],
                            tick_body=tick_cpp[:8000],
                        )
                    ],
                    description=desc[:200],
                )
            )

    return out


def expand_draft(draft: DesignDraft, source_prompt: Optional[str] = None) -> GameDesignSpec:
    """Deterministically expand a DesignDraft into a validated GameDesignSpec."""
    from ..kit.rules import GAME_TYPE_LAYOUT_MAP, get_layout_for_game_type, get_required_modules_for_game_type

    proj_name = _pascal(draft.title)
    tmpl = GENRE_TEMPLATES.get(draft.genre, GENRE_TEMPLATES[Genre.CUSTOM])
    layout = tmpl["layout"]

    pitch_title = f"{draft.title} {draft.pitch} {source_prompt or ''}".lower()
    game_type_hint = ""
    for gt in GAME_TYPE_LAYOUT_MAP:
        if re.search(rf"\b{re.escape(gt.replace('_', ' '))}\b", pitch_title) or re.search(rf"\b{re.escape(gt)}\b", pitch_title):
            if gt == "snake" and "ladder" in pitch_title:
                continue
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
    if size_key == "small" and sum(de.count for de in draft.entities) > 30:
        size_key = "medium"
    size_w, size_h = LEVEL_SIZES.get(size_key, LEVEL_SIZES["small"])

    seed = int(hashlib.sha256(f"{draft.title}|{source_prompt or draft.pitch}".encode("utf-8")).hexdigest()[:7], 16) % (2**31 - 1)

    layout_params: Dict[str, Any] = {}
    if game_type_hint == "racing" or re.search(r"\b(racing|race\s+track|racer|kart|driving|hoverbike|speedway|circuit)\b", pitch_title):
        layout_params["track_mode"] = "racing"
        m_laps = re.search(r"\b(\d+)\s+laps?\b", pitch_title)
        layout_params["laps"] = int(m_laps.group(1)) if m_laps else 3
    elif game_type_hint == "tower_defense" or re.search(r"\b(tower\s+defense|lane\s+defense|defend\s+the\s+(?:base|core|nexus|crystal))\b", pitch_title):
        layout = LayoutKind.LANES
        layout_params["lane_mode"] = "tower_defense"

    if re.search(r"\b(zero[- ]gravity|0g|weightless)\b", pitch_title):
        layout_params["gravity_z"] = -150.0
    elif re.search(r"\b(low[- ]gravity|moon\s+gravity|lunar)\b", pitch_title):
        layout_params["gravity_z"] = -380.0

    # 1. Level & Scene
    level = LevelSpec(
        level_id="level_1",
        layout=layout,
        size_m=Vec2(x=size_w, y=size_h),
        biome=draft.biome,
        lighting=draft.lighting,
        seed=seed,
        layout_params=layout_params,
    )
    scene = Scene(levels=[level], start_level="level_1")

    # 2. Collect Entities
    existing_kinds: Set[EntityKind] = set()
    raw_entities: List[Tuple[EntityKind, int, str, Dict[str, Any], List[str], str]] = []

    for kind, count, slot_or_strat in tmpl["always_entities"]:
        existing_kinds.add(kind)
        raw_entities.append((kind, count, slot_or_strat, {}, [], ""))

    for de in draft.entities:
        if de.kind in (EntityKind.PLAYER, EntityKind.BOARD, EntityKind.CARD_TABLE, EntityKind.SPAWNER) and de.kind in existing_kinds:
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

    has_spawner = any(k == EntityKind.SPAWNER for k, _, _, _, _, _ in raw_entities)
    has_enemy = any(k in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY) for k, _, _, _, _, _ in raw_entities)
    has_pickup = any(k == EntityKind.PICKUP for k, _, _, _, _, _ in raw_entities)
    has_goal = any(k == EntityKind.GOAL for k, _, _, _, _, _ in raw_entities)
    has_guard = any(k == EntityKind.GUARD for k, _, _, _, _, _ in raw_entities)
    has_board = any(k == EntityKind.BOARD for k, _, _, _, _, _ in raw_entities)
    has_card = any(k == EntityKind.CARD_TABLE for k, _, _, _, _, _ in raw_entities)
    has_player = any(k == EntityKind.PLAYER for k, _, _, _, _, _ in raw_entities)

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

    if draft.genre == Genre.PLATFORMER and any(l.type in ("health_zero", "fall_off") for l in draft.lose):
        for idx, (k, c, st, pr, tg, nt) in enumerate(raw_entities):
            if k == EntityKind.PLAYER and not pr.get("lives"):
                raw_entities[idx] = (k, c, st, {**pr, "lives": 3}, tg, nt)

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

        final_props = dict(KIT_DEFAULT_PROPS.get(kind, {}))
        if kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY) and diff_scale != 1.0:
            for key in ("attack_damage", "max_health"):
                if key in final_props:
                    final_props[key] = round(float(final_props[key]) * diff_scale, 1)
        if kind == EntityKind.BOARD and not user_props.get("board_mode"):
            try:
                from .prompt_analysis import analyze_prompt, _board_props_for_brief
                brief_board = analyze_prompt(f"{draft.title} {draft.pitch} {source_prompt or ''}")
                _, inferred_b_props = _board_props_for_brief(brief_board)
                final_props.update(inferred_b_props)
            except Exception:
                pass
        if kind == EntityKind.PICKUP and "objective_id" not in user_props:
            final_props["objective_id"] = candidate_id
        if kind == EntityKind.PLAYER and "attack_mode" not in user_props and (
                draft.genre == Genre.TOP_DOWN_SHOOTER or draft.camera == CameraKind.FIRST_PERSON):
            final_props["attack_mode"] = "projectile"
        if kind == EntityKind.PLAYER and draft.genre == Genre.PLATFORMER:
            final_props.setdefault("air_control", 0.45)
            if layout_params.get("track_mode") == "racing":
                final_props.setdefault("move_speed", 1100.0)
                final_props.setdefault("sprint_multiplier", 2.0)
            else:
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

    pickup_ents = [e for e in entities if e.kind == EntityKind.PICKUP]
    pickup_ent = pickup_ents[0] if pickup_ents else None
    enemy_ent = next((e for e in entities if e.kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY)), None)

    for sp in [e for e in entities if e.kind == EntityKind.SPAWNER]:
        target = sp.props.get("enemy_entity_id")
        if not any(e.entity_id == target for e in entities):
            if enemy_ent is None:
                enemy_ent = EntitySpec(
                    entity_id="enemies" if "enemies" not in {e.entity_id for e in entities} else "wave_enemies",
                    kind=EntityKind.ENEMY,
                    module=DEFAULT_MODULE["enemy"],
                    level_id="level_1",
                    count=max(1, int(sp.props.get("enemies_per_wave", 4))),
                    placement=Placement(strategy="scatter"),
                    props=sanitize_props(
                        "kit.enemy_melee",
                        {
                            **KIT_DEFAULT_PROPS[EntityKind.ENEMY],
                            "attack_damage": round(15.0 * diff_scale, 1),
                            "max_health": round(50.0 * diff_scale, 1),
                        },
                    )[0],
                    tags=["GF_Owned", "spawned_by_spawner"],
                )
                entities.append(enemy_ent)
            sp.props = {**sp.props, "enemy_entity_id": enemy_ent.entity_id}
        if diff_scale != 1.0 and "enemies_per_wave" in sp.props:
            sp.props = {
                **sp.props,
                "enemies_per_wave": max(1, min(50, int(round(int(sp.props["enemies_per_wave"]) * diff_scale)))),
            }

    # Wire switches to doors automatically if switches have no target_tag
    door_ent = next((e for e in entities if e.kind == EntityKind.DOOR), None)
    for sw in [e for e in entities if e.kind == EntityKind.SWITCH]:
        if not sw.props.get("target_tag") and door_ent is not None:
            sw.props = {**sw.props, "target_tag": door_ent.entity_id}

    # 3. Rules & Goals
    rules: List[RuleSpec] = []
    rule_idx = 1

    if pickup_ent:
        rules.append(
            RuleSpec(
                rule_id=f"rule_{rule_idx}",
                when=EventRef(event="pickup.collected"),
                effects=[AddStat(stat="game.score", delta=float(pickup_ent.props.get("value", 1)) * 10.0)],
                description="Award points on pickup",
            )
        )
        rule_idx += 1

    if enemy_ent:
        enemy_effects: List[Effect] = [AddStat(stat="game.score", delta=25.0)]
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

    win_types = [w.type for w in draft.win]
    goal_ent = next((e for e in entities if e.kind == EntityKind.GOAL), None)
    effective_wins = list(draft.win)
    if "collect_all" in win_types and "reach_goal" in win_types and goal_ent is not None and pickup_ents:
        total = sum(e.count for e in pickup_ents)
        if len(pickup_ents) == 1:
            stat = f"entity.{pickup_ents[0].entity_id}.collected"
        else:
            stat = "game.counter.collected"
            rules.append(
                RuleSpec(
                    rule_id="count_collected",
                    when=EventRef(event="pickup.collected"),
                    effects=[AddStat(stat=stat, delta=1.0)],
                    description="Count every collectible",
                )
            )
        goal_ent.props = {**goal_ent.props, "required_stat": stat, "required_value": float(total)}
        effective_wins = [w for w in draft.win if w.type != "collect_all"]

    win_conds: List[Condition] = []
    has_timer_win = False
    for w in effective_wins:
        if w.type == "collect_all":
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

    lose_conds: List[Condition] = []
    for l in draft.lose:
        if l.type == "health_zero":
            player_ent = next((e for e in entities if e.kind == EntityKind.PLAYER), None)
            lives = int(player_ent.props.get("lives", 0) or 0) if player_ent else 0
            if lives > 0:
                lose_conds.append(StatCompare(stat="player.lives", op="<=", value=0.0))
            else:
                lose_conds.append(StatCompare(stat="player.health", op="<=", value=0.0))
        elif l.type == "timer_runs_out":
            if not has_timer_win:
                lose_conds.append(TimerElapsed(seconds=float(l.seconds or l.target or 60)))
        elif l.type == "fall_off":
            lose_conds.append(EventOccurred(event="player.died"))
        elif l.type == "board_loss":
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

    game_events = {"game.started", "game.won", "game.lost", "game.restarted", "game.paused", "game.resumed"}
    allowed_events = set(game_events)
    for e in entities:
        if e.module in MODULE_EVENTS:
            allowed_events.update(MODULE_EVENTS[e.module])

    # Synthesize or enrich architecture from prompt/draft when not provided
    arch_input = getattr(draft, "architecture", None)
    if not arch_input and source_prompt:
        try:
            from .template_registry import default_registry
            dec = default_registry.evaluate_strategy(source_prompt)
            arch_input = dec.suggested_architecture
        except Exception:
            arch_input = None

    compiled_custom_rules = _compile_custom_rules(
        draft.custom_rules,
        arch_input,
        allowed_events,
        enemy_ent,
        pickup_ent,
        rule_idx,
    )
    rules.extend(compiled_custom_rules)

    # 4. Input
    actions = list(tmpl.get("actions", [IA_MOVE, IA_LOOK]))
    action_ids = {a.action_id for a in actions}

    if draft.camera in (CameraKind.FIRST_PERSON, CameraKind.THIRD_PERSON):
        for ia in (IA_MOVE, IA_LOOK, IA_JUMP):
            if ia.action_id not in action_ids:
                actions.append(ia)
                action_ids.add(ia.action_id)
    elif draft.camera == CameraKind.SIDE_SCROLLER:
        for ia in (IA_MOVE, IA_JUMP):
            if ia.action_id not in action_ids:
                actions.append(ia)
                action_ids.add(ia.action_id)
    elif draft.camera == CameraKind.TOP_DOWN:
        for ia in (IA_MOVE, IA_LOOK):
            if ia.action_id not in action_ids:
                actions.append(ia)
                action_ids.add(ia.action_id)

    has_interactive_world = any(
        e.kind in (EntityKind.DOOR, EntityKind.SWITCH, EntityKind.NPC, EntityKind.BOMB_SITE)
        for e in entities
    )
    if has_interactive_world and IA_INTERACT.action_id not in action_ids and len(actions) < 16:
        actions.append(IA_INTERACT)
        action_ids.add(IA_INTERACT.action_id)

    has_combat_elements = (
        has_enemy
        or has_spawner
        or any(
            getattr(e, "kind", None) in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY, EntityKind.SPAWNER)
            for e in entities
        )
        or any(
            "shoot" in cr.lower() or "attack" in cr.lower() or "gun" in cr.lower() or "weapon" in cr.lower()
            for cr in draft.custom_rules
        )
    )

    if has_combat_elements:
        if IA_FIRE.action_id not in action_ids and IA_ATTACK.action_id not in action_ids:
            if draft.camera in (CameraKind.FIRST_PERSON, CameraKind.TOP_DOWN):
                actions.append(IA_FIRE)
            else:
                actions.append(IA_ATTACK)
            action_ids.add(actions[-1].action_id)

    player_ent_for_input = next((e for e in entities if e.kind == EntityKind.PLAYER), None)
    if player_ent_for_input:
        if player_ent_for_input.props.get("dash_impulse") and IA_DASH.action_id not in action_ids and len(actions) < 16:
            actions.append(IA_DASH)
            action_ids.add(IA_DASH.action_id)
        elif player_ent_for_input.props.get("sprint_multiplier") and IA_SPRINT.action_id not in action_ids and len(actions) < 16:
            actions.append(IA_SPRINT)
            action_ids.add(IA_SPRINT.action_id)

        weapons_list = player_ent_for_input.props.get("weapons")
        if isinstance(weapons_list, list) and len(weapons_list) >= 2:
            for ia_w in (IA_WEAPON_1, IA_WEAPON_2, IA_WEAPON_3)[: len(weapons_list)]:
                if ia_w.action_id not in action_ids and len(actions) < 16:
                    actions.append(ia_w)
                    action_ids.add(ia_w.action_id)

    board_ent_for_input = next((e for e in entities if e.kind == EntityKind.BOARD), None)
    if board_ent_for_input:
        bmode = str(board_ent_for_input.props.get("board_mode", ""))
        if (
            bmode in ("roll_and_move", "race_board", "linear_path", "ludo")
            or board_ent_for_input.props.get("dice_sides")
            or board_ent_for_input.props.get("warp_tiles")
        ) and IA_ROLL_DICE.action_id not in action_ids and len(actions) < 16:
            actions.append(IA_ROLL_DICE)
            action_ids.add(IA_ROLL_DICE.action_id)

    input_spec = InputSpec(actions=actions)

    # 5. UI & HUD
    hud_elements: List[HudElement] = []
    if any(e.kind == EntityKind.PLAYER for e in entities):
        hud_elements.append(HudElement(element_id="hud_health", kind="bar", binds="player.health", label="Health"))

    # Add dynamic HUD bars/counters for stats referenced in rules or player props
    referenced_stats: Set[str] = set()
    for r in rules:
        for c in r.conditions:
            if hasattr(c, "stat") and getattr(c, "stat"):
                referenced_stats.add(str(getattr(c, "stat")))
        for eff in r.effects:
            if hasattr(eff, "stat") and getattr(eff, "stat"):
                referenced_stats.add(str(getattr(eff, "stat")))

    dynamic_hud_map = [
        ("player.shield", "hud_shield", "bar", "Shield"),
        ("player.oxygen", "hud_oxygen", "bar", "Oxygen"),
        ("player.mana", "hud_mana", "bar", "Mana"),
        ("player.stamina", "hud_stamina", "bar", "Stamina"),
        ("player.ammo", "hud_ammo", "counter", "Ammo"),
        ("game.gold", "hud_gold", "counter", "Gold"),
    ]
    for stat_name, el_id, el_kind, el_label in dynamic_hud_map:
        if stat_name in referenced_stats and len(hud_elements) < 8:
            hud_elements.append(HudElement(element_id=el_id, kind=el_kind, binds=stat_name, label=el_label))  # type: ignore[arg-type]

    if layout_params.get("track_mode") == "racing" and len(hud_elements) < 9:
        hud_elements.append(HudElement(element_id="hud_laps", kind="counter", binds="game.laps", label="Laps"))

    for i, pe in enumerate(pickup_ents[:3]):
        if len(hud_elements) >= 10:
            break
        plabel = _tag_value(pe.tags, "label") or "Pickups"
        hud_elements.append(
            HudElement(
                element_id=f"hud_pickups{'' if i == 0 else '_' + str(i + 1)}",
                kind="counter",
                binds=f"entity.{pe.entity_id}.collected",
                label=(_plural(plabel) if not plabel.endswith("s") else plabel)[:30],
            )
        )
    if any(w.type == "defeat_all" for w in draft.win) and enemy_ent and not has_spawner and len(hud_elements) < 10:
        elabel = _tag_value(enemy_ent.tags, "label") or "Enemies"
        hud_elements.append(
            HudElement(
                element_id="hud_enemies",
                kind="counter",
                binds=f"entity.{enemy_ent.entity_id}.remaining",
                label=f"{_plural(elabel) if not elabel.endswith('s') else elabel} left"[:30],
            )
        )
    if has_spawner and len(hud_elements) < 10:
        hud_elements.append(
            HudElement(element_id="hud_waves", kind="counter", binds="game.counter.waves_cleared", label="Waves cleared")
        )
    if any(e.kind == EntityKind.PLAYER and int(e.props.get("lives", 0) or 0) > 0 for e in entities) and len(hud_elements) < 10:
        hud_elements.append(HudElement(element_id="hud_lives", kind="counter", binds="player.lives", label="Lives"))
    if any(isinstance(c, TimerElapsed) for c in win_conds + lose_conds) and len(hud_elements) < 11:
        hud_elements.append(HudElement(element_id="hud_timer", kind="timer", binds="game.time_s", label="Time"))
    if len(hud_elements) < 12:
        hud_elements.append(HudElement(element_id="hud_score", kind="counter", binds="game.score", label="Score"))

    ui_spec = UISpec(hud=hud_elements[:12], main_menu=True, pause_menu=True, end_screen=True)

    # 6. Feedback rows
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
    for ev, vfx, sfx in FEEDBACK_CATALOG + [
        ("wave.cleared", "vfx.ring", "sfx.fanfare"),
        ("landmark.discovered", "vfx.magic_trail", "sfx.chime_low"),
        ("door.opened", None, "sfx.chime_low"),
    ]:
        if ev in allowed_events and not any(f.on.event == ev for f in feedback):
            msg = messages.get(ev)
            feedback.append(
                FeedbackSpec(
                    on=EventRef(event=ev),
                    vfx=vfx,
                    sfx=sfx,
                    camera_shake=shakes.get(ev, 0.0),
                    ui_message=msg[:60] if msg else None,
                )
            )

    # 7. Acceptance Scenarios
    scenarios: List[ScenarioRef] = []
    jump_course = (
        draft.genre == Genre.PLATFORMER
        and draft.difficulty != "easy"
        and layout_params.get("track_mode") != "racing"
    )
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
    theme_id, palette, ambience, music = None, None, "none", draft.music_mood
    try:
        from .prompt_analysis import THEMES, analyze_prompt
        brief = analyze_prompt(f"{full_prompt} {draft.title}")
        theme_id = brief.theme
        if theme_id is None:
            theme_id = {
                Biome.FOREST: "forest",
                Biome.DESERT: "desert",
                Biome.ISLAND: "island",
                Biome.MOUNTAIN: "castle",
                Biome.DUNGEON: "dungeon",
                Biome.INDOOR: "cyber",
            }.get(draft.biome)
        if theme_id and theme_id in THEMES:
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

    phases: List[PhaseSpec] = []
    if has_spawner and len(entities) > 0:
        sp_ent = next((e for e in entities if e.kind == EntityKind.SPAWNER), None)
        w_cnt = int(sp_ent.props.get("wave_count", 3)) if sp_ent else 3
        for w_i in range(1, min(w_cnt + 1, 8)):
            phases.append(
                PhaseSpec(
                    phase_id=f"wave_{w_i}",
                    description=f"Wave {w_i} progression stage",
                    enter_when=StatCompare(stat="game.counter.waves_cleared", op=">=", value=float(w_i - 1)),
                    params={"speed_multiplier": round(1.0 + 0.1 * (w_i - 1), 2)},
                )
            )
    progression = Progression(phases=phases, difficulty=draft.difficulty, difficulty_params={"scale": diff_scale})

    try:
        arch_spec = None
        eff_arch = getattr(draft, "architecture", None) or arch_input
        if eff_arch:
            try:
                arch_spec = ArchitectureSpec.model_validate(eff_arch)
            except Exception:
                allowed_arch = set(ArchitectureSpec.model_fields)
                filtered = {k: v for k, v in eff_arch.items() if k in allowed_arch}
                try:
                    arch_spec = ArchitectureSpec.model_validate(filtered)
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
