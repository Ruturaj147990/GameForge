"""P0 WI-0.1: plans complete only on evidence (audit F-03)."""
from pathlib import Path

import pytest

from src.gameforge_ide.backend.agent.plan_executor import TaskPlanExecutor
from src.gameforge_ide.backend.agent.plan_generator import PlanGenerator
from src.gameforge_ide.backend.agent.task_plan import TaskNode, TaskPlan
from src.gameforge_ide.backend.agent.task_state import TaskAcceptancePredicate, TaskState
from src.gameforge_ide.backend.tools.gateway import ToolGateway


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    return d


def _state(pred: TaskAcceptancePredicate) -> TaskState:
    return TaskState(session_id="s", goal="g", acceptance=[pred])


def test_custom_predicate_preset_true_is_ignored(ws):
    st = _state(TaskAcceptancePredicate(predicate_type="custom", target="inspection_complete", satisfied=True))
    ok, unmet = st.evaluate_acceptance(ws, set(), [])
    assert not ok and unmet


def test_custom_predicate_unknown_target_never_satisfied(ws):
    st = _state(TaskAcceptancePredicate(predicate_type="custom", target="whatever", satisfied=True))
    ok, unmet = st.evaluate_acceptance(ws, set(), [{"tool_name": "list_dir", "status": "SUCCESS", "output": {}}])
    assert not ok and "no registered evaluator" in unmet[0]


def test_inspection_complete_satisfied_by_successful_list_dir(ws):
    st = _state(TaskAcceptancePredicate(predicate_type="custom", target="inspection_complete"))
    ok, _ = st.evaluate_acceptance(ws, set(), [{"tool_name": "list_dir", "status": "SUCCESS", "output": {}}])
    assert ok


def test_task_without_tool_and_predicates_fails(ws):
    plan = TaskPlan(goal="no evidence")
    plan.add_task(TaskNode(task_id="t1", title="t", objective="o", expected_result="r"))
    result = TaskPlanExecutor(ws, tool_gateway=ToolGateway(ws)).run_plan(plan, auto_approve_all=True)
    assert result.tasks["t1"].status == "FAILED"
    assert "NO_EVIDENCE" in result.tasks["t1"].error_message


def test_default_plan_completes_only_via_real_read(ws):
    (ws / "a.txt").write_text("x", encoding="utf-8")
    plan = PlanGenerator(ws, tool_gateway=ToolGateway(ws)).generate_plan_from_prompt("tidy things up")
    result = TaskPlanExecutor(ws, tool_gateway=ToolGateway(ws)).run_plan(plan, auto_approve_all=True)
    assert result.tasks["step1_inspect"].status == "COMPLETED"
