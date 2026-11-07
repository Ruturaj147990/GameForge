"""Unit tests for Context Usage Telemetry & Compaction Survival (DEF-303)."""

from pathlib import Path
import pytest

from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.models.context_usage import ContextBreakdown, ContextUsageReport
from src.gameforge_ide.backend.services.agent_service import BackendAgentService
from src.gameforge_ide.backend.session_manager import SessionManager


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "context.md").write_text("# GameForge Project Context\n\n## A. Identity\nGame platform.", encoding="utf-8")
    return tmp_path


def test_context_usage_breakdown_and_utilization():
    """ContextBreakdown totals and ContextUsageReport calculations."""
    bd = ContextBreakdown(
        system_prompt=1000,
        conversation=2000,
        memory=500,
        retrieved_docs=1500,
        tool_definitions=800,
        other_overhead=200,
        reserved_output=2048,
    )
    assert bd.total_prompt_tokens() == 6000

    report = ContextUsageReport.create(
        model_id="gameforge-qwen3.5-9b",
        nominal_capacity=32768,
        breakdown=bd,
        reserved_output=2048,
        is_exact=False,
        estimation_method="conservative_byte_ratio",
        session_id="sess_test_1",
    )

    assert report.model_id == "gameforge-qwen3.5-9b"
    assert report.nominal_capacity == 32768
    assert report.effective_budget == 30720  # 32768 - 2048
    assert report.used_tokens == 6000
    assert report.remaining_tokens == 24720  # 30720 - 6000
    expected_utilization = round((6000 / 30720) * 100.0, 1)
    assert report.utilization_pct == expected_utilization
    assert report.is_estimated is True
    assert report.breakdown.reserved_output == 2048


def test_context_manager_get_context_usage(workspace: Path):
    """ContextManager calculates live usage with categorized token accounting."""
    cm = ContextManager(workspace)
    sm = SessionManager(workspace)
    session = sm.create_session(name="Test Session")

    # Add messages to session
    sm.append_message(session.session_id, "user", "Implement player jump mechanic in Source/Player.cpp")
    sm.append_message(session.session_id, "assistant", "I will inspect Source/Player.cpp and declare the jump method.")

    report = cm.get_context_usage(
        session_id=session.session_id,
        model_id="gameforge-qwen3.5-9b",
        session_manager=sm,
    )

    assert report.session_id == session.session_id
    assert report.model_id == "gameforge-qwen3.5-9b"
    assert report.nominal_capacity == 32768
    assert report.breakdown.system_prompt > 0
    assert report.breakdown.conversation > 0
    assert report.breakdown.memory > 0
    assert report.used_tokens > 0
    assert report.remaining_tokens > 0
    assert 0.0 <= report.utilization_pct <= 100.0


def test_compaction_preserves_facts_without_amnesia():
    """Conversation history compaction preserves file paths, decisions, and goals without amnesia."""
    history = [
        {"role": "user", "content": "Create a roguelike dungeon in Source/DungeonGenerator.cpp with 5 rooms"},
        {"role": "assistant", "content": "[Observation for `read_file`]: file contents of DungeonGenerator.h"},
        {"role": "assistant", "content": "We agreed and decided on grid layout using 64x64 cells. Completed: room generation."},
        {"role": "user", "content": "Now add enemies to Source/EnemySpawner.cpp"},
        {"role": "assistant", "content": "[Observation for `write_file`]: wrote EnemySpawner.cpp"},
        {"role": "user", "content": "Make sure collision works in Source/Physics.cpp"},
        {"role": "assistant", "content": "Collision verified."},
        {"role": "user", "content": "Check tests in tests/test_dungeon.py"},
        {"role": "assistant", "content": "All tests passed cleanly."},
        {"role": "user", "content": "What was our grid size?"},
    ]

    compacted = ContextManager.compact_conversation_history(
        history,
        max_tokens=100,  # force compression of intermediate turns
        preserve_recent=3,
    )

    assert len(compacted) < len(history)
    # Check that initial prompt is preserved
    assert "Source/DungeonGenerator.cpp" in compacted[0]["content"]

    # Check intermediate summary preserved facts and files
    summary_msg = compacted[1]["content"]
    assert "DungeonGenerator" in summary_msg or "EnemySpawner" in summary_msg or "decided" in summary_msg
    assert "without amnesia" in summary_msg

    # Check that recent turns are intact
    assert compacted[-1]["content"] == "What was our grid size?"


def test_runtime_and_backend_agent_service_telemetry(workspace: Path):
    """AgentRuntime and BackendAgentService expose live get_context_usage."""
    runtime = AgentRuntime(workspace)
    session = runtime.session_manager.create_session("TelemetrySession")

    # Query via runtime
    report_rt = runtime.get_context_usage(session.session_id)
    assert isinstance(report_rt, ContextUsageReport)
    assert report_rt.nominal_capacity == 32768
    assert report_rt.used_tokens > 0

    # Query via BackendAgentService
    service = BackendAgentService(workspace)
    report_svc = service.get_context_usage(session.session_id)
    assert isinstance(report_svc, ContextUsageReport)
    assert report_svc.session_id == session.session_id
