"""Preset GameDesignSpecs matching the 5 legacy recipe genres (P1 WI-1.5)."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from src.gameforge_ide.pipeline.spec_from_prompt import (
    _AI_EASY,
    _AI_MED,
    _DENSITY,
    _DIFF,
    _ENEMIES,
    _HOTSEAT,
    _HP,
    _NAME,
    _SEED,
    _SIZE,
    _TARGET,
    _WAVES,
    _WIN,
    _pascal,
)
from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .expand import expand_draft
from .gds import (
    CameraKind,
    EndGame,
    EntityKind,
    EntitySpec,
    EventRef,
    GameDesignSpec,
    Genre,
    Placement,
    RuleSpec,
    StatCompare,
)


def _find_entity(gds: GameDesignSpec, kind: EntityKind) -> Optional[EntitySpec]:
    for e in gds.entities:
        if e.kind == kind:
            return e
    return None


def preset_tic_tac_toe(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Tic-Tac-Toe"
    draft = DesignDraft(
        title=t,
        genre=Genre.GRID_BOARD,
        camera=CameraKind.FIXED_BOARD,
        pitch="3x3 board game, align three in a row",
        win=[DraftWin(type="board_win")],
        lose=[DraftLose(type="board_loss")],
    )
    gds = expand_draft(draft)
    board = _find_entity(gds, EntityKind.BOARD)
    if board:
        board.props = {
            "board_size": 3,
            "win_length": 3,
            "vs_ai": True,
            "gravity": False,
            "ai_level": "perfect",
            "cell_size_cm": 200,
        }
        board.props.update(overrides.get("board_props", {}))
        for k in ("board_size", "win_length", "vs_ai", "gravity", "ai_level", "cell_size_cm"):
            if k in overrides:
                board.props[k] = overrides[k]
    return gds


def preset_connect_four(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Connect Four"
    draft = DesignDraft(
        title=t,
        genre=Genre.GRID_BOARD,
        camera=CameraKind.FIXED_BOARD,
        pitch="7x7 grid, pieces drop down, four in a row",
        win=[DraftWin(type="board_win")],
        lose=[DraftLose(type="board_loss")],
    )
    gds = expand_draft(draft)
    board = _find_entity(gds, EntityKind.BOARD)
    if board:
        board.props = {
            "board_size": 7,
            "win_length": 4,
            "vs_ai": True,
            "gravity": True,
            "ai_level": "greedy",
            "cell_size_cm": 200,
        }
        board.props.update(overrides.get("board_props", {}))
        for k in ("board_size", "win_length", "vs_ai", "gravity", "ai_level", "cell_size_cm"):
            if k in overrides:
                board.props[k] = overrides[k]
    return gds


def preset_gomoku(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Gomoku"
    draft = DesignDraft(
        title=t,
        genre=Genre.GRID_BOARD,
        camera=CameraKind.FIXED_BOARD,
        pitch="15x15 board, five in a row",
        win=[DraftWin(type="board_win")],
        lose=[DraftLose(type="board_loss")],
    )
    gds = expand_draft(draft)
    board = _find_entity(gds, EntityKind.BOARD)
    if board:
        board.props = {
            "board_size": 15,
            "win_length": 5,
            "vs_ai": True,
            "gravity": False,
            "ai_level": "perfect",
            "cell_size_cm": 150,
        }
        board.props.update(overrides.get("board_props", {}))
        for k in ("board_size", "win_length", "vs_ai", "gravity", "ai_level", "cell_size_cm"):
            if k in overrides:
                board.props[k] = overrides[k]
    return gds


def preset_platformer(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Platformer"
    count = int(overrides.get("collectible_target", 5))
    draft = DesignDraft(
        title=t,
        genre=Genre.PLATFORMER,
        camera=CameraKind.THIRD_PERSON,
        pitch="3D obstacle course with jumping, collectibles, checkpoints, and goal",
        win=[DraftWin(type="collect_all", target=count), DraftWin(type="reach_goal")],
        lose=[DraftLose(type="fall_off")],
        difficulty=overrides.get("difficulty", "normal"),
    )
    gds = expand_draft(draft)
    player = _find_entity(gds, EntityKind.PLAYER)
    if player:
        player.props = {
            "player_speed": 600,
            "jump_velocity": 650,
            "gravity_scale": 1.2,
            "air_control": 0.35,
            "kill_z": -500,
        }
        player.props.update(overrides.get("player_props", {}))
    pickups = _find_entity(gds, EntityKind.PICKUP)
    if pickups:
        pickups.count = count
    return gds


def preset_arena_combat(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Arena Combat"
    waves = int(overrides.get("wave_count", 3))
    enemies = int(overrides.get("enemies_per_wave", 4))
    draft = DesignDraft(
        title=t,
        genre=Genre.ARENA_COMBAT,
        camera=CameraKind.TOP_DOWN,
        pitch="Top-down arena combat with waves of enemies",
        win=[DraftWin(type="defeat_all", target=waves)],
        lose=[DraftLose(type="health_zero")],
        difficulty=overrides.get("difficulty", "normal"),
    )
    gds = expand_draft(draft)
    spawner = _find_entity(gds, EntityKind.SPAWNER)
    if spawner:
        spawner.props = {
            "wave_count": waves,
            "enemies_per_wave": enemies,
            "enemy_max_health": 50,
            "enemy_attack_damage": 15,
            "enemy_attack_range": 120,
            "enemy_attack_cooldown": 1.0,
            "enemy_speed": 350,
        }
        spawner.props.update(overrides.get("spawner_props", {}))
    player = _find_entity(gds, EntityKind.PLAYER)
    if player:
        player.props = {
            "player_max_health": 100,
            "player_attack_damage": 35,
            "player_attack_range": 250,
            "player_attack_cooldown": 0.4,
        }
        player.props.update(overrides.get("player_props", {}))
    return gds


def preset_card_battler(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Card Battler"
    hp = int(overrides.get("player_base_health", 30))
    draft = DesignDraft(
        title=t,
        genre=Genre.CARD_BATTLER,
        camera=CameraKind.FIXED_BOARD,
        pitch="Single-player 3-lane card battler with deck building and AI opponent",
        win=[DraftWin(type="match_win")],
        lose=[DraftLose(type="match_loss")],
        difficulty=overrides.get("difficulty", "normal"),
    )
    gds = expand_draft(draft)
    table = _find_entity(gds, EntityKind.CARD_TABLE)
    if table:
        table.props = {
            "player_base_health": hp,
            "opponent_base_health": hp,
            "starting_hand_size": 4,
            "max_hand_size": 7,
            "base_energy_per_turn": 3,
            "lane_count": 3,
        }
        table.props.update(overrides.get("table_props", {}))
    return gds


def preset_procedural_world(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Procedural World"
    draft = DesignDraft(
        title=t,
        genre=Genre.EXPLORATION,
        camera=CameraKind.THIRD_PERSON,
        pitch="Procedural landscape with height variation, spline road, and landmark traversal",
        win=[DraftWin(type="reach_goal")],
    )
    gds = expand_draft(draft)
    lvl = gds.scene.levels[0]
    lvl.layout_params = {
        "terrain_type": overrides.get("terrain_type", "Valley"),
        "elevation_scale": float(overrides.get("elevation_scale", 1800.0)),
        "road_width": float(overrides.get("road_width", 350.0)),
        "foliage_density": float(overrides.get("foliage_density", 40.0)),
        "landmark_type": overrides.get("landmark_type", "Ruins"),
    }
    lvl.seed = int(overrides.get("seed", 2026))

    landmark = _find_entity(gds, EntityKind.LANDMARK)
    if not landmark:
        gds.entities.append(
            EntitySpec(
                entity_id="landmark",
                kind=EntityKind.LANDMARK,
                module="kit.landmark",
                level_id=lvl.level_id,
                count=1,
                placement=Placement(strategy="slot", slot="landmark"),
            )
        )
    return gds


def preset_relic_hunt(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Relic Hunt"
    draft = DesignDraft(
        title=t,
        genre=Genre.ACTION_ADVENTURE,
        camera=CameraKind.THIRD_PERSON,
        pitch="A third-person forest adventure: collect 5 relics while avoiding 3 guards and return them to the old hermit",
        win=[DraftWin(type="reach_goal")],
    )
    gds = expand_draft(draft)
    lvl = gds.scene.levels[0]
    lvl.layout = "open_world"
    lvl.lighting = "day"

    gds.entities = [
        EntitySpec(
            entity_id="player",
            kind=EntityKind.PLAYER,
            module="kit.player_character",
            level_id=lvl.level_id,
            count=1,
            props={"move_speed": 600.0, "max_health": 100.0},
        ),
        EntitySpec(
            entity_id="giver",
            kind=EntityKind.NPC,
            module="kit.quest_giver",
            level_id=lvl.level_id,
            count=1,
            props={"objective_id": "relics", "objective_title": "Recover 5 relics", "objective_target": 5},
        ),
        EntitySpec(
            entity_id="relics",
            kind=EntityKind.PICKUP,
            module="kit.pickup",
            level_id=lvl.level_id,
            count=5,
            props={"objective_id": "relics", "value": 1.0},
        ),
        EntitySpec(
            entity_id="guard",
            kind=EntityKind.GUARD,
            module="kit.guard",
            level_id=lvl.level_id,
            count=3,
            props={"aggro_radius": 1200.0, "patrol_radius": 800.0, "move_speed": 400.0},
        ),
        EntitySpec(
            entity_id="goal",
            kind=EntityKind.GOAL,
            module="kit.goal",
            level_id=lvl.level_id,
            count=1,
            props={"required_stat": "entity.relics.collected", "required_value": 5.0},
        ),
    ]
    return gds


def preset_top_down_shooter(title: Optional[str] = None, **overrides) -> GameDesignSpec:
    t = title or "Top-Down Arena Shooter"
    waves = int(overrides.get("wave_count", 3))
    enemies = int(overrides.get("enemies_per_wave", 4))
    draft = DesignDraft(
        title=t,
        genre=Genre.TOP_DOWN_SHOOTER,
        camera=CameraKind.TOP_DOWN,
        pitch="Top-down arena shooter: survive 3 waves of enemies",
        win=[DraftWin(type="defeat_all", target=waves)],
        lose=[DraftLose(type="health_zero")],
    )
    gds = expand_draft(draft)
    lvl = gds.scene.levels[0]
    lvl.layout = "arena"

    player = _find_entity(gds, EntityKind.PLAYER)
    if player:
        player.props["attack_mode"] = "projectile"
        player.props["move_speed"] = 650.0

    spawner = _find_entity(gds, EntityKind.SPAWNER)
    if spawner:
        spawner.props = {
            "wave_count": waves,
            "enemies_per_wave": enemies,
            "seconds_between_waves": 3.0,
            "spawn_radius": 500.0,
        }
    return gds


PRESETS: Dict[str, Callable[..., GameDesignSpec]] = {
    "tic_tac_toe": preset_tic_tac_toe,
    "connect_four": preset_connect_four,
    "gomoku": preset_gomoku,
    "platformer": preset_platformer,
    "arena_combat": preset_arena_combat,
    "card_battler": preset_card_battler,
    "procedural_world": preset_procedural_world,
    "relic_hunt": preset_relic_hunt,
    "top_down_shooter": preset_top_down_shooter,
}

PRESET_KEYWORDS: Dict[str, List[str]] = {
    "tic_tac_toe": [
        "tic tac toe", "tic-tac-toe", "tictactoe", "noughts and crosses",
        "naughts and crosses", "xs and os", "x and o", "x's and o's",
    ],
    "connect_four": [
        "four in a row", "4 in a row", "connect four", "connect 4",
    ],
    "gomoku": [
        "gomoku", "five in a row", "5 in a row", "omok", "renju",
    ],
    "platformer": [
        "platformer", "3d platformer", "jump and run", "jumping game",
        "platform game", "parkour",
    ],
    "arena_combat": [
        "arena combat", "arena", "gladiator", "wave combat", "brawler", "action arena",
    ],
    "card_battler": [
        "card battler", "card game", "deck battler", "deck builder",
        "card battle", "lane battler", "hearthstone",
    ],
    "procedural_world": [
        "procedural world", "procedural landscape", "procedural terrain",
        "terrain generation", "procedural environment", "landscape generation", "hiking trail",
    ],
}


def extract_preset_overrides(preset_id: str, prompt: str) -> Dict[str, Any]:
    """Extract overrides from prompt text using the legacy parameter regexes."""
    overrides: Dict[str, Any] = {}
    m = _NAME.search(prompt)
    if m:
        overrides["title"] = m.group(1).strip()

    if preset_id in ("tic_tac_toe", "connect_four", "gomoku"):
        m = _SIZE.search(prompt)
        if m and m.group(1) == m.group(2):
            overrides["board_size"] = int(m.group(1))
        m = _WIN.search(prompt)
        if m:
            overrides["win_length"] = int(m.group(1))
        if _HOTSEAT.search(prompt):
            overrides["vs_ai"] = False
        if _AI_EASY.search(prompt):
            overrides["ai_level"] = "random"
        elif _AI_MED.search(prompt):
            overrides["ai_level"] = "greedy"
    elif preset_id == "platformer":
        m = _TARGET.search(prompt)
        if m:
            overrides["collectible_target"] = int(m.group(1))
        m = _DIFF.search(prompt)
        if m:
            overrides["difficulty"] = m.group(1).lower()
    elif preset_id == "arena_combat":
        m = _WAVES.search(prompt)
        if m:
            overrides["wave_count"] = int(m.group(1))
        m = _ENEMIES.search(prompt)
        if m:
            overrides["enemies_per_wave"] = int(m.group(1))
        m = _DIFF.search(prompt)
        if m:
            overrides["difficulty"] = m.group(1).lower()
    elif preset_id == "card_battler":
        m = _HP.search(prompt)
        if m:
            overrides["player_base_health"] = int(m.group(1))
        m = _DIFF.search(prompt)
        if m:
            overrides["difficulty"] = m.group(1).lower()
    elif preset_id == "procedural_world":
        text = prompt.lower()
        if re.search(r"\b(mountain|mountains|alpine|peaks?)\b", text):
            overrides["terrain_type"] = "Mountains"
        elif re.search(r"\b(plateau|mesa)\b", text):
            overrides["terrain_type"] = "Plateau"
        elif re.search(r"\b(hills?|rolling hills?)\b", text):
            overrides["terrain_type"] = "Hills"
        elif re.search(r"\b(valley|canyon)\b", text):
            overrides["terrain_type"] = "Valley"
        m = _SEED.search(prompt)
        if m:
            overrides["seed"] = int(m.group(1))
        m = _DENSITY.search(prompt)
        if m:
            overrides["foliage_density"] = float(m.group(1))

    return overrides


def get_preset_spec(name: str) -> GameDesignSpec:
    """Retrieve a default GameDesignSpec for a named preset."""
    factories = {
        "relic_hunt": preset_relic_hunt,
        "platformer": preset_platformer,
        "arena_combat": preset_arena_combat,
        "card_battler": preset_card_battler,
        "procedural_world": preset_procedural_world,
        "top_down_shooter": preset_top_down_shooter,
        "tic_tac_toe": preset_tic_tac_toe,
        "connect_four": preset_connect_four,
        "gomoku": preset_gomoku,
    }
    factory = factories.get(name)
    if factory is None:
        raise KeyError(f"Unknown preset name: {name!r}")
    return factory()

