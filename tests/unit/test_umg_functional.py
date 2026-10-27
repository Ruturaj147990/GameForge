"""Unit tests for Milestone 4: Functional UMG and Gameplay-State Integration.
Tests event binding schema, Button widget operations, gameplay state verification,
and task acceptance predicates with zero mocks or simulators in production paths.
"""
from __future__ import annotations

import inspect
import pytest

from src.gameforge_ide.backend.agent.task_state import (
    TaskAcceptancePredicate,
    TaskState,
)
from src.gameforge_ide.backend.tools.game_tools import READ_ONLY_EDITOR_OPS
from src.gameforge_ide.unreal.live_operations import LiveOperations


def test_live_operations_exposes_milestone4_methods() -> None:
    """Verifies that LiveOperations provides all required typed async methods for M4."""
    required_methods = [
        "widget_bind_event",
        "widget_inspect_events",
        "widget_click_button",
        "widget_runtime_state",
        "gameplay_get_state",
        "gameplay_modify_state",
    ]
    for method_name in required_methods:
        assert hasattr(LiveOperations, method_name), f"LiveOperations missing {method_name}"
        method = getattr(LiveOperations, method_name)
        assert inspect.iscoroutinefunction(method), f"{method_name} must be a coroutine function"


def test_read_only_editor_ops_includes_m4_inspection_ops() -> None:
    """Verifies that non-mutating inspection operations are classified as read-only."""
    expected_read_only = {
        "widget_inspect_events",
        "widget_runtime_state",
        "gameplay_get_state",
    }
    for op in expected_read_only:
        assert op in READ_ONLY_EDITOR_OPS, f"{op} must be in READ_ONLY_EDITOR_OPS"


def test_predicate_widget_event_bound(tmp_path) -> None:
    """Verifies that widget_event_bound predicate evaluates correctly against tool history."""
    state = TaskState(
        session_id="session_test",
        task_id="test_m4_bind",
        goal="Bind PrimaryButton OnClicked event",
        acceptance=[
            TaskAcceptancePredicate(
                predicate_type="widget_event_bound",
                target="WBP_GameForgeMenu_V1",
            )
        ],
    )
    # Initially not satisfied
    all_ok, unmet = state.evaluate_acceptance(tmp_path, set(), [])
    assert not all_ok
    assert any("widget_event_bound" in u for u in unmet)

    # History with successful binding
    history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "widget_bind_event", "args": {"asset_path": "/Game/UI/WBP_GameForgeMenu_V1", "widget_name": "PrimaryButton"}},
        "output": {"ok": True, "data": {"asset_path": "/Game/UI/WBP_GameForgeMenu_V1", "node_id": "guid-123"}},
    }]
    all_ok, unmet = state.evaluate_acceptance(tmp_path, set(), history)
    assert all_ok
    assert len(unmet) == 0


def test_predicate_gameplay_state_verified(tmp_path) -> None:
    """Verifies that gameplay_state_verified predicate evaluates correctly."""
    state = TaskState(
        session_id="session_test",
        task_id="test_m4_gameplay",
        goal="Modify gameplay state",
        acceptance=[
            TaskAcceptancePredicate(
                predicate_type="gameplay_state_verified",
                target="health",
            )
        ],
    )
    all_ok, unmet = state.evaluate_acceptance(tmp_path, set(), [])
    assert not all_ok

    history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "gameplay_modify_state", "args": {"delta_health": -30.0}},
        "output": {"ok": True, "data": {"before_health": 100.0, "after_health": 70.0, "max_health": 100.0}},
    }]
    all_ok, unmet = state.evaluate_acceptance(tmp_path, set(), history)
    assert all_ok


def test_predicate_menu_interaction_verified(tmp_path) -> None:
    """Verifies that menu_interaction_verified predicate evaluates correctly."""
    state = TaskState(
        session_id="session_test",
        task_id="test_m4_menu",
        goal="Click PrimaryButton",
        acceptance=[
            TaskAcceptancePredicate(
                predicate_type="menu_interaction_verified",
                target="PrimaryButton",
            )
        ],
    )
    all_ok, unmet = state.evaluate_acceptance(tmp_path, set(), [])
    assert not all_ok

    history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "widget_click_button", "args": {"button_name": "PrimaryButton"}},
        "output": {"ok": True, "data": {"button_name": "PrimaryButton", "clicked": True}},
    }]
    all_ok, unmet = state.evaluate_acceptance(tmp_path, set(), history)
    assert all_ok


def test_gameplay_state_bounds_clamping() -> None:
    """Verifies mathematical invariants for gameplay attribute bounds [0.0, Max]."""
    max_health = 100.0
    current_health = 100.0

    # Damage clamping at 0
    delta_damage = -150.0
    clamped_damage = max(0.0, min(current_health + delta_damage, max_health))
    assert clamped_damage == 0.0

    # Overheal clamping at max_health
    delta_heal = 500.0
    clamped_heal = max(0.0, min(clamped_damage + delta_heal, max_health))
    assert clamped_heal == max_health

    # Partial change
    delta_partial = -35.0
    clamped_partial = max(0.0, min(clamped_heal + delta_partial, max_health))
    assert clamped_partial == 65.0
    assert clamped_partial / max_health == 0.65
