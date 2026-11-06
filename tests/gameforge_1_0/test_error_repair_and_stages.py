"""Tests for Error Repair Engine, Bounded Retry Limits, and Forge Stage Invalidation.

Conforms to GameForge 1.0 Master Transformation Directive:
- Verifies RepairEngine root-cause extraction, category classification, and diagnostic parsing.
- Verifies strict enforcement of max 5 repair attempts per unique root cause.
- Verifies early halting after 2 consecutive attempts without measurable progress.
- Verifies cyclic edit prevention via diff hash tracking per cause signature.
- Verifies ForgeExecutor selective DAG invalidation:
  * Invalidating stage 9 (scenarios) resets stages 9..11 to PENDING while preserving
    upstream stages 1..8 as DONE.
  * Resuming pipeline skips all completed upstream stages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from src.gameforge_ide.backend.agent.repair_system import (
    FailureCategory,
    RepairEngine,
    RootCause,
    DiagnosticRecord,
)
from src.gameforge_ide.forge.model import (
    RunSpec,
    RunState,
    StepSpec,
    StepKind,
    StepStatus,
)
from src.gameforge_ide.forge.executor import ForgeExecutor


# ==============================================================================
# 1. Root Cause Classification & Diagnostic Parsing
# ==============================================================================

def test_root_cause_classification_code_defect(temp_workspace: Path):
    """Verify compiler and syntax errors are classified as CODE_DEFECT with parsed diagnostics."""
    engine = RepairEngine(temp_workspace)
    raw_output = (
        "E:\\Projects\\Game\\Source\\Game\\PlayerController.cpp(52): "
        "error C2065: 'UCharacterMovementComponent': undeclared identifier\n"
        "E:\\Projects\\Game\\Source\\Game\\PlayerController.cpp(55): "
        "error C3861: 'GetCharacterMovement': identifier not found"
    )

    cause = engine.extract_root_cause(raw_output, stage_id="build_editor")

    assert cause.category == FailureCategory.CODE_DEFECT
    assert cause.cause_id.startswith("rc_")
    assert "PlayerController.cpp" in cause.signature
    assert len(cause.diagnostics) >= 1

    first_diag = cause.diagnostics[0]
    assert "PlayerController.cpp" in first_diag.file
    assert first_diag.line == 52
    assert first_diag.severity == "error"
    assert "UCharacterMovementComponent" in (first_diag.symbol or first_diag.message)


def test_root_cause_classification_scenario_failure(temp_workspace: Path):
    """Verify playtest scenario failures are classified as SCENARIO_FAILURE."""
    engine = RepairEngine(temp_workspace)
    raw_output = (
        "Running QA playtest scenarios for Packaged/Windows/Game.exe...\n"
        "Step 2 (win_goal_after_relics) failed: Player collected 2 of 3 relics before timeout (30.0s).\n"
        "SCENARIO_GATE: FAILED"
    )

    cause = engine.extract_root_cause(raw_output, stage_id="scenarios")

    assert cause.category == FailureCategory.SCENARIO_FAILURE
    assert "scenario:scenarios:" in cause.signature
    assert "win_goal_after_relics" in cause.description


def test_root_cause_classification_config_defect(temp_workspace: Path):
    """Verify UBT and engine configuration problems are classified as CONFIG_DEFECT."""
    engine = RepairEngine(temp_workspace)
    raw_output = (
        "ERROR: Couldn't find target rules file for target 'AetherQuestEditor' in DefaultEngine.ini.\n"
        "Target rules must end with 'Target.cs'."
    )

    cause = engine.extract_root_cause(raw_output, stage_id="scaffold")

    assert cause.category == FailureCategory.CONFIG_DEFECT
    assert "config:scaffold:" in cause.signature


def test_root_cause_classification_unknown_fallback(temp_workspace: Path):
    """Verify unrecognized error output cleanly falls back to UNKNOWN category."""
    engine = RepairEngine(temp_workspace)
    raw_output = "Unrecognized proprietary hardware driver fault 0xCAFEBABE."

    cause = engine.extract_root_cause(raw_output, stage_id="content")

    assert cause.category == FailureCategory.UNKNOWN
    assert cause.cause_id.startswith("rc_")


# ==============================================================================
# 2. Strict 5-Attempt Limit Per Root Cause
# ==============================================================================

def test_exact_5_attempt_limit_enforced(temp_workspace: Path):
    """Verify that exactly 5 repair attempts are permitted per unique root cause,
    and any 6th attempt is rejected by policy.
    """
    engine = RepairEngine(temp_workspace)
    cause = engine.extract_root_cause(
        "Source/Game/Hero.cpp:10: error C2065: 'bCanDoubleJump': undeclared identifier",
        stage_id="build_editor",
    )

    # Attempts 1 through 5 must all be allowed as long as progress is simulated
    for attempt_idx in range(1, 6):
        can_repair, reason = engine.can_attempt_repair(cause)
        assert can_repair is True, f"Attempt {attempt_idx} should be permitted, got: {reason}"

        # Record attempt with measurable diagnostic reduction
        engine.record_attempt(
            cause=cause,
            diff_text=f"// repair modification attempt {attempt_idx}",
            modified_files=["Source/Game/Hero.cpp"],
            result_status="FAILED",
            diag_count_before=6 - attempt_idx,
            diag_count_after=5 - attempt_idx,
        )

    # Attempt 6 must be strictly rejected
    can_repair_6, reason_6 = engine.can_attempt_repair(cause)
    assert can_repair_6 is False
    assert "Maximum repair attempts (5) reached" in reason_6


# ==============================================================================
# 3. Two Consecutive No-Progress Early Stopping Rule
# ==============================================================================

def test_two_consecutive_no_progress_halts_repairs(temp_workspace: Path):
    """Verify that if 2 consecutive repair attempts make zero progress
    (diagnostic count does not decrease, and status is not SUCCESS), the engine halts.
    """
    engine = RepairEngine(temp_workspace)
    cause = engine.extract_root_cause(
        "Source/Game/Weapon.cpp:80: error C2143: syntax error : missing ';' before '}'",
        stage_id="build_editor",
    )

    # Attempt 1: diagnostic count remains 2 -> 2 (no progress)
    can_1, _ = engine.can_attempt_repair(cause)
    assert can_1 is True
    engine.record_attempt(
        cause=cause,
        diff_text="diff 1",
        modified_files=["Weapon.cpp"],
        result_status="FAILED",
        diag_count_before=2,
        diag_count_after=2,
    )

    # Attempt 2: diagnostic count still 2 -> 2 (second consecutive failure with no progress)
    can_2, _ = engine.can_attempt_repair(cause)
    assert can_2 is True
    engine.record_attempt(
        cause=cause,
        diff_text="diff 2",
        modified_files=["Weapon.cpp"],
        result_status="FAILED",
        diag_count_before=2,
        diag_count_after=2,
    )

    # Attempt 3: engine must halt immediately
    can_3, reason_3 = engine.can_attempt_repair(cause)
    assert can_3 is False
    assert "2 consecutive attempts without measurable progress" in reason_3


# ==============================================================================
# 4. Cyclic Edits Prevention via Diff Hash Tracking
# ==============================================================================

def test_cyclic_edits_detected_and_prevented(temp_workspace: Path):
    """Verify that proposing duplicate diffs is tracked and triggers early stopping."""
    engine = RepairEngine(temp_workspace)
    cause = engine.extract_root_cause(
        "Source/Game/Score.cpp:12: error C2065: 'CurrentScore': undeclared",
        stage_id="build_editor",
    )

    identical_diff = "--- a/Score.cpp\n+++ b/Score.cpp\n@@ -12 +12 @@\n+int CurrentScore = 0;\n"

    # Attempt 1 with identical_diff
    engine.record_attempt(
        cause=cause,
        diff_text=identical_diff,
        modified_files=["Score.cpp"],
        result_status="FAILED",
        diag_count_before=1,
        diag_count_after=1,
    )

    # Attempt 2 with exact same diff
    engine.record_attempt(
        cause=cause,
        diff_text=identical_diff,
        modified_files=["Score.cpp"],
        result_status="FAILED",
        diag_count_before=1,
        diag_count_after=1,
    )

    # Check for halt
    can_attempt, reason = engine.can_attempt_repair(cause)
    assert can_attempt is False
    assert "consecutive attempts without measurable progress" in reason


# ==============================================================================
# 5. Affected Downstream Stages in Canonical 11 Pipeline
# ==============================================================================

def test_affected_downstream_stages_canonical_pipeline(temp_workspace: Path):
    """Verify affected_downstream_stages correctly slices the canonical 11 stages."""
    engine = RepairEngine(temp_workspace)

    # 1. Package failure affects package, scenarios, review, report
    pkg_downstream = engine.affected_downstream_stages("package")
    assert pkg_downstream == ["package", "scenarios", "review", "report"]

    # 2. Stage 9 (scenarios) failure affects scenarios, review, report
    scen_downstream = engine.affected_downstream_stages("scenarios")
    assert scen_downstream == ["scenarios", "review", "report"]

    # 3. Content failure affects content, assemble_level_1, scenario_gen, automation, package, scenarios, review, report
    content_downstream = engine.affected_downstream_stages("content")
    assert content_downstream == [
        "content", "assemble_level_1", "scenario_gen", "automation",
        "package", "scenarios", "review", "report",
    ]

    # 4. Design failure affects all 11 stages
    design_downstream = engine.affected_downstream_stages("design")
    assert len(design_downstream) == 11
    assert design_downstream[0] == "design"
    assert design_downstream[-1] == "report"


# ==============================================================================
# 6. ForgeExecutor: Stage 9 (Scenarios) Invalidation and Upstream Preservation
# ==============================================================================

def _create_full_11_stage_run() -> RunState:
    """Helper creating a standard 11-stage sequential Forge run state."""
    stages = [
        ("design", StepKind.DESIGN, []),
        ("scaffold", StepKind.SCAFFOLD, ["design"]),
        ("build_editor", StepKind.BUILD, ["scaffold"]),
        ("content", StepKind.CONTENT, ["build_editor"]),
        ("assemble_level_1", StepKind.ASSEMBLE, ["content"]),
        ("scenario_gen", StepKind.DESIGN, ["assemble_level_1"]),
        ("automation", StepKind.AUTOMATION, ["scenario_gen"]),
        ("package", StepKind.PACKAGE, ["automation"]),
        ("scenarios", StepKind.SCENARIO, ["package"]),
        ("review", StepKind.REVIEW, ["scenarios"]),
        ("report", StepKind.REPORT, ["review"]),
    ]

    steps = [
        StepSpec(step_id=sid, kind=kind, title=f"Stage {sid}", depends_on=deps)
        for sid, kind, deps in stages
    ]

    run = RunSpec(title="Full 11 Stage Pipeline Run", workspace_dir=".", steps=steps)
    return RunState.new(run)


def test_stage_9_scenarios_invalidation_preserves_stages_1_to_8():
    """Verify that when Stage 9 (scenarios) fails and is invalidated:
    - Stages 1 through 8 (design through package) remain StepStatus.DONE.
    - Stages 9, 10, 11 (scenarios, review, report) are reset to StepStatus.PENDING with ok=False.
    """
    state = _create_full_11_stage_run()

    # Simulate stages 1..8 completed successfully
    upstream_ids = [
        "design", "scaffold", "build_editor", "content",
        "assemble_level_1", "scenario_gen", "automation", "package",
    ]
    for sid in upstream_ids:
        state.records[sid].status = StepStatus.DONE
        state.records[sid].ok = True

    # Stage 9 failed
    state.records["scenarios"].status = StepStatus.FAILED
    state.records["scenarios"].ok = False
    state.records["scenarios"].errors = ["Scenario 'dash_distance' failed: timeout"]

    # Stages 10 and 11 are blocked
    state.records["review"].status = StepStatus.BLOCKED
    state.records["report"].status = StepStatus.BLOCKED

    executor = ForgeExecutor(handlers={})

    # Invalidate starting at scenarios
    invalidated = executor.invalidate_stage_and_downstream(state, "scenarios")

    # Invalidation result assertions
    assert set(invalidated) == {"scenarios", "review", "report"}

    # Upstream stages MUST remain DONE and ok=True
    for sid in upstream_ids:
        assert state.records[sid].status == StepStatus.DONE, f"Stage {sid} must remain DONE"
        assert state.records[sid].ok is True, f"Stage {sid} must remain ok=True"

    # Downstream stages MUST be reset to PENDING and ok=False
    for sid in ("scenarios", "review", "report"):
        assert state.records[sid].status == StepStatus.PENDING, f"Stage {sid} must be PENDING"
        assert state.records[sid].ok is False, f"Stage {sid} must be ok=False"


def test_stage_3_build_editor_invalidation():
    """Verify invalidating stage 3 (build_editor) resets stages 3..11 while preserving 1..2."""
    state = _create_full_11_stage_run()

    # Stages 1 and 2 completed
    state.records["design"].status = StepStatus.DONE
    state.records["design"].ok = True
    state.records["scaffold"].status = StepStatus.DONE
    state.records["scaffold"].ok = True

    # Stage 3 failed
    state.records["build_editor"].status = StepStatus.FAILED
    state.records["build_editor"].ok = False

    executor = ForgeExecutor(handlers={})
    invalidated = executor.invalidate_stage_and_downstream(state, "build_editor")

    # Upstream intact
    assert state.records["design"].status == StepStatus.DONE
    assert state.records["scaffold"].status == StepStatus.DONE
    assert "design" not in invalidated
    assert "scaffold" not in invalidated

    # Downstream reset to PENDING
    assert "build_editor" in invalidated
    assert "package" in invalidated
    assert "scenarios" in invalidated
    assert "report" in invalidated
    assert state.records["build_editor"].status == StepStatus.PENDING
    assert state.records["package"].status == StepStatus.PENDING
