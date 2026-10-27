"""Unit and regression tests for Phase 1 — Trustworthy Agent Runtime.

Verifies conformance to GameForge Master Blueprint (Oct 27, 2026):
1. Reproduction and prevention of GF-AGENT-001 (narrative completion without evidence).
2. Acceptance predicates evaluated against real disk observations.
3. Repetition loop control terminates closed on 3rd identical call.
4. Pinned context budget preflight checks fail closed before provider call.
5. Diff approval resumes suspended task.
6. Stale diff base hash verification blocks mutation.
"""

from __future__ import annotations

import asyncio
import json
import pytest
from pathlib import Path
from typing import AsyncIterator

from src.gameforge_ide.backend.agent.runtime import AgentEvent, AgentRuntime
from src.gameforge_ide.backend.agent.task_state import (
    TaskAcceptancePredicate,
    TaskBudget,
    TaskState,
)
from src.gameforge_ide.backend.providers.base import (
    ChatResponse,
    ModelInfo,
    ModelProvider,
    ProviderCapabilities,
    StreamChunk,
)
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.session_manager import SessionManager


class MockScriptedProvider(ModelProvider):
    """Test double that yields a predetermined sequence of model responses."""

    def __init__(self, scripted_responses: list[str], max_context: int = 16384):
        self.scripted_responses = list(scripted_responses)
        self.response_index = 0
        self._max_context = max_context

    def get_provider_id(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="test-model", name="Test Model", provider="mock")]

    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,
            max_context=self._max_context,
        )

    def complete(self, *args, **kwargs) -> ChatResponse:
        token = self.scripted_responses[0] if self.scripted_responses else "OK"
        return ChatResponse(content=token, model="test-model")

    async def stream_chat(self, *args, **kwargs) -> AsyncIterator[StreamChunk]:
        if self.response_index < len(self.scripted_responses):
            text = self.scripted_responses[self.response_index]
            self.response_index += 1
        else:
            text = "Default idle response."
        yield StreamChunk(token=text)


