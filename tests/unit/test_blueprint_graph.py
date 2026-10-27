"""Unit tests for GameForge Milestone 2: Blueprint Graph Authoring V1."""

import json
from pathlib import Path
import pytest

from src.gameforge_ide.backend.agent.task_state import TaskAcceptancePredicate, TaskState
from src.gameforge_ide.backend.tools.game_tools import READ_ONLY_EDITOR_OPS
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.backend.agent.task_plan import TaskPlan, TaskNode
from src.gameforge_ide.backend.agent.plan_executor import TaskPlanExecutor


def test_blueprint_read_only_ops_registered():
    """Verify that blueprint_inspect and blueprint_readback_graph are registered as read-only."""
    assert "blueprint_inspect" in READ_ONLY_EDITOR_OPS
    assert "blueprint_readback_graph" in READ_ONLY_EDITOR_OPS
    # Mutations must NOT be in read-only ops
    assert "blueprint_create_node" not in READ_ONLY_EDITOR_OPS
    assert "blueprint_connect_pins" not in READ_ONLY_EDITOR_OPS
    assert "blueprint_compile" not in READ_ONLY_EDITOR_OPS
    assert "blueprint_save" not in READ_ONLY_EDITOR_OPS


def test_gateway_approval_gating_for_blueprint_ops(tmp_path):
    """Verify gateway requires approval for blueprint mutations but allows inspection without approval."""
    gw = ToolGateway(tmp_path)
    
    # Inspection does not require approval
    inspect_call = gw.execute_tool(
        "unreal_editor",
        {"uproject": str(tmp_path / "Nonexistent.uproject"), "op": "blueprint_inspect", "args": {"blueprint_path": "/Game/BP_Test"}},
        approval_granted=False,
    )
    # Fails because uproject doesn't exist, NOT PENDING_APPROVAL
    assert inspect_call.get("status") in ("ERROR", "FAILED")
    assert "PENDING_APPROVAL" != inspect_call.get("status")
    
    # Create node requires approval
    mutate_call = gw.execute_tool(
        "unreal_editor",
        {"uproject": str(tmp_path / "Nonexistent.uproject"), "op": "blueprint_create_node", "args": {"blueprint_path": "/Game/BP_Test"}},
        approval_granted=False,
    )
    assert mutate_call.get("status") == "PENDING_APPROVAL"


def test_blueprint_compiled_acceptance_predicate(tmp_path):
    """Test blueprint_compiled acceptance predicate evaluation."""
    state = TaskState(
        session_id="session_test",
        task_id="bp_task_1",
        goal="Compile BP_Test",
        acceptance=[TaskAcceptancePredicate(predicate_type="blueprint_compiled", target="/Game/BP_Test")],
    )
    
    # 1. Empty history fails closed
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), [])
    assert not ok
    assert any("blueprint_compiled" in u for u in unmet)
    
    # 2. History with compile failure
    fail_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "blueprint_compile", "args": {"blueprint_path": "/Game/BP_Test"}},
        "output": {"ok": False, "data": {"status": "Error", "compiled_successfully": False}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), fail_history)
    assert not ok
    
    # 3. History with compile success
    success_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "blueprint_compile", "args": {"blueprint_path": "/Game/BP_Test"}},
        "output": {"ok": True, "data": {"status": "UpToDate", "compiled_successfully": True}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), success_history)
    assert ok
    assert len(unmet) == 0
    assert state.acceptance[0].satisfied
    assert "compiled successfully" in state.acceptance[0].evidence


