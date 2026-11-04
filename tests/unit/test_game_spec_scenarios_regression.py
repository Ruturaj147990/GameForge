"""Regression tests for GDS acceptance test generator producing achievable assertions."""
from __future__ import annotations

import pytest

from src.gameforge_ide.design.presets import preset_arena_combat, preset_platformer, preset_tic_tac_toe
from src.gameforge_ide.qa.game_spec_tests import (
    AcceptanceTestSpec,
    acceptance_tests_to_scenarios,
    generate_acceptance_tests,
)
from src.gameforge_ide.qa.scenario import (
    EventCountExpectation,
    EventExpectation,
    NavigateToStep,
    Scenario,
)


def test_win_on_collect_all_covers_all_pickups_for_large_count():
    """Verify that win_on_collect_all generates navigation steps for all pickups, not capped at 3."""
    gds = preset_platformer(collectible_target=6)
    tests = generate_acceptance_tests(gds)
    win_spec = next(t for t in tests if t.test_id == "win_on_collect_all")
    assert win_spec.params.get("pickup_count") == 6

    scenario = win_spec.to_scenario()
    nav_steps = [s for s in scenario.steps if isinstance(s, NavigateToStep)]
    # Must visit all 6 pickups: GF_Pickup_1 through GF_Pickup_6
    assert len(nav_steps) == 6
    visited_tags = [s.navigate_to.tag for s in nav_steps]
    assert visited_tags == [f"GF_Pickup_{i}" for i in range(1, 7)]


def test_collectibles_exist_asserts_active_collection():
    """Verify that collectibles_exist has an active step and requires at least 1 pickup collected."""
    gds = preset_platformer(collectible_target=5)
    tests = generate_acceptance_tests(gds)
    col_spec = next(t for t in tests if t.test_id == "collectibles_exist")

    scenario = col_spec.to_scenario()
    # Check expectation requires min >= 1
    exp = scenario.expect[0]
    assert isinstance(exp, EventCountExpectation)
    assert exp.event_count == "pickup.collected"
    assert exp.min >= 1


def test_combat_damages_enemies_navigates_into_range():
    """Verify that combat_damages_enemies moves the player within melee/attack range before attacking."""
    gds = preset_arena_combat()
    tests = generate_acceptance_tests(gds)
    combat_spec = next(t for t in tests if t.test_id == "combat_damages_enemies")

    scenario = combat_spec.to_scenario()
    nav_steps = [s for s in scenario.steps if isinstance(s, NavigateToStep)]
    assert len(nav_steps) >= 1
    assert "Enemy" in nav_steps[0].navigate_to.tag


def test_snakes_and_ladders_scenarios_inject_turns():
    """Verify that snake and ladder transition scenarios inject dice roll inputs rather than idly waiting."""
    from src.gameforge_ide.design.gds import EntityKind
    gds = preset_tic_tac_toe(title="Snakes and Ladders")
    gds.meta.source_prompt = "Make a snakes and ladders board game with 100 cells"
    for e in gds.entities:
        if e.kind == EntityKind.BOARD:
            e.props["snakes"] = [16, 6]
            e.props["ladders"] = [1, 38]

    tests = generate_acceptance_tests(gds)
    snake_test = next(t for t in tests if t.test_id == "snake_transition")
    scenario = snake_test.to_scenario()

    # Steps must include input injection
    has_inject = any(hasattr(s, "inject") for s in scenario.steps)
    assert has_inject, "snake_transition must inject dice rolls or actions to trigger transition"
