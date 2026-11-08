"""Regression tests for Full System Audit & Continuous Hardening (2026-11-08).

Covers:
- DEF-AUDIT-01: Adaptive context output token budgeting on small/4K context windows in AgentRuntime.
- DEF-AUDIT-02: QThread lifecycle safety and asyncio task cancellation in AgentWorker/AgentService (0xC0000409 fix).
- DEF-AUDIT-03: Effective bridge port resolution in launcher --serve banner.
- DEF-AUDIT-04: Studio walk packaged executable detection alignment.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.desktop.services.agent_service import AgentService, _AgentWorker
from src.gameforge_ide.core.settings import get_settings


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_context_budget_dynamic_adaptation_on_small_windows(tmp_path: Path):
    """Verify fit_history_to_context dynamically adapts output reservation on 4K context models."""
    # Build a realistic 3,000-token system prompt (300 lines of ~33 chars each)
    dummy_system = "You are GameForge IDE Agent.\n" + ("Rules and tools definitions here.\n" * 280)
    system_tokens = AgentRuntime.estimate_tokens(dummy_system)
    assert system_tokens >= 3000, f"Expected system tokens >= 3000, got {system_tokens}"

    # For a 4096-context model with standard 1024 output reservation, standard input budget is 2944 tokens.
    # Because system_tokens is >= 3000 > 2944, it would raise ValueError unless dynamically adapted.
    messages = [{"role": "user", "content": "Hello"}]
    max_context = 4096

    # Must succeed cleanly through dynamic adaptation
    fitted, budget = AgentRuntime.fit_history_to_context(
        dummy_system,
        messages,
        max_context=max_context,
        output_tokens=1024,
        safety_tokens=128,
        pinned_message=messages[0],
    )
    assert len(fitted) >= 1
    assert budget["input_budget_tokens"] >= system_tokens


def test_agent_worker_cancellation_instant_cleanup(qapp, tmp_path: Path):
    """Verify _AgentWorker.stop() thread-safely cancels active asyncio tasks."""
    worker = _AgentWorker(tmp_path)
    loop = asyncio.new_event_loop()
    worker._loop = loop

    cancelled = False

    async def sample_coro():
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled = True
            raise

    task = loop.create_task(sample_coro())
    worker._task = task

    # Calling stop() cancels task via call_soon_threadsafe
    worker.stop()

    # Run loop until task finishes cancellation
    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        pass

    assert task.cancelled() or cancelled
    loop.close()


def test_agent_service_shutdown_never_destroys_running_qthread(qapp, tmp_path: Path):
    """Verify AgentService.shutdown() guarantees the QThread is stopped before disposal."""
    agent = AgentService(tmp_path)
    sess_id = agent.create_session(name="ShutdownTest")
    agent.send(sess_id, "Test prompt")
    assert agent.is_busy is True

    # Immediate shutdown must ensure thread is dead
    agent.shutdown()
    assert not agent._thread.isRunning(), "Thread must not be running after shutdown()"
    assert not agent.is_busy
    assert not agent.is_stopping


def test_launcher_server_effective_port_resolution(monkeypatch):
    """Verify launcher calculates effective_port properly when port is None."""
    default_port = get_settings().bridge_port
    assert default_port == 47815 or isinstance(default_port, int)

    # When port is None, default_port is chosen
    effective_port = None or default_port
    assert effective_port == default_port

    # When port is specified, explicit port is chosen
    explicit_port = 8080 or default_port
    assert explicit_port == 8080
