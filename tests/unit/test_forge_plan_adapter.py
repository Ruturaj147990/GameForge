"""Unit tests for Forge plan adapter and tool call handler."""
import threading
from pathlib import Path
import pytest

from src.gameforge_ide.backend.agent.task_plan import TaskNode, TaskPlan
from src.gameforge_ide.backend.agent.task_state import TaskAcceptancePredicate
from src.gameforge_ide.forge.model import StepKind, StepStatus
from src.gameforge_ide.forge.plan_adapter import plan_to_run, run_plan_on_forge, run_state_to_task_plan
from src.gameforge_ide.forge.handlers.tool_call import tool_call_handler
from src.gameforge_ide.forge.executor import StepContext, StepOutcome


def test_plan_to_run_conversion(tmp_path: Path):
    plan = TaskPlan(goal="Test Conversion Goal")
    t1 = TaskNode(
        task_id="t1",
        title="Task 1",
        objective="Inspect",
        expected_result="Ok",
        task_type="inspect",
        permitted_tools=["read_file"],
        dependency_ids=[],
        requires_approval=False,
        timeout_seconds=60.0,
        retry_limit=1,
        tool_call={"name": "read_file", "arguments": {"subpath": "test.txt"}},
        acceptance=[TaskAcceptancePredicate(predicate_type="file_exists", target="test.txt")],
    )
    t2 = TaskNode(
        task_id="t2",
        title="Task 2 Mutate",
        objective="Mutate actor",
        expected_result="Actor spawned",
        task_type="editor_op",
        permitted_tools=["unreal_editor"],
        dependency_ids=["t1"],
        requires_approval=True,
        timeout_seconds=120.0,
        retry_limit=2,
        tool_call={"name": "unreal_editor", "arguments": {"op": "spawn_actor", "args": {}}},
    )
    plan.add_task(t1)
    plan.add_task(t2)

    run_spec = plan_to_run(plan, tmp_path)
    assert run_spec.run_id == plan.plan_id
    assert run_spec.title == plan.goal
    assert len(run_spec.steps) == 2

    s1 = next(s for s in run_spec.steps if s.step_id == "t1")
    assert s1.kind == StepKind.TOOL_CALL
    assert s1.depends_on == []
    assert s1.approval == "none"
    assert s1.engine_lock is False
    assert s1.timeout_s == 60.0
    assert s1.max_attempts == 2

    s2 = next(s for s in run_spec.steps if s.step_id == "t2")
    assert s2.kind == StepKind.TOOL_CALL
    assert s2.depends_on == ["t1"]
    assert s2.approval == "step"
    assert s2.engine_lock is True  # spawn_actor is mutating
    assert s2.timeout_s == 120.0
    assert s2.max_attempts == 3


def test_tool_call_handler_repetition_limit(tmp_path: Path):
    from src.gameforge_ide.forge.model import RunSpec, StepRecord, StepSpec
    run = RunSpec(run_id="run_rep", title="Repetition Test", workspace_dir=str(tmp_path), steps=[])
    step = StepSpec(
        step_id="step_rep",
        kind=StepKind.TOOL_CALL,
        title="Rep Step",
        inputs={
            "tool": "read_file",
            "arguments": {"subpath": "a.txt"},
            "repetition_limit": 3,
        },
    )
    record = StepRecord(step_id="step_rep")
    shared = {}

    for i in range(2):
        ctx = StepContext(
            run=run,
            step=step,
            record=record,
            shared=shared,
            project_dir=None,
            workspace_dir=tmp_path,
            cancel=threading.Event(),
            log=lambda l: None,
        )
        out = tool_call_handler(ctx)
        # Even if read_file fails with file not found, it's not repetition blocked yet
        assert not (out.blocked and "repetition" in str(out.errors))

    # 3rd identical call
    ctx = StepContext(
        run=run,
        step=step,
        record=record,
        shared=shared,
        project_dir=None,
        workspace_dir=tmp_path,
        cancel=threading.Event(),
        log=lambda l: None,
    )
    out = tool_call_handler(ctx)
    assert out.ok is False
    assert out.blocked is True
    assert any("repetition_budget_exhausted" in e for e in out.errors)


def test_tool_call_handler_permitted_tools(tmp_path: Path):
    from src.gameforge_ide.forge.model import RunSpec, StepRecord, StepSpec
    run = RunSpec(run_id="run_perm", title="Perm Test", workspace_dir=str(tmp_path), steps=[])
    step = StepSpec(
        step_id="step_perm",
        kind=StepKind.TOOL_CALL,
        title="Perm Step",
        inputs={
            "tool": "propose_edit",
            "arguments": {},
            "permitted_tools": ["read_file", "list_dir"],
        },
    )
    record = StepRecord(step_id="step_perm")
    ctx = StepContext(
        run=run,
        step=step,
        record=record,
        shared={},
        project_dir=None,
        workspace_dir=tmp_path,
        cancel=threading.Event(),
        log=lambda l: None,
    )
    out = tool_call_handler(ctx)
    assert out.ok is False
    assert out.blocked is True
    assert any("not in permitted tools" in e for e in out.errors)


def test_tool_call_handler_no_evidence_fail_closed(tmp_path: Path):
    from src.gameforge_ide.forge.model import RunSpec, StepRecord, StepSpec
    run = RunSpec(run_id="run_no_ev", title="No Ev Test", workspace_dir=str(tmp_path), steps=[])
    step = StepSpec(
        step_id="step_no_ev",
        kind=StepKind.TOOL_CALL,
        title="No Ev Step",
        inputs={"tool": "", "arguments": {}, "acceptance": []},
        approval="none",
    )
    record = StepRecord(step_id="step_no_ev")
    ctx = StepContext(
        run=run,
        step=step,
        record=record,
        shared={},
        project_dir=None,
        workspace_dir=tmp_path,
        cancel=threading.Event(),
        log=lambda l: None,
    )
    out = tool_call_handler(ctx)
    assert out.ok is False
    assert out.blocked is True
    assert any("NO_EVIDENCE" in e for e in out.errors)


def test_run_plan_on_forge_happy_path(tmp_path: Path):
    # Create test file in tmp_path
    (tmp_path / "hello.txt").write_text("Hello Forge!", encoding="utf-8")

    plan = TaskPlan(goal="Read test file and verify existence")
    t1 = TaskNode(
        task_id="t1",
        title="Read hello.txt",
        objective="Read file",
        expected_result="Content read",
        task_type="inspect",
        permitted_tools=["read_file"],
        tool_call={"name": "read_file", "arguments": {"subpath": "hello.txt"}},
        acceptance=[TaskAcceptancePredicate(predicate_type="file_exists", target="hello.txt")],
    )
    plan.add_task(t1)

    events = []
    res = run_plan_on_forge(plan, tmp_path, auto_approve_all=True, on_event=lambda ev: events.append(ev))
    assert res.status == "COMPLETED"
    assert res.tasks["t1"].status == "COMPLETED"
    assert res.tasks["t1"].acceptance[0].satisfied is True
    assert len(events) >= 2
