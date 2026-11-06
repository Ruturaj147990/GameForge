"""Pytest fixtures for GameForge 1.0 test suite."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator, List

import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.models.modes import (
    AutonomyProfile,
    TaskLifecycleStatus,
    TaskMode,
)
from src.gameforge_ide.backend.models.plan_artifact import (
    PlanArtifact,
    PlanRevision,
    PlanStep,
)


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """Headless/offscreen QApplication instance for PySide6 widget tests."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Provides a fresh isolated temporary workspace directory."""
    with tempfile.TemporaryDirectory(prefix="gf_test_ws_") as tmpdir:
        ws = Path(tmpdir).resolve()
        # Create standard directory layout
        (ws / "Source" / "Game").mkdir(parents=True, exist_ok=True)
        (ws / "Config").mkdir(parents=True, exist_ok=True)
        (ws / "Content" / "Maps").mkdir(parents=True, exist_ok=True)
        (ws / ".gameforge").mkdir(parents=True, exist_ok=True)
        yield ws


@pytest.fixture
def sample_plan_steps() -> List[PlanStep]:
    """Returns a realistic set of PlanStep objects for testing."""
    return [
        PlanStep(
            step_id="step_inspect_01",
            title="Inspect Character Setup",
            description="Locate base ACharacter class and verify existing EnhancedInput bindings",
            target_files=["Source/Game/BaseCharacter.h", "Source/Game/BaseCharacter.cpp"],
            tools=["search_code", "read_file"],
            verification="Identify CharacterMovementComponent pointer and input actions",
            status="pending",
        ),
        PlanStep(
            step_id="step_implement_02",
            title="Implement Dash Mechanics",
            description="Add Dash() function, cooldown timer, and impulse application in PlayerController.cpp",
            target_files=["Source/Game/PlayerController.h", "Source/Game/PlayerController.cpp"],
            tools=["propose_edit", "apply_edit", "write_file"],
            verification="Source compiles without C2065 undeclared identifier errors",
            status="pending",
        ),
        PlanStep(
            step_id="step_verify_03",
            title="Verify Dash in Automated Playtest",
            description="Execute automated scenario verifying dash distance > 500 units",
            target_files=[],
            tools=["unreal_run_tests"],
            verification="Scenario test dash_distance_exceeds_threshold returns PASS",
            status="pending",
        ),
    ]


@pytest.fixture
def sample_plan_artifact(sample_plan_steps: List[PlanStep]) -> PlanArtifact:
    """Returns a fully-formed PlanArtifact in awaiting_approval state."""
    return PlanArtifact(
        plan_id="plan_test_abc123",
        session_id="session_test_999",
        version=1,
        goal="Implement Top-Down Roguelike Dash System",
        summary="Add character dash mechanics with cooldown timers and automated test validation.",
        implementation_method="direct_code_edit",
        steps=sample_plan_steps,
        status="awaiting_approval",
        proceed_confirmed=False,
    )
