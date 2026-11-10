"""Natural-language prompt -> Game Spec (recipe + validated parameters).

Provides unified access to:
- is_game_creation_request
- match_prompt, spec_from_prompt, refine_with_model
- expand_game_flags
- RecipeEntry, RECIPES, GameSpec, SPEC_SCHEMA
- Parameter regexes (_TARGET, _DIFF, _NAME, _WAVES, _ENEMIES, _HP, _SEED, _DENSITY, _SIZE, _WIN, _pascal, etc.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Union

from ..legacy_recipes.arena_combat.recipe import ArenaCombatParams
from ..legacy_recipes.card_battler.recipe import CardBattlerParams
from ..legacy_recipes.grid_board_game.recipe import GridBoardParams
from ..legacy_recipes.platformer.recipe import PlatformerParams
from ..legacy_recipes.procedural_world.recipe import ProceduralWorldParams

_CREATE = re.compile(
    r"\b(create|make|mak|mkae|maek|build|buid|biuld|generate|develop|design|give me|gimme|"
    r"i want|wanna|want|need|write|complete|finish|expand|build out|author|code|cod|implement|"
    r"deploy|construct|produce|craft|scaffold|spin up|whip up|put together|start|program|"
    r"craete|creat|creaet|crte|setup|set up)\b",
    re.I,
)
_GAME_WORD = re.compile(
    r"\b(game|gameplay|level|prototype|demo|mini[- ]?game|arcade)\b",
    re.I,
)
_NOUN_GAME = re.compile(
    r"\b(platformer|3d platformer|arena combat|card battler|procedural world|"
    r"tic[- ]?tac[- ]?toe|connect four|four in a row|gomoku|five in a row|"
    r"board game|grid board|sudoku|chess|checkers|draughts|minesweeper|tetris|roguelike|tower defense|"
    r"tactical fps|fps|brawler|moba)\b",
    re.I,
)
_CREATE_GAME = re.compile(
    rf"{_CREATE.pattern}.*(?:{_GAME_WORD.pattern}|{_NOUN_GAME.pattern})",
    re.I,
)


@dataclass
class RecipeEntry:
    recipe_id: str
    title: str
    keywords: List[str]
    description: str
    defaults: Dict


RECIPES: List[RecipeEntry] = [
    RecipeEntry(
        "grid_board_game",
        "Sudoku",
        ["sudoku", "number puzzle", "9x9 grid", "su doku"],
        "9x9 grid board puzzle with 81 cells",
        {
            "board_size": 9,
            "win_length": 9,
            "vs_ai": False,
            "display_title": "Sudoku",
            "project_name": "Sudoku",
        },
    ),
    RecipeEntry(
        "grid_board_game",
        "Tic-Tac-Toe",
        [
            "tic tac toe",
            "tic-tac-toe",
            "tictactoe",
            "noughts and crosses",
            "naughts and crosses",
            "xs and os",
            "x and o",
            "x's and o's",
        ],
        "3x3 board, three in a row",
        {
            "board_size": 3,
            "win_length": 3,
            "display_title": "Tic-Tac-Toe",
            "project_name": "TicTacToe",
        },
    ),
    RecipeEntry(
        "grid_board_game",
        "Gomoku",
        ["gomoku", "five in a row", "5 in a row", "omok", "renju"],
        "large board, five in a row",
        {
            "board_size": 15,
            "win_length": 5,
            "display_title": "Gomoku",
            "project_name": "Gomoku",
        },
    ),
    RecipeEntry(
        "grid_board_game",
        "Four in a Row (grid)",
        ["four in a row", "4 in a row", "connect four", "connect 4"],
        "7x7 grid, pieces drop down, four in a row",
        {
            "board_size": 7,
            "win_length": 4,
            "display_title": "Four in a Row",
            "project_name": "FourInARow",
            "gravity": True,
        },
    ),
    RecipeEntry(
        "grid_board_game",
        "N-in-a-row board game",
        ["in a row", "grid game", "board game", "grid board"],
        "configurable grid and line length",
        {
            "board_size": 5,
            "win_length": 4,
            "display_title": "Line Up",
            "project_name": "LineUp",
        },
    ),
    RecipeEntry(
        "platformer",
        "3D Platformer",
        ["platformer", "3d platformer", "jump and run", "jumping game", "platform game", "parkour"],
        "3D obstacle course with jumping, collectibles, checkpoints, and goal",
        {
            "collectible_target": 5,
            "difficulty": "normal",
            "display_title": "3D Platformer",
            "project_name": "Platformer",
        },
    ),
    RecipeEntry(
        "arena_combat",
        "Arena Combat",
        ["arena combat", "arena", "gladiator", "wave combat", "brawler", "action arena"],
        "Top-down / 3D arena combat with player attack, AI navigation enemies, waves, and HUD",
        {
            "wave_count": 3,
            "enemies_per_wave": 4,
            "difficulty": "normal",
            "display_title": "Arena Combat",
            "project_name": "ArenaCombat",
        },
    ),
    RecipeEntry(
        "card_battler",
        "Card Battler",
        ["card battler", "card game", "deck battler", "deck builder", "card battle", "lane battler"],
        "Single-player 3-lane card battler with card definitions, energy, combat, AI opponent, and interactive UMG HUD",
        {
            "player_base_health": 30,
            "opponent_base_health": 30,
            "difficulty": "normal",
            "display_title": "Card Battler",
            "project_name": "CardBattler",
        },
    ),
    RecipeEntry(
        "procedural_world",
        "Procedural World",
        [
            "procedural world",
            "procedural landscape",
            "procedural terrain",
            "terrain generation",
            "procedural environment",
            "landscape generation",
            "hiking trail",
        ],
        "Procedural landscape with height variation, spline road, vegetation scatter, landmark, and traversal",
        {
            "terrain_type": "Valley",
            "elevation_scale": 1800.0,
            "road_width": 350.0,
            "foliage_density": 40,
            "landmark_type": "Ruins",
            "display_title": "Procedural Landscape",
            "project_name": "ProceduralWorld",
            "seed": 2026,
        },
    ),
]

_SEED = re.compile(r"\bseed\s*[:=]?\s*(\d{1,8})\b", re.I)
_DENSITY = re.compile(r"\b(\d{1,4})\s*(?:foliage|trees?|plants?|instances?|bushes?)\b", re.I)
_ELEVATION = re.compile(r"\belevation(?:\s*scale)?\s*[:=]?\s*(\d{2,6})\b", re.I)
_SIZE = re.compile(r"\b(\d{1,2})\s*(?:x|by|×)\s*(\d{1,2})\b", re.I)
_WIN = re.compile(r"\b(\d{1,2})\s*(?:in a row|in-a-row|to win)\b", re.I)
_TARGET = re.compile(r"\b(\d{1,2})\s*(?:collectibles?|coins?|gems?|items?|stars?|relics?|crystals?|orbs?)\b", re.I)
_WAVES = re.compile(r"\b(\d{1,2})\s*(?:waves?|rounds?)\b", re.I)
_ENEMIES = re.compile(r"\b(\d{1,2})\s*(?:enemies|enemy|monsters?|targets?)\s*(?:per wave|each wave|a wave)?\b", re.I)
_HP = re.compile(r"\b(\d{1,3})\s*(?:hp|health|base health)\b", re.I)
_NAME = re.compile(
    r"\b(?:called|named|titled)\s+[\"']?([A-Za-z][A-Za-z0-9 \-]{0,40}?)[\"']?"
    r"(?=\s+(?:against|with|vs|versus|for|that|and|in|on|where|using|which|set|at)\b|[.,!;:]|\s*$)",
    re.I,
)
_HOTSEAT = re.compile(
    r"\b(two[- ]players?|2[- ]players?|two[- ]humans?|2[- ]humans?|local[- ]versus|"
    r"local[- ]co[- ]?op|hot[- ]?seat|local[- ]multiplayer|pvp|against a friend|vs (?:a )?friend)\b",
    re.I,
)
_AI_EASY = re.compile(r"\b(easy|beginner|random)\b", re.I)
_AI_MED = re.compile(r"\b(medium|normal|greedy)\b", re.I)
_DIFF = re.compile(r"\b(easy|normal|hard|expert)\b", re.I)
_COLOR_WORDS = {
    "red": (1.0, 0.22, 0.2),
    "blue": (0.1, 0.45, 1.0),
    "green": (0.15, 0.8, 0.3),
    "yellow": (1.0, 0.85, 0.1),
    "purple": (0.55, 0.25, 0.95),
    "orange": (1.0, 0.55, 0.1),
    "pink": (1.0, 0.4, 0.7),
    "white": (0.95, 0.95, 0.95),
    "black": (0.05, 0.05, 0.06),
    "cyan": (0.1, 0.85, 0.9),
}


@dataclass
class GameSpec:
    matched: bool
    recipe_id: Optional[str] = None
    recipe_title: Optional[str] = None
    params: Optional[
        Union[
            GridBoardParams,
            PlatformerParams,
            ArenaCombatParams,
            CardBattlerParams,
            ProceduralWorldParams,
        ]
    ] = None
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.matched or not self.params:
            return "No recipe matched: " + "; ".join(self.reasons)
        p = self.params
        if isinstance(p, ProceduralWorldParams):
            return (
                f"{p.display_title}: Procedural {p.terrain_type} landscape (elevation {p.elevation_scale} cm), "
                f"spline road, {p.foliage_density} foliage instances, {p.landmark_type} landmark. Unreal project `{p.project_name}`."
            )
        if isinstance(p, PlatformerParams):
            return (
                f"{p.display_title}: 3D obstacle course, {p.collectible_target} collectibles, "
                f"{p.difficulty} difficulty. Unreal project `{p.project_name}`."
            )
        if isinstance(p, ArenaCombatParams):
            return (
                f"{p.display_title}: {p.wave_count} waves, {p.enemies_per_wave} enemies/wave, "
                f"{p.difficulty} difficulty. Unreal project `{p.project_name}`."
            )
        if isinstance(p, CardBattlerParams):
            return (
                f"{p.display_title}: 3-lane card battler, base health {p.player_base_health}, "
                f"{p.difficulty} difficulty. Unreal project `{p.project_name}`."
            )
        opp = f"vs computer ({p.ai_level})" if p.vs_ai else "two players, hot-seat"
        return (
            f"{p.display_title}: {p.board_size}x{p.board_size} board{', pieces drop down' if p.gravity else ''}, "
            f"{p.win_length} in a row, {opp}. Unreal project `{p.project_name}`."
        )

    def to_dict(self) -> Dict:
        return {
            "matched": self.matched,
            "recipe_id": self.recipe_id,
            "recipe_title": self.recipe_title,
            "params": self.params.to_dict() if self.params else None,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "acceptance": self.acceptance,
            "summary": self.summary(),
        }


def is_game_creation_request(prompt: str) -> bool:
    """Delegate game creation intent classification to the canonical design.intent classifier."""
    from .intent import is_game_creation_request as _intent_is_creation

    return _intent_is_creation(prompt)


def _pascal(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    if not out or not out[0].isalpha():
        out = "Game" + out
    return out[:30]


def match_prompt(prompt: str) -> GameSpec:
    text = " " + prompt.lower().replace("’", "'") + " "
    best: Optional[RecipeEntry] = None
    best_kw = ""

    m_preset = re.search(r"\bpreset:([a-z0-9_]+)\b", prompt, re.I)
    if m_preset:
        p_name = m_preset.group(1).lower()
        recipe_alias = {
            "platformer": "platformer",
            "3d_platformer": "platformer",
            "arena_combat": "arena_combat",
            "arena": "arena_combat",
            "card_battler": "card_battler",
            "card_game": "card_battler",
            "procedural_world": "procedural_world",
            "grid_board_game": "grid_board_game",
            "grid_board": "grid_board_game",
            "tic_tac_toe": "grid_board_game",
            "gomoku": "grid_board_game",
            "connect_four": "grid_board_game",
        }
        target_recipe = recipe_alias.get(p_name)
        if target_recipe:
            for entry in RECIPES:
                if entry.recipe_id == target_recipe:
                    if target_recipe == "grid_board_game" and p_name in ("gomoku", "connect_four"):
                        if p_name in entry.keywords or p_name.replace("_", " ") in entry.keywords:
                            best = entry
                            best_kw = f"preset:{p_name}"
                            break
                    else:
                        best = entry
                        best_kw = f"preset:{p_name}"
                        break

    if best is None:
        for entry in RECIPES:
            for kw in entry.keywords:
                if re.search(rf"\b{re.escape(kw)}\b", text) and len(kw) > len(best_kw):
                    best, best_kw = entry, kw

        if best is not None and not m_preset:
            conflicting_genres = {"rpg", "puzzle", "dungeon", "survival", "roguelike", "stealth", "horror"}
            prompt_words = set(re.findall(r"\b\w+\b", text))
            if prompt_words.intersection(conflicting_genres):
                best = None

    if best is None:
        return GameSpec(
            False,
            reasons=[
                "no installed recipe matches this request; installed: "
                + ", ".join(sorted({r.title for r in RECIPES}))
            ],
        )

    d = dict(best.defaults)
    reasons = [f"matched recipe '{best.title}' on '{best_kw}'"]

    if best.recipe_id == "platformer":
        m = _TARGET.search(prompt)
        if m:
            d["collectible_target"] = int(m.group(1))
            reasons.append(f"collectible target {m.group(1)} from prompt")
        m = _DIFF.search(prompt)
        if m:
            d["difficulty"] = m.group(1).lower()
            reasons.append(f"difficulty '{d['difficulty']}' from prompt")
        m = _NAME.search(prompt)
        if m:
            title = m.group(1).strip()
            d["display_title"] = title
            d["project_name"] = _pascal(title)
            reasons.append(f"title '{title}' from prompt")
        params = PlatformerParams(
            project_name=d["project_name"],
            display_title=d["display_title"],
            collectible_target=d["collectible_target"],
            difficulty=d["difficulty"],
        )
        try:
            params.validate()
        except ValueError as exc:
            return GameSpec(False, best.recipe_id, best.title, reasons=reasons + [f"invalid parameters: {exc}"])
        acceptance = [
            f"build_ok({params.project_name}Editor Win64 Development)",
            f"automation_pass(GameForge.{params.project_name}.*)",
            "level_readback(SpawnPoint, Collectible, FinishVolume, DirectionalLight)",
            f"package_ok(Win64 Development) -> {params.project_name}.exe",
            "packaged_selftest(GF_PLATFORMER_SELFTEST PASS: goal reached, collectibles registered)",
            "packaged_screenshot_has_content",
        ]
        return GameSpec(True, best.recipe_id, best.title, params, 0.9, reasons, acceptance)

    if best.recipe_id == "arena_combat":
        m = _WAVES.search(prompt)
        if m:
            d["wave_count"] = int(m.group(1))
            reasons.append(f"wave count {m.group(1)} from prompt")
        m = _ENEMIES.search(prompt)
        if m:
            d["enemies_per_wave"] = int(m.group(1))
            reasons.append(f"enemies per wave {m.group(1)} from prompt")
        m = _DIFF.search(prompt)
        if m:
            d["difficulty"] = m.group(1).lower()
            reasons.append(f"difficulty '{d['difficulty']}' from prompt")
        m = _NAME.search(prompt)
        if m:
            title = m.group(1).strip()
            d["display_title"] = title
            d["project_name"] = _pascal(title)
            reasons.append(f"title '{title}' from prompt")
        params = ArenaCombatParams(
            project_name=d["project_name"],
            display_title=d["display_title"],
            wave_count=d["wave_count"],
            enemies_per_wave=d["enemies_per_wave"],
            difficulty=d["difficulty"],
        )
        try:
            params.validate()
        except ValueError as exc:
            return GameSpec(False, best.recipe_id, best.title, reasons=reasons + [f"invalid parameters: {exc}"])
        acceptance = [
            f"build_ok({params.project_name}Editor Win64 Development)",
            f"automation_pass(GameForge.{params.project_name}.*)",
            "level_readback(Sun, SkyFill, Arena_Floor, Wall_North, Wall_South, Wall_East, Wall_West, NavMeshBounds, PlayerStart)",
            f"package_ok(Win64 Development) -> {params.project_name}.exe",
            "packaged_selftest(GF_ARENA_SELFTEST PASS: player spawn, attack, enemy AI controller, enemy damage, wave progression, defeat, reset)",
            "packaged_screenshot_has_content",
        ]
        return GameSpec(True, best.recipe_id, best.title, params, 0.9, reasons, acceptance)

    if best.recipe_id == "procedural_world":
        if re.search(r"\b(mountain|mountains|alpine|peaks?)\b", text):
            d["terrain_type"] = "Mountains"
            reasons.append("terrain 'Mountains' from prompt")
        elif re.search(r"\b(plateau|mesa)\b", text):
            d["terrain_type"] = "Plateau"
            reasons.append("terrain 'Plateau' from prompt")
        elif re.search(r"\b(hills?|rolling hills?)\b", text):
            d["terrain_type"] = "Hills"
            reasons.append("terrain 'Hills' from prompt")
        elif re.search(r"\b(valley|canyon)\b", text):
            d["terrain_type"] = "Valley"
            reasons.append("terrain 'Valley' from prompt")

        if re.search(r"\b(tower|spire)\b", text):
            d["landmark_type"] = "Tower"
            reasons.append("landmark 'Tower' from prompt")
        elif re.search(r"\b(shrine|temple)\b", text):
            d["landmark_type"] = "Shrine"
            reasons.append("landmark 'Shrine' from prompt")
        elif re.search(r"\b(ruins?|ancient ruins?)\b", text):
            d["landmark_type"] = "Ruins"
            reasons.append("landmark 'Ruins' from prompt")

        m = _SEED.search(prompt)
        if m:
            d["seed"] = int(m.group(1))
            reasons.append(f"seed {d['seed']} from prompt")

        m = _DENSITY.search(prompt)
        if m:
            d["foliage_density"] = int(m.group(1))
            reasons.append(f"foliage density {d['foliage_density']} from prompt")

        m = _ELEVATION.search(prompt)
        if m:
            d["elevation_scale"] = float(m.group(1))
            reasons.append(f"elevation scale {d['elevation_scale']} from prompt")

        m = _NAME.search(prompt)
        if m:
            title = m.group(1).strip()
            d["display_title"] = title
            d["project_name"] = _pascal(title)
            reasons.append(f"title '{title}' from prompt")

        params = ProceduralWorldParams(
            project_name=d["project_name"],
            display_title=d["display_title"],
            seed=d.get("seed", 2026),
            terrain_type=d["terrain_type"],
            elevation_scale=d["elevation_scale"],
            road_width=d["road_width"],
            foliage_density=d["foliage_density"],
            landmark_type=d["landmark_type"],
        )
        try:
            params.validate()
        except ValueError as exc:
            return GameSpec(False, best.recipe_id, best.title, reasons=reasons + [f"invalid parameters: {exc}"])
        acceptance = [
            f"build_ok({params.project_name}Editor Win64 Development)",
            f"automation_pass(GameForge.{params.project_name}.*)",
            "level_readback(Sun, SkyFill, NavMeshBounds, PlayerStart)",
            f"package_ok(Win64 Development) -> {params.project_name}.exe",
            "packaged_selftest(GF_PROCEDURAL_SELFTEST PASS: landscape valid, player spawn, road traversal, landmark discovery, reset)",
            "packaged_screenshot_has_content",
        ]
        return GameSpec(True, best.recipe_id, best.title, params, 0.9, reasons, acceptance)

    if best.recipe_id == "card_battler":
        m = _HP.search(prompt)
        if m:
            hp = int(m.group(1))
            d["player_base_health"] = hp
            d["opponent_base_health"] = hp
            reasons.append(f"base health {hp} from prompt")
        m = _DIFF.search(prompt)
        if m:
            d["difficulty"] = m.group(1).lower()
            reasons.append(f"difficulty '{d['difficulty']}' from prompt")
        m = _NAME.search(prompt)
        if m:
            title = m.group(1).strip()
            d["display_title"] = title
            d["project_name"] = _pascal(title)
            reasons.append(f"title '{title}' from prompt")
        params = CardBattlerParams(
            project_name=d["project_name"],
            display_title=d["display_title"],
            player_base_health=d["player_base_health"],
            opponent_base_health=d["opponent_base_health"],
            difficulty=d["difficulty"],
        )
        try:
            params.validate()
        except ValueError as exc:
            return GameSpec(False, best.recipe_id, best.title, reasons=reasons + [f"invalid parameters: {exc}"])
        acceptance = [
            f"build_ok({params.project_name}Editor Win64 Development)",
            f"automation_pass(GameForge.{params.project_name}.*)",
            "level_readback(Sun, SkyFill, BattleMat, PlayerStart)",
            f"package_ok(Win64 Development) -> {params.project_name}.exe",
            "packaged_selftest(GF_CARD_SELFTEST PASS: deck integrity, no duplicate ids, energy spending, illegal play rejection, opponent AI, combat resolution, victory/defeat, reset)",
            "packaged_screenshot_has_content",
        ]
        return GameSpec(True, best.recipe_id, best.title, params, 0.9, reasons, acceptance)

    m = _SIZE.search(prompt)
    if m and m.group(1) == m.group(2):
        sz = int(m.group(1))
        d["board_size"] = 10 if sz >= 100 else max(3, min(15, sz))
        reasons.append(f"board {m.group(1)}x{m.group(2)} from prompt")
    m = _WIN.search(prompt)
    if m:
        d["win_length"] = int(m.group(1))
        reasons.append(f"win length {m.group(1)} from prompt")
    d["board_size"] = 10 if int(d.get("board_size", 3)) >= 100 else max(3, min(15, int(d.get("board_size", 3))))
    d["win_length"] = max(3, min(int(d.get("win_length", 3)), d["board_size"]))
    vs_ai = not _HOTSEAT.search(prompt)
    ai_level = "random" if _AI_EASY.search(prompt) else "greedy" if _AI_MED.search(prompt) else "perfect"
    m = _NAME.search(prompt)
    if m:
        title = m.group(1).strip()
        d["display_title"] = title
        d["project_name"] = _pascal(title)
        reasons.append(f"title '{title}' from prompt")
    colors = [c for c in _COLOR_WORDS if re.search(rf"\b{c}\b", text)]
    params = GridBoardParams(
        project_name=d["project_name"],
        display_title=d["display_title"],
        board_size=d["board_size"],
        win_length=d["win_length"],
        vs_ai=vs_ai,
        ai_level=ai_level,
        gravity=bool(d.get("gravity", False) or re.search(r"\b(gravity|drop|falling pieces)\b", text)),
    )
    if len(colors) >= 1:
        params.player1_color = _COLOR_WORDS[colors[0]]
    if len(colors) >= 2:
        params.player2_color = _COLOR_WORDS[colors[1]]
    try:
        params.validate()
    except ValueError as exc:
        return GameSpec(False, best.recipe_id, best.title, reasons=reasons + [f"invalid parameters: {exc}"])
    acceptance = [
        f"build_ok({params.project_name}Editor Win64 Development)",
        f"automation_pass(GameForge.{params.project_name}.*)",
        "level_readback(Table, Sun, SkyFill)",
        f"package_ok(Win64 Development) -> {params.project_name}.exe",
        "packaged_selftest(GF_SELFTEST PASS: row win, move rejection after end, full game vs AI)",
        "packaged_screenshot_has_content",
    ]
    return GameSpec(
        True,
        best.recipe_id,
        best.title,
        params,
        0.9 if best_kw != "board game" else 0.6,
        reasons,
        acceptance,
    )


spec_from_prompt = match_prompt

SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "display_title": {"type": "string"},
        "board_size": {"type": "integer"},
        "win_length": {"type": "integer"},
        "vs_ai": {"type": "boolean"},
        "ai_level": {"type": "string", "enum": ["random", "greedy", "perfect"]},
    },
    "required": ["display_title", "board_size", "win_length", "vs_ai", "ai_level"],
}


def refine_with_model(spec: GameSpec, prompt: str, complete_json: Callable[[str, Dict], Optional[str]]) -> GameSpec:
    """Let a model adjust parameters through a JSON schema. Invalid output is ignored."""
    if not spec.matched or not spec.params:
        return spec
    instruction = (
        "Extract game parameters for a grid board game from the request. Respond with JSON only.\n"
        f"Current defaults: {json.dumps({k: spec.params.to_dict()[k] for k in SPEC_SCHEMA['properties']})}\n"
        f"Request: {prompt}"
    )
    try:
        raw = complete_json(instruction, SPEC_SCHEMA)
        data = json.loads(raw or "")
    except Exception as exc:
        spec.reasons.append(f"model refinement skipped: {type(exc).__name__}")
        return spec
    candidate = GridBoardParams(
        **{**spec.params.to_dict(), **{k: data[k] for k in SPEC_SCHEMA["properties"] if k in data}}
    )
    candidate.project_name = (
        _pascal(candidate.display_title)
        if candidate.display_title != spec.params.display_title
        else spec.params.project_name
    )
    try:
        candidate.validate()
    except (ValueError, TypeError) as exc:
        spec.reasons.append(f"model output rejected: {exc}")
        return spec
    spec.params = candidate
    spec.reasons.append("parameters refined by model (validated)")
    return spec


_FLAG = re.compile(
    r"--(hotseat|gravity|size|win|ai|title|target|coins|difficulty|waves|enemies|hp|seed|density|terrain|landmark)(?:[=\s]+(\"[^\"]*\"|'[^']*'|[^\s-][^\s]*))?",
    re.I,
)


def expand_game_flags(text: str) -> str:
    """Turn `/game` shortcut flags into the phrases match_prompt understands."""
    phrases = []

    def sub(m):
        flag, val = m.group(1).lower(), (m.group(2) or "").strip("\"'")
        if flag == "hotseat":
            phrases.append("two player")
        elif flag == "gravity":
            phrases.append("gravity")
        elif flag == "size" and val.isdigit():
            phrases.append(f"{val}x{val}")
        elif flag == "win" and val.isdigit():
            phrases.append(f"{val} in a row")
        elif (flag == "target" or flag == "coins") and val.isdigit():
            phrases.append(f"{val} collectibles")
        elif flag == "difficulty" and val:
            phrases.append(f"{val}")
        elif flag == "waves" and val.isdigit():
            phrases.append(f"{val} waves")
        elif flag == "enemies" and val.isdigit():
            phrases.append(f"{val} enemies")
        elif flag == "hp" and val.isdigit():
            phrases.append(f"{val} hp")
        elif flag == "seed" and val.isdigit():
            phrases.append(f"seed {val}")
        elif flag == "density" and val.isdigit():
            phrases.append(f"{val} foliage")
        elif flag == "terrain" and val:
            phrases.append(f"{val} terrain")
        elif flag == "landmark" and val:
            phrases.append(f"{val} landmark")
        elif flag == "ai" and val:
            phrases.append(
                {"easy": "easy", "random": "easy", "medium": "medium", "greedy": "medium"}.get(val.lower(), "")
            )
        elif flag == "title" and val:
            phrases.append(f"called {val}.")
        return ""

    base = _FLAG.sub(sub, text).strip()
    return " ".join([base] + [p for p in phrases if p]).strip()


__all__ = [
    "RECIPES",
    "GameSpec",
    "RecipeEntry",
    "SPEC_SCHEMA",
    "is_game_creation_request",
    "match_prompt",
    "spec_from_prompt",
    "refine_with_model",
    "expand_game_flags",
    "_CREATE",
    "_GAME_WORD",
    "_CREATE_GAME",
    "_NOUN_GAME",
    "_SEED",
    "_DENSITY",
    "_SIZE",
    "_WIN",
    "_TARGET",
    "_WAVES",
    "_ENEMIES",
    "_HP",
    "_NAME",
    "_HOTSEAT",
    "_AI_EASY",
    "_AI_MED",
    "_DIFF",
    "_COLOR_WORDS",
    "_pascal",
    "_FLAG",
]