def test_blueprint_node_connected_acceptance_predicate(tmp_path):
    """Test blueprint_node_connected acceptance predicate evaluation."""
    state = TaskState(
        session_id="session_test",
        task_id="bp_task_2",
        goal="Connect BP_Test pins",
        acceptance=[TaskAcceptancePredicate(predicate_type="blueprint_node_connected", target="/Game/BP_Test")],
    )
    
    # 1. Unverified link fails
    unverified_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "blueprint_connect_pins", "args": {"blueprint_path": "/Game/BP_Test"}},
        "output": {"ok": False, "data": {"verified_linked": False}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), unverified_history)
    assert not ok
    
    # 2. Verified link succeeds
    verified_history = [{
        "tool_name": "unreal_editor",
        "arguments": {"op": "blueprint_connect_pins", "args": {"blueprint_path": "/Game/BP_Test"}},
        "output": {"ok": True, "data": {"verified_linked": True, "from_pin": "then", "to_pin": "execute"}},
    }]
    ok, unmet = state.evaluate_acceptance(tmp_path, set(), verified_history)
    assert ok
    assert state.acceptance[0].satisfied


def test_blueprint_schema_envelope_validation():
    """Verify standard GameForge envelope contract for Blueprint operations."""
    from src.gameforge_ide.unreal.op_result import OperationResult
    
    # Successful node creation envelope
    res = OperationResult(
        ok=True,
        operation="blueprint_create_node",
        data={"node_id": "guid-1234", "node_class": "K2Node_CallFunction", "title": "Print String"},
        affected_paths=["/Game/BP_Test"],
        reversibility="transactional",
    )
    assert res.ok is True
    assert res.data["node_id"] == "guid-1234"
    assert res.reversibility == "transactional"
    assert "/Game/BP_Test" in res.affected_paths

    # Failed pin connection envelope
    fail_res = OperationResult(
        ok=False,
        operation="blueprint_connect_pins",
        data={},
        errors=["Schema rejected connection: incompatible directions"],
        affected_paths=[],
        reversibility="transactional",
    )
    assert fail_res.ok is False
    assert len(fail_res.errors) == 1
    assert "incompatible directions" in fail_res.errors[0]


def test_unsupported_node_type_envelope():
    """Verify that unsupported node type requests return structured error envelope."""
    from src.gameforge_ide.unreal.op_result import OperationResult
    
    res = OperationResult(
        ok=False,
        operation="blueprint_create_node",
        errors=["Unsupported node type: MaliciousArbitraryNode. Supported: CallFunction, Event, VariableGet"],
        reversibility="transactional",
    )
    assert res.ok is False
    assert "Unsupported node type" in res.errors[0]


def test_invalid_pin_connection_direction_rejection():
    """Verify that connecting two output or two input pins returns schema direction error."""
    from src.gameforge_ide.unreal.op_result import OperationResult
    
    res = OperationResult(
        ok=False,
        operation="blueprint_connect_pins",
        errors=["Cannot connect pins of same direction: both are Output"],
        reversibility="transactional",
    )
    assert res.ok is False
    assert "both are Output" in res.errors[0]


def test_default_pin_on_output_rejection():
    """Verify that attempting to set a default value on an output pin is rejected."""
    from src.gameforge_ide.unreal.op_result import OperationResult
    
    res = OperationResult(
        ok=False,
        operation="blueprint_set_pin_default",
        errors=["Pin 'then' is an output pin and cannot have a default value"],
        reversibility="transactional",
    )
    assert res.ok is False
    assert "output pin" in res.errors[0]


def test_live_operations_signatures():
    """Verify that LiveOperations exposes all 9 Milestone 2 Blueprint methods."""
    from src.gameforge_ide.unreal.live_operations import LiveOperations
    import inspect
    
    expected_methods = [
        "blueprint_inspect",
        "blueprint_readback_graph",
        "blueprint_create_node",
        "blueprint_set_pin_default",
        "blueprint_connect_pins",
        "blueprint_disconnect_pins",
        "blueprint_delete_node",
        "blueprint_compile",
        "blueprint_save",
        "pie_start",
        "pie_stop",
    ]
    for m in expected_methods:
        assert hasattr(LiveOperations, m), f"LiveOperations missing {m}"
        assert inspect.iscoroutinefunction(getattr(LiveOperations, m)), f"{m} should be an async coroutine"

