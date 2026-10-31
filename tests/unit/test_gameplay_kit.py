"""Unit tests for Phase 5 Gameplay Kit v2 (WI-5.1 through WI-5.14)."""
from __future__ import annotations

import math
import pytest

from src.gameforge_ide.design.presets import preset_platformer, preset_tic_tac_toe
from src.gameforge_ide.kit import (
    KIT,
    ConditionEvaluator,
    EvaluationContext,
    RulesEvaluator,
    all_modules,
    build_runtime_def,
    get_module,
    validate_runtime_def,
)


def test_kit_registry_contains_modules():
    """Verify standard kit modules are registered and accessible."""
    modules = all_modules()
    assert len(modules) >= 12

    pickup = get_module("kit.pickup")
    assert pickup.runtime_class == "/Script/GameForgeRuntime.GameForgePickup"
    assert "coin" in pickup.entity_kinds
    assert "pickup.collected" in pickup.emits

    enemy = get_module("kit.enemy_melee")
    assert enemy.runtime_class == "/Script/GameForgeRuntime.GameForgeEnemy"
    assert "attack_damage" in enemy.params_model.model_fields

    board = get_module("kit.grid_board")
    assert board.runtime_class == "/Script/GameForgeRuntime.GameForgeGridBoard"
    assert "board.win" in board.emits


def test_runtime_def_generation_from_gds():
    """Verify gfdef/1 generator creates compliant dictionary from GDS."""
    gds = preset_platformer()
    gfdef = build_runtime_def(gds)

    assert gfdef["schema"] == "gfdef/1"
    assert gfdef["title"] == gds.meta.title
    assert "player" in gfdef
    assert "stats" in gfdef
    assert "entities" in gfdef
    assert "win" in gfdef
    assert "lose" in gfdef

    errors = validate_runtime_def(gfdef)
    assert not errors, f"gfdef validation errors: {errors}"


def test_condition_evaluator_count_at_least():
    """Verify count_at_least condition logic."""
    counts = {("pickup.collected", "coin"): 5, ("pickup.collected", None): 5}
    ctx = EvaluationContext(count_events=lambda e, ent: counts.get((e, ent), 0))

    # Passed
    cond_pass = {"kind": "count_at_least", "event": "pickup.collected", "source": "coin", "n": 3}
    ok, err = ConditionEvaluator.evaluate(cond_pass, ctx)
    assert ok is True and err is None

    # Failed
    cond_fail = {"kind": "count_at_least", "event": "pickup.collected", "source": "coin", "n": 10}
    ok, err = ConditionEvaluator.evaluate(cond_fail, ctx)
    assert ok is False and err is None

    # Malformed (missing n)
    cond_bad = {"kind": "count_at_least", "event": "pickup.collected"}
    ok, err = ConditionEvaluator.evaluate(cond_bad, ctx)
    assert ok is False and err is not None


def test_condition_evaluator_stat_comparisons():
    """Verify stat condition operator evaluation including NaN safety."""
    stats = {"player.health": 80.0, "game.score": 100.0}
    ctx = EvaluationContext(get_stat=lambda s: stats.get(s, float("nan")))

    # <=
    ok, _ = ConditionEvaluator.evaluate({"kind": "stat", "stat": "player.health", "op": "<=", "value": 100.0}, ctx)
    assert ok is True

    # ==
    ok, _ = ConditionEvaluator.evaluate({"kind": "stat", "stat": "game.score", "op": "==", "value": 100.0}, ctx)
    assert ok is True

    # Unknown stat -> NaN -> condition is False
    ok, _ = ConditionEvaluator.evaluate({"kind": "stat", "stat": "unknown.stat", "op": ">=", "value": 0.0}, ctx)
    assert ok is False


