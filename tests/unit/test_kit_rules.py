"""Unit tests for GameForge Kit Rules & Pure Gameplay Logic Seeds (Section 5D & 5E)."""
from __future__ import annotations

import random
import pytest

from src.gameforge_ide.kit.evaluator import ConditionEvaluator, EvaluationContext
from src.gameforge_ide.kit.rules import (
    RaceProgress,
    RacerProgress,
    sudoku_conflicts,
    is_sudoku_solved,
    parse_player_slots,
    PlayerSlotConfig,
    tic_tac_toe_result,
    SnakesAndLaddersRules,
    LudoRules,
    TetrisState,
    SnakeState,
    ChessState,
    TowerDefenseState,
    RoguelikeState,
    ZombieSurvivalState,
    GAME_TYPE_LAYOUT_MAP,
    get_layout_for_game_type,
    get_required_modules_for_game_type,
    resolve_codegen_features,
    check_composition_features,
)
from src.gameforge_ide.design.gds import (
    Acceptance,
    CustomCode,
    EntityKind,
    EntitySpec,
    EventRef,
    GameDesignSpec,
    RuleSpec,
)
from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.composer.model import CompositionError


# ── Section 5E.1: Evaluator Contract Verification ─────────────────────────────

def test_evaluator_public_contract():
    """Section 5E.1: Use the real evaluator API in tests."""
    ctx = EvaluationContext(
        get_stat=lambda name: 3.0 if name == "game.score" else float("nan"),
        count_events=lambda event, entity: 2 if event == "pickup.collected" else 0,
        has_event=lambda event, entity: event == "game.started",
    )
    result, error = ConditionEvaluator.evaluate(
        {
            "kind": "all",
            "items": [
                {"kind": "stat", "stat": "game.score", "op": ">=", "value": 3},
                {"kind": "count_at_least", "event": "pickup.collected", "n": 2},
            ],
        },
        ctx,
    )
    assert error is None
    assert result is True


# ── Section 5D.1: Feature Resolution & Composition Features ───────────────────

def test_resolve_codegen_features_and_composition_check():
    """Section 5D.1: Ensure custom rules declare features and composition validates them."""
    rules = [
        RuleSpec(
            rule_id="r1",
            description="Double jump mechanic with boost",
            when=EventRef(event="player.jumped"),
            effects=[
                CustomCode(
                    kind="custom_code",
                    handler_name="DoubleJumpRule",
                    description="Execute double jump impulse",
                    on_event_body="// jump",
                )
            ],
        )
    ]
    features = resolve_codegen_features(rules)
    assert "DoubleJumpRule" in features
    assert "custom.doublejumprule" in features
    assert "jump" in features

    gds = preset_platformer()
    gds.rules = rules
    gds.acceptance.required_features = ["DoubleJumpRule"]
    # Should not raise
    check_composition_features(gds)

    # Missing feature should raise CompositionError
    gds.acceptance.required_features = ["DoubleJumpRule", "grappling_hook"]
    with pytest.raises(CompositionError) as exc_info:
        check_composition_features(gds)
    assert "grappling_hook" in str(exc_info.value)


# ── Section 5D.2: Race Progression Logic ──────────────────────────────────────

def test_race_progression_deterministic_state():
    """Section 5D.2: Lap/checkpoint sequencing and lap time recording."""
    race = RaceProgress(checkpoint_count=3, lap_target=2)
    race.add_racer("racer_1", start_time=10.0)

    # Checkpoint 0 reached
    ok, ev = race.pass_checkpoint("racer_1", 0, now_seconds=12.5)
    assert ok is True
    assert ev == "checkpoint.reached"

    # Out of order checkpoint rejected
    ok, ev = race.pass_checkpoint("racer_1", 2, now_seconds=15.0)
    assert ok is False and ev is None

    # Checkpoint 1 reached
    ok, ev = race.pass_checkpoint("racer_1", 1, now_seconds=15.0)
    assert ok is True and ev == "checkpoint.reached"

    # Lap 1 finished (checkpoint 2 reached)
    ok, ev = race.pass_checkpoint("racer_1", 2, now_seconds=20.0)
    assert ok is True
    assert ev == "lap.completed"
    assert len(race.racers["racer_1"].lap_times) == 1
    assert race.racers["racer_1"].lap_times[0] == 10.0

    # Lap 2: CP 0, 1, 2 => race finished
    race.pass_checkpoint("racer_1", 0, 25.0)
    race.pass_checkpoint("racer_1", 1, 30.0)
    ok, ev = race.pass_checkpoint("racer_1", 2, 35.0)
    assert ok is True
    assert ev == "race.finished"
    assert race.racers["racer_1"].finished is True


# ── Section 5D.3: Sudoku Rule Logic ───────────────────────────────────────────

