"""Unit tests for Agent Fix It / Error Repair routing and autonomous pipeline resumption."""
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.gameforge_ide.backend.agent.intent_classifier import is_repair_request
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.session_manager import Session, SessionManager
from src.gameforge_ide.forge.model import RunSpec, RunState, StepRecord, StepStatus


class DummySessionMgr:
    def __init__(self):
        self._sessions = {}

    def get_session(self, sid):
        return self._sessions.get(sid)

    def save_session(self, session):
        self._sessions[session.session_id] = session

    def append_message(self, sid, role, content):
        if sid in self._sessions:
            self._sessions[sid].messages.append({"role": role, "content": content})


class DummyRouter:
    def get_provider(self, ptype):
        return None


@pytest.fixture
def agent_runtime(tmp_path: Path) -> AgentRuntime:
    return AgentRuntime(
        workspace_root=tmp_path,
        session_manager=DummySessionMgr(),  # type: ignore
        model_router=DummyRouter(),  # type: ignore
    )


def test_is_repair_request_matching():
    """Verify natural repair and fix phrases match is_repair_request."""
    positive_phrases = [
        "Fix it",
        "Fix all the errors.",
        "Fix all the errors",
        "fix this",
        "fix errors",
        "fix",
        "Repair it",
        "repair",
        "Make it work",
        "make it work!",
        "debug it",
        "debug",
        "resolve the issue",
        "resolve",
        "Please fix it",
        "fix the build",
        "fix the scenarios",
        "try again and fix",
    ]
    for p in positive_phrases:
        assert is_repair_request(p) is True, f"Expected {p!r} to match is_repair_request"

    negative_phrases = [
        "Create a simple platformer game",
        "Double the player speed and add 5 coins",
        "What is the current project status?",
        "How do cameras work in Unreal Engine?",
        "What does the chat do?",
    ]
    for p in negative_phrases:
        assert is_repair_request(p) is False, f"Expected {p!r} to NOT match is_repair_request"


def test_is_game_modification_request_rejects_repair_prompts(agent_runtime: AgentRuntime):
    """Ensure bare fix/repair instructions are NEVER routed to modify_game."""
    assert agent_runtime._is_game_modification_request("Fix it") is False
    assert agent_runtime._is_game_modification_request("Fix all the errors.") is False
    assert agent_runtime._is_game_modification_request("Repair") is False
    assert agent_runtime._is_game_modification_request("debug it") is False


def test_resolve_failed_run_context_from_metadata(agent_runtime: AgentRuntime):
    """Verify failed run context resolution from session metadata."""
    sess = Session(
        session_id="test_sess_01",
        workspace_path=str(agent_runtime.workspace_root),
        metadata={
            "last_failed_run": {
                "run_id": "run_test_123",
                "project_dir": str(agent_runtime.workspace_root / "Games" / "TestGame"),
                "failed_stage": "scenarios",
                "error": "Scenario failed",
            }
        },
    )
    ctx = agent_runtime._resolve_failed_run_context(sess, "Fix it")
    assert ctx is not None
    assert ctx["run_id"] == "run_test_123"
    assert ctx["failed_stage"] == "scenarios"


def test_resolve_failed_run_context_from_history(agent_runtime: AgentRuntime):
    """Verify failed run context resolution from recent assistant failure message."""
    failure_msg = (
        "Game build did **not** complete. It stopped at stage `scenarios`.\n\n"
        "**Error:** Step 0 (inject) failed: UNKNOWN_ACTION\n\n"
        "Project directory: `E:\\GameForge\\projects\\Sudoku` - run `run_20261110_200153_733a50` can be resumed from the Build view.\n\n"
        "Tell me to fix it and I will inspect the logs and source for that stage."
    )
    sess = Session(
        session_id="test_sess_02",
        workspace_path=str(agent_runtime.workspace_root),
        messages=[
            {"role": "user", "content": "Create me the Sudoku simple game."},
            {"role": "assistant", "content": failure_msg},
        ],
    )
    ctx = agent_runtime._resolve_failed_run_context(sess, "Fix all the errors.")
    assert ctx is not None
    assert ctx["run_id"] == "run_20261110_200153_733a50"
    assert "Sudoku" in ctx["project_dir"]
    assert ctx["failed_stage"] == "scenarios"


@pytest.mark.anyio
async def test_execute_stage_repair_stream(agent_runtime: AgentRuntime, tmp_path: Path):
    """Verify stage repair stream auto-repairs scenario artifacts and completes cleanly."""
    pdir = tmp_path / "TestProject"
    pdir.mkdir(parents=True)
    sc_dir = pdir / "GameForge" / "scenarios"
    sc_dir.mkdir(parents=True)
    
    # Create scenario with invalid navigation
    bad_sc = {
        "schema_": "scenario/1",
        "scenario_id": "win_1",
        "description": "pickup navigation",
        "timeout_s": 30.0,
        "steps": [{"navigate_to": {"tag": "GF_E_pickups"}}],
        "expect": [{"event_count": "pickup.collected", "min": 5}],
    }
    (sc_dir / "win_1.json").write_text(json.dumps(bad_sc, indent=2), encoding="utf-8")

    # Create run state in store
    from src.gameforge_ide.forge.store import RunStore
    store = RunStore(project_dir=pdir, workspace_dir=pdir)
    run_spec = RunSpec(
        run_id="run_repair_001",
        title="Repair Test",
        origin="test",
        project_dir=str(pdir),
        workspace_dir=str(pdir),
        steps=[],
    )
    run_state = RunState(
        run=run_spec,
        records={
            "scenarios": StepRecord(step_id="scenarios", status=StepStatus.FAILED, ok=False, errors=["nav failed"])
        },
        status="FAILED",
    )
    store.save(run_state)

    sess = Session(session_id="test_sess_03", workspace_path=str(agent_runtime.workspace_root), project_dir=str(pdir))
    task_state = MagicMock()
    failed_ctx = {
        "run_id": "run_repair_001",
        "project_dir": str(pdir),
        "failed_stage": "scenarios",
    }

    events = []
    async for ev in agent_runtime._execute_stage_repair_stream("test_sess_03", sess, task_state, failed_ctx):
        events.append(ev)

    assert len(events) >= 1
    # Check that win_1.json was repaired to not use navigate_to GF_E_pickups
    repaired_sc = json.loads((sc_dir / "win_1.json").read_text(encoding="utf-8"))
    assert "navigate_to" not in json.dumps(repaired_sc["steps"])