def test_condition_evaluator_nesting_and_depth_limit():
    """Verify 'all' and 'any' compound conditions and max depth guard."""
    stats = {"a": 10.0, "b": 20.0}
    ctx = EvaluationContext(get_stat=lambda s: stats.get(s, float("nan")))

    cond_all = {
        "kind": "all",
        "conditions": [
            {"kind": "stat", "stat": "a", "op": "==", "value": 10.0},
            {"kind": "stat", "stat": "b", "op": "==", "value": 20.0},
        ],
    }
    ok, err = ConditionEvaluator.evaluate(cond_all, ctx)
    assert ok is True and err is None

    # Depth > 3 guard
    deep_cond = {
        "kind": "all",
        "conditions": [{
            "kind": "all",
            "conditions": [{
                "kind": "all",
                "conditions": [{
                    "kind": "all",
                    "conditions": [{"kind": "stat", "stat": "a", "op": ">", "value": 0.0}],
                }],
            }],
        }],
    }
    ok, err = ConditionEvaluator.evaluate(deep_cond, ctx)
    assert ok is False and "depth" in err.lower()


def test_rules_evaluator_event_simulation():
    """Verify RulesEvaluator stat mutation and win/lose resolution."""
    gfdef = {
        "schema": "gfdef/1",
        "title": "Coin Game",
        "stats": {
            "player.health": {"initial": 100.0, "min": 0.0, "max": 100.0},
            "game.score": {"initial": 0.0},
        },
        "rules": [
            {
                "id": "collect_score",
                "when": {"e": "pickup.collected", "ent": "coin"},
                "if": [],
                "do": [{"kind": "add_stat", "stat": "game.score", "delta": 25.0}],
            },
            {
                "id": "take_damage",
                "when": {"e": "hazard.touched", "ent": None},
                "if": [],
                "do": [{"kind": "add_stat", "stat": "player.health", "delta": -100.0}],
            },
        ],
        "win": [{"kind": "stat", "stat": "game.score", "op": ">=", "value": 50.0}],
        "lose": [{"kind": "stat", "stat": "player.health", "op": "<=", "value": 0.0}],
    }

    evaluator = RulesEvaluator(gfdef)

    # First coin -> score 25 -> not won yet
    evaluator.handle_event("pickup.collected", "coin")
    assert evaluator.get_stat("game.score") == 25.0
    assert evaluator.game_ended is False

    # Second coin -> score 50 -> win condition met
    evaluator.handle_event("pickup.collected", "coin")
    assert evaluator.get_stat("game.score") == 50.0
    assert evaluator.game_ended is True
    assert evaluator.outcome == "win"
    assert evaluator.end_reason == "win[0]"


def test_rules_evaluator_lose_tiebreak():
    """Verify tie-break rule: lose condition evaluated before win condition."""
    gfdef = {
        "schema": "gfdef/1",
        "title": "Simultaneous Win Lose",
        "stats": {"score": {"initial": 100.0}, "health": {"initial": 0.0}},
        "rules": [],
        "win": [{"kind": "stat", "stat": "score", "op": ">=", "value": 100.0}],
        "lose": [{"kind": "stat", "stat": "health", "op": "<=", "value": 0.0}],
    }
    evaluator = RulesEvaluator(gfdef)
    evaluator.handle_event("tick")
    assert evaluator.game_ended is True
    assert evaluator.outcome == "lose"
    assert evaluator.end_reason == "lose[0]"


def test_kit_module_events_parity():
    """Verify KIT module IDs and emitted events match design.events_catalog.MODULE_EVENTS 1:1."""
    from src.gameforge_ide.design.events_catalog import MODULE_EVENTS

    assert set(KIT.keys()) == set(MODULE_EVENTS.keys())
    for k, events in MODULE_EVENTS.items():
        assert set(KIT[k].emits) == set(events), f"Mismatch in emits for {k}"


def test_gds_entity_props_validation():
    """Verify that invalid props for a kit module fail GDS validation."""
    from src.gameforge_ide.design.presets import preset_platformer

    gds = preset_platformer()
    # Add an illegal property to the pickup entity
    gds.entities[1].props["illegal_field_name_xyz"] = 123
    with pytest.raises(ValueError, match="props invalid"):
        gds._cross_refs()

