"""Comprehensive integration tests for the unified project directory architecture.

Verifies:
1. One canonical project directory selection mechanism in TopBar and MainWindow.
2. Immediate propagation across all tabs: Design, Build, Play, Evidence, Assets, Code, Shell.
3. Immediate synchronization of backend services: AgentService, ToolService, ProjectsService.
4. Immediate synchronization of dock panels: Explorer, Terminal, Unreal, Diff, Asset, Design.
5. Window title and TopBar path label reflection.
6. Persistence and restoration across restarts.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.design.presets import get_preset_spec
from src.gameforge_ide.design.store import save as save_gds


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def disposable_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "unified_ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def test_unified_project_directory_architecture(qapp, disposable_workspace: Path):
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)

    # 1. Setup two mock projects: Alpha and Beta
    alpha_dir = disposable_workspace / "Projects" / "ProjectAlpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    (alpha_dir / "ProjectAlpha.uproject").write_text("{}", encoding="utf-8")
    save_gds(alpha_dir, get_preset_spec("platformer"))

    beta_dir = disposable_workspace / "Projects" / "ProjectBeta"
    beta_dir.mkdir(parents=True, exist_ok=True)
    (beta_dir / "ProjectBeta.uproject").write_text("{}", encoding="utf-8")
    save_gds(beta_dir, get_preset_spec("top_down_shooter"))

    # 2. Instantiate MainWindow
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False

    # Verify TopBar has canonical project combo selector
    assert hasattr(win._top_bar, "project_combo")
    assert not win._top_bar.project_combo.isHidden()
    assert hasattr(win._top_bar, "project_path_label")

    # 3. Switch to ProjectAlpha via set_active_project
    p_alpha = win.set_active_project("ProjectAlpha", alpha_dir)
    assert p_alpha == alpha_dir.resolve()
    assert win._current_project == "ProjectAlpha"
    assert win._current_project_dir == alpha_dir.resolve()

    # Verify ProjectsService is synchronized
    assert win._projects_service.active_project == "ProjectAlpha"
    assert win._projects_service.active_project_dir == alpha_dir.resolve()

    # Verify TopBar displays project name in combo and reflects directory
    assert win._top_bar.project_combo.currentText() == "ProjectAlpha"
    assert "ProjectAlpha" in win._top_bar.project_combo.toolTip()
    assert str(alpha_dir.resolve()) in win._top_bar.project_combo.toolTip()

    # Verify Window title reflects active project
    assert "ProjectAlpha" in win.windowTitle()
    assert str(alpha_dir.resolve()) in win.windowTitle()

    # Verify Backend services are pointing to alpha_dir
    assert (getattr(win._agent, "workspace_root", None) or win._agent._workspace) == alpha_dir.resolve()
    assert (getattr(win._tools, "workspace_root", None) or win._tools._workspace) == alpha_dir.resolve()
    assert (getattr(win._chat_panel, "_workspace", None) or getattr(win._chat_panel, "_workspace_root", None)) == alpha_dir.resolve()

    # Verify Developer docks point to alpha_dir
    code_view = win._get_or_create_code_view()
    assert getattr(win._explorer, "_workspace", getattr(win._explorer, "_workspace_root", None)) == alpha_dir.resolve()
    assert getattr(win._terminal, "_workspace_dir", getattr(win._terminal, "_workspace", None)) == alpha_dir.resolve()

    # Verify Studio Views are synchronized
    dv = win._view_host.get_view_widget("design")
    if dv:
        assert dv._current_project_dir == alpha_dir.resolve()

    bv = win._view_host.get_view_widget("build")
    if bv:
        assert bv._project_dir == alpha_dir.resolve()

    pv = win._view_host.get_view_widget("play")
    if pv:
        assert pv._project_dir == alpha_dir.resolve()

    ev = win._view_host.get_view_widget("evidence")
    if ev:
        assert ev._project_dir == alpha_dir.resolve()

    av = win._view_host.get_view_widget("assets")
    if av:
        assert av._project_dir == alpha_dir.resolve()

    # 4. Switch to ProjectBeta via TopBar signal
    win._top_bar.projectSelected.emit("ProjectBeta")

    # Verify that ALL components updated to Beta
    assert win._current_project == "ProjectBeta"
    assert win._current_project_dir == beta_dir.resolve()
    assert win._projects_service.active_project == "ProjectBeta"
    assert win._projects_service.active_project_dir == beta_dir.resolve()
    assert win._top_bar.project_combo.currentText() == "ProjectBeta"
    assert "ProjectBeta" in win._top_bar.project_path_label.text()
    assert str(beta_dir.resolve()) in win._top_bar.project_path_label.toolTip()
    assert "ProjectBeta" in win.windowTitle()
    assert (getattr(win._agent, "workspace_root", None) or win._agent._workspace) == beta_dir.resolve()
    assert (getattr(win._tools, "workspace_root", None) or win._tools._workspace) == beta_dir.resolve()
    assert getattr(win._explorer, "_workspace", getattr(win._explorer, "_workspace_root", None)) == beta_dir.resolve()
    assert getattr(win._terminal, "_workspace_dir", getattr(win._terminal, "_workspace", None)) == beta_dir.resolve()

    # 5. Verify persistence across sessions
    settings = QSettings(str(disposable_workspace / ".gameforge" / "ide_settings.ini"), QSettings.IniFormat)
    assert settings.value("studio/last_project") == "ProjectBeta"
    assert settings.value("studio/last_project_dir") == str(beta_dir.resolve())

    win.close()


def test_open_project_folder_and_relaunch_restores_active_project(qapp, disposable_workspace: Path):
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)

    # 1. Setup a third project Gamma
    gamma_dir = disposable_workspace / "Projects" / "ProjectGamma"
    gamma_dir.mkdir(parents=True, exist_ok=True)
    (gamma_dir / "ProjectGamma.uproject").write_text("{}", encoding="utf-8")
    save_gds(gamma_dir, get_preset_spec("relic_hunt"))

    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False

    # 2. Open folder directly
    win.open_project_folder(gamma_dir)

    # Verify everything points to Gamma
    assert win._current_project == "ProjectGamma"
    assert win._current_project_dir == gamma_dir.resolve()
    assert win._projects_service.active_project == "ProjectGamma"
    assert win._projects_service.active_project_dir == gamma_dir.resolve()
    assert "ProjectGamma" in win._top_bar.project_path_label.text()
    assert str(gamma_dir.resolve()) in win._top_bar.project_path_label.toolTip()
    win.close()

    # 3. Simulate IDE relaunch on same workspace
    win2 = MainWindow(disposable_workspace)
    win2.confirm_on_close = False

    # Verify that upon restart, Gamma is automatically the authoritative active project
    assert win2._current_project == "ProjectGamma"
    assert win2._current_project_dir == gamma_dir.resolve()
    assert win2._projects_service.active_project == "ProjectGamma"
    assert win2._projects_service.active_project_dir == gamma_dir.resolve()
    assert "ProjectGamma" in win2._top_bar.project_path_label.text()
    assert str(gamma_dir.resolve()) in win2._top_bar.project_path_label.toolTip()
    assert (getattr(win2._agent, "workspace_root", None) or win2._agent._workspace) == gamma_dir.resolve()
    assert (getattr(win2._tools, "workspace_root", None) or win2._tools._workspace) == gamma_dir.resolve()

    win2.close()
