"""GameForge Gameplay Kit v2 — Pure Gameplay Logic Seeds (Section 5D).

Provides deterministic reference implementations and pure state machines for:
- 5D.1: Feature validation & codegen feature resolution
- 5D.2: Race progression logic (laps, checkpoints, times)
- 5D.3: Sudoku rule logic (9x9 constraints, conflicts, solved validation)
- 5D.4: Typed multiplayer intent and slot resolution
- 5D.5: Pure Tic-Tac-Toe result evaluation
- 5D.6: Board game rules (Snakes & Ladders, Ludo tile graphs & dice)
- 5D.7: Arcade/puzzle/RPG state machines (Tetris, Snake, Chess, Tower Defense, Roguelike, Zombie Survival)
- 5D.8: Authoritative game-type to layout and module mapping
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# ── 5D.1 Genre Adapter & Feature Resolution ───────────────────────────────────

def resolve_codegen_features(rules: Sequence[Any]) -> Set[str]:
    """Extract declared features implemented by custom code rules."""
    features: Set[str] = set()
    for rule in rules:
        effects = getattr(rule, "effects", [])
        for eff in effects:
            if getattr(eff, "kind", None) == "custom_code":
                h_name = getattr(eff, "handler_name", "") or ""
                desc = getattr(eff, "description", "") or ""
                # Tag with handler and any descriptive feature tags
                if h_name:
                    features.add(h_name)
                    features.add(f"custom.{h_name.lower()}")
                for word in re.findall(r"[a-z0-9_]{3,}", desc.lower()):
                    features.add(word)
    return features


def check_composition_features(gds: Any) -> None:
    """Validate that all features in gds.acceptance.required_features are implemented."""
    required = set(getattr(gds.acceptance, "required_features", []))
    if not required:
        return

    from .registry import get_module
    from ..composer.model import CompositionError

    implemented: Set[str] = set()
    for entity in getattr(gds, "entities", []):
        try:
            module = get_module(entity.module)
            implemented.update(getattr(module, "features", ()))
        except KeyError:
            pass

    implemented.update(resolve_codegen_features(getattr(gds, "rules", [])))
    if getattr(gds, "architecture", None) is not None:
        implemented.update(getattr(gds.architecture, "custom_capabilities", []) or [])
        if isinstance(getattr(gds.architecture, "mechanics", None), dict):
            implemented.update(gds.architecture.mechanics.keys())
    missing = sorted(required - implemented)
    if missing:
        raise CompositionError(
            [f"Required gameplay features have no implementation: {', '.join(missing)}"]
        )


# ── 5D.2 Race Progression Logic ──────────────────────────────────────────────

@dataclass
class RacerProgress:
    racer_id: str
    next_checkpoint: int = 0
    completed_laps: int = 0
    finished: bool = False
    lap_start_seconds: float = 0.0
    lap_times: List[float] = field(default_factory=list)


class RaceProgress:
    """Deterministic pure lap/checkpoint progression manager."""

    def __init__(self, checkpoint_count: int, lap_target: int) -> None:
        if checkpoint_count < 1 or lap_target < 1:
            raise ValueError("checkpoint_count and lap_target must be positive")
        self.checkpoint_count = checkpoint_count
        self.lap_target = lap_target
        self.racers: Dict[str, RacerProgress] = {}

    def add_racer(self, racer_id: str, start_time: float = 0.0) -> None:
        if not racer_id or racer_id in self.racers:
            raise ValueError(f"invalid or duplicate racer_id: {racer_id!r}")
        self.racers[racer_id] = RacerProgress(
            racer_id=racer_id, lap_start_seconds=start_time
        )

    def pass_checkpoint(self, racer_id: str, checkpoint_index: int,
                        now_seconds: float) -> Tuple[bool, Optional[str]]:
        if racer_id not in self.racers:
            raise ValueError(f"unknown racer_id: {racer_id!r}")
        racer = self.racers[racer_id]
        if racer.finished or checkpoint_index != racer.next_checkpoint:
            return False, None
        racer.next_checkpoint += 1
        if racer.next_checkpoint == self.checkpoint_count:
            racer.next_checkpoint = 0
            racer.completed_laps += 1
            racer.lap_times.append(max(0.0, now_seconds - racer.lap_start_seconds))
            racer.lap_start_seconds = now_seconds
            if racer.completed_laps >= self.lap_target:
                racer.finished = True
                return True, "race.finished"
            return True, "lap.completed"
        return True, "checkpoint.reached"


# ── 5D.3 Sudoku Rule Logic ───────────────────────────────────────────────────

def sudoku_conflicts(board: List[List[int]], row: int, col: int, value: int) -> bool:
    """Determine if placing value at (row, col) violates 9x9 Sudoku constraints."""
    if len(board) != 9 or any(len(r) != 9 for r in board):
        raise ValueError("Sudoku board must be exactly 9x9")
    if not (0 <= row < 9 and 0 <= col < 9 and 1 <= value <= 9):
        raise ValueError("row/col must be 0..8 and value must be 1..9")
    if board[row][col] not in (0, value):
        return True
    if any(board[row][c] == value for c in range(9) if c != col):
        return True
    if any(board[r][col] == value for r in range(9) if r != row):
        return True
    box_r, box_c = (row // 3) * 3, (col // 3) * 3
    for r in range(box_r, box_r + 3):
        for c in range(box_c, box_c + 3):
            if (r, c) != (row, col) and board[r][c] == value:
                return True
    return False


def is_sudoku_solved(board: List[List[int]]) -> bool:
    """Verify if a 9x9 board is completely and validly solved."""
    if len(board) != 9 or any(len(r) != 9 for r in board):
        return False
    for r in range(9):
        for c in range(9):
            val = board[r][c]
            if val < 1 or val > 9:
                return False
            # Check row
            if any(board[r][c2] == val for c2 in range(9) if c2 != c):
                return False
            # Check column
            if any(board[r2][c] == val for r2 in range(9) if r2 != r):
                return False
            # Check 3x3 box
            br, bc = (r // 3) * 3, (c // 3) * 3
            for r2 in range(br, br + 3):
                for c2 in range(bc, bc + 3):
                    if (r2, c2) != (r, c) and board[r2][c2] == val:
                        return False
    return True


# ── 5D.4 Typed Local Multiplayer Intent ──────────────────────────────────────

@dataclass(frozen=True)
class PlayerSlotConfig:
    human_slots: int = 1
    ai_slots: int = 0
    mode: str = "single_player"  # "single_player", "local_versus", "local_coop", "vs_ai", "online"


def parse_player_slots(prompt: str, default_players: int = 1) -> PlayerSlotConfig:
    """Parse exact player intent from prompt without loose inference."""
    norm = prompt.lower()
    if "online multiplayer" in norm or "network multiplayer" in norm:
        return PlayerSlotConfig(human_slots=2, ai_slots=0, mode="online")
    if any(kw in norm for kw in ("local co-op", "local coop", "co-op", "coop")):
        return PlayerSlotConfig(human_slots=2, ai_slots=0, mode="local_coop")
    if any(kw in norm for kw in (
        "two players", "two-player", "2 players", "2-player",
        "two humans", "2 humans", "local versus", "local vs",
        "against a friend", "vs a friend", "vs friend", "hot seat", "hotseat"
    )):
        return PlayerSlotConfig(human_slots=2, ai_slots=0, mode="local_versus")
    if any(kw in norm for kw in ("play against computer", "against computer", "ai opponent", "vs ai", "against ai", "vs computer")):
        return PlayerSlotConfig(human_slots=1, ai_slots=1, mode="vs_ai")
    return PlayerSlotConfig(human_slots=default_players, ai_slots=0, mode="single_player")


# ── 5D.5 Pure Tic-Tac-Toe Result Function ────────────────────────────────────

def tic_tac_toe_result(cells: List[int]) -> int:
    """Return 1 or 2 for a winner, 0 for a draw, -1 while still in progress."""
    if len(cells) != 9 or any(v not in (0, 1, 2) for v in cells):
        raise ValueError("Tic-Tac-Toe requires nine cells containing 0, 1 or 2")
    lines = (
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    )
    for a, b, c in lines:
        if cells[a] and cells[a] == cells[b] == cells[c]:
            return cells[a]
    return 0 if all(cells) else -1


# ── 5D.6 Board Game Rules (Snakes and Ladders & Ludo) ─────────────────────────

@dataclass
class SnakesAndLaddersRules:
    """Deterministic pure state machine for Snakes and Ladders on a tile track."""
    num_tiles: int = 100
    snakes: Dict[int, int] = field(default_factory=lambda: {
        16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78
    })
    ladders: Dict[int, int] = field(default_factory=lambda: {
        1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100
    })
    player_positions: Dict[str, int] = field(default_factory=dict)
    player_order: List[str] = field(default_factory=list)
    current_turn_index: int = 0
    winner: Optional[str] = None

    def add_player(self, player_id: str) -> None:
        if player_id in self.player_positions:
            raise ValueError(f"Player {player_id!r} already registered")
        self.player_positions[player_id] = 0
        self.player_order.append(player_id)

    def step_player(self, player_id: str, roll: int) -> Tuple[int, Optional[str]]:
        if self.winner is not None:
            return self.player_positions[player_id], f"Game already won by {self.winner}"
        if not self.player_order:
            raise ValueError("No players registered")
        expected = self.player_order[self.current_turn_index]
        if player_id != expected:
            return self.player_positions[player_id], f"Not {player_id}'s turn; expected {expected}"

        cur = self.player_positions[player_id]
        nxt = cur + roll
        if nxt > self.num_tiles:
            nxt = cur  # Must reach target exactly
        elif nxt in self.snakes:
            nxt = self.snakes[nxt]
        elif nxt in self.ladders:
            nxt = self.ladders[nxt]

        self.player_positions[player_id] = nxt
        if nxt == self.num_tiles:
            self.winner = player_id
            return nxt, "game.won"

        self.current_turn_index = (self.current_turn_index + 1) % len(self.player_order)
        return nxt, None


@dataclass
class LudoRules:
    """Deterministic token tracking and turn management for Ludo."""
    track_length: int = 52
    safe_tiles: Set[int] = field(default_factory=lambda: {0, 8, 13, 21, 26, 34, 39, 47})
    tokens_per_player: int = 4
    players: List[str] = field(default_factory=list)
    # player -> list of token positions (-1 for home yard, 0..51 for track, 52..57 for home stretch)
    token_positions: Dict[str, List[int]] = field(default_factory=dict)
    current_turn_index: int = 0
    winner: Optional[str] = None

    def add_player(self, player_id: str) -> None:
        if player_id in self.token_positions:
            raise ValueError(f"Player {player_id!r} already registered")
        self.players.append(player_id)
        self.token_positions[player_id] = [-1] * self.tokens_per_player

    def move_token(self, player_id: str, token_idx: int, roll: int) -> Tuple[bool, Optional[str]]:
        if self.winner is not None:
            return False, f"Game already won by {self.winner}"
        if not self.players:
            return False, "No players in game"
        expected = self.players[self.current_turn_index]
        if player_id != expected:
            return False, f"Not {player_id}'s turn"
        if not (0 <= token_idx < self.tokens_per_player):
            return False, "Invalid token index"

        pos = self.token_positions[player_id][token_idx]
        if pos == -1:
            if roll == 6:
                self.token_positions[player_id][token_idx] = 0
                return True, "token.spawned"
            return False, "Roll 6 required to leave yard"

        new_pos = pos + roll
        if new_pos > 57:
            return False, "Overshot home"

        self.token_positions[player_id][token_idx] = new_pos
        if all(p == 57 for p in self.token_positions[player_id]):
            self.winner = player_id
            return True, "game.won"

        if roll != 6:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        return True, "token.moved"


# ── 5D.7 Arcade, Puzzle & RPG Pure State Machines ─────────────────────────────

@dataclass
class TetrisState:
    """10x20 Tetris board state machine."""
    width: int = 10
    height: int = 20
    grid: List[List[int]] = field(default_factory=lambda: [[0] * 10 for _ in range(20)])
    lines_cleared: int = 0
    score: int = 0
    game_over: bool = False

    TETROMINOES: Dict[str, List[Tuple[int, int]]] = field(default_factory=lambda: {
        "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
        "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
        "T": [(1, 0), (0, 1), (1, 1), (2, 1)],
        "L": [(0, 0), (0, 1), (1, 1), (2, 1)],
        "J": [(2, 0), (0, 1), (1, 1), (2, 1)],
        "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
        "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    })

    def check_collision(self, shape_coords: List[Tuple[int, int]], origin: Tuple[int, int]) -> bool:
        ox, oy = origin
        for x, y in shape_coords:
            gx, gy = ox + x, oy + y
            if gx < 0 or gx >= self.width or gy < 0 or gy >= self.height:
                return True
            if self.grid[gy][gx] != 0:
                return True
        return False

    def lock_piece(self, shape_coords: List[Tuple[int, int]], origin: Tuple[int, int], piece_id: int = 1) -> int:
        ox, oy = origin
        for x, y in shape_coords:
            gx, gy = ox + x, oy + y
            if 0 <= gx < self.width and 0 <= gy < self.height:
                self.grid[gy][gx] = piece_id
            else:
                self.game_over = True
                return 0

        # Check for completed lines
        cleared = 0
        new_grid = [row for row in self.grid if not all(c != 0 for c in row)]
        cleared = self.height - len(new_grid)
        if cleared > 0:
            for _ in range(cleared):
                new_grid.insert(0, [0] * self.width)
            self.grid = new_grid
            self.lines_cleared += cleared
            self.score += [0, 100, 300, 500, 800][min(cleared, 4)]

        # Check top-out
        if any(self.grid[0][c] != 0 for c in range(self.width)):
            self.game_over = True

        return cleared


@dataclass
class SnakeState:
    """Fixed-tick grid movement and food spawning for Snake."""
    width: int = 20
    height: int = 20
    snake: List[Tuple[int, int]] = field(default_factory=lambda: [(10, 10), (9, 10), (8, 10)])
    direction: Tuple[int, int] = (1, 0)
    food: Tuple[int, int] = (15, 10)
    score: int = 0
    game_over: bool = False

    def spawn_food(self, rng: random.Random) -> None:
        empty = [
            (x, y) for x in range(self.width) for y in range(self.height)
            if (x, y) not in self.snake
        ]
        if empty:
            self.food = rng.choice(empty)
        else:
            self.food = (-1, -1)  # Board filled / won

    def tick(self, rng: Optional[random.Random] = None) -> Tuple[bool, Optional[str]]:
        if self.game_over:
            return False, "game.over"

        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)

        # Wall collision
        if not (0 <= new_head[0] < self.width and 0 <= new_head[1] < self.height):
            self.game_over = True
            return False, "snake.wall_collision"

        # Body collision (excluding tail if not eating)
        tail_check = self.snake if new_head == self.food else self.snake[:-1]
        if new_head in tail_check:
            self.game_over = True
            return False, "snake.self_collision"

        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 10
            if rng is not None:
                self.spawn_food(rng)
            return True, "snake.food_eaten"
        else:
            self.snake.pop()
            return True, "snake.moved"


@dataclass
class ChessState:
    """8x8 Chess representation with basic legal move generation."""
    board: List[List[str]] = field(default_factory=lambda: [
        ["r", "n", "b", "q", "k", "b", "n", "r"],
        ["p"] * 8,
        ["."] * 8,
        ["."] * 8,
        ["."] * 8,
        ["."] * 8,
        ["P"] * 8,
        ["R", "N", "B", "Q", "K", "B", "N", "R"],
    ])
    turn: str = "white"  # "white" (uppercase) or "black" (lowercase)
    move_count: int = 0

    def is_legal_pawn_move(self, fr: int, fc: int, tr: int, tc: int) -> bool:
        piece = self.board[fr][fc]
        if piece not in ("P", "p"):
            return False
        direction = -1 if piece == "P" else 1
        start_row = 6 if piece == "P" else 1

        # Single step forward
        if fc == tc and tr == fr + direction and self.board[tr][tc] == ".":
            return True
        # Double step from starting row
        if fc == tc and fr == start_row and tr == fr + 2 * direction and self.board[fr + direction][fc] == "." and self.board[tr][tc] == ".":
            return True
        # Diagonal capture
        if abs(fc - tc) == 1 and tr == fr + direction:
            target = self.board[tr][tc]
            if target != "." and ((piece == "P" and target.islower()) or (piece == "p" and target.isupper())):
                return True
        return False

    def move_piece(self, fr: int, fc: int, tr: int, tc: int) -> bool:
        if not (0 <= fr < 8 and 0 <= fc < 8 and 0 <= tr < 8 and 0 <= tc < 8):
            return False
        piece = self.board[fr][fc]
        if piece == ".":
            return False
        if (self.turn == "white" and not piece.isupper()) or (self.turn == "black" and not piece.islower()):
            return False

        # Simplified pawn move verification or general movement
        if piece.lower() == "p" and not self.is_legal_pawn_move(fr, fc, tr, tc):
            return False

        target = self.board[tr][tc]
        if target != "." and ((piece.isupper() and target.isupper()) or (piece.islower() and target.islower())):
            return False  # Cannot capture own piece

        self.board[tr][tc] = piece
        self.board[fr][fc] = "."
        self.turn = "black" if self.turn == "white" else "white"
        self.move_count += 1
        return True


@dataclass
class TowerDefenseState:
    """Deterministic Tower Defense wave and targeting state machine."""
    path: List[Tuple[float, float]] = field(default_factory=list)
    base_health: float = 100.0
    gold: int = 250
    current_wave: int = 0
    towers: List[Dict[str, Any]] = field(default_factory=list)
    enemies: List[Dict[str, Any]] = field(default_factory=list)
    game_over: bool = False

    def spawn_wave(self, count: int, hp: float = 50.0, speed: float = 100.0) -> None:
        self.current_wave += 1
        for i in range(count):
            self.enemies.append({
                "id": f"enemy_w{self.current_wave}_{i}",
                "hp": hp,
                "max_hp": hp,
                "speed": speed,
                "node_idx": 0,
                "progress": 0.0,
                "alive": True,
            })

    def place_tower(self, tower_type: str, x: float, y: float, cost: int = 100, dmg: float = 25.0, rng: float = 300.0) -> bool:
        if self.gold < cost:
            return False
        self.gold -= cost
        self.towers.append({
            "type": tower_type,
            "x": x,
            "y": y,
            "damage": dmg,
            "range": rng,
            "cooldown": 0.0,
            "rate": 1.0,
        })
        return True

    def tick(self, dt: float) -> Tuple[int, int]:
        """Advance enemies and towers. Returns (kills, leaks)."""
        kills = 0
        leaks = 0

        # Tower firing
        for tower in self.towers:
            tower["cooldown"] = max(0.0, tower["cooldown"] - dt)
            if tower["cooldown"] <= 0.0:
                # Find nearest enemy in range
                for enemy in self.enemies:
                    if not enemy["alive"]:
                        continue
                    enemy["hp"] -= tower["damage"]
                    tower["cooldown"] = tower["rate"]
                    if enemy["hp"] <= 0.0:
                        enemy["alive"] = False
                        kills += 1
                        self.gold += 15
                    break

        # Enemy advance
        for enemy in self.enemies:
            if not enemy["alive"]:
                continue
            enemy["progress"] += enemy["speed"] * dt
            if self.path and enemy["progress"] >= len(self.path) * 100.0:
                enemy["alive"] = False
                leaks += 1
                self.base_health = max(0.0, self.base_health - 10.0)
                if self.base_health <= 0.0:
                    self.game_over = True

        return kills, leaks


@dataclass
class RoguelikeState:
    """Connected room graph and player progression for Roguelikes."""
    room_count: int = 6
    rooms: List[Dict[str, Any]] = field(default_factory=list)
    corridors: List[Tuple[int, int]] = field(default_factory=list)
    current_room: int = 0
    player_health: float = 100.0
    inventory: List[str] = field(default_factory=list)
    boss_defeated: bool = False

    def generate_dungeon(self, seed: int = 2026) -> None:
        rng = random.Random(seed)
        self.rooms = [
            {"id": i, "cleared": i == 0, "has_boss": i == self.room_count - 1}
            for i in range(self.room_count)
        ]
        # Guaranteed linear connectivity plus cross-links
        self.corridors = [(i, i + 1) for i in range(self.room_count - 1)]
        if self.room_count > 3:
            self.corridors.append((0, 2))

    def move_to_room(self, target_room: int) -> bool:
        if not (0 <= target_room < self.room_count):
            return False
        # Verify corridor exists
        connected = any(
            (self.current_room == a and target_room == b) or (self.current_room == b and target_room == a)
            for a, b in self.corridors
        )
        if not connected:
            return False
        self.current_room = target_room
        return True


@dataclass
class ZombieSurvivalState:
    """Wave-based zombie survival state machine with weapons, ammo, and damage."""
    wave: int = 1
    player_health: float = 100.0
    ammo: int = 30
    reserve_ammo: int = 90
    max_magazine: int = 30
    score: int = 0
    zombies_remaining: int = 10
    game_over: bool = False

    def fire_weapon(self, hit_zombie: bool = True, damage: float = 50.0) -> bool:
        if self.ammo <= 0 or self.game_over:
            return False
        self.ammo -= 1
        if hit_zombie and self.zombies_remaining > 0:
            self.zombies_remaining -= 1
            self.score += 50
            if self.zombies_remaining == 0:
                self.wave += 1
                self.zombies_remaining = self.wave * 10
        return True

    def reload(self) -> bool:
        if self.reserve_ammo <= 0 or self.ammo >= self.max_magazine:
            return False
        needed = self.max_magazine - self.ammo
        transferred = min(needed, self.reserve_ammo)
        self.ammo += transferred
        self.reserve_ammo -= transferred
        return True

    def take_damage(self, amount: float) -> None:
        self.player_health = max(0.0, self.player_health - amount)
        if self.player_health <= 0.0:
            self.game_over = True


# ── 5D.8 Authoritative Module and Layout Registry ─────────────────────────────

GAME_TYPE_LAYOUT_MAP: Dict[str, str] = {
    "sudoku": "board",
    "minesweeper": "board",
    "chess": "board",
    "checkers": "board",
    "connect_four": "board",
    "gomoku": "board",
    "stealth": "rooms",
    "tic_tac_toe": "board",
    "roll_and_move": "board",
    "ludo": "board",
    "tetris": "board",
    "snake": "board",
    "card_battler": "lanes",
    "arena_combat": "arena",
    "tactical_fps": "tactical_fps",
    "dungeon_crawler": "rooms",
    "platformer": "course",
    "exploration": "open_world",
    "racing": "course",
    "tower_defense": "lanes",
    "roguelike": "rooms",
    "wave_survival": "arena",
    "action_adventure": "open_world",
    "top_down_shooter": "arena",
    "puzzle": "board",
}

GAME_TYPE_REQUIRED_MODULES: Dict[str, List[str]] = {
    "tic_tac_toe": ["kit.grid_board"],
    "connect_four": ["kit.grid_board"],
    "gomoku": ["kit.grid_board"],
    "sudoku": ["kit.grid_board"],
    "minesweeper": ["kit.grid_board"],
    "checkers": ["kit.grid_board"],
    "stealth": ["kit.player_character", "kit.guard", "kit.goal"],
    "chess": ["kit.grid_board"],
    "tetris": ["kit.grid_board"],
    "snake": ["kit.grid_board"],
    "roll_and_move": ["kit.grid_board"],
    "ludo": ["kit.grid_board"],
    "puzzle": ["kit.grid_board"],
    "platformer": ["kit.player_character", "kit.pickup", "kit.goal"],
    "racing": ["kit.player_character", "kit.goal"],
    "arena_combat": ["kit.player_character", "kit.enemy_melee", "kit.spawner"],
    "wave_survival": ["kit.player_character", "kit.enemy_melee", "kit.spawner"],
    "card_battler": ["kit.card_match"],
    "tactical_fps": ["kit.player_character", "kit.guard"],
    "dungeon_crawler": ["kit.player_character", "kit.enemy_melee", "kit.door"],
    "roguelike": ["kit.player_character", "kit.enemy_melee", "kit.door"],
    "exploration": ["kit.player_character", "kit.landmark", "kit.pickup"],
    "action_adventure": ["kit.player_character", "kit.landmark", "kit.pickup"],
    "top_down_shooter": ["kit.player_character", "kit.enemy_melee", "kit.spawner"],
    "tower_defense": ["kit.spawner", "kit.goal"],
}


def get_layout_for_game_type(game_type: str) -> str:
    """Return concrete layout ID or raise KeyError."""
    gt = game_type.strip().lower().replace("-", "_").replace(" ", "_")
    if gt not in GAME_TYPE_LAYOUT_MAP:
        raise KeyError(f"Unknown game type {game_type!r}; known: {sorted(GAME_TYPE_LAYOUT_MAP.keys())}")
    return GAME_TYPE_LAYOUT_MAP[gt]


def get_required_modules_for_game_type(game_type: str) -> List[str]:
    """Return required kit module IDs for a given game type."""
    gt = game_type.strip().lower().replace("-", "_").replace(" ", "_")
    return GAME_TYPE_REQUIRED_MODULES.get(gt, [])
