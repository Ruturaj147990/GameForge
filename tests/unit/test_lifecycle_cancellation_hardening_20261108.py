"""Lifecycle, QThread shutdown, and cancellation hardening tests."""

import inspect
import threading
import time
import pytest
from pathlib import Path

from src.gameforge_ide.desktop.services.agent_service import AgentService, _AgentWorker
from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider


def test_shutdown_does_not_contain_qthread_terminate():
    """Verify that AgentService.shutdown contains zero calls to QThread.terminate()."""
    shutdown_src = inspect.getsource(AgentService.shutdown)
    assert ".terminate()" not in shutdown_src
    assert "self._thread.terminate()" not in shutdown_src


def test_worker_stop_does_not_initialize_runtime_synchronously():
    """Verify that calling stop on an uninitialized worker sets flag without creating runtime."""
    worker = _AgentWorker(workspace_root=Path("."))
    assert getattr(worker, "_runtime", None) is None

    # Call stop - must not initialize runtime on current thread
    worker.stop()
    assert getattr(worker, "_runtime", None) is None
    assert worker._stop_flag.is_set()


def test_provider_chat_with_tools_cancellation_event():
    """Verify that chat_with_tools supports cancel_event and aborts immediately when set."""
    provider = OllamaProvider(host="127.0.0.1:11434")
    cancel_event = threading.Event()
    cancel_event.set()  # Cancelled before start

    with pytest.raises(RuntimeError, match="Operation cancelled"):
        provider.chat_with_tools(
            model_id="gameforge-qwen3.5-9b:latest",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[],
            cancel_event=cancel_event,
        )


def test_worker_run_stops_immediately_if_cancelled_before_start():
    """Verify that _AgentWorker.run does not initialize runtime if stop_flag is already set."""
    worker = _AgentWorker(workspace_root=Path("."))
    worker.set_task("sess_test", "Do something")
    worker.stop()  # Cancel before starting

    # Run should exit immediately
    worker.run()
    assert getattr(worker, "_runtime", None) is None