def test_sudoku_rule_logic_conflicts_and_solution():
    """Section 5D.3: 9x9 row, column, and box constraints."""
    # Empty 9x9 board
    board = [[0] * 9 for _ in range(9)]

    # Out of bounds value raises ValueError
    with pytest.raises(ValueError):
        sudoku_conflicts(board, 0, 0, 10)

    # Place a 5 at (0, 0)
    board[0][0] = 5

    # Same row conflict
    assert sudoku_conflicts(board, 0, 3, 5) is True
    assert sudoku_conflicts(board, 0, 3, 6) is False

    # Same column conflict
    assert sudoku_conflicts(board, 4, 0, 5) is True
    assert sudoku_conflicts(board, 4, 0, 7) is False

    # Same 3x3 box conflict
    assert sudoku_conflicts(board, 1, 1, 5) is True
    assert sudoku_conflicts(board, 1, 1, 8) is False

    # Distant cell no conflict
    assert sudoku_conflicts(board, 5, 5, 5) is False

    # Solved board validation
    valid_solved = [
        [5, 3, 4, 6, 7, 8, 9, 1, 2],
        [6, 7, 2, 1, 9, 5, 3, 4, 8],
        [1, 9, 8, 3, 4, 2, 5, 6, 7],
        [8, 5, 9, 7, 6, 1, 4, 2, 3],
        [4, 2, 6, 8, 5, 3, 7, 9, 1],
        [7, 1, 3, 9, 2, 4, 8, 5, 6],
        [9, 6, 1, 5, 3, 7, 2, 8, 4],
        [2, 8, 7, 4, 1, 9, 6, 3, 5],
        [3, 4, 5, 2, 8, 6, 1, 7, 9],
    ]
    assert is_sudoku_solved(valid_solved) is True

    # Mutate to create conflict
    valid_solved[0][0] = 6
    assert is_sudoku_solved(valid_solved) is False


# ── Section 5D.4: Typed Multiplayer Intent ────────────────────────────────────

def test_typed_multiplayer_intent():
    """Section 5D.4: Distinguish two human players from AI-controlled opponents."""
    cfg1 = parse_player_slots("make a two players local versus game")
    assert cfg1.mode == "local_versus"
    assert cfg1.human_slots == 2
    assert cfg1.ai_slots == 0

    cfg2 = parse_player_slots("play against computer in chess")
    assert cfg2.mode == "vs_ai"
    assert cfg2.human_slots == 1
    assert cfg2.ai_slots == 1

    cfg3 = parse_player_slots("create a 2-player local co-op platformer")
    assert cfg3.mode == "local_coop"
    assert cfg3.human_slots == 2

    cfg4 = parse_player_slots("an online multiplayer battle arena")
    assert cfg4.mode == "online"


# ── Section 5D.5: Pure Tic-Tac-Toe Result ─────────────────────────────────────

def test_pure_tic_tac_toe_result():
    """Section 5D.5: Reference Tic-Tac-Toe result evaluator."""
    # In progress
    assert tic_tac_toe_result([0] * 9) == -1

    # Row 0 win for player 1
    assert tic_tac_toe_result([1, 1, 1, 2, 2, 0, 0, 0, 0]) == 1

    # Col 1 win for player 2
    assert tic_tac_toe_result([1, 2, 0, 1, 2, 0, 0, 2, 1]) == 2

    # Diagonal win for player 1
    assert tic_tac_toe_result([1, 2, 0, 0, 1, 2, 0, 0, 1]) == 1

    # Draw
    draw_board = [
        1, 2, 1,
        1, 2, 2,
        2, 1, 1,
    ]
    assert tic_tac_toe_result(draw_board) == 0


# ── Section 5D.6: Board Game Rules (Snakes and Ladders & Ludo) ─────────────────

def test_snakes_and_ladders_rules():
    """Section 5D.6: Tile graph progression, ladders, snakes, and turn order."""
    game = SnakesAndLaddersRules()
    game.add_player("p1")
    game.add_player("p2")

    # Player 1 rolls 1 => lands on ladder tile 1 -> climbs to 38
    pos, ev = game.step_player("p1", 1)
    assert pos == 38
    assert ev is None

    # Not p1's turn
    pos2, err = game.step_player("p1", 3)
    assert "expected p2" in err

    # Player 2 rolls 4 => lands on ladder tile 4 -> climbs to 14
    pos, ev = game.step_player("p2", 4)
    assert pos == 14

    # Player 1 rolls into a snake (e.g. from 38 rolls 9 to 47 -> slides to 26)
    pos, ev = game.step_player("p1", 9)
    assert pos == 26


