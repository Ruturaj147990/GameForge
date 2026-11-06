"""Regression tests for ChatPanel actions and cards."""
from __future__ import annotations

import os
import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel
from src.gameforge_ide.desktop.services.agent_service import AgentService


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_chat_panel_start_make_game(qapp, tmp_path):
    """Verify clicking make game on start screen sets input to '/game ' without error."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        panel._on_start_make_game()
        assert panel._input.toPlainText() == "/game "
    finally:
        agent.shutdown()


def test_chat_panel_open_design_card(qapp, tmp_path):
    """Verify _add_open_design_card uses tokens correctly and emits openDesignRequested."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        emitted = []
        panel.openDesignRequested.connect(emitted.append)

        card = panel._add_open_design_card({"prompt": "create a space shooter", "mode": "create"})
        assert card is not None
        assert card.objectName() == "openDesignCard"

        btn = card.findChild(QPushButton, "btnOpenInDesign")
        assert btn is not None
        btn.click()
        assert emitted == ["create a space shooter"]
    finally:
        agent.shutdown()


def test_chat_panel_no_duplicate_assistant_bubble_on_card(qapp, tmp_path):
    """Verify ChatPanel displays token notice once and does not duplicate text below card."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        from src.gameforge_ide.desktop.panels.chat_panel import _MessageBubble
        msg = "I've mapped your request to update active project TeamArena."
        panel._on_token(msg)
        panel._on_status("READY", {"card": {"type": "open_design", "prompt": "Complete the game", "mode": "change"}})
        panel._on_done(msg)

        assistant_bubbles = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), _MessageBubble)
            and panel._msg_layout.itemAt(i).widget().role == "assistant"
        ]
        assert len(assistant_bubbles) == 1, f"Expected exactly 1 assistant bubble, got {len(assistant_bubbles)}"
    finally:
        agent.shutdown()


def test_chat_panel_streaming_suppresses_raw_json_tool_leaks(qapp, tmp_path):
    """Verify raw JSON tool calls streamed as tokens do not leak into assistant bubbles."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        from src.gameforge_ide.desktop.panels.chat_panel import _MessageBubble

        # Stream raw JSON tool call tokens
        raw_call = '{"tool": "unreal_editor", "args": {"op": "new_level"}}'
        for ch in raw_call:
            panel._on_token(ch)

        # Confirm no assistant bubble was created leaking this raw JSON
        assistant_bubbles = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), _MessageBubble)
            and panel._msg_layout.itemAt(i).widget().role == "assistant"
        ]
        assert len(assistant_bubbles) == 0, f"Expected 0 assistant bubbles for raw tool call, got {len(assistant_bubbles)}"

        # Complete tool call turn
        panel._on_tool_called("unreal_editor", {"op": "new_level"})
        panel._on_tool_result("unreal_editor", {"status": "SUCCESS"})
        panel._on_done("")
    finally:
        agent.shutdown()


def test_chat_panel_status_bar_indeterminate_busy_and_reset(qapp, tmp_path):
    """Verify status bar transitions between ready and busy animated states and clean reset."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        sb = panel._status_bar
        assert sb._label.text() == "Ready"
        assert not sb._pulse_timer.isActive()

        sb.set_busy("THINKING")
        assert sb._label.text() == "THINKING"
        assert sb._pulse_timer.isActive()

        sb.set_ready()
        assert sb._label.text() == "Ready"
        assert not sb._pulse_timer.isActive()

        # Add message bubble and test clean reset
        panel._add_bubble("user", "Hello GameForge")
        assert panel._msg_layout.count() > 1
        panel._clear_chat()
        assert panel._token_buffer == ""
        assert panel._active_bubble is None
    finally:
        agent.shutdown()
