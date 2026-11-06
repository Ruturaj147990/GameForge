"""Tests for AssistantPanel model selector dropdown discovery, population, and synchronization."""

import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.shell.assistant_panel import AssistantPanel
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel
from src.gameforge_ide.desktop.services.agent_service import AgentService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_assistant_panel_model_dropdown_populates_all_models(qapp, tmp_path: Path):
    agent_service = AgentService(tmp_path)
    chat_panel = ChatPanel(agent_service, workspace_root=tmp_path)
    assistant_panel = AssistantPanel(chat_panel)
    try:
        all_models = [m.get("id", m.get("name", "unknown")) for m in agent_service.list_models()]
        assert len(all_models) >= 1, "Expected at least 1 model from AgentService"

        assistant_panel.set_models(all_models, all_models[0])

        combo = assistant_panel.model_combo
        assert combo.count() == len(all_models)
        for idx, expected in enumerate(all_models):
            assert combo.itemText(idx) == expected

        # Switching model in dropdown triggers modelChanged and synchronizes with chat_panel
        changed_models = []
        assistant_panel.modelChanged.connect(changed_models.append)

        if len(all_models) > 1:
            new_model = all_models[1]
            combo.setCurrentText(new_model)
            assert chat_panel._current_model == new_model
            assert new_model in changed_models
    finally:
        chat_panel.deleteLater()
        assistant_panel.deleteLater()
        agent_service.shutdown()


def test_assistant_panel_refreshes_on_show_popup(qapp, tmp_path: Path):
    agent_service = AgentService(tmp_path)
    chat_panel = ChatPanel(agent_service, workspace_root=tmp_path)
    assistant_panel = AssistantPanel(chat_panel)
    try:
        # Initially populated with only 1 model
        assistant_panel.set_models(["gameforge-qwen3.5-9b:latest"])
        assert assistant_panel.model_combo.count() == 1

        # Trigger showPopup (which triggers _refresh_models_from_source)
        assistant_panel.model_combo.showPopup()
        assistant_panel.model_combo.hidePopup()

        # Now all models from agent_service are loaded!
        all_models = [m.get("id", m.get("name", "unknown")) for m in agent_service.list_models()]
        assert assistant_panel.model_combo.count() == len(all_models)
        assert assistant_panel.model_combo.count() >= 1
    finally:
        chat_panel.deleteLater()
        assistant_panel.deleteLater()
        agent_service.shutdown()


def test_chat_panel_emits_models_loaded(qapp, tmp_path: Path):
    agent_service = AgentService(tmp_path)
    chat_panel = ChatPanel(agent_service, workspace_root=tmp_path)
    assistant_panel = AssistantPanel(chat_panel)
    try:
        # Set assistant_panel to empty
        assistant_panel.model_combo.clear()
        assert assistant_panel.model_combo.count() == 0

        # Call chat_panel._load_models() which emits models_loaded
        chat_panel._load_models()

        # AssistantPanel should now be populated automatically via the connected signal
        all_models = [m.get("id", m.get("name", "unknown")) for m in agent_service.list_models()]
        assert assistant_panel.model_combo.count() == len(all_models)
    finally:
        chat_panel.deleteLater()
        assistant_panel.deleteLater()
        agent_service.shutdown()
