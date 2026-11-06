"""Targeted test suite verifying Phase 1 backend transformations.

Covers:
- TaskMode and AutonomyProfile semantics and lifecycle transitions
- PlanArtifact creation, revision history, markdown export, and proceed confirmation
- AutonomyProfile enforcement in ToolGateway
- Atomic write_file, rollback tracking, and verify_disk_contents
- RepairEngine root-cause extraction, 5-attempt limit, and cycle detection
- ForgeExecutor selective DAG invalidation and stage resumption
- SessionManager persistence of task modes and plan artifacts
- Universal AgentRuntime game creation plan synthesis without legacy open_design bypass
"""
import json
import tempfile
from pathlib import Path
import pytest

from src.gameforge_ide.backend.models.modes import (
    TaskMode,
    AutonomyProfile,
    TaskLifecycleStatus,
    can_transition,
)
from src.gameforge_ide.backend.models.plan_artifact import (
    PlanArtifact,
    PlanStep,
    PlanRevision,
)
from src.gameforge_ide.backend.agent.repair_system import (
    RepairEngine,
    RootCause,
    FailureCategory,
)
from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.forge.model import RunSpec, RunState, StepSpec, StepKind, StepStatus
from src.gameforge_ide.forge.executor import ForgeExecutor


def test_modes_and_lifecycle_state_machine():
    """Verify enum values and deterministic lifecycle transitions."""
    assert TaskMode.PLANNING == "planning"
    assert TaskMode.FAST == "fast"
    assert AutonomyProfile.MANUAL == "manual"
    assert AutonomyProfile.AUTO_EDIT == "auto_edit"
    assert AutonomyProfile.AGENTIC == "agentic"

    # Valid transitions
    assert can_transition(TaskLifecycleStatus.CREATED, TaskLifecycleStatus.UNDERSTANDING)
    assert can_transition(TaskLifecycleStatus.UNDERSTANDING, TaskLifecycleStatus.PLANNING)
    assert can_transition(TaskLifecycleStatus.PLANNING, TaskLifecycleStatus.AWAITING_PLAN_APPROVAL)
    assert can_transition(TaskLifecycleStatus.AWAITING_PLAN_APPROVAL, TaskLifecycleStatus.RUNNING)
    assert can_transition(TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.VERIFYING)
    assert can_transition(TaskLifecycleStatus.VERIFYING, TaskLifecycleStatus.COMPLETED)
    assert can_transition(TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.REPAIRING)
    assert can_transition(TaskLifecycleStatus.REPAIRING, TaskLifecycleStatus.RUNNING)

    # Invalid transitions
    assert not can_transition(TaskLifecycleStatus.COMPLETED, TaskLifecycleStatus.RUNNING)
    assert not can_transition(TaskLifecycleStatus.FAILED, TaskLifecycleStatus.VERIFYING)


def test_plan_artifact_creation_revision_and_proceed():
    """Verify PlanArtifact structure, multi-turn revisions, and proceed confirmation."""
    steps = [
        PlanStep(
            step_id="step_1",
            title="Project Discovery",
            description="Inspect directory structure and project configuration",
        ),
        PlanStep(
            step_id="step_2",
            title="Implement Core Logic",
            description="Write gameplay C++ classes and character controller",
            target_files=["Source/Game/PlayerController.cpp"],
        ),
    ]

    plan = PlanArtifact(
        plan_id="plan_test_001",
        session_id="session_001",
        goal="Create Player Controller",
        summary="Scaffold and verify controller classes",
        steps=steps,
    )

    assert plan.status == "awaiting_approval"
    assert plan.version == 1
    assert len(plan.steps) == 2

    # Markdown export
    md = plan.to_markdown()
    assert "Technical Plan: Create Player Controller" in md
    assert "Proposed Implementation Steps" in md
    assert "Source/Game/PlayerController.cpp" in md
    assert "Proceed" in md

    # Revision
    plan.record_revision(
        user_prompt="Add jump velocity parameter",
        summary_of_changes="Added jump velocity parameter to controller",
    )
    assert plan.version == 2
    assert len(plan.revisions) == 1
    assert plan.revisions[0].user_prompt == "Add jump velocity parameter"

    # Confirm proceed
    plan.confirm_proceed()
    assert plan.status == "approved"
    assert plan.proceed_confirmed is True