def test_ludo_rules():
    """Section 5D.6: Ludo token yard exit and home progression."""
    ludo = LudoRules()
    ludo.add_player("red")

    # Roll 5 cannot leave yard
    ok, msg = ludo.move_token("red", 0, 5)
    assert ok is False

    # Roll 6 spawns token onto track
    ok, msg = ludo.move_token("red", 0, 6)
    assert ok is True
    assert msg == "token.spawned"
    assert ludo.token_positions["red"][0] == 0


# ── Section 5D.7: Arcade, Puzzle & RPG State Machines ─────────────────────────

def test_tetris_state():
    """Section 5D.7: Tetris board collision and line clearing."""
    tetris = TetrisState()
    # O piece (2x2) at origin (0, 0)
    o_shape = tetris.TETROMINOES["O"]
    assert tetris.check_collision(o_shape, (0, 0)) is False

    # Fill row 19 except for (0, 19) and (1, 19)
    for c in range(2, 10):
        tetris.grid[19][c] = 2

    # Lock O piece at (0, 18) filling row 18 and 19
    cleared = tetris.lock_piece(o_shape, (0, 18), piece_id=1)
    # Row 19 should have cleared
    assert cleared == 1
    assert tetris.lines_cleared == 1
    assert tetris.score == 100


def test_snake_state():
    """Section 5D.7: Snake grid movement, food eating, and collision."""
    snake = SnakeState(snake=[(5, 5), (4, 5)], direction=(1, 0), food=(6, 5))
    # Tick forward onto food
    ok, ev = snake.tick()
    assert ok is True
    assert ev == "snake.food_eaten"
    assert len(snake.snake) == 3
    assert snake.score == 10

    # Turn into wall
    snake.direction = (0, -1)
    snake.snake = [(0, 0), (0, 1)]
    ok, ev = snake.tick()
    assert ok is False
    assert ev == "snake.wall_collision"


def test_chess_state():
    """Section 5D.7: 8x8 Chess pawn move and turn alternation."""
    chess = ChessState()
    assert chess.turn == "white"

    # White pawn from (6, 4) to (4, 4) (e2 to e4 double-step)
    ok = chess.move_piece(6, 4, 4, 4)
    assert ok is True
    assert chess.board[4][4] == "P"
    assert chess.board[6][4] == "."
    assert chess.turn == "black"

    # Black pawn from (1, 4) to (3, 4)
    ok = chess.move_piece(1, 4, 3, 4)
    assert ok is True
    assert chess.turn == "white"


def test_tower_defense_state():
    """Section 5D.7: Tower placement, range targeting, and damage."""
    td = TowerDefenseState(path=[(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)])
    assert td.gold == 250
    ok = td.place_tower("cannon", 50.0, 0.0, cost=100, dmg=50.0, rng=200.0)
    assert ok is True
    assert td.gold == 150

    td.spawn_wave(count=1, hp=50.0, speed=10.0)
    kills, leaks = td.tick(dt=0.5)
    assert kills == 1
    assert td.enemies[0]["alive"] is False


def test_roguelike_state():
    """Section 5D.7: Seeded room connectivity and progression."""
    rogue = RoguelikeState(room_count=4)
    rogue.generate_dungeon(seed=2026)
    assert rogue.current_room == 0

    # Move to connected room 1
    assert rogue.move_to_room(1) is True
    assert rogue.current_room == 1

    # Move to disconnected room 3
    assert rogue.move_to_room(3) is False


def test_zombie_survival_state():
    """Section 5D.7: Weapon fire, ammo consumption, reloading, and damage."""
    zombie = ZombieSurvivalState(ammo=1, reserve_ammo=31)
    assert zombie.fire_weapon(hit_zombie=True) is True
    assert zombie.ammo == 0

    # Cannot fire when empty
    assert zombie.fire_weapon() is False

    # Reload fills magazine
    assert zombie.reload() is True
    assert zombie.ammo == 30
    assert zombie.reserve_ammo == 1

    # Player damage
    zombie.take_damage(100.0)
    assert zombie.player_health == 0.0
    assert zombie.game_over is True


# ── Section 5D.8: Authoritative Module and Layout Registry ─────────────────────

def test_authoritative_layout_and_module_registry():
    """Section 5D.8: Single authoritative layout and module mapping."""
    assert get_layout_for_game_type("sudoku") == "board"
    assert get_layout_for_game_type("chess") == "board"
    assert get_layout_for_game_type("platformer") == "course"
    assert get_layout_for_game_type("tactical_fps") == "tactical_fps"
    assert get_layout_for_game_type("arena_combat") == "arena"

    with pytest.raises(KeyError):
        get_layout_for_game_type("nonexistent_game_type")

    mods = get_required_modules_for_game_type("platformer")
    assert "kit.player_character" in mods
    assert "kit.pickup" in mods
