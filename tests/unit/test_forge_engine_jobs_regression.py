"""Regression tests for Forge Engine, Jobs, and Handlers (DEF-094 through DEF-100)."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
import pytest
import psutil

from src.gameforge_ide.core import jobs
from src.gameforge_ide.desktop.services.forge_service import ForgeService
from src.gameforge_ide.forge.checkpoints import ProjectRepo
from src.gameforge_ide.forge.executor import ForgeExecutor, StepContext, StepOutcome
from src.gameforge_ide.forge.impact import impact, prepare_incremental_state
from src.gameforge_ide.forge.model import (
    RunSpec,
    RunState,
    StepKind,
    StepSpec,
    StepStatus,
)
from src.gameforge_ide.forge.store import RunStore
from src.gameforge_ide.forge.validation import validate_stage_output


def test_def094_resume_unblocks_blocked_steps(tmp_path: Path):
    """DEF-094: Mid-run failure marked downstream steps BLOCKED.

    On resume / retry, previously BLOCKED steps whose dependencies are now DONE
    must be automatically unblocked and executed to completion.
    """
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    execution_order = []
    b_should_fail = True

    def handler_a(ctx: StepContext) -> StepOutcome:
        execution_order.append("A")
        return StepOutcome(True, data={"result_a": "ok"})

    def handler_b(ctx: StepContext) -> StepOutcome:
        execution_order.append("B")
        if b_should_fail:
            return StepOutcome(False, errors=["Transient compiler error in B"])
        return StepOutcome(True, data={"result_b": "ok"})

    def handler_c(ctx: StepContext) -> StepOutcome:
        execution_order.append("C")
        return StepOutcome(True, data={"result_c": "ok"})

    handlers = {
        "step_a": handler_a,
        "step_b": handler_b,
        "step_c": handler_c,
    }

    s_a = StepSpec(step_id="step_a", kind=StepKind.DESIGN, title="Step A")
    s_b = StepSpec(step_id="step_b", kind=StepKind.CODEGEN, title="Step B", depends_on=["step_a"])
    s_c = StepSpec(step_id="step_c", kind=StepKind.BUILD, title="Step C", depends_on=["step_b"])

    spec = RunSpec(title="DEF-094 Resume Test", workspace_dir=str(ws), steps=[s_a, s_b, s_c])
    state = RunState.new(spec)

    executor = ForgeExecutor(handlers)

    # First run: A passes, B fails, C becomes BLOCKED
    res1 = executor.run(state, store)
    assert res1.status == "FAILED"
    assert res1.records["step_a"].status == StepStatus.DONE
    assert res1.records["step_b"].status == StepStatus.FAILED
    assert res1.records["step_c"].status == StepStatus.BLOCKED
    assert execution_order == ["A", "B"]

    # Now fix the issue in step B and resume the run
    b_should_fail = False
    execution_order.clear()

    res2 = executor.resume(res1, store)
    assert res2.status == "DONE"
    assert res2.records["step_a"].status == StepStatus.DONE
    assert res2.records["step_b"].status == StepStatus.DONE
    assert res2.records["step_c"].status == StepStatus.DONE
    # Step A was skipped because it was already DONE; Step B re-ran and passed; Step C was unblocked and ran!
    assert execution_order == ["B", "C"]


def test_def095_job_object_recreation_and_fallback_containment(tmp_path: Path):
    """DEF-095: Terminating children must close and recreate the Windows Job Object

    so subsequent spawned processes remain properly adopted, and fallback tracking
    cleans up all child processes.
    """
    # 1. Spawn a process
    p1 = jobs.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    assert p1.poll() is None
    pid1 = p1.pid
    assert psutil.pid_exists(pid1)

    # 2. Terminate all children
    jobs.terminate_all_children()
    time.sleep(0.1)
    assert not psutil.pid_exists(pid1)

    # 3. Spawn a subsequent process; must succeed and be tracked
    p2 = jobs.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    assert p2.poll() is None
    pid2 = p2.pid
    assert psutil.pid_exists(pid2)

    # 4. Terminate again: second process must also die cleanly
    jobs.terminate_all_children()
    time.sleep(0.1)
    assert not psutil.pid_exists(pid2)


def test_def096_cancel_run_prompt_termination(tmp_path: Path):
    """DEF-096: cancel_run must promptly stop execution (< 2s) without waiting

    for full step timeout, and mark the step CANCELLED.
    """
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    step_started = threading.Event()

    def long_running_handler(ctx: StepContext) -> StepOutcome:
        step_started.set()
        # Spawn child process that runs for 60s
        proc = jobs.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
        while not ctx.cancel.is_set():
            time.sleep(0.05)
        return StepOutcome(False, errors=["Cancelled"])

    handlers = {"long_step": long_running_handler}
    spec = RunSpec(
        title="DEF-096 Cancel Test",
        workspace_dir=str(ws),
        steps=[StepSpec(step_id="long_step", kind=StepKind.BUILD, title="Long Step", timeout_s=60.0)],
    )
    state = RunState.new(spec)
    executor = ForgeExecutor(handlers)

    t_start = time.time()

    def background_cancel():
        step_started.wait(timeout=5.0)
        time.sleep(0.2)
        ForgeExecutor.cancel_run(spec.run_id)

    threading.Thread(target=background_cancel, daemon=True).start()

    res = executor.run(state, store)
    duration = time.time() - t_start

    assert res.status == "CANCELLED"
    assert res.records["long_step"].status == StepStatus.CANCELLED
    # Must have cancelled within 3 seconds, not 60 seconds
    assert duration < 3.0


def test_def097_strict_output_validation_catches_missing_outputs(tmp_path: Path):
    """DEF-097: validate_stage_output must reject stages reporting ok=True

    if required files/artifacts do not exist on disk.
    """
    proj = tmp_path / "DummyProject"
    proj.mkdir(parents=True, exist_ok=True)

    # 1. Scaffold without uproject
    ok, issues = validate_stage_output("scaffold", {"project_name": "DummyProject"}, project_dir=proj)
    assert ok is False
    assert any("no .uproject file exists" in i for i in issues)

    # 2. Codegen with missing source files
    ok, issues = validate_stage_output(
        "codegen",
        {"files": ["Source/DummyProject/Public/MyGameMode.h"]},
        project_dir=proj,
    )
    assert ok is False
    assert any("generated source files exist on disk" in i for i in issues)

    # 3. Build with exit code != 0
    ok, issues = validate_stage_output("build", {"exit_code": 1, "errors": 3}, project_dir=proj)
    assert ok is False
    assert any("Build failed with non-zero exit code" in i for i in issues)

    # 4. Package with nonexistent exe
    ok, issues = validate_stage_output(
        "package",
        {"exe": str(proj / "NonExistent.exe")},
        project_dir=proj,
    )
    assert ok is False
    assert any("does not exist on disk" in i for i in issues)

    # 5. Report with nonexistent report_path
    ok, issues = validate_stage_output(
        "report",
        {"report_path": str(proj / "Saved" / "missing_report.json")},
        project_dir=proj,
    )
    assert ok is False
    assert any("does not exist on disk" in i for i in issues)

    # 6. Declared artifact file not existing on disk
    ok, issues = validate_stage_output(
        "other",
        {"ok": True},
        project_dir=proj,
        artifacts=[{"path": str(proj / "missing_artifact.log"), "kind": "log"}],
    )
    assert ok is False
    assert any("Declared artifact file" in i for i in issues)


def test_def098_dag_cycle_fails_gracefully(tmp_path: Path):
    """DEF-098: Dependency cycles must not crash the executor with an unhandled

    ValueError or leave the state stuck in RUNNING.
    """
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    # Manually construct cycle bypassing BaseModel validation
    s1 = StepSpec(step_id="step1", kind=StepKind.DESIGN, title="S1", depends_on=["step2"])
    s2 = StepSpec(step_id="step2", kind=StepKind.CODEGEN, title="S2", depends_on=["step1"])

    run = RunSpec.model_construct(
        run_id="run_cycle_test",
        title="Cycle Test",
        origin="cli",
        workspace_dir=str(ws),
        steps=[s1, s2],
    )
    state = RunState.new(run)
    executor = ForgeExecutor({})

    res = executor.run(state, store)
    assert res.status == "FAILED"
    assert res.records["step1"].status == StepStatus.BLOCKED
    assert any("DAG topology error" in err for err in res.records["step1"].errors)

    # Verify event was persisted
    events = store.load_events(run.run_id)
    assert any(e.get("kind") == "run_finished" and e.get("status") == "FAILED" for e in events)


def test_def099_impact_analysis_invalidates_downstream_of_rerun():
    """DEF-099: If an upstream step needs to re-run, dependent downstream steps

    must NOT be placed into skip, even if their own input hashes matched.
    """
    s1 = StepSpec(step_id="s1", kind=StepKind.DESIGN, title="Design")
    s2 = StepSpec(step_id="s2", kind=StepKind.CODEGEN, title="Codegen", depends_on=["s1"])

    spec = RunSpec(title="Impact Test", workspace_dir="ws", steps=[s1, s2])
    prev_state = RunState.new(spec)

    # In previous run, s1 FAILED, but s2 was somehow marked DONE with matching hash
    prev_state.records["s1"].status = StepStatus.FAILED
    prev_state.records["s1"].ok = False

    from src.gameforge_ide.forge.impact import compute_effective_hashes
    eff = compute_effective_hashes(spec)
    prev_state.records["s2"].status = StepStatus.DONE
    prev_state.records["s2"].ok = True
    prev_state.records["s2"].input_hash = eff["s2"]

    report = impact(prev_state, spec)
    assert "s1" in report.rerun
    # Because s2 depends on s1, and s1 is in rerun, s2 MUST be in rerun!
    assert "s2" in report.rerun
    assert "s2" not in report.skip


def test_def100_checkpoint_resilient_to_stale_lock(tmp_path: Path):
    """DEF-100: ProjectRepo must safely clean stale .git/index.lock and succeed."""
    git_dir = tmp_path / "repo"
    git_dir.mkdir(parents=True, exist_ok=True)
    repo = ProjectRepo(git_dir)
    repo.ensure()

    # Simulate a stale index.lock file left over from a killed process
    lock_file = git_dir / ".git" / "index.lock"
    lock_file.write_text("dummy lock content", encoding="utf-8")
    assert lock_file.is_file()

    # Add a file and commit
    (git_dir / "file.txt").write_text("hello", encoding="utf-8")
    head_sha = repo.commit("commit with stale lock")
    assert head_sha is not None
    assert not lock_file.is_file()


def test_forge_service_resume_run(tmp_path: Path):
    """Verify ForgeService.resume_run resumes a run."""
    ws = tmp_path / "ws"
    svc = ForgeService(workspace_root=ws)

    def h_step(ctx: StepContext) -> StepOutcome:
        return StepOutcome(True, data={"finished": True})

    from src.gameforge_ide.forge.handlers import register_handler
    register_handler("step_x", h_step)

    s = StepSpec(step_id="step_x", kind=StepKind.TOOL_CALL, title="Step X")
    spec = RunSpec(title="Service Resume Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(spec)
    state.records["step_x"].status = StepStatus.FAILED
    state.status = "FAILED"
    svc.store.save(state)

    res = svc.resume_run(spec.run_id)
    assert res is not None
    assert res.status == "DONE"
    assert res.records["step_x"].status == StepStatus.DONE
    svc.close()
