"""Tests for acceptance predicate path resolution, engine header filtering, and false model_not_acting prevention."""

import pytest
from pathlib import Path
from typing import AsyncIterator

from src.gameforge_ide.backend.agent.task_state import (
    TaskState,
    TaskAcceptancePredicate,
    is_ignorable_header_or_system_file,
    _matches_target,
)
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.providers.base import (
    ChatResponse,
    ModelInfo,
    ModelProvider,
    ProviderCapabilities,
    StreamChunk,
)


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


def test_is_ignorable_header_or_system_file():
    # Engine headers
    assert is_ignorable_header_or_system_file("CoreMinimal.h") is True
    assert is_ignorable_header_or_system_file("GameFramework/Actor.h") is True
    assert is_ignorable_header_or_system_file("Kismet/BlueprintFunctionLibrary.h") is True
    assert is_ignorable_header_or_system_file("Engine/Engine.h") is True
    assert is_ignorable_header_or_system_file("Components/StaticMeshComponent.h") is True
    assert is_ignorable_header_or_system_file("EnhancedInput/Public/InputActionValue.h") is True
    assert is_ignorable_header_or_system_file("GameplayAbilities/Public/AttributeSet.h") is True

    # UHT generated headers
    assert is_ignorable_header_or_system_file("GridCell.generated.h") is True
    assert is_ignorable_header_or_system_file("MyCharacter.generated.h") is True

    # System headers
    assert is_ignorable_header_or_system_file("stdio.h") is True
    assert is_ignorable_header_or_system_file("windows.h") is True

    # Genuine project source headers/files - MUST NOT BE IGNORED
    assert is_ignorable_header_or_system_file("Source/Sudoku/GridCell.h") is False
    assert is_ignorable_header_or_system_file("GridCell.h") is False
    assert is_ignorable_header_or_system_file("GridCell.cpp") is False
    assert is_ignorable_header_or_system_file("Config/DefaultGame.ini") is False
    assert is_ignorable_header_or_system_file("Sudoku.uproject") is False


def test_matches_target():
    # Exact and wildcard
    assert _matches_target("Source/Sudoku/GridCell.h", "*") is True
    assert _matches_target("Source/Sudoku/GridCell.h", "Source/Sudoku/GridCell.h") is True

    # Basename matching
    assert _matches_target("Source/Sudoku/GridCell.h", "GridCell.h") is True
    assert _matches_target("Source/Sudoku/GridCell.cpp", "GridCell.h") is False

    # Path suffix matching
    assert _matches_target("Source/Sudoku/GridCell.h", "Sudoku/GridCell.h") is True
    assert _matches_target("Sudoku/GridCell.h", "Source/Sudoku/GridCell.h") is True

    # Glob matching
    assert _matches_target("Source/Sudoku/GridCell.h", "*.h") is True
    assert _matches_target("Source/Sudoku/GridCell.cpp", "*.h") is False


def test_evaluate_acceptance_subpath_and_ignorable(tmp_path: Path):
    # Setup project directory with Source/Sudoku/GridCell.h
    source_dir = tmp_path / "Source" / "Sudoku"
    source_dir.mkdir(parents=True)
    grid_cell = source_dir / "GridCell.h"
    grid_cell.write_text("// Sudoku Grid Cell\n", encoding="utf-8")

    task = TaskState(
        task_id="t1",
        session_id="s1",
        goal="Create Sudoku GridCell",
        acceptance=[
            # Basename target pointing to a file in a subdirectory
            TaskAcceptancePredicate(predicate_type="file_exists", target="GridCell.h"),
            TaskAcceptancePredicate(predicate_type="file_changed", target="GridCell.h"),
            # Engine headers that should be safely ignored
            TaskAcceptancePredicate(predicate_type="file_exists", target="CoreMinimal.h"),
            TaskAcceptancePredicate(predicate_type="file_changed", target="CoreMinimal.h"),
            TaskAcceptancePredicate(predicate_type="file_exists", target="GridCell.generated.h"),
            TaskAcceptancePredicate(predicate_type="file_changed", target="GridCell.generated.h"),
        ],
    )

    # GridCell was modified under Source/Sudoku/GridCell.h
    modified = {"Source/Sudoku/GridCell.h"}
    tool_hist = [{
        "tool_name": "write_file",
        "arguments": {"subpath": "Source/Sudoku/GridCell.h"},
        "status": "SUCCESS",
        "output": {"file_path": "Source/Sudoku/GridCell.h", "bytes_written": 20},
    }]

    all_sat, unmet = task.evaluate_acceptance(tmp_path, modified, tool_hist)
    assert all_sat is True
    assert len(unmet) == 0


def test_propose_acceptance_predicates_filters_engine_headers(tmp_path: Path):
    session_mgr = SessionManager(tmp_path)
    router = ModelRouter()
    runtime = AgentRuntime(workspace_root=tmp_path, session_manager=session_mgr, model_router=router)
    prompt = (
        "Create GridCell.h and GridCell.cpp for Sudoku. "
        "It includes CoreMinimal.h, GameFramework/Actor.h, and GridCell.generated.h."
    )
    preds = runtime._propose_acceptance_predicates(prompt)
    targets = [p.target for p in preds]

    # GridCell.h and GridCell.cpp should be present
    assert "GridCell.h" in targets
    assert "GridCell.cpp" in targets

    # Engine and generated headers MUST NOT be present
    assert "CoreMinimal.h" not in targets
    assert "GameFramework/Actor.h" not in targets
    assert "GridCell.generated.h" not in targets


@pytest.mark.anyio
async def test_no_false_model_not_acting_when_files_modified(tmp_path: Path):
    """When a model modifies files, a subsequent narrative turn must NOT be marked model_not_acting."""
    session_mgr = SessionManager(tmp_path)
    session = session_mgr.create_session("Test Session", "test-model", "mock", task_mode="fast", autonomy_profile="agentic")

    # Turn 1: Model calls write_file
    # Turn 2: Model returns narrative explaining the completed work
    scripted = [
        '{"name": "write_file", "arguments": {"subpath": "Source/Sudoku/GridBoard.h", "content": "// GridBoard"}}',
        "I have created GridBoard.h for your Sudoku project. The grid is ready.",
    ]
    mock_provider = MockScriptedProvider(scripted)
    router = ModelRouter()
    router.register_provider("mock", mock_provider)

    runtime = AgentRuntime(
        workspace_root=tmp_path,
        session_manager=session_mgr,
        model_router=router,
        max_iterations=6,
    )

    prompt = "Create GridBoard.h and GridBoardParams.ini for Sudoku."
    events = []
    async for ev in runtime.execute_task_stream(session.session_id, prompt):
        events.append(ev)

    terminal_ev = events[-1]
    # Must NOT be an error or BLOCKED with model_not_acting
    assert terminal_ev.event_type == "done"
    assert terminal_ev.metadata.get("terminal_status") == "COMPLETED"
    assert "Source/Sudoku/GridBoard.h" in terminal_ev.metadata.get("modified_files", [])
