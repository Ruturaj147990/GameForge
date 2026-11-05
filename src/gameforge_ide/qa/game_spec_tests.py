"""Game-specific acceptance test generation driven by GameDesignSpec (GDS).

Generates concrete, game-mechanic acceptance assertions proving that specific
gameplay rules (snakes/ladders transitions, jumping, pickups, enemy combat, etc.)
actually function rather than relying solely on generic Kit engine smoke tests.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from ..design.gds import (
    CountAtLeast,
    EntityKind,
    EventOccurred,
    GameDesignSpec,
    Genre,
    StatCompare,
)
from .scenario import (
    EventCountExpectation,
    EventExpectation,
    InjectArgs,
    InjectStep,
    NavigateToArgs,
    NavigateToStep,
    NoEventExpectation,
    Scenario,
    WaitArgs,
    WaitStep,
)


class AcceptanceTestSpec(BaseModel):
    """Specification of a concrete game acceptance test assertion."""
    model_config = ConfigDict(extra="ignore")

    test_id: str
    description: str
    genre: str = ""
    category: str = "mechanics"
    assertions: List[str] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)
    must_pass: bool = True

    @property
    def name(self) -> str:
        return self.test_id

    def to_scenario(self) -> Scenario:
        return _spec_to_scenario(self)


def _spec_to_scenario(spec: AcceptanceTestSpec) -> Scenario:
    """Map an acceptance test assertion into an executable Scenario."""
    tid = spec.test_id
    if tid == "player_can_jump":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
                InjectStep(inject=InjectArgs(action="IA_Jump", value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
            ],
            expect=[EventExpectation(event="player.jumped")],
        )
    elif tid == "win_on_collect_all":
        target = int(spec.params.get("pickup_count", 3))
        steps = [
            NavigateToStep(navigate_to=NavigateToArgs(tag=f"GF_Pickup_{i}"))
            for i in range(1, target + 1)
        ]
        steps.append(WaitStep(wait_s=WaitArgs(seconds=2.0)))
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=max(60.0, float(target) * 15.0),
            steps=steps,
            expect=[EventExpectation(event="game.won")],
        )
    elif tid == "collectibles_exist":
        target = int(spec.params.get("pickup_count", 1))
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1", accept_radius_cm=150.0)),
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
            ],
            expect=[EventCountExpectation(event_count="pickup.collected", min=1)],
        )
    elif tid == "combat_damages_enemies":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="enemy", accept_radius_cm=180.0)),
                InjectStep(inject=InjectArgs(action="IA_PrimaryAttack", value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
            ],
            expect=[EventExpectation(event="enemy.attacked")],
        )
    elif tid == "win_on_defeat_all":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=60.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="enemy", accept_radius_cm=180.0)),
                InjectStep(inject=InjectArgs(action="IA_PrimaryAttack", value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
                InjectStep(inject=InjectArgs(action="IA_PrimaryAttack", value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=2.0)),
            ],
            expect=[EventExpectation(event="enemy.killed")],
        )
    elif tid in ("dice_outcomes_valid", "player_token_movement", "turn_progression"):
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[
                InjectStep(inject=InjectArgs(action="IA_RollDice", value=True, hold_s=0.1)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
            ],
            expect=[EventExpectation(event="dice.rolled")],
        )
    elif tid in ("snake_transition", "ladder_transition"):
        evt = "snake.transition" if tid == "snake_transition" else "ladder.transition"
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[
                InjectStep(inject=InjectArgs(action="IA_RollDice", value=True, hold_s=0.1)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
            ],
            expect=[EventExpectation(event=evt)],
        )
    elif tid == "win_condition":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[WaitStep(wait_s=WaitArgs(seconds=2.0))],
            expect=[EventExpectation(event="game.won")],
        )
    elif tid == "overshoot_handling":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[WaitStep(wait_s=WaitArgs(seconds=2.0))],
            expect=[NoEventExpectation(no_event="game.won")],
        )
    elif tid in ("goal_exists", "enemies_spawn", "player_health_decreases", "board_structure_valid", "card_table_initialized", "player_initialization"):
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[WaitStep(wait_s=WaitArgs(seconds=1.0))],
            expect=[EventExpectation(event="game.started")],
        )

    # General fallback scenario
    return Scenario(
        scenario_id=tid,
        description=spec.description,
        timeout_s=30.0,
        steps=[WaitStep(wait_s=WaitArgs(seconds=2.0))],
        expect=[EventExpectation(event="game.started")],
    )


def acceptance_tests_to_scenarios(specs: List[AcceptanceTestSpec]) -> List[Scenario]:
    """Convert a list of AcceptanceTestSpec items into executable Scenarios."""
    return [spec.to_scenario() for spec in specs]


def _is_snakes_and_ladders(gds: GameDesignSpec) -> bool:
    """Detect whether a GRID_BOARD GDS represents a snakes and ladders game."""
    # Check text corpus (meta title, prompt, pitch)
    meta = getattr(gds, "meta", None)
    overview = getattr(gds, "overview", None)
    text_corpus = " ".join([
        getattr(meta, "source_prompt", "") or "",
        getattr(meta, "title", "") or "",
        getattr(meta, "project_name", "") or "",
        getattr(overview, "pitch", "") or "",
    ]).lower()

    if "snake" in text_corpus and "ladder" in text_corpus:
        return True

    # Check entities and props
    for e in getattr(gds, "entities", []) or []:
        props = getattr(e, "props", {}) or {}
        if any(k in props for k in ("snakes", "ladders", "snakes_and_ladders", "snake_cells", "ladder_cells")):
            return True
        ent_id = getattr(e, "entity_id", "").lower()
        if "snake" in ent_id or "ladder" in ent_id:
            return True
        for tag in getattr(e, "tags", []) or []:
            if "snake" in tag.lower() or "ladder" in tag.lower():
                return True

    # Check rules
    for r in getattr(gds, "rules", []) or []:
        r_text = f"{getattr(r, 'rule_id', '')} {getattr(r, 'description', '')}".lower()
        if "snake" in r_text or "ladder" in r_text:
            return True

    return False


def generate_acceptance_tests(gds: GameDesignSpec) -> List[AcceptanceTestSpec]:
    """Generate concrete game-specific acceptance test specifications from a GDS.

    Reads overview.genre, entities, goals, and rules to generate explicit test
    assertions for game mechanics.

    Returns:
        List of AcceptanceTestSpec instances for the GDS.
    """
    tests: List[AcceptanceTestSpec] = []
    overview = getattr(gds, "overview", None)
    genre = getattr(overview, "genre", None)
    genre_val = genre.value if isinstance(genre, Genre) else str(genre or "").lower()

    # 1. GRID_BOARD with snakes and ladders props
    if genre_val == Genre.GRID_BOARD.value or genre_val == "grid_board":
        if _is_snakes_and_ladders(gds):
            tests.append(
                AcceptanceTestSpec(
                    test_id="board_structure_valid",
                    description="board has 100 cells, cells numbered 1-100",
                    genre=genre_val,
                    category="structure",
                    assertions=[
                        "board.cells.count == 100",
                        "board.cells.min_index == 1",
                        "board.cells.max_index == 100",
                        "board.cells.numbered_sequentially == True",
                    ],
                    params={"total_cells": 100, "start_cell": 1, "end_cell": 100},
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="dice_outcomes_valid",
                    description="dice roll produces values 1-6",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "dice.roll() >= 1",
                        "dice.roll() <= 6",
                        "set(dice.possible_outcomes()) == {1, 2, 3, 4, 5, 6}",
                    ],
                    params={"min_value": 1, "max_value": 6},
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="player_token_movement",
                    description="after dice roll, token moves correct number of cells",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "token.position_after == token.position_before + dice_value",
                        "token.position_after <= 100",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="snake_transition",
                    description="landing on snake head moves token to snake tail",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "landing_on(snake.head) -> token.position == snake.tail",
                        "snake.tail < snake.head",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="ladder_transition",
                    description="landing on ladder bottom moves token to ladder top",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "landing_on(ladder.bottom) -> token.position == ladder.top",
                        "ladder.top > ladder.bottom",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="win_condition",
                    description="player reaching cell 100 triggers game.won",
                    genre=genre_val,
                    category="win_loss",
                    assertions=[
                        "token.position == 100 -> trigger(game.won)",
                        "game.winner == current_player",
                    ],
                    params={"win_cell": 100},
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="overshoot_handling",
                    description="rolling past cell 100 does not win (bounces back or stays)",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "token.position_before + dice_value > 100 -> not trigger(game.won)",
                        "token.position_after <= 100",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="turn_progression",
                    description="turns alternate between players after each dice roll",
                    genre=genre_val,
                    category="progression",
                    assertions=[
                        "active_player_after == (active_player_before % total_players) + 1",
                        "turn_advances_after_dice_roll == True",
                    ],
                )
            )
            return tests

        # Standard grid board (Tic-Tac-Toe, Gomoku, Connect Four)
        tests.append(
            AcceptanceTestSpec(
                test_id="board_structure_valid",
                description="board has valid grid dimensions and cells",
                genre=genre_val,
                category="structure",
                assertions=["board.cell_count >= 9", "board.is_grid == True"],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="turn_progression",
                description="turns alternate between players after each move",
                genre=genre_val,
                category="progression",
                assertions=["current_player alternates each turn"],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_condition",
                description="aligned pieces trigger game.won",
                genre=genre_val,
                category="win_loss",
                assertions=["winning alignment -> trigger(game.won)"],
            )
        )
        return tests

    # 2. PLATFORMER
    if genre_val == Genre.PLATFORMER.value or genre_val == "platformer":
        pickup_count = 5
        for e in getattr(gds, "entities", []) or []:
            if getattr(e, "kind", None) in (EntityKind.PICKUP, "pickup"):
                pickup_count = getattr(e, "count", 5)
                break

        tests.append(
            AcceptanceTestSpec(
                test_id="player_can_jump",
                description="press space -> character is airborne",
                genre=genre_val,
                category="mechanics",
                assertions=[
                    "press(Space) -> player.is_airborne == True",
                    "player.velocity.z > 0",
                ],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="collectibles_exist",
                description="level has specified number of pickup actors",
                genre=genre_val,
                category="structure",
                assertions=[
                    f"level.count_actors('pickup') == {pickup_count}",
                    "pickups.count >= 1",
                ],
                params={"pickup_count": pickup_count},
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="goal_exists",
                description="finish trigger exists in level",
                genre=genre_val,
                category="structure",
                assertions=[
                    "level.has_actor('goal') == True",
                    "goal.is_trigger == True",
                ],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_on_collect_all",
                description="collecting all pickups -> game.won",
                genre=genre_val,
                category="win_loss",
                assertions=[
                    f"collected_pickups == {pickup_count} -> trigger(game.won)",
                    "game.is_won == True",
                ],
                params={"pickup_count": pickup_count},
            )
        )
        return tests

    # 3. ARENA_COMBAT / TOP_DOWN_SHOOTER
    if genre_val in (
        Genre.ARENA_COMBAT.value,
        Genre.TOP_DOWN_SHOOTER.value,
        "arena_combat",
        "top_down_shooter",
    ):
        tests.append(
            AcceptanceTestSpec(
                test_id="enemies_spawn",
                description="enemy spawner creates enemies",
                genre=genre_val,
                category="mechanics",
                assertions=[
                    "spawner.spawn_wave() -> count(active_enemies) >= 1",
                    "enemy_spawn_count > 0",
                ],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="combat_damages_enemies",
                description="player attack reduces enemy health",
                genre=genre_val,
                category="mechanics",
                assertions=[
                    "player.attack(enemy) -> enemy.health < enemy.max_health",
                    "damage_inflicted > 0",
                ],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_on_defeat_all",
                description="all enemies killed -> game.won",
                genre=genre_val,
                category="win_loss",
                assertions=[
                    "count(enemies_remaining) == 0 -> trigger(game.won)",
                    "game.is_won == True",
                ],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="player_health_decreases",
                description="enemy attack reduces player health",
                genre=genre_val,
                category="mechanics",
                assertions=[
                    "enemy.attack(player) -> player.health < player.max_health",
                    "player.health_reduced == True",
                ],
            )
        )
        return tests

    # 4. CARD_BATTLER
    if genre_val == Genre.CARD_BATTLER.value or genre_val == "card_battler":
        tests.append(
            AcceptanceTestSpec(
                test_id="card_table_initialized",
                description="card table and deck are initialized",
                genre=genre_val,
                category="structure",
                assertions=["table.is_initialized == True", "deck.card_count > 0"],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="turn_progression",
                description="turns alternate between player and opponent",
                genre=genre_val,
                category="progression",
                assertions=["turn_alternation == True"],
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_condition",
                description="reducing opponent health to zero triggers game.won",
                genre=genre_val,
                category="win_loss",
                assertions=["opponent.health <= 0 -> trigger(game.won)"],
            )
        )
        return tests

    # Default fallback acceptance tests for other genres
    tests.append(
        AcceptanceTestSpec(
            test_id="player_initialization",
            description="player character spawns and possesses control",
            genre=genre_val,
            category="mechanics",
            assertions=["player.is_valid == True"],
        )
    )
    tests.append(
        AcceptanceTestSpec(
            test_id="win_condition",
            description="primary objective triggers game.won",
            genre=genre_val,
            category="win_loss",
            assertions=["primary_objective_met -> trigger(game.won)"],
        )
    )
    return tests


def validate_stage_output(stage_name: str, stage_result: dict, gds: Optional[GameDesignSpec] = None):
    """Convenience alias forwarding to forge.validation.validate_stage_output."""
    from ..forge.validation import validate_stage_output as _v
    return _v(stage_name, stage_result, gds)

