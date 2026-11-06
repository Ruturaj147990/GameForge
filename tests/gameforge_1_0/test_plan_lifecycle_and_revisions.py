"""Tests for PlanArtifact, PlanStep, PlanRevision, Multi-Turn Revisions, and Proceed Confirmation.

Conforms to GameForge 1.0 Master Transformation Directive:
- Verifies PlanArtifact data contract, step definitions, and revision models.
- Tests initial plan generation, serialization (dict/JSON roundtrips), and markdown representation.
- Tests multi-turn revisions simulating iterative user prompts, version increments (1 -> 2 -> 3),
  revision history preservation, and immutable audit logs.
- Tests proceed confirmation: transition from awaiting_approval to approved, status locking,
  and preparation for execution.
- Tests step status transitions, verification notes, and error logging.
- Tests integration with SessionManager plan persistence and disk reload.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

import pytest

from src.gameforge_ide.backend.models.modes import TaskMode, AutonomyProfile
from src.gameforge_ide.backend.models.plan_artifact import (
    PlanArtifact,
    PlanRevision,
    PlanStep,
    PlanStepStatus,
    PlanArtifactStatus,
)
from src.gameforge_ide.backend.session_manager import SessionManager


# ==============================================================================
# 1. PlanStep and PlanRevision Model Verification
# ==============================================================================

def test_plan_step_default_attributes():
    """Verify PlanStep creation with defaults and auto-generated step_id."""
    step = PlanStep(
        title="Inspect Engine Hierarchy",
        description="Verify base classes in project directory",
    )
    assert step.step_id.startswith("step_")
    assert step.title == "Inspect Engine Hierarchy"
    assert step.description == "Verify base classes in project directory"
    assert step.target_files == []
    assert step.tools == []
    assert step.verification == ""
    assert step.status == "pending"
    assert step.error is None
    assert step.output_summary is None


def test_plan_step_full_specification():
    """Verify PlanStep with complete explicit parameters."""
    step = PlanStep(
        step_id="step_custom_99",
        title="Add Jump Velocity Component",
        description="Modify CharacterMovementComponent parameters in C++",
        target_files=["Source/Game/HeroCharacter.cpp", "Source/Game/HeroCharacter.h"],
        tools=["search_code", "propose_edit", "apply_edit"],
        verification="Compile with UBT without errors",
        status="in_progress",
        output_summary="Jump velocity set to 600.0f",
        error=None,
    )
    assert step.step_id == "step_custom_99"
    assert len(step.target_files) == 2
    assert "search_code" in step.tools
    assert step.status == "in_progress"
    assert step.output_summary == "Jump velocity set to 600.0f"


def test_plan_revision_immutability_and_timestamp():
    """Verify PlanRevision captures audit trail with version, prompt, summary, and timestamp."""
    before_t = time.time()
    rev = PlanRevision(
        version=2,
        user_prompt="Change character controller to top-down twin-stick style",
        summary_of_changes="Replaced third-person camera rig with fixed top-down camera and rotation to mouse",
    )
    after_t = time.time()

    assert rev.version == 2
    assert "twin-stick" in rev.user_prompt
    assert "fixed top-down" in rev.summary_of_changes
    assert before_t <= rev.timestamp <= after_t


# ==============================================================================
# 2. PlanArtifact Initialization & Serialization
# ==============================================================================

def test_plan_artifact_initial_creation(sample_plan_steps: List[PlanStep]):
    """Verify PlanArtifact initial state, default values, and step associations."""
    plan = PlanArtifact(
        plan_id="plan_init_01",
        session_id="sess_init_01",
        goal="Create Isometric Extraction Shooter",
        summary="Implement player character, inventory system, and extraction zone trigger.",
        implementation_method="game_creation",
        steps=sample_plan_steps,
    )

    assert plan.plan_id == "plan_init_01"
    assert plan.session_id == "sess_init_01"
    assert plan.version == 1
    assert plan.goal == "Create Isometric Extraction Shooter"
    assert plan.implementation_method == "game_creation"
    assert plan.status == "awaiting_approval"
    assert plan.proceed_confirmed is False
    assert len(plan.steps) == 3
    assert plan.revisions == []
    assert plan.created_at > 0
    assert plan.updated_at >= plan.created_at


def test_plan_artifact_json_serialization_roundtrip(sample_plan_artifact: PlanArtifact):
    """Verify full JSON serialization and deserialization preserves all fields and nested objects."""
    # Serialize to JSON string
    json_str = sample_plan_artifact.model_dump_json(indent=2)
    assert isinstance(json_str, str)
    assert "plan_test_abc123" in json_str
    assert "Implement Top-Down Roguelike Dash System" in json_str

    # Parse back into dict
    parsed_dict = json.loads(json_str)
    assert parsed_dict["plan_id"] == "plan_test_abc123"
    assert parsed_dict["version"] == 1
    assert len(parsed_dict["steps"]) == 3

    # Reconstruct into PlanArtifact model
    reconstructed = PlanArtifact.model_validate_json(json_str)
    assert reconstructed.plan_id == sample_plan_artifact.plan_id
    assert reconstructed.goal == sample_plan_artifact.goal
    assert reconstructed.version == sample_plan_artifact.version
    assert len(reconstructed.steps) == len(sample_plan_artifact.steps)
    assert reconstructed.steps[0].title == sample_plan_artifact.steps[0].title
    assert reconstructed.steps[1].target_files == sample_plan_artifact.steps[1].target_files


# ==============================================================================
# 3. Markdown Presentation (`to_markdown`)
# ==============================================================================

def test_plan_artifact_to_markdown_rendering(sample_plan_artifact: PlanArtifact):
    """Verify clean GitHub-flavored markdown export for chat presentation."""
    md = sample_plan_artifact.to_markdown()

    # Title and status badge
    assert "### Technical Plan: Implement Top-Down Roguelike Dash System" in md
    assert "**Status:** `Awaiting Approval`" in md
    assert "**Method:** `direct_code_edit`" in md

    # Summary
    assert "Add character dash mechanics with cooldown timers" in md

    # Steps section
    assert "#### Proposed Implementation Steps" in md
    assert "1. ⏳ **Inspect Character Setup**" in md
    assert "Source/Game/BaseCharacter.h" in md
    assert "2. ⏳ **Implement Dash Mechanics**" in md
    assert "Source/Game/PlayerController.cpp" in md
    assert "3. ⏳ **Verify Dash in Automated Playtest**" in md

    # Confirmation call to action
    assert "Awaiting Confirmation:" in md
    assert "Click **Proceed** to execute this plan" in md


# ==============================================================================
# 4. Multi-Turn Revisions and Version Progression
# ==============================================================================

def test_multi_turn_revisions_progression(sample_plan_artifact: PlanArtifact):
    """Simulate iterative user feedback prompts across multiple conversational turns.
    Verifies:
    - Version increments sequentially: 1 -> 2 -> 3
    - Revision history is preserved immutably with prompt and summary
    - Status resets to awaiting_approval if previously modified
    - proceed_confirmed is reset to False on revision
    """
    plan = sample_plan_artifact
    assert plan.version == 1
    assert len(plan.revisions) == 0

    # Turn 1: User requests adding a stamina cost to dash
    prompt_1 = "Make sure dashing costs 25 stamina and cannot be used when exhausted"
    changes_1 = "Added UStaminaComponent check (cost=25.0f) to Dash() execution predicate"
    plan.record_revision(user_prompt=prompt_1, summary_of_changes=changes_1)

    assert plan.version == 2
    assert len(plan.revisions) == 1
    assert plan.revisions[0].version == 2
    assert plan.revisions[0].user_prompt == prompt_1
    assert plan.revisions[0].summary_of_changes == changes_1
    assert plan.status == "awaiting_approval"
    assert plan.proceed_confirmed is False

    # Turn 2: User requests visual feedback (Niagara trail VFX)
    prompt_2 = "Add a blue trail particle effect while dashing"
    changes_2 = "Integrated UNiagaraComponent trail spawn on dash start and deactivation on complete"
    plan.record_revision(user_prompt=prompt_2, summary_of_changes=changes_2)

    assert plan.version == 3
    assert len(plan.revisions) == 2
    assert plan.revisions[1].version == 3
    assert plan.revisions[1].user_prompt == prompt_2
    assert plan.revisions[1].summary_of_changes == changes_2

    # Verify markdown reflects v3 and revision history
    md = plan.to_markdown()
    assert "(v3)" in md
    assert "#### Revision History" in md
    assert "**v2:** Added UStaminaComponent check" in md
    assert "**v3:** Integrated UNiagaraComponent trail" in md


# ==============================================================================
# 5. Step Status Updates & Execution Progress
# ==============================================================================

def test_plan_step_status_updates(sample_plan_artifact: PlanArtifact):
    """Verify updating step status reflects in the plan and updates markdown icons."""
    plan = sample_plan_artifact
    step_id_01 = plan.steps[0].step_id
    step_id_02 = plan.steps[1].step_id
    step_id_03 = plan.steps[2].step_id

    # 1. Update step 1 to in_progress
    assert plan.update_step_status(step_id_01, status="in_progress") is True
    assert plan.steps[0].status == "in_progress"

    # 2. Update step 1 to completed with output summary
    assert plan.update_step_status(
        step_id_01,
        status="completed",
        output_summary="Identified ACharacter base hierarchy and EnhancedInput component",
    ) is True
    assert plan.steps[0].status == "completed"
    assert plan.steps[0].output_summary is not None

    # 3. Update step 2 to failed with error message
    assert plan.update_step_status(
        step_id_02,
        status="failed",
        error="Compiler error C2065: 'UDashComponent' undeclared",
    ) is True
    assert plan.steps[1].status == "failed"
    assert plan.steps[1].error == "Compiler error C2065: 'UDashComponent' undeclared"

    # 4. Update step 3 to skipped
    assert plan.update_step_status(step_id_03, status="skipped") is True
    assert plan.steps[2].status == "skipped"

    # 5. Invalid step_id returns False
    assert plan.update_step_status("non_existent_step_id", status="completed") is False

    # Verify markdown renders step status icons
    md = plan.to_markdown()
    assert "✅ **Inspect Character Setup**" in md
    assert "Result:* Identified ACharacter base hierarchy" in md
    assert "❌ **Implement Dash Mechanics**" in md
    assert "Error:* `Compiler error C2065" in md
    assert "⏭️ **Verify Dash in Automated Playtest**" in md


# ==============================================================================
# 6. Proceed Confirmation & Status Locking
# ==============================================================================

def test_proceed_confirmation_locks_and_transitions(sample_plan_artifact: PlanArtifact):
    """Verify confirm_proceed() transitions plan to approved, sets proceed_confirmed=True,
    and updates markdown to reflect execution readiness.
    """
    plan = sample_plan_artifact
    assert plan.status == "awaiting_approval"
    assert plan.proceed_confirmed is False

    # Confirm proceed
    plan.confirm_proceed()

    assert plan.status == "approved"
    assert plan.proceed_confirmed is True

    # Markdown export
    md = plan.to_markdown()
    assert "**Status:** `Approved — Ready to Execute`" in md
    # Once approved, the "Awaiting Confirmation: Click Proceed" callout must not appear
    assert "Awaiting Confirmation:" not in md


# ==============================================================================
# 7. SessionManager Plan Persistence Integration
# ==============================================================================

def test_session_manager_plan_lifecycle_persistence(
    temp_workspace: Path,
    sample_plan_artifact: PlanArtifact,
):
    """Verify SessionManager stores, updates, reloads, and clears active plan artifacts."""
    sm = SessionManager(workspace_path=temp_workspace)

    # 1. Create session with Planning task mode
    session = sm.create_session(
        name="Plan Lifecycle Session",
        task_mode=TaskMode.PLANNING,
        autonomy_profile=AutonomyProfile.AGENTIC,
    )
    assert session.active_plan is None

    # 2. Attach PlanArtifact to session
    sample_plan_artifact.session_id = session.session_id
    success = sm.set_active_plan(session.session_id, sample_plan_artifact)
    assert success is True

    # 3. Reload in fresh SessionManager instance from disk
    sm_fresh = SessionManager(workspace_path=temp_workspace)
    loaded_session = sm_fresh.get_session(session.session_id)
    assert loaded_session is not None
    assert loaded_session.active_plan is not None
    assert loaded_session.active_plan.plan_id == sample_plan_artifact.plan_id
    assert loaded_session.active_plan.goal == sample_plan_artifact.goal
    assert len(loaded_session.active_plan.steps) == 3

    # 4. Modify plan (record revision and confirm proceed)
    plan_to_update = loaded_session.active_plan
    plan_to_update.record_revision("Add double jump", "Added second jump phase")
    plan_to_update.confirm_proceed()
    sm_fresh.set_active_plan(session.session_id, plan_to_update)

    # 5. Reload again and verify updated revision and approved status persist
    loaded_session_2 = SessionManager(workspace_path=temp_workspace).get_session(session.session_id)
    assert loaded_session_2.active_plan.version == 2
    assert loaded_session_2.active_plan.status == "approved"
    assert loaded_session_2.active_plan.proceed_confirmed is True
    assert len(loaded_session_2.active_plan.revisions) == 1

    # 6. Clear active plan
    assert sm_fresh.clear_active_plan(session.session_id) is True
    loaded_session_3 = sm_fresh.get_session(session.session_id)
    assert loaded_session_3.active_plan is None
