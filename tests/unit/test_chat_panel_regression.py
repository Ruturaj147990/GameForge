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
