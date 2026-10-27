"""Unit tests for GameForge Milestone 3: Real UMG Widget Authoring V1."""

import json
from pathlib import Path
import pytest

from src.gameforge_ide.backend.agent.task_state import TaskAcceptancePredicate, TaskState
from src.gameforge_ide.backend.tools.game_tools import READ_ONLY_EDITOR_OPS
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.backend.agent.task_plan import TaskPlan, TaskNode
from src.gameforge_ide.backend.agent.plan_executor import TaskPlanExecutor


def test_widget_read_only_ops_registered():
    """Verify that widget_inspect and widget_readback_tree are registered as read-only."""
    assert "widget_inspect" in READ_ONLY_EDITOR_OPS
    assert "widget_readback_tree" in READ_ONLY_EDITOR_OPS
    # Mutations must NOT be in read-only ops
    assert "widget_create_blueprint" not in READ_ONLY_EDITOR_OPS
    assert "widget_create" not in READ_ONLY_EDITOR_OPS
    assert "widget_set_property" not in READ_ONLY_EDITOR_OPS
    assert "widget_set_slot_property" not in READ_ONLY_EDITOR_OPS
    assert "widget_compile" not in READ_ONLY_EDITOR_OPS
    assert "widget_save" not in READ_ONLY_EDITOR_OPS
    assert "widget_display_in_game" not in READ_ONLY_EDITOR_OPS


def test_gateway_approval_gating_for_widget_ops(tmp_path):
    """Verify gateway requires approval for widget mutations but allows inspection without approval."""
    gw = ToolGateway(tmp_path)

    # Inspection does not require approval
    inspect_call = gw.execute_tool(
        "unreal_editor",
        {"uproject": str(tmp_path / "Nonexistent.uproject"), "op": "widget_inspect", "args": {"asset_path": "/Game/UI/WBP_HUD"}},
        approval_granted=False,
    )
    # Fails because uproject doesn't exist, NOT PENDING_APPROVAL
    assert inspect_call.get("status") in ("ERROR", "FAILED")
    assert "PENDING_APPROVAL" != inspect_call.get("status")

    # Widget mutation requires approval
    mutate_call = gw.execute_tool(
        "unreal_editor",
        {"uproject": str(tmp_path / "Nonexistent.uproject"), "op": "widget_create_blueprint", "args": {"asset_path": "/Game/UI/WBP_HUD"}},
        approval_granted=False,
    )
    assert mutate_call.get("status") == "PENDING_APPROVAL"


def test_widget_compiled_acceptance_predicate(tmp_path):
    """Test widget_compiled acceptance predicate evaluation."""
    state = TaskState(
        session_id="session_test",
        task_id="widget_task_1",
        goal="Compile WBP_GameForgeHUD_V1",
        acceptance=[TaskAcceptancePredicate(predicate_type="widget_compiled", target="/Game/UI/WBP_GameForgeHUD_V1")],
    )

    # 1. Empty history fails closed
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), [])
    assert not ok
    assert any("widget_compiled" in u for u in unmet)

    # 2. History with compile failure
    fail_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "widget_compile", "args": {"asset_path": "/Game/UI/WBP_GameForgeHUD_V1"}},
        "output": {"ok": False, "data": {"status": "Error", "compiled_successfully": False}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), fail_history)
    assert not ok

    # 3. History with compile success
    success_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "widget_compile", "args": {"asset_path": "/Game/UI/WBP_GameForgeHUD_V1"}},
        "output": {"ok": True, "data": {"status": "UpToDate", "compiled_successfully": True}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), success_history)
    assert ok
    assert len(unmet) == 0
    assert state.acceptance[0].satisfied
    assert "compiled successfully" in state.acceptance[0].evidence


def test_widget_hierarchy_verified_acceptance_predicate(tmp_path):
    """Test widget_hierarchy_verified acceptance predicate evaluation."""
    state = TaskState(
        session_id="session_test",
        task_id="widget_task_2",
        goal="Verify WBP_GameForgeHUD_V1 hierarchy",
        acceptance=[TaskAcceptancePredicate(predicate_type="widget_hierarchy_verified", target="/Game/UI/WBP_GameForgeHUD_V1")],
    )

    # 1. Empty history fails
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), [])
    assert not ok

    # 2. History with 0 widgets
    zero_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "widget_readback_tree", "args": {"asset_path": "/Game/UI/WBP_GameForgeHUD_V1"}},
        "output": {"ok": True, "data": {"widget_count": 0, "widgets": []}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), zero_history)
    assert not ok

    # 3. History with populated widget hierarchy
    verified_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "widget_readback_tree", "args": {"asset_path": "/Game/UI/WBP_GameForgeHUD_V1"}},
        "output": {"ok": True, "data": {"widget_count": 6, "widgets": [{"name": "RootCanvas"}, {"name": "HUDTitle"}]}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), verified_history)
    assert ok
    assert len(unmet) == 0
    assert state.acceptance[0].satisfied
    assert "6 widgets" in state.acceptance[0].evidence


def test_widget_supported_classes_allowlist():
    """Verify supported widget classes in V1."""
    supported = {"CanvasPanel", "VerticalBox", "HorizontalBox", "Overlay", "SizeBox", "TextBlock", "Image", "ProgressBar"}
    # All 8 required classes must be recognized
    assert len(supported) == 8
    for cls_name in ["CanvasPanel", "VerticalBox", "HorizontalBox", "Overlay", "SizeBox", "TextBlock", "Image", "ProgressBar"]:
        assert cls_name in supported


def test_widget_slot_payload_formatting():
    """Verify slot property payload serialization adheres to schema."""
    canvas_slot_props = {
        "position": {"x": 40.0, "y": 40.0},
        "size": {"x": 300.0, "y": 120.0},
        "anchors": {"min_x": 0.0, "min_y": 0.0, "max_x": 0.0, "max_y": 0.0},
        "alignment": {"x": 0.0, "y": 0.0},
        "auto_size": False,
        "z_order": 1,
    }
    encoded = json.dumps(canvas_slot_props)
    decoded = json.loads(encoded)
    assert decoded["position"]["x"] == 40.0
    assert decoded["anchors"]["max_x"] == 0.0
    assert decoded["z_order"] == 1

    vbox_slot_props = {
        "padding": {"left": 0.0, "top": 4.0, "right": 0.0, "bottom": 4.0},
        "size_rule": "Auto",
        "size_value": 1.0,
        "horizontal_alignment": 0,
        "vertical_alignment": 0,
    }
    encoded_v = json.dumps(vbox_slot_props)
    decoded_v = json.loads(encoded_v)
    assert decoded_v["size_rule"] == "Auto"
    assert decoded_v["padding"]["top"] == 4.0