def test_autonomy_profile_enforcement_in_tool_gateway():
    """Verify backend ToolGateway strictly enforces MANUAL, AUTO_EDIT, and AGENTIC rules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gateway = ToolGateway(Path(tmpdir))

        # 1. Read-only operations never require approval in ANY profile
        for prof in (AutonomyProfile.MANUAL, AutonomyProfile.AUTO_EDIT, AutonomyProfile.AGENTIC):
            assert not gateway.tool_requires_approval("read_file", {"subpath": "a.txt"}, autonomy_profile=prof)
            assert not gateway.tool_requires_approval("list_dir", {"subpath": "."}, autonomy_profile=prof)
            assert not gateway.tool_requires_approval("verify_disk", {"subpath": "a.txt"}, autonomy_profile=prof)
            assert not gateway.tool_requires_approval("git_status", {}, autonomy_profile=prof)

        # 2. MANUAL profile: all mutations and commands require approval
        assert gateway.tool_requires_approval("write_file", {"subpath": "a.txt", "content": "x"}, autonomy_profile=AutonomyProfile.MANUAL)
        assert gateway.tool_requires_approval("apply_edit", {"diff_id": "d1"}, autonomy_profile=AutonomyProfile.MANUAL)
        assert gateway.tool_requires_approval("run_command", {"command": "pytest"}, autonomy_profile=AutonomyProfile.MANUAL)
        assert gateway.tool_requires_approval("unreal_build", {"uproject_rel_path": "a.uproject"}, autonomy_profile=AutonomyProfile.MANUAL)

        # 3. AUTO_EDIT profile: safe file modifications auto-proceed, commands & builds require approval
        assert not gateway.tool_requires_approval("write_file", {"subpath": "a.txt", "content": "x"}, autonomy_profile=AutonomyProfile.AUTO_EDIT)
        assert not gateway.tool_requires_approval("apply_edit", {"diff_id": "d1"}, autonomy_profile=AutonomyProfile.AUTO_EDIT)
        assert not gateway.tool_requires_approval("rollback_edit", {"diff_id": "d1"}, autonomy_profile=AutonomyProfile.AUTO_EDIT)
        assert gateway.tool_requires_approval("run_command", {"command": "pytest"}, autonomy_profile=AutonomyProfile.AUTO_EDIT)
        assert gateway.tool_requires_approval("unreal_build", {"uproject_rel_path": "a.uproject"}, autonomy_profile=AutonomyProfile.AUTO_EDIT)

        # 4. AGENTIC profile: safe file modifications + allowlisted commands + test runs auto-proceed
        assert not gateway.tool_requires_approval("write_file", {"subpath": "a.txt", "content": "x"}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert not gateway.tool_requires_approval("apply_edit", {"diff_id": "d1"}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert not gateway.tool_requires_approval("run_command", {"command": "pytest tests/unit/"}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert not gateway.tool_requires_approval("run_command", {"command": "python -m pytest"}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert not gateway.tool_requires_approval("run_command", {"command": "git status"}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert not gateway.tool_requires_approval("unreal_run_tests", {"uproject": "Game.uproject"}, autonomy_profile=AutonomyProfile.AGENTIC)

        # High-risk / unallowlisted commands require approval even in AGENTIC
        assert gateway.tool_requires_approval("run_command", {"command": "rmdir /s /q ."}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert gateway.tool_requires_approval("run_command", {"command": "curl http://external.site"}, autonomy_profile=AutonomyProfile.AGENTIC)


def test_edit_tools_write_file_and_verify_disk():
    """Verify EditTools.write_file creates files atomically with rollback support and verify_disk_contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        boundary = BoundaryManager(Path(tmpdir))
        edit_tools = EditTools(boundary)

        target_file = "src/modules/core.py"
        test_content = "def compute():\n    return 42\n"

        # 1. Write new file
        res = edit_tools.write_file(subpath=target_file, content=test_content)
        assert res["status"] == "SUCCESS"
        assert "diff_id" in res

        # 2. Verify on disk
        full_p = Path(tmpdir) / target_file
        assert full_p.exists()
        assert full_p.read_text(encoding="utf-8") == test_content

        # 3. Verify disk contents via helper
        verify_res = edit_tools.verify_disk_contents(subpath=target_file, expected_fragment="return 42")
        assert verify_res["status"] == "SUCCESS"
        assert verify_res["verified"] is True

        # 4. Overwrite file and test rollback
        new_content = "def compute():\n    return 100\n"
        res2 = edit_tools.write_file(subpath=target_file, content=new_content)
        assert res2["status"] == "SUCCESS"
        assert full_p.read_text(encoding="utf-8") == new_content

        # Roll back second write
        rb_res = edit_tools.rollback_edit(diff_id=res2["diff_id"])
        assert rb_res["status"] == "SUCCESS"
        assert full_p.read_text(encoding="utf-8") == test_content


