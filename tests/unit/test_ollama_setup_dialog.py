"""
tests/unit/test_ollama_setup_dialog.py
Unit tests for Ollama Setup Dialog and Readiness fix action integration.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from src.gameforge_ide.core.systems import SystemRow, SystemsSnapshot
from src.gameforge_ide.desktop.dialogs.ollama_setup import (
    OllamaSetupDialog,
    check_ollama_status,
    find_ollama_executable,
)
from src.gameforge_ide.desktop.views.home_view import HomeView, ReadinessRowWidget


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_readiness_row_set_up_button_emits_fix_action(app):
    """Verify that clicking Set up on an offline Ollama row emits fixActionRequested."""
    row = SystemRow(key="ollama", state="offline", summary="Ollama offline", fix_action="start_ollama")
    widget = ReadinessRowWidget(row)
    
    received = []
    widget.fixActionRequested.connect(received.append)

    btn = widget.findChild(QPushButton, "btn_fix_ollama")
    assert btn is not None
    assert btn.text() == "Set up"
    
    btn.click()
    assert received == ["start_ollama"]


def test_home_view_forwards_fix_action(app):
    """Verify that HomeView propagates fixActionRequested when a row button is clicked."""
    view = HomeView()
    received = []
    view.fixActionRequested.connect(received.append)

    snap = SystemsSnapshot(
        rows=(
            SystemRow(key="ollama", state="offline", summary="Ollama offline", fix_action="start_ollama"),
            SystemRow(key="hosted", state="degraded", summary="No hosted profiles opted in", fix_action="open_hosted"),
        ),
        taken_at=100.0,
    )
    view._latest_snapshot = snap
    view._render_readiness()

    btn_ollama = view.findChild(QPushButton, "btn_fix_ollama")
    assert btn_ollama is not None
    btn_ollama.click()
    assert "start_ollama" in received

    btn_hosted = view.findChild(QPushButton, "btn_fix_hosted")
    assert btn_hosted is not None
    btn_hosted.click()
    assert "open_hosted" in received

    view.deleteLater()


def test_find_ollama_executable():
    """Verify discoverability of the local Ollama binary."""
    exe = find_ollama_executable()
    # On this development host, ollama should be found either in PATH or models parent
    assert exe is not None
    assert exe.name.lower().startswith("ollama")


def test_ollama_setup_dialog_ui(app):
    """Verify initialization and controls of the OllamaSetupDialog."""
    dlg = OllamaSetupDialog()
    assert dlg.windowTitle() == "Ollama Setup — GameForge"

    btn_start = dlg.findChild(QPushButton, "btn_start_ollama")
    assert btn_start is not None

    btn_settings = dlg.findChild(QPushButton, "btn_open_settings")
    assert btn_settings is not None

    dlg.deleteLater()
