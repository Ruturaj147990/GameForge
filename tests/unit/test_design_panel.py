"""Unit tests for DesignPanel (P1 WI-1.10)."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.panels.design_panel import DesignPanel
from src.gameforge_ide.design.presets import get_preset_spec
from src.gameforge_ide.design.store import save as save_gds


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_design_panel_empty_workspace(qapp, tmp_path):
    """Verify design panel handles workspace with no GDS gracefully."""
    panel = DesignPanel(tmp_path)
    assert panel.workspace_root == tmp_path
    assert "No `GameForge/design/game.gds.json` found" in panel._md_browser.toMarkdown()
    assert "No spec loaded" in panel._status_lbl.text()


def test_design_panel_set_workspace_loads_new_gds(qapp, tmp_path):
    """Verify set_workspace dynamically switches directory and reloads GDS."""
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()

    # Save a spec in ws2
    spec2 = get_preset_spec("platformer")
    save_gds(ws2, spec2)

    panel = DesignPanel(ws1)
    assert panel.workspace_root == ws1
    assert "No spec loaded" in panel._status_lbl.text()

    # Switch workspace to ws2
    panel.set_workspace(ws2)
    assert panel.workspace_root == ws2
    assert "Spec loaded (valid)" in panel._status_lbl.text()
    assert spec2.meta.project_name in panel._json_edit.toPlainText()
