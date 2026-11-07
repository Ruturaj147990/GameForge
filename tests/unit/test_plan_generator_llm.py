"""Unit tests for Genuine LLM Planning & Elimination of Fake Plans (DEF-302)."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.gameforge_ide.backend.agent.plan_generator import PlanGenerator
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.models.plan_artifact import PlanArtifact, PlanStep
from src.gameforge_ide.backend.providers.base import ModelProvider
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.session_manager import SessionManager


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "context.md").write_text("# Context\n", encoding="utf-8")
    return tmp_path


def test_llm_plan_generation_with_model_completion(workspace: Path):
    """PlanGenerator queries configured LLM and deterministically validates structured plan."""
    router = ModelRouter()
    mock_provider = MagicMock(spec=ModelProvider)
    mock_response = {
        "goal": "Build an endless runner obstacle game",
        "summary": "Implement procedurally generated obstacle runner with jumping mechanics",
        "implementation_method": "game_creation",
        "steps": [
            {
                "step_id": "step_1_spec",
                "title": "1. Runner Game Design Spec",
                "description": "Configure runner speed scaling and gap widths",
                "target_files": ["GameForge/design/runner.gds.json"],
                "tools": ["write_file"],
                "verification": "Valid GDS schema",
            },
            {
                "step_id": "step_2_scaffold",
                "title": "2. Runner GameMode & Spawner",
                "description": "Declare RunnerGameMode and TrackSpawner actors",
                "target_files": ["Source/MyGame/RunnerGameMode.h"],
                "tools": ["write_file"],
                "verification": "Headers compile without errors",
            },
        ],
    }
    mock_provider.complete_json = MagicMock(return_value=json.dumps(mock_response))
    router.register_provider("ollama", mock_provider)

    generator = PlanGenerator(workspace, model_router=router)
    plan = generator.generate_llm_plan_artifact(
        prompt="Build an endless runner obstacle game",
        session_id="sess_runner_1",
        is_game=True,
        turn_id="turn_1",
    )

    assert isinstance(plan, PlanArtifact)
    assert plan.goal == "Build an endless runner obstacle game"
    assert len(plan.steps) == 2
    assert plan.steps[0].title == "1. Runner Game Design Spec"
    assert plan.steps[1].target_files == ["Source/MyGame/RunnerGameMode.h"]

    # Verify provenance and telemetry
    assert plan.metadata.get("provenance") == "llm_generated"
    assert plan.metadata.get("turn_id") == "turn_1"
    assert "prompt_hash" in plan.metadata
    assert plan.metadata.get("duration_seconds") is not None


def test_elimination_of_static_sudoku_hardcoding(workspace: Path):
    """Verifies that non-Sudoku requests NEVER receive hardcoded Sudoku steps."""
    generator = PlanGenerator(workspace)

    # 1. Platformer request
    plan_platformer = generator.generate_llm_plan_artifact(
        prompt="Make a 3D platformer game with coin collection and moving platforms",
        session_id="sess_plat",
        is_game=True,
    )
    for step in plan_platformer.steps:
        assert "sudoku" not in step.title.lower()
        assert "sudoku" not in step.description.lower()
        for f in step.target_files:
            assert "sudoku" not in f.lower()

    # 2. Combat shooter request
    plan_shooter = generator.generate_llm_plan_artifact(
        prompt="Make a tactical shooter game with enemy combat bots and rifle shooting",
        session_id="sess_shoot",
        is_game=True,
    )
    for step in plan_shooter.steps:
        assert "sudoku" not in step.title.lower()
        for f in step.target_files:
            assert "sudoku" not in f.lower()


def test_plan_id_provenance_and_duplicate_prevention(workspace: Path):
    """PlanGenerator attaches deterministic provenance and prevents duplicate plan creation."""
    generator = PlanGenerator(workspace)
    prompt = "Create a snake grid game in Unreal"

    plan_1 = generator.generate_llm_plan_artifact(
        prompt=prompt,
        session_id="sess_snake",
        is_game=True,
    )
    assert plan_1.plan_id.startswith("plan_")
    assert plan_1.metadata.get("prompt_hash") is not None

    # Passing existing plan prevents duplicate creation
    plan_2 = generator.generate_llm_plan_artifact(
        prompt=prompt,
        session_id="sess_snake",
        is_game=True,
        existing_plan=plan_1,
    )
    assert plan_2 is plan_1  # Exact same object returned without duplicate recreation


def test_multi_turn_plan_revision(workspace: Path):
    """User can send revision prompt updating plan version and recording change history."""
    generator = PlanGenerator(workspace)
    plan = generator.generate_llm_plan_artifact(
        prompt="Build a labyrinth exploration game",
        session_id="sess_lab",
        is_game=True,
    )
    assert plan.version == 1
    assert len(plan.revisions) == 0

    # User revises the plan to add lighting and fog
    plan.record_revision(
        user_prompt="Add dark volumetric fog and a torch lighting system to the labyrinth",
        summary_of_changes="Added volumetric fog and torch mechanics",
    )
    assert plan.version == 2
    assert len(plan.revisions) == 1
    assert plan.revisions[0].version == 2
    assert plan.revisions[0].summary_of_changes == "Added volumetric fog and torch mechanics"
    assert plan.status == "awaiting_approval"
    assert plan.proceed_confirmed is False

    # Proceed confirms the plan
    plan.confirm_proceed()
    assert plan.proceed_confirmed is True
    assert plan.status == "approved"


def test_runtime_build_plan_artifact_delegates_to_llm_generator(workspace: Path):
    """AgentRuntime._build_plan_artifact delegates to PlanGenerator without hardcoding."""
    sm = SessionManager(workspace)
    sess = sm.create_session("TestSess")
    runtime = AgentRuntime(workspace, session_manager=sm)

    plan = runtime._build_plan_artifact(
        session_id=sess.session_id,
        prompt="Make an arena brawler game with wave spawner",
        is_game=True,
    )

    assert isinstance(plan, PlanArtifact)
    assert "arena" in plan.goal.lower() or "brawler" in plan.goal.lower()
    for step in plan.steps:
        assert "sudoku" not in step.title.lower()
        for f in step.target_files:
            assert "sudoku" not in f.lower()