@pytest.fixture
def agent_env(tmp_path: Path):
    """Creates a temporary workspace, session manager, and mock router."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_mgr = SessionManager(workspace)
    session = session_mgr.create_session("Test Session", "test-model", "mock")
    return workspace, session_mgr, session


@pytest.mark.anyio
async def test_gf_agent_001_narrative_without_tools_triggers_nudge_then_blocks(agent_env):
    """GF-AGENT-001 Reproduction & Fix:

    A model that answers an actionable mutate task with prose and no tools must
    receive ONE structured nudge listing unmet predicates, and if it replies with prose
    again, terminate as BLOCKED (model_not_acting), NEVER declaring done.
    """
    workspace, session_mgr, session = agent_env
    # Model returns two consecutive narrative text blocks without tools
    scripted = [
        "I will now create the GameForge project files for you.",
        "I have completely finished creating all the requested project files. Enjoy!",
    ]
    mock_provider = MockScriptedProvider(scripted)
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=workspace,
        session_manager=session_mgr,
        model_router=router,
        max_iterations=6,
    )

    events: list[AgentEvent] = []
    prompt = "Create a new Unreal project at GameForgeProject/GameForgeProject.uproject"
    async for ev in runtime.execute_task_stream(session.session_id, prompt):
        events.append(ev)

    # Verify structured nudge was sent
    nudge_events = [e for e in events if e.metadata.get("action") == "nudge_unmet_predicates"]
    assert len(nudge_events) == 1, "Expected exactly one structured nudge for unmet predicates."

    # Verify task terminated as BLOCKED with model_not_acting
    error_events = [e for e in events if e.event_type == "error"]
    assert len(error_events) >= 1
    final_error = error_events[-1]
    assert final_error.metadata.get("status") == "BLOCKED"
    assert final_error.metadata.get("reason") == "model_not_acting"

    # Verify it NEVER declared done
    done_events = [e for e in events if e.event_type == "done"]
    assert len(done_events) == 0, "Narrative output must NEVER yield event_type='done' when predicates are unmet!"

    # Verify task state on disk
    task_state = runtime.get_task_state(session.session_id)
    assert task_state is not None
    assert task_state.terminal_status == "BLOCKED"
    assert task_state.terminal_reason == "model_not_acting"


@pytest.mark.anyio
async def test_multi_file_task_completes_only_when_predicates_satisfied(agent_env):
    """A multi-file task must complete ONLY when every specified acceptance predicate passes."""
    workspace, session_mgr, session = agent_env

    # Step 1: Model proposes edit for file 1
    resp1 = (
        '```json\n'
        '{\n  "tool": "propose_edit",\n  "args": {\n    "subpath": "Config/DefaultEngine.ini",\n    "replacement_content": "[Core.Log]\\nLogTemp=All"\n  }\n}\n'
        '```'
    )
    mock_provider = MockScriptedProvider([resp1])
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=workspace,
        session_manager=session_mgr,
        model_router=router,
    )

    predicates = [
        TaskAcceptancePredicate(predicate_type="file_exists", target="Config/DefaultEngine.ini"),
        TaskAcceptancePredicate(predicate_type="file_exists", target="Config/DefaultGame.ini"),
    ]

    events: list[AgentEvent] = []
    async for ev in runtime.execute_task_stream(
        session.session_id,
        "Create Config/DefaultEngine.ini and Config/DefaultGame.ini",
        acceptance_predicates=predicates,
    ):
        events.append(ev)

    # First turn proposed edit for file 1 and suspended
    assert any(e.event_type == "diff_pending" for e in events)
    diff_event = next(e for e in events if e.event_type == "diff_pending")
    diff_id = diff_event.metadata["diff_id"]

    # Apply diff 1 through edit tools
    apply_res = runtime.tool_gateway.edit_tools.apply_diff(diff_id)
    assert apply_res["status"] == "SUCCESS"

    # Resume task after diff 1 — file 2 is still missing, so predicates must NOT be satisfied yet
    task_state = runtime.get_task_state(session.session_id)
    assert task_state is not None
    all_sat, unmet = task_state.evaluate_acceptance(workspace, {"Config/DefaultEngine.ini"}, [])
    assert not all_sat
    assert len(unmet) == 1
    assert "DefaultGame.ini" in unmet[0]

    # Create file 2 on disk
    (workspace / "Config").mkdir(parents=True, exist_ok=True)
    (workspace / "Config" / "DefaultGame.ini").write_text("[Game]\nTitle=Test", encoding="utf-8")

    # Now re-evaluate: both predicates must be satisfied
    all_sat2, unmet2 = task_state.evaluate_acceptance(workspace, {"Config/DefaultEngine.ini", "Config/DefaultGame.ini"}, [])
    assert all_sat2
    assert len(unmet2) == 0


@pytest.mark.anyio
async def test_repetition_budget_exhaustion_terminates_closed(agent_env):
    """If a model invokes an identical tool with identical args 3 times, harness terminates as BLOCKED."""
    workspace, session_mgr, session = agent_env

    # 3 identical tool calls
    call_str = (
        '```json\n'
        '{\n  "tool": "list_dir",\n  "args": {"subpath": ""}\n}\n'
        '```'
    )
    mock_provider = MockScriptedProvider([call_str, call_str, call_str])
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=workspace,
        session_manager=session_mgr,
        model_router=router,
        max_iterations=6,
    )

    events: list[AgentEvent] = []
    async for ev in runtime.execute_task_stream(session.session_id, "Explore the directory"):
        events.append(ev)

    error_events = [e for e in events if e.event_type == "error"]
    assert len(error_events) >= 1
    final_err = error_events[-1]
    assert final_err.metadata.get("status") == "BLOCKED"
    assert final_err.metadata.get("reason") == "repetition_budget_exhausted"


@pytest.mark.anyio
async def test_pinned_context_overflow_fails_closed(agent_env):
    """If the pinned context alone exceeds the model's input budget, preflight fails closed."""
    workspace, session_mgr, session = agent_env
    # Model context small (e.g. 512 tokens), system context alone exceeds it
    mock_provider = MockScriptedProvider(["hello"], max_context=512)
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=workspace,
        session_manager=session_mgr,
        model_router=router,
    )

    events: list[AgentEvent] = []
    async for ev in runtime.execute_task_stream(session.session_id, "Hello"):
        events.append(ev)

    errs = [e for e in events if e.event_type == "error"]
    assert len(errs) >= 1
    assert "preflight failed" in errs[0].content.lower()


