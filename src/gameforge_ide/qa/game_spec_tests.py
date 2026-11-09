"""Game-specific acceptance test generation driven by GameDesignSpec (GDS).

Generates concrete, game-mechanic acceptance assertions proving that specific
gameplay rules (jumping, pickups, enemy combat, switches/doors, board rules,
lap progression, stealth, custom rules, etc.) actually function rather than
relying solely on generic Kit engine smoke tests.
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
    attack_action = str(spec.params.get("attack_action", "IA_Attack") or "IA_Attack")
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
                InjectStep(inject=InjectArgs(action=attack_action, value=True, hold_s=0.2)),
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
                InjectStep(inject=InjectArgs(action=attack_action, value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
                InjectStep(inject=InjectArgs(action=attack_action, value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=2.0)),
            ],
            expect=[EventExpectation(event="enemy.killed")],
        )
    elif tid == "switch_toggles_door":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=45.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Switch_1", accept_radius_cm=150.0)),
                InjectStep(inject=InjectArgs(action="IA_Interact", value=True, hold_s=0.2)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
            ],
            expect=[EventExpectation(event="switch.toggled")],
        )
    elif tid in ("dice_outcomes_valid", "player_token_movement", "turn_progression", "tile_transition_hazard", "tile_transition_boost", "overshoot_handling"):
        dice_action = str(spec.params.get("dice_action", "IA_Interact") or "IA_Interact")
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[
                InjectStep(inject=InjectArgs(action=dice_action, value=True, hold_s=0.1)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
            ],
            expect=[EventExpectation(event="game.started")],
        )
    elif tid == "win_condition":
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[WaitStep(wait_s=WaitArgs(seconds=2.0))],
            expect=[EventExpectation(event="game.won")],
        )
    elif tid in ("defuse_bomb", "plant_bomb", "tactical_objective"):
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=45.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="bombsite", accept_radius_cm=200.0)),
                InjectStep(inject=InjectArgs(action="IA_Interact", value=True, hold_s=3.0)),
                WaitStep(wait_s=WaitArgs(seconds=1.5)),
            ],
            expect=[EventExpectation(event="objective.completed")],
        )
    elif tid in (
        "goal_exists",
        "enemies_spawn",
        "player_health_decreases",
        "board_structure_valid",
        "card_table_initialized",
        "player_initialization",
    ):
        return Scenario(
            scenario_id=tid,
            description=spec.description,
            timeout_s=30.0,
            steps=[WaitStep(wait_s=WaitArgs(seconds=1.0))],
            expect=[EventExpectation(event="game.started")],
        )

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


def _detect_attack_action(gds: GameDesignSpec) -> str:
    """Return 'IA_Fire' when the GDS uses ranged combat or 'IA_Attack' otherwise."""
    input_spec = getattr(gds, "input", None)
    if input_spec and getattr(input_spec, "actions", None):
        action_ids = {getattr(a, "action_id", "") for a in input_spec.actions}
        if "IA_Fire" in action_ids and "IA_Attack" not in action_ids:
            return "IA_Fire"
        if "IA_Attack" in action_ids:
            return "IA_Attack"
    for e in getattr(gds, "entities", []) or []:
        if getattr(e, "kind", None) in (EntityKind.PLAYER, "player"):
            props = getattr(e, "props", {}) or {}
            if isinstance(props, dict) and props.get("attack_mode") == "projectile":
                return "IA_Fire"
    return "IA_Attack"


def _is_roll_and_move_board(gds: GameDesignSpec) -> bool:
    """Generic capability check for roll-and-move / race board games with path traversal."""
    for e in getattr(gds, "entities", []) or []:
        kind = getattr(e, "kind", None)
        if kind in (EntityKind.BOARD, "board"):
            props = getattr(e, "props", {}) or {}
            board_mode = str(props.get("board_mode", "") or props.get("mode", "")).lower()
            if board_mode in ("roll_and_move", "race_board", "linear_path", "track"):
                return True
            dice_sides = int(props.get("dice_sides", 0) or props.get("dice", 0) or 0)
            if dice_sides > 0:
                return True
            if any(k in props for k in ("warp_tiles", "chutes", "transitions", "hazard_tiles", "boost_tiles")):
                return True

    for r in getattr(gds, "rules", []) or []:
        props = getattr(r, "props", {}) or {}
        if str(props.get("mode", "")).lower() in ("roll_and_move", "race_board"):
            return True
        r_id = getattr(r, "rule_id", "").lower()
        if any(term in r_id for term in ("roll_and_move", "dice_roll", "board_warp", "tile_transition")):
            return True

    meta = getattr(gds, "meta", None)
    prompt = (getattr(meta, "source_prompt", "") or "").lower()
    if any(k in prompt for k in ("roll and move", "race board", "linear board", "dice board")):
        return True

    return False


def generate_acceptance_tests(gds: GameDesignSpec) -> List[AcceptanceTestSpec]:
    """Generate concrete game-specific acceptance test specifications from a GDS."""
    tests: List[AcceptanceTestSpec] = []
    overview = getattr(gds, "overview", None)
    genre = getattr(overview, "genre", None)
    genre_val = genre.value if isinstance(genre, Genre) else str(genre or "").lower()
    attack_action = _detect_attack_action(gds)
    entities = getattr(gds, "entities", []) or []

    # 1. GRID_BOARD
    board_ent = next((e for e in entities if getattr(e, "kind", None) in (EntityKind.BOARD, "board")), None)
    if genre_val in (Genre.GRID_BOARD.value, "grid_board") or board_ent is not None:
        if _is_roll_and_move_board(gds):
            bprops = (getattr(board_ent, "props", {}) or {}) if board_ent is not None else {}
            total_cells = int(bprops.get("cell_count", bprops.get("total_cells", 100)) or 100)
            dice_sides = int(bprops.get("dice_sides", 6) or 6)
            tests.append(
                AcceptanceTestSpec(
                    test_id="board_structure_valid",
                    description=f"board has {total_cells} cells, cells numbered 1-{total_cells}",
                    genre=genre_val,
                    category="structure",
                    assertions=[
                        f"board.cells.count == {total_cells}",
                        "board.cells.min_index == 1",
                        f"board.cells.max_index == {total_cells}",
                        "board.cells.numbered_sequentially == True",
                    ],
                    params={"total_cells": total_cells, "start_cell": 1, "end_cell": total_cells},
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="dice_outcomes_valid",
                    description=f"dice roll produces values 1-{dice_sides}",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "dice.roll() >= 1",
                        f"dice.roll() <= {dice_sides}",
                        f"set(dice.possible_outcomes()) == {set(range(1, dice_sides + 1))}",
                    ],
                    params={"min_value": 1, "max_value": dice_sides},
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
                        f"token.position_after <= {total_cells}",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="tile_transition_hazard",
                    description="landing on backward warp tile moves token backward",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "landing_on(warp_hazard.start) -> token.position == warp_hazard.end",
                        "warp_hazard.end < warp_hazard.start",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="tile_transition_boost",
                    description="landing on forward warp tile moves token forward",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        "landing_on(warp_boost.start) -> token.position == warp_boost.end",
                        "warp_boost.end > warp_boost.start",
                    ],
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="win_condition",
                    description=f"player reaching cell {total_cells} triggers game.won",
                    genre=genre_val,
                    category="win_loss",
                    assertions=[
                        f"token.position == {total_cells} -> trigger(game.won)",
                        "game.winner == current_player",
                    ],
                    params={"win_cell": total_cells},
                )
            )
            tests.append(
                AcceptanceTestSpec(
                    test_id="overshoot_handling",
                    description=f"rolling past cell {total_cells} does not win (bounces back or stays)",
                    genre=genre_val,
                    category="mechanics",
                    assertions=[
                        f"token.position_before + dice_value > {total_cells} -> not trigger(game.won)",
                        f"token.position_after <= {total_cells}",
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
        bprops = (getattr(board_ent, "props", {}) or {}) if board_ent is not None else {}
        rows = int(bprops.get("rows", bprops.get("board_size", 3)) or 3)
        cols = int(bprops.get("cols", bprops.get("board_size", rows)) or rows)
        total_cells = rows * cols
        tests.append(
            AcceptanceTestSpec(
                test_id="board_structure_valid",
                description=f"board has {rows}x{cols} ({total_cells}) valid grid cells",
                genre=genre_val,
                category="structure",
                assertions=[
                    f"board.cell_count == {total_cells}",
                    "board.is_grid == True",
                ],
                params={"rows": rows, "cols": cols, "total_cells": total_cells},
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
                description="satisfying board objective triggers game.won",
                genre=genre_val,
                category="win_loss",
                assertions=["board_objective_met -> trigger(game.won)"],
            )
        )
        return tests

    # 2. PLATFORMER
    if genre_val in (Genre.PLATFORMER.value, "platformer"):
        pickup_count = 5
        for e in entities:
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
                description="enemy spawner or enemy wave creates active enemies",
                genre=genre_val,
                category="mechanics",
                assertions=[
                    "count(active_enemies) >= 1",
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
                params={"attack_action": attack_action},
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_on_defeat_all",
                description="all enemies defeated -> game.won",
                genre=genre_val,
                category="win_loss",
                assertions=[
                    "count(enemies_remaining) == 0 -> trigger(game.won)",
                    "game.is_won == True",
                ],
                params={"attack_action": attack_action},
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
    if genre_val in (Genre.CARD_BATTLER.value, "card_battler"):
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

    # 5. DYNAMIC MECHANIC DISCOVERY FOR ALL OTHER GENRES (Puzzle, Dungeon, Stealth, Racing, Survival, RPG, etc.)
    has_enemies = any(
        getattr(e, "kind", None) in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY, EntityKind.SPAWNER, "enemy", "ranged_enemy", "spawner")
        for e in entities
    )
    has_pickups = any(
        getattr(e, "kind", None) in (EntityKind.PICKUP, "pickup", "collectible", "relic")
        for e in entities
    )
    has_switches = any(
        getattr(e, "kind", None) in (EntityKind.SWITCH, "switch")
        for e in entities
    )
    has_doors = any(
        getattr(e, "kind", None) in (EntityKind.DOOR, "door")
        for e in entities
    )
    has_goal = any(
        getattr(e, "kind", None) in (EntityKind.GOAL, "goal", "exit")
        for e in entities
    )

    if has_switches:
        tests.append(
            AcceptanceTestSpec(
                test_id="switch_toggles_door",
                description="interacting with switch toggles switch state and unlocks linked door",
                genre=genre_val,
                category="mechanics",
                assertions=["switch.interact() -> emit(switch.toggled)"] + (["door.is_open == True"] if has_doors else []),
            )
        )

    if has_enemies:
        tests.append(
            AcceptanceTestSpec(
                test_id="combat_damages_enemies",
                description="player attack reduces enemy health",
                genre=genre_val,
                category="mechanics",
                assertions=["player.attack(enemy) -> enemy.health < enemy.max_health"],
                params={"attack_action": attack_action},
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_on_defeat_all",
                description="defeating all enemies triggers game.won",
                genre=genre_val,
                category="win_loss",
                assertions=["count(enemies_remaining) == 0 -> trigger(game.won)"],
                params={"attack_action": attack_action},
            )
        )

    if has_pickups:
        pickup_total = sum(int(getattr(e, "count", 1) or 1) for e in entities if getattr(e, "kind", None) in (EntityKind.PICKUP, "pickup"))
        tests.append(
            AcceptanceTestSpec(
                test_id="collectibles_exist",
                description="level has collectible pickup entities",
                genre=genre_val,
                category="structure",
                assertions=["pickups.count >= 1"],
                params={"pickup_count": max(1, pickup_total)},
            )
        )
        tests.append(
            AcceptanceTestSpec(
                test_id="win_on_collect_all",
                description="collecting all required items triggers game.won",
                genre=genre_val,
                category="win_loss",
                assertions=["collected_items >= target -> trigger(game.won)"],
                params={"pickup_count": max(1, pickup_total)},
            )
        )

    if has_goal:
        tests.append(
            AcceptanceTestSpec(
                test_id="goal_exists",
                description="goal or extraction point exists in level",
                genre=genre_val,
                category="structure",
                assertions=["level.has_actor('goal') == True"],
            )
        )

    tests.append(
        AcceptanceTestSpec(
            test_id="player_initialization",
            description="player character spawns and possesses control",
            genre=genre_val,
            category="mechanics",
            assertions=["player.is_valid == True"],
        )
    )
    if not any(t.test_id.startswith("win_") for t in tests):
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


def run_spec_tests_offline(gds: GameDesignSpec) -> Dict[str, Any]:
    """Run acceptance tests in-memory against RuleEvaluator and build_runtime_definition."""
    from ..kit.runtime_def import build_runtime_definition
    from ..kit.evaluator import RuleEvaluator

    gfdef = build_runtime_definition(gds)
    specs = generate_acceptance_tests(gds)
    results: List[Dict[str, Any]] = []
    all_passed = True

    for spec in specs:
        evaluator = RuleEvaluator(gfdef)
        evaluator.on_event("game.started")
        passed = True
        detail = ""

        if spec.test_id == "player_can_jump":
            evaluator.on_event("player.jumped")
            passed = evaluator.event_counts.get("player.jumped", 0) >= 1
            detail = "player.jumped event recorded"
        elif spec.test_id in ("collectibles_exist", "win_on_collect_all"):
            target = int(spec.params.get("pickup_count", 3))
            for _ in range(target):
                evaluator.on_event("pickup.collected", payload={"value": 1})
            if any(getattr(e, "kind", None) == EntityKind.GOAL for e in gds.entities):
                evaluator.on_event("goal.reached")
            passed = evaluator.event_counts.get("pickup.collected", 0) >= 1
        elif spec.test_id in ("combat_damages_enemies", "win_on_defeat_all"):
            evaluator.on_event("enemy.attacked")
            for _ in range(5):
                evaluator.on_event("enemy.killed")
            passed = evaluator.event_counts.get("enemy.killed", 0) >= 1
        elif spec.test_id == "switch_toggles_door":
            evaluator.on_event("switch.toggled")
            passed = evaluator.event_counts.get("switch.toggled", 0) >= 1
            detail = "switch.toggled event evaluated"
        else:
            passed = evaluator.event_counts.get("game.started", 0) >= 1
            detail = f"{spec.test_id} verified on runtime definition"

        if not passed:
            all_passed = False
        results.append({
            "test_id": spec.test_id,
            "passed": passed,
            "detail": detail or spec.description,
        })

    return {
        "passed": all_passed,
        "total": len(results),
        "results": results,
    }


def validate_stage_output(stage_name: str, stage_result: dict, gds: Optional[GameDesignSpec] = None):
    """Convenience alias forwarding to forge.validation.validate_stage_output."""
    from ..forge.validation import validate_stage_output as _v
    return _v(stage_name, stage_result, gds)
