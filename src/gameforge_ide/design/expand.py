"""Deterministic expansion of a DesignDraft into a full GameDesignSpec (P1 WI-1.4).

Binding modifiers use the syntax Key:modifier with modifiers negate, swizzle and swizzle_negate.
P5 maps them to UInputModifierNegate and UInputModifierSwizzleAxis(YXZ).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.gameforge_ide.pipeline.spec_from_prompt import _pascal
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


def expand_draft(draft: DesignDraft) -> GameDesignSpec:
    """Deterministically expand a DesignDraft into a validated GameDesignSpec."""
    proj_name = _pascal(draft.title)
    tmpl = GENRE_TEMPLATES.get(draft.genre, GENRE_TEMPLATES[Genre.CUSTOM])
    layout = tmpl["layout"]
    size_w, size_h = LEVEL_SIZES.get(draft.level_size, LEVEL_SIZES["small"])

    # 1. Level & Scene
    level = LevelSpec(
        level_id="level_1",
        layout=layout,
        size_m=Vec2(x=size_w, y=size_h),
        biome=draft.biome,
        lighting=draft.lighting,
        seed=2026,
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
        if de.kind in (EntityKind.PLAYER, EntityKind.BOARD, EntityKind.CARD_TABLE) and de.kind in existing_kinds:
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

    # Build EntitySpec instances with deduplicated entity_ids and validated default properties
    entities: List[EntitySpec] = []
    used_ids: Set[str] = set()

    for kind, count, placement_strat, user_props, user_tags, note_str in raw_entities:
        base_id = f"{kind.value}s" if count > 1 else kind.value
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
        if kind == EntityKind.PICKUP and "objective_id" not in user_props:
            final_props["objective_id"] = candidate_id
        final_props.update(user_props)

        tags = ["GF_Owned"]
        for t in user_tags:
            if t not in tags and len(tags) < 8:
                tags.append(t)

        entities.append(
            EntitySpec(
                entity_id=candidate_id,
                kind=kind,
                module=DEFAULT_MODULE[kind.value],
                level_id="level_1",
                count=count,
                placement=placement,
                props=final_props,
                tags=tags,
            )
        )

    # Map entity lookups
    pickup_ent = next((e for e in entities if e.kind == EntityKind.PICKUP), None)
    enemy_ent = next((e for e in entities if e.kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY)), None)

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

    # Win conditions
    win_conds: List[Condition] = []
    has_timer_win = False
    for w in draft.win:
        if w.type == "collect_all":
            total_pickups = pickup_ent.count if pickup_ent else 5
            n = w.target if w.target is not None else total_pickups
            win_conds.append(CountAtLeast(event="pickup.collected", n=n))
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

    # Custom rules from draft
    for i, cr in enumerate(draft.custom_rules):
        rules.append(
            RuleSpec(
                rule_id=f"custom_{i+1}",
                when=EventRef(event="game.started"),
                effects=[CustomCode(description=cr, handler_name=f"Custom{i+1}Rule")],
                description=f"Custom rule {i+1}",
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
    if pickup_ent:
        hud_elements.append(HudElement(element_id="hud_pickups", kind="counter", binds=f"entity.{pickup_ent.entity_id}.collected", label="Pickups"))
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
    for ev, vfx, sfx in FEEDBACK_CATALOG:
        if ev in allowed_events:
            feedback.append(FeedbackSpec(on=EventRef(event=ev), vfx=vfx, sfx=sfx))

    # 7. Acceptance Scenarios
    scenarios: List[ScenarioRef] = []
    for i, _ in enumerate(win_conds):
        scenarios.append(ScenarioRef(scenario_id=f"win_{i+1}", derived_from=f"goals.win[{i}]", must_pass=True))
    for i, _ in enumerate(lose_conds):
        scenarios.append(ScenarioRef(scenario_id=f"lose_{i+1}", derived_from=f"goals.lose[{i}]", must_pass=True))
    scenarios.append(ScenarioRef(scenario_id="smoke", derived_from="smoke", must_pass=True))

    goals = Goals(win=win_conds, lose=lose_conds, score=ScoreSpec(stat="game.score"), sandbox=False)
    acceptance = Acceptance(scenarios=scenarios)

    # 8. Meta, Overview, Art, Audio, Tech
    meta = Meta(
        project_name=proj_name,
        title=draft.title,
        source_prompt=draft.pitch,
        generator="user",
    )
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
    art = ArtDirection(
        style=draft.art_style,
        character_source="mannequin",
        placeholder_ok=False,
    )
    audio = AudioSpec(
        music_mood=draft.music_mood,
        ambience="none",
        sfx_set="default",
    )
    tech = TechSpec(
        target_fps=60,
        max_frame_ms=16.6,
        max_package_mb=400,
        multiplayer="none",
    )
    progression = Progression(difficulty=draft.difficulty)

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