def test_repair_engine_attempt_limits_and_cycle_prevention():
    """Verify RepairEngine enforces 5-attempt limit, no-progress stop, and downstream invalidation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RepairEngine(Path(tmpdir))

        # 1. Root cause extraction
        err_text = "error C2065: 'UCharacterMovementComponent': undeclared identifier in PlayerController.cpp:45"
        root_cause = engine.extract_root_cause(err_text, stage_id="build_editor")
        assert root_cause.category == FailureCategory.CODE_DEFECT
        assert root_cause.cause_id.startswith("rc_")

        # 2. Attempt accounting up to 5
        for attempt in range(1, 6):
            can_rep, reason = engine.can_attempt_repair(root_cause)
            assert can_rep is True, f"Attempt {attempt} should be allowed"
            engine.record_attempt(
                root_cause,
                diff_text=f"// fix attempt {attempt}",
                modified_files=["PlayerController.cpp"],
                result_status="FAILED",
                diag_count_before=5 - attempt + 1,
                diag_count_after=5 - attempt,  # progress is made each time
            )

        # 6th attempt must be rejected
        can_rep, reason = engine.can_attempt_repair(root_cause)
        assert can_rep is False
        assert "Maximum repair attempts (5) reached" in reason

        # 3. No progress stop after 2 consecutive identical failures
        engine_no_prog = RepairEngine(Path(tmpdir))
        rc2 = engine_no_prog.extract_root_cause("fatal error: missing asset", stage_id="content")

        # First attempt: no progress (1 error before, 1 after)
        can_rep, _ = engine_no_prog.can_attempt_repair(rc2)
        assert can_rep is True
        engine_no_prog.record_attempt(rc2, "fix1", [], "FAILED", diag_count_before=1, diag_count_after=1)

        # Second attempt: still no progress
        can_rep, _ = engine_no_prog.can_attempt_repair(rc2)
        assert can_rep is True
        engine_no_prog.record_attempt(rc2, "fix2", [], "FAILED", diag_count_before=1, diag_count_after=1)

        # Third attempt: stopped due to 2 consecutive attempts with no progress
        can_rep, reason = engine_no_prog.can_attempt_repair(rc2)
        assert can_rep is False
        assert "2 consecutive attempts without measurable progress" in reason

        # 4. Downstream stage invalidation
        downstream = engine.affected_downstream_stages("package")
        assert downstream == ["package", "scenarios", "review", "report"]

        downstream_scen = engine.affected_downstream_stages("scenarios")
        assert downstream_scen == ["scenarios", "review", "report"]


def test_forge_executor_stage_invalidation_and_resumption():
    """Verify ForgeExecutor can selectively invalidate downstream stages while preserving upstream work."""
    step1 = StepSpec(step_id="design", kind=StepKind.DESIGN, title="Design Spec")
    step2 = StepSpec(step_id="scaffold", kind=StepKind.SCAFFOLD, title="Scaffold Project", depends_on=["design"])
    step3 = StepSpec(step_id="build_editor", kind=StepKind.BUILD, title="Build Editor", depends_on=["scaffold"])
    step4 = StepSpec(step_id="scenarios", kind=StepKind.SCENARIO, title="Run Scenarios", depends_on=["build_editor"])
    step5 = StepSpec(step_id="report", kind=StepKind.REPORT, title="Generate Report", depends_on=["scenarios"])

    run = RunSpec(
        title="Test Run",
        workspace_dir=".",
        steps=[step1, step2, step3, step4, step5],
    )
    state = RunState.new(run)

    # Simulate steps 1-4 completed successfully
    for sid in ("design", "scaffold", "build_editor"):
        state.records[sid].status = StepStatus.DONE
        state.records[sid].ok = True

    # Step 4 failed
    state.records["scenarios"].status = StepStatus.FAILED
    state.records["scenarios"].ok = False
    state.records["scenarios"].errors = ["Scenario 1 timed out"]

    # Step 5 is blocked
    state.records["report"].status = StepStatus.BLOCKED

    executor = ForgeExecutor(handlers={})

    # Invalidate starting at scenarios
    invalidated = executor.invalidate_stage_and_downstream(state, "scenarios")
    assert "scenarios" in invalidated
    assert "report" in invalidated
    assert "design" not in invalidated
    assert "scaffold" not in invalidated
    assert "build_editor" not in invalidated

    # Upstream stages must remain DONE
    assert state.records["design"].status == StepStatus.DONE
    assert state.records["scaffold"].status == StepStatus.DONE
    assert state.records["build_editor"].status == StepStatus.DONE

    # Downstream stages must be reset to PENDING
    assert state.records["scenarios"].status == StepStatus.PENDING
    assert state.records["scenarios"].ok is False
    assert state.records["report"].status == StepStatus.PENDING


def test_session_manager_mode_and_plan_persistence():
    """Verify SessionManager stores and reloads TaskMode, AutonomyProfile, and active PlanArtifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(workspace_path=Path(tmpdir))

        session = sm.create_session(
            name="Autonomous Session",
            task_mode=TaskMode.FAST,
            autonomy_profile=AutonomyProfile.AUTO_EDIT,
        )

        assert session.task_mode == TaskMode.FAST
        assert session.autonomy_profile == AutonomyProfile.AUTO_EDIT

        # Create and assign PlanArtifact
        plan = PlanArtifact(
            plan_id="plan_p1",
            session_id=session.session_id,
            goal="Test Plan Persistence",
            summary="Verify reload from disk",
        )
        sm.set_active_plan(session.session_id, plan)

        # Reload from disk in a fresh SessionManager instance
        sm_reloaded = SessionManager(workspace_path=Path(tmpdir))
        loaded_sess = sm_reloaded.get_session(session.session_id)

        assert loaded_sess is not None
        assert loaded_sess.task_mode == TaskMode.FAST
        assert loaded_sess.autonomy_profile == AutonomyProfile.AUTO_EDIT
        assert loaded_sess.active_plan is not None
        assert loaded_sess.active_plan.plan_id == "plan_p1"
        assert loaded_sess.active_plan.goal == "Test Plan Persistence"


def test_universal_assistant_no_open_design_bypass():
    """Verify GameForge assistant recognizes creation requests and plans them directly without open_design bypass."""
    from src.gameforge_ide.backend.agent.runtime import AgentRuntime

    router = ModelRouter()
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(workspace_path=Path(tmpdir))

        runtime = AgentRuntime(
            workspace_root=Path(tmpdir),
            session_manager=sm,
            model_router=router,
        )

        # 1. Intent classifier detects game creation
        prompt = "Create a complete top-down survival roguelike with inventory and packaging"
        assert runtime._is_game_creation_request(prompt) is True

        # 2. Plan artifact is synthesized directly
        plan = runtime._build_plan_artifact("sess_123", prompt, is_game=True)
        assert isinstance(plan, PlanArtifact)
        assert plan.implementation_method == "game_creation"
        assert len(plan.steps) >= 5

        # Confirm step names match real pipeline, not open_design detour
        step_titles = [s.title.lower() for s in plan.steps]
        assert any("scaffold" in t for t in step_titles)
        assert any("build" in t or "compile" in t for t in step_titles)
        assert any("package" in t for t in step_titles)

        # Markdown export contains Proceed prompt
        md = plan.to_markdown()
        assert "Proceed" in md
        assert "open_design" not in md