@pytest.mark.anyio
async def test_stale_diff_base_hash_mismatch_rejected(agent_env):
    """If a file changes on disk after a diff was proposed, applying the diff is rejected."""
    workspace, session_mgr, session = agent_env
    target = workspace / "Source" / "Player.cpp"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("int health = 100;", encoding="utf-8")

    edit_tools = agent_env[1]  # session manager
    from src.gameforge_ide.backend.security.boundary import BoundaryManager
    from src.gameforge_ide.backend.tools.edit_tools import EditTools

    boundary = BoundaryManager(workspace)
    tools = EditTools(boundary)

    # Propose edit based on original bytes
    prop = tools.propose_edit(
        subpath="Source/Player.cpp",
        target_content="int health = 100;",
        replacement_content="int health = 200;",
    )
    diff_id = prop["diff_id"]

    # External modification behind the agent's back
    target.write_text("int health = 150; // External edit", encoding="utf-8")

    # Attempt to apply original diff
    res = tools.apply_diff(diff_id)
    assert res["status"] == "STALE"
    assert "File changed after this diff was proposed" in res["error"]


@pytest.mark.anyio
async def test_diff_approval_resumes_task_and_completes(agent_env):
    """When a diff is approved, resume_task_after_diff applies the change, evaluates predicates, and completes."""
    workspace, session_mgr, session = agent_env
    # Model proposes edit
    resp = (
        '```json\n'
        '{\n  "tool": "propose_edit",\n  "args": {\n    "subpath": "Source/GameMode.cpp",\n    "replacement_content": "// Valid GameMode"\n  }\n}\n'
        '```'
    )
    mock_provider = MockScriptedProvider([resp])
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=workspace,
        session_manager=session_mgr,
        model_router=router,
    )

    predicates = [
        TaskAcceptancePredicate(predicate_type="file_exists", target="Source/GameMode.cpp"),
    ]

    # Run initial task
    initial_events: list[AgentEvent] = []
    async for ev in runtime.execute_task_stream(
        session.session_id,
        "Create Source/GameMode.cpp",
        acceptance_predicates=predicates,
    ):
        initial_events.append(ev)

    # Must be waiting approval
    diff_event = next(e for e in initial_events if e.event_type == "diff_pending")
    diff_id = diff_event.metadata["diff_id"]

    # Apply diff to disk
    runtime.tool_gateway.edit_tools.apply_diff(diff_id)

    # Resume task after approval
    resume_events: list[AgentEvent] = []
    async for ev in runtime.resume_task_after_diff(session.session_id, diff_id, approved=True):
        resume_events.append(ev)

    # Task should now be completed
    assert any(e.event_type == "done" and e.metadata.get("terminal_status") == "COMPLETED" for e in resume_events)
    task_state = runtime.get_task_state(session.session_id)
    assert task_state.terminal_status == "COMPLETED"


@pytest.mark.anyio
async def test_rejected_diff_halts_task(agent_env):
    """When a diff is rejected, the task halts with CANCELLED status."""
    workspace, session_mgr, session = agent_env
    resp = (
        '```json\n'
        '{\n  "tool": "propose_edit",\n  "args": {\n    "subpath": "Source/Bad.cpp",\n    "replacement_content": "// Bad code"\n  }\n}\n'
        '```'
    )
    mock_provider = MockScriptedProvider([resp])
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=workspace,
        session_manager=session_mgr,
        model_router=router,
    )

    initial_events = []
    async for ev in runtime.execute_task_stream(session.session_id, "Create Source/Bad.cpp"):
        initial_events.append(ev)

    diff_event = next(e for e in initial_events if e.event_type == "diff_pending")
    diff_id = diff_event.metadata["diff_id"]

    resume_events = []
    async for ev in runtime.resume_task_after_diff(session.session_id, diff_id, approved=False):
        resume_events.append(ev)

    assert any(e.event_type == "done" and e.metadata.get("terminal_status") == "CANCELLED" for e in resume_events)
    task_state = runtime.get_task_state(session.session_id)
    assert task_state.terminal_status == "CANCELLED"

