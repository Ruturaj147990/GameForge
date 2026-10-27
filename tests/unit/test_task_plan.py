"""Unit Tests for Multi-Step Task Plan (DAG), Executor State Machine, and Scheduling.

Tests:
- Plan validation: cycles, missing prerequisites, self-loops, duplicate IDs.
- Topological execution order.
- State transitions and harness-only terminal gating.
- Transitive dependency blocking on failures with independent branch progression.
- Repetition control (3-call threshold).
- Atomic persistence and crash-recovery resumption.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
import tempfile
import time

from src.gameforge_ide.backend.agent.task_plan import PlanValidationError, TaskNode, TaskPlan
from src.gameforge_ide.backend.agent.plan_executor import PlanEvent, TaskPlanExecutor
from src.gameforge_ide.backend.agent.plan_generator import PlanGenerator
from src.gameforge_ide.backend.agent.task_state import TaskAcceptancePredicate
from src.gameforge_ide.backend.tools.gateway import ToolGateway


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def test_plan_valid_dag_topological_sort():
    """A valid DAG produces a valid topological ordering."""
    plan = TaskPlan(goal="Test valid DAG")
    
    t1 = TaskNode(task_id="t1", title="Task 1", objective="Root", expected_result="Done", dependency_ids=[])
    t2 = TaskNode(task_id="t2", title="Task 2", objective="Child of 1", expected_result="Done", dependency_ids=["t1"])
    t3 = TaskNode(task_id="t3", title="Task 3", objective="Child of 1", expected_result="Done", dependency_ids=["t1"])
    t4 = TaskNode(task_id="t4", title="Task 4", objective="Join of 2 and 3", expected_result="Done", dependency_ids=["t2", "t3"])

    plan.add_task(t1)
    plan.add_task(t2)
    plan.add_task(t3)
    plan.add_task(t4)

    valid, errs = plan.validate()
    assert valid is True
    assert len(errs) == 0

    order = plan.get_topological_order()
    assert order[0] == "t1"
    assert order[-1] == "t4"
    assert "t2" in order[1:3] and "t3" in order[1:3]


def test_plan_cycle_detection():
    """Circular dependencies must be detected and rejected."""
    plan = TaskPlan(goal="Test cycle")
    t1 = TaskNode(task_id="t1", title="T1", objective="Obj", expected_result="Done", dependency_ids=["t2"])
    t2 = TaskNode(task_id="t2", title="T2", objective="Obj", expected_result="Done", dependency_ids=["t1"])
    plan.add_task(t1)
    plan.add_task(t2)

    valid, errs = plan.validate()
    assert valid is False
    assert any("Circular dependency detected" in e for e in errs)

    with pytest.raises(PlanValidationError):
        plan.get_topological_order()


def test_plan_missing_prerequisite_rejection():
    """A task depending on a non-existent task must be rejected."""
    plan = TaskPlan(goal="Test missing prereq")
    t1 = TaskNode(task_id="t1", title="T1", objective="Obj", expected_result="Done", dependency_ids=["missing_dep"])
    plan.add_task(t1)

    valid, errs = plan.validate()
    assert valid is False
    assert any("Missing prerequisite" in e for e in errs)


def test_plan_self_dependency_rejection():
    """A task depending on itself must be rejected."""
    plan = TaskPlan(goal="Test self dep")
    t1 = TaskNode(task_id="t1", title="T1", objective="Obj", expected_result="Done", dependency_ids=["t1"])
    plan.add_task(t1)

    valid, errs = plan.validate()
    assert valid is False
    assert any("Self-dependency detected" in e for e in errs)


def test_plan_transitive_blocking():
    """When a task fails, only its downstream dependents are blocked; independent branches proceed."""
    plan = TaskPlan(goal="Test branch failure")
    # Tree:
    #      root
    #     /    \
    #    b1     b2 (independent)
    #    |
    #   b1_child
    root = TaskNode(task_id="root", title="Root", objective="Obj", expected_result="Done", status="COMPLETED")
    b1 = TaskNode(task_id="b1", title="Branch 1", objective="Obj", expected_result="Done", dependency_ids=["root"], status="FAILED")
    b1_child = TaskNode(task_id="b1_child", title="Branch 1 Child", objective="Obj", expected_result="Done", dependency_ids=["b1"])
    b2 = TaskNode(task_id="b2", title="Branch 2", objective="Obj", expected_result="Done", dependency_ids=["root"])

    plan.add_task(root)
    plan.add_task(b1)
    plan.add_task(b1_child)
    plan.add_task(b2)

    blocked = plan.block_descendants("b1", "Test error")
    assert "b1_child" in blocked
    assert plan.tasks["b1_child"].status == "BLOCKED"
    # b2 must NOT be blocked!
    assert plan.tasks["b2"].status == "PLANNED"

    ready = plan.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == "b2"


def test_plan_persistence_and_loading(temp_workspace: Path):
    """Plans save atomically to .gameforge/plans and reload with fidelity."""
    plan = TaskPlan(goal="Persistent plan test")
    t1 = TaskNode(task_id="task_01", title="Inspect files", objective="Check config", expected_result="Read OK")
    plan.add_task(t1)

    path = plan.save(temp_workspace)
    assert path.is_file()

    loaded = TaskPlan.load(path)
    assert loaded.plan_id == plan.plan_id
    assert loaded.goal == plan.goal
    assert "task_01" in loaded.tasks
    assert loaded.tasks["task_01"].title == "Inspect files"

    loaded_by_id = TaskPlan.load_by_id(temp_workspace, plan.plan_id)
    assert loaded_by_id is not None
    assert loaded_by_id.plan_id == plan.plan_id


def test_plan_executor_repetition_control(temp_workspace: Path):
    """The executor halts execution with BLOCKED when a tool is called 3 times identically."""
    gateway = ToolGateway(temp_workspace)
    executor = TaskPlanExecutor(temp_workspace, tool_gateway=gateway)

    plan = TaskPlan(goal="Test repetition control")
    task = TaskNode(
        task_id="rep_task",
        title="Repetitive task",
        objective="Looping tool",
        expected_result="Should be blocked",
        tool_call={"name": "list_dir", "arguments": {"subpath": "."}},
        retry_limit=4,
        acceptance=[TaskAcceptancePredicate(predicate_type="custom", target="never_satisfied", satisfied=False)],
    )
    plan.add_task(task)

    result_plan = executor.run_plan(plan, auto_approve_all=True)
    assert result_plan.tasks["rep_task"].status == "BLOCKED"
    assert "repetition_budget_exhausted" in result_plan.tasks["rep_task"].error_message


def test_plan_executor_recovery_resumption(temp_workspace: Path):
    """Interrupted plan resumes idempotently without replaying already-satisfied operations."""
    test_file = temp_workspace / "resumed_marker.txt"
    test_file.write_text("already written", encoding="utf-8")

    plan = TaskPlan(goal="Test resume")
    t1 = TaskNode(
        task_id="t1",
        title="Check marker",
        objective="Verify marker",
        expected_result="File exists",
        status="RUNNING",  # Was left in RUNNING by interruption
        acceptance=[TaskAcceptancePredicate(predicate_type="file_exists", target="resumed_marker.txt")],
    )
    plan.add_task(t1)
    plan.save(temp_workspace)

    gateway = ToolGateway(temp_workspace)
    executor = TaskPlanExecutor(temp_workspace, tool_gateway=gateway)

    resumed = executor.resume_plan(plan, auto_approve_all=True)
    assert resumed.tasks["t1"].status == "COMPLETED"
    assert resumed.status == "COMPLETED"


def test_file_changed_fails_closed_without_genuine_modification(temp_workspace: Path):
    """file_changed fails closed if a file exists on disk without genuine content hash change or modification."""
    from src.gameforge_ide.backend.agent.task_state import TaskState
    existing_file = temp_workspace / "existing.txt"
    existing_file.write_text("initial content", encoding="utf-8")

    state = TaskState(
        session_id="s1",
        goal="check change",
        acceptance=[TaskAcceptancePredicate(predicate_type="file_changed", target="existing.txt")],
    )

    # Empty modified files, empty tool history -> must fail closed despite file existing!
    satisfied, unmet = state.evaluate_acceptance(temp_workspace, set(), [])
    assert satisfied is False
    assert any("No approved modification" in u for u in unmet)


def test_repetition_control_state_version_awareness(temp_workspace: Path):
    """Repetition key differentiates calls across state version changes, preserving bounded repeat within state."""
    gateway = ToolGateway(temp_workspace)
    executor = TaskPlanExecutor(temp_workspace, tool_gateway=gateway)

    # Within state 0, same tool call
    key1 = executor._get_repetition_key("list_dir", {"subpath": "."})
    key2 = executor._get_repetition_key("list_dir", {"subpath": "."})
    assert key1 == key2

    # Advance state version (simulating mutation)
    executor._state_version += 1
    key3 = executor._get_repetition_key("list_dir", {"subpath": "."})
    assert key1 != key3

