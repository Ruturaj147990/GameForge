import threading
import time
from pathlib import Path
import pytest

from src.gameforge_ide.forge.executor import (
    ForgeExecutor,
    StepContext,
    StepOutcome,
)
from src.gameforge_ide.forge.model import (
    RunSpec,
    RunState,
    StepKind,
    StepRecord,
    StepSpec,
    StepStatus,
)
from src.gameforge_ide.forge.store import RunStore


def test_happy_path_3_steps_persistence(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    calls = []

    def handler_design(ctx: StepContext) -> StepOutcome:
        calls.append("design")
        ctx.log("designing game")
        return StepOutcome(True, data={"recipe": "platformer"})

    def handler_scaffold(ctx: StepContext) -> StepOutcome:
        calls.append("scaffold")
        assert ctx.shared["s1"]["recipe"] == "platformer"
        return StepOutcome(True, data={"scaffolded": True})

    def handler_build(ctx: StepContext) -> StepOutcome:
        calls.append("build")
        return StepOutcome(True, data={"built": True}, artifacts=[{"path": "build.log", "kind": "log"}])

    handlers = {
        StepKind.DESIGN.value: handler_design,
        StepKind.SCAFFOLD.value: handler_scaffold,
        StepKind.BUILD.value: handler_build,
    }

    s1 = StepSpec(step_id="s1", kind=StepKind.DESIGN, title="Design")
    s2 = StepSpec(step_id="s2", kind=StepKind.SCAFFOLD, title="Scaffold", depends_on=["s1"])
    s3 = StepSpec(step_id="s3", kind=StepKind.BUILD, title="Build", depends_on=["s2"])

    run = RunSpec(title="Happy Path", workspace_dir=str(ws), steps=[s1, s2, s3])
    state = RunState.new(run)

    # Track store.save calls
    save_count = 0
    orig_save = store.save

    def tracking_save(st):
        nonlocal save_count
        save_count += 1
        return orig_save(st)

    store.save = tracking_save

    executor = ForgeExecutor(handlers)
    result = executor.run(state, store)

    assert result.status == "DONE"
    assert calls == ["design", "scaffold", "build"]
    assert all(r.status == StepStatus.DONE for r in result.records.values())
    assert result.records["s3"].artifacts[0].path == "build.log"

    # Persistence happened at run start, each step start, each step finish, and run finish
    # 1 (run_started) + 3*(step_started + step_finished) + 1 (run_finished) = 8 saves
    assert save_count >= 8

    # Events were appended
    events = store.load_events(run.run_id)
    kinds = [e["kind"] for e in events]
    assert "run_started" in kinds
    assert "log" in kinds
    assert "run_finished" in kinds


def test_failure_blocks_dependants_leaves_independent(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    # a -> b (fails) -> c (should be blocked)
    # independent: x (should pass)
    calls = []

    def handle_ok(ctx: StepContext) -> StepOutcome:
        calls.append(ctx.step.step_id)
        return StepOutcome(True)

    def handle_fail(ctx: StepContext) -> StepOutcome:
        calls.append(ctx.step.step_id)
        return StepOutcome(False, errors=["Compile error in Game.cpp"])

    handlers = {
        StepKind.DESIGN.value: handle_ok,
        StepKind.CODEGEN.value: handle_fail,
        StepKind.BUILD.value: handle_ok,
        StepKind.CONTENT.value: handle_ok,
    }

    a = StepSpec(step_id="a", kind=StepKind.DESIGN, title="A")
    b = StepSpec(step_id="b", kind=StepKind.CODEGEN, title="B", depends_on=["a"])
    c = StepSpec(step_id="c", kind=StepKind.BUILD, title="C", depends_on=["b"])
    x = StepSpec(step_id="x", kind=StepKind.CONTENT, title="X")

    run = RunSpec(title="Branch Test", workspace_dir=str(ws), steps=[a, b, c, x])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)
    result = executor.run(state, store)

    assert result.status == "FAILED"
    assert result.records["a"].status == StepStatus.DONE
    assert result.records["b"].status == StepStatus.FAILED
    assert result.records["c"].status == StepStatus.BLOCKED
    assert result.records["x"].status == StepStatus.DONE
    assert "Compile error" in result.records["b"].errors[0]
    assert "dependency not done" in result.records["c"].errors[0]


def test_resume_skips_done_steps(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    call_counts = {"s1": 0, "s2": 0}

    def h_s1(ctx: StepContext) -> StepOutcome:
        call_counts["s1"] += 1
        return StepOutcome(True)

    def h_s2(ctx: StepContext) -> StepOutcome:
        call_counts["s2"] += 1
        return StepOutcome(True)

    handlers = {StepKind.DESIGN.value: h_s1, StepKind.BUILD.value: h_s2}

    s1 = StepSpec(step_id="s1", kind=StepKind.DESIGN, title="S1")
    s2 = StepSpec(step_id="s2", kind=StepKind.BUILD, title="S2", depends_on=["s1"])

    run = RunSpec(title="Resume Test", workspace_dir=str(ws), steps=[s1, s2])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)
    # First run completes s1, simulate crash mid-s2 by mutating s2 to RUNNING
    state = executor.run(state, store)
    assert state.status == "DONE"
    assert call_counts == {"s1": 1, "s2": 1}

    # Simulate crash during s2
    state.records["s2"].status = StepStatus.RUNNING
    state.status = "RUNNING"

    # Second run should resume s2, skipping s1
    resumed = executor.run(state, store)
    assert resumed.status == "DONE"
    assert call_counts["s1"] == 1  # s1 was skipped!
    assert call_counts["s2"] == 2  # s2 re-ran!


def test_input_hash_change_invalidates_downstream(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    # Graph: s1 -> s2 -> s3
    call_counts = {"s1": 0, "s2": 0, "s3": 0}

    def make_handler(name):
        def fn(ctx: StepContext) -> StepOutcome:
            call_counts[name] += 1
            return StepOutcome(True)
        return fn

    handlers = {
        StepKind.DESIGN.value: make_handler("s1"),
        StepKind.CODEGEN.value: make_handler("s2"),
        StepKind.BUILD.value: make_handler("s3"),
    }

    s1 = StepSpec(step_id="s1", kind=StepKind.DESIGN, title="S1", inputs={"v": 1})
    s2 = StepSpec(step_id="s2", kind=StepKind.CODEGEN, title="S2", depends_on=["s1"], inputs={"opt": True})
    s3 = StepSpec(step_id="s3", kind=StepKind.BUILD, title="S3", depends_on=["s2"])

    run = RunSpec(title="Hash Invalidation", workspace_dir=str(ws), steps=[s1, s2, s3])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)
    state = executor.run(state, store)
    assert state.status == "DONE"
    assert call_counts == {"s1": 1, "s2": 1, "s3": 1}

    # Now modify inputs of s2: s1 is upstream (unchanged), s2 changed, s3 downstream (affected)
    s2_new = StepSpec(step_id="s2", kind=StepKind.CODEGEN, title="S2", depends_on=["s1"], inputs={"opt": False})
    run_modified = RunSpec(title="Hash Invalidation", workspace_dir=str(ws), steps=[s1, s2_new, s3])
    state.run = run_modified

    state_after = executor.run(state, store)
    assert state_after.status == "DONE"
    assert call_counts["s1"] == 1  # s1 was skipped
    assert call_counts["s2"] == 2  # s2 re-ran
    assert call_counts["s3"] == 2  # s3 re-ran because s2's effective hash changed


def test_run_approval_suspends_and_resumes(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    called = False

    def handle(ctx: StepContext) -> StepOutcome:
        nonlocal called
        called = True
        return StepOutcome(True)

    handlers = {StepKind.BUILD.value: handle}
    s = StepSpec(step_id="s1", kind=StepKind.BUILD, title="Build", approval="run")
    run = RunSpec(title="Approval Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)

    # First run: suspends waiting for approval
    res1 = executor.run(state, store)
    assert res1.status == "WAITING_APPROVAL"
    assert called is False

    # Grant approval
    state.approvals["run"] = "apr_test_123"

    # Second run: proceeds to completion
    res2 = executor.run(state, store)
    assert res2.status == "DONE"
    assert called is True


def test_repair_hook_retry(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    attempts = 0

    def handler(ctx: StepContext) -> StepOutcome:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return StepOutcome(False, errors=["repairable error"], repairable=True)
        return StepOutcome(True, data={"repaired": True})

    repaired_count = 0

    def repair_hook(ctx: StepContext, out: StepOutcome) -> bool:
        nonlocal repaired_count
        repaired_count += 1
        return True

    handlers = {StepKind.CODEGEN.value: handler}
    repair_hooks = {StepKind.CODEGEN.value: repair_hook}

    s = StepSpec(step_id="code", kind=StepKind.CODEGEN, title="Codegen", max_attempts=3)
    run = RunSpec(title="Repair Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers, repair_hooks=repair_hooks)
    res = executor.run(state, store)

    assert res.status == "DONE"
    assert attempts == 3
    assert repaired_count == 2
    assert res.records["code"].attempts == 3


def test_step_timeout(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    def slow_handler(ctx: StepContext) -> StepOutcome:
        # Check cancel event or sleep
        for _ in range(50):
            if ctx.cancel.is_set():
                break
            time.sleep(0.05)
        return StepOutcome(True)

    handlers = {StepKind.BUILD.value: slow_handler}
    s = StepSpec(step_id="build", kind=StepKind.BUILD, title="Build", timeout_s=0.2)
    run = RunSpec(title="Timeout Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)
    res = executor.run(state, store)

    assert res.status == "FAILED"
    assert res.records["build"].status == StepStatus.FAILED
    assert any("TIMEOUT" in err for err in res.records["build"].errors)


def test_handler_exception_handled_as_failure(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    def crashing_handler(ctx: StepContext) -> StepOutcome:
        raise RuntimeError("Unexpected boom!")

    handlers = {StepKind.BUILD.value: crashing_handler}
    s = StepSpec(step_id="build", kind=StepKind.BUILD, title="Build")
    run = RunSpec(title="Crash Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)
    res = executor.run(state, store)

    assert res.status == "FAILED"
    assert res.records["build"].status == StepStatus.FAILED
    assert any("RuntimeError: Unexpected boom!" in err for err in res.records["build"].errors)


def test_cancel_mid_run(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    executor = None

    def handle_s1(ctx: StepContext) -> StepOutcome:
        # Cancel the executor while s1 is running
        executor.request_cancel()
        return StepOutcome(True)

    def handle_s2(ctx: StepContext) -> StepOutcome:
        return StepOutcome(True)

    handlers = {StepKind.DESIGN.value: handle_s1, StepKind.BUILD.value: handle_s2}
    s1 = StepSpec(step_id="s1", kind=StepKind.DESIGN, title="S1")
    s2 = StepSpec(step_id="s2", kind=StepKind.BUILD, title="S2", depends_on=["s1"])

    run = RunSpec(title="Cancel Test", workspace_dir=str(ws), steps=[s1, s2])
    state = RunState.new(run)

    executor = ForgeExecutor(handlers)
    res = executor.run(state, store)

    assert res.status == "CANCELLED"
    assert res.records["s1"].status == StepStatus.DONE
    assert res.records["s2"].status == StepStatus.PENDING
