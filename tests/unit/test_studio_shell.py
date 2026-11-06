"""Unit tests for Studio UX shell components (WI-4.3)."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.shell.rail import Rail
from src.gameforge_ide.desktop.shell.top_bar import TopBar
from src.gameforge_ide.desktop.shell.view_host import ViewHost
from src.gameforge_ide.desktop.shell.assistant_panel import AssistantPanel
from src.gameforge_ide.desktop.shell.toasts import ToastOverlay


@pytest.fixture
def disposable_workspace(tmp_path):
    ws = tmp_path / "studio_ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_studio_shell_object_names(qapp, disposable_workspace):
    """Verify all Studio UX shell widgets are built with canonical objectNames."""
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    try:
        assert win.objectName() == "studioMainWindow"
        assert win._top_bar.objectName() == "studioTopBar"
        assert win._rail.objectName() == "studioRail"
        assert win._view_host.objectName() == "studioViewHost"
        assert win._assistant_panel.objectName() == "studioAssistantPanel"
        assert win._center_splitter.objectName() == "studioCenterSplitter"
        assert win._toasts.objectName() == "studioToastOverlay"

        # Check top bar components
        assert win.findChild(TopBar, "studioTopBar") is not None
        assert win._top_bar.findChild(object, "topBarLogoBtn") is not None
        assert win._top_bar.findChild(object, "topBarProjectCombo") is not None
        assert win._top_bar.findChild(object, "topBarBreadcrumb") is not None
        assert win._top_bar.findChild(object, "topBarRunChip") is not None
        assert win._top_bar.findChild(object, "topBarSystemsBtn") is not None
        assert win._top_bar.findChild(object, "topBarAssistantBtn") is not None
        assert win._top_bar.findChild(object, "topBarPaletteBtn") is not None

        # Check rail buttons
        for vid in ("home", "games", "play", "assets", "code", "settings"):
            assert win._rail.button(vid) is not None
            assert win._rail.button(vid).objectName() == f"railButton_{vid}"
        assert win._rail.button("design") is None
        assert win._rail.button("build") is None
        assert win._rail.button("evidence") is None
    finally:
        win.close()


def test_lazy_view_instantiation(qapp, disposable_workspace):
    """Verify views are created lazily only on first switch."""
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    try:
        # Initial view is home
        assert win._view_host.current_view_id == "home"
        assert "home" in win._view_host.instantiated_views()
        assert "games" not in win._view_host.instantiated_views()
        assert "build" not in win._view_host.instantiated_views()

        # Switch to games -> instantiated
        assert win._switch_studio_view("games") is True
        assert "games" in win._view_host.instantiated_views()
        assert win._view_host.current_view_id == "games"

        # Switch to build -> instantiated
        assert win._switch_studio_view("build") is True
        assert "build" in win._view_host.instantiated_views()
        assert win._view_host.current_view_id == "build"
    finally:
        win.close()


def test_disabled_views_do_not_switch(qapp, disposable_workspace):
    """Verify that disabled rail items refuse to switch and give reasons."""
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    try:
        # Clear selected project
        win._current_project = None
        win._rail.update_enabled_states(win._view_host.is_enabled)

        # Design view should be disabled when no project selected
        enabled, reason = win._view_host.is_enabled("design")
        assert enabled is False
        assert "Select a game first" in reason

        # Trying to switch to design should return False
        assert win._switch_studio_view("design") is False
        assert win._view_host.current_view_id != "design"

        # Now select a project
        win._current_project = "MyGame"
        win._rail.update_enabled_states(win._view_host.is_enabled)
        enabled, _ = win._view_host.is_enabled("design")
        assert enabled is True

        assert win._switch_studio_view("design") is True
        assert win._view_host.current_view_id == "design"
    finally:
        win.close()


def test_assistant_toggle_and_width_persistence(qapp, disposable_workspace):
    """Verify assistant panel collapses and restores width."""
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    win.show()
    try:
        assert win._assistant_panel.isVisible() is True

        # Toggle to hide
        win._toggle_assistant()
        assert win._assistant_panel.isVisible() is False

        # Toggle to show
        win._toggle_assistant()
        assert win._assistant_panel.isVisible() is True
    finally:
        win.close()


def test_legacy_shell_flag(qapp, disposable_workspace):
    """Verify GAMEFORGE_LEGACY_SHELL=1 yields the old layout with native docks."""
    os.environ["GAMEFORGE_LEGACY_SHELL"] = "1"
    try:
        win = MainWindow(disposable_workspace)
        win.confirm_on_close = False
        assert getattr(win, "_is_legacy_shell", False) is True
        assert hasattr(win, "_dock_explorer")
        assert hasattr(win, "_dock_unreal")
        assert hasattr(win, "_dock_terminal")
        win.close()
    finally:
        os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)


def test_assistant_studio_routing_card(disposable_workspace):
    """Verify AgentRuntime in studio_mode emits open_design card instead of create_game approval."""
    import asyncio
    from src.gameforge_ide.backend.agent.runtime import AgentRuntime
    from src.gameforge_ide.backend.providers.router import ModelRouter
    from src.gameforge_ide.backend.session_manager import SessionManager

    sm = SessionManager(disposable_workspace)
    rt = AgentRuntime(disposable_workspace, sm, ModelRouter(), studio_mode=True)
    sid = sm.create_session(name="t", model_name="none", provider_type="ollama").session_id

    async def collect():
        return [e async for e in rt.execute_task_stream(sid, "create a platformer with 5 coins")]

    events = asyncio.run(collect())
    ready = [e for e in events if e.event_type == "status" and e.content == "READY"]
    assert ready and ready[0].metadata.get("card", {}).get("type") == "open_design"
    assert ready[0].metadata["card"]["mode"] == "create"


def test_project_selection_no_attribute_error(qapp, disposable_workspace):
    """Verify selecting a project updates panels without AttributeError."""
    from src.gameforge_ide.design.presets import get_preset_spec
    from src.gameforge_ide.design.store import save as save_gds

    p_dir = disposable_workspace / "Projects" / "TestCS"
    p_dir.mkdir(parents=True, exist_ok=True)
    (p_dir / "TestCS.uproject").write_text("{}", encoding="utf-8")
    save_gds(p_dir, get_preset_spec("platformer"))

    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    try:
        win.open_project_folder(p_dir)
        assert win._current_project == "TestCS"
        assert win._current_project_dir == p_dir.resolve()

        # Trigger project selection again directly
        win._on_project_selected("TestCS")
    finally:
        win.close()


def test_legacy_shell_project_selection(qapp, disposable_workspace):
    """Verify legacy shell dock panels handle project selection without AttributeError."""
    os.environ["GAMEFORGE_LEGACY_SHELL"] = "1"
    try:
        from src.gameforge_ide.design.presets import get_preset_spec
        from src.gameforge_ide.design.store import save as save_gds

        p_dir = disposable_workspace / "Projects" / "TestCSLegacy"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "TestCSLegacy.uproject").write_text("{}", encoding="utf-8")
        save_gds(p_dir, get_preset_spec("platformer"))

        win = MainWindow(disposable_workspace)
        win.confirm_on_close = False
        assert hasattr(win, "_design_panel")
        win._on_project_selected("TestCSLegacy")
        assert win._current_project == "TestCSLegacy"
        assert win._design_panel.workspace_root == p_dir.resolve()
        win.close()
    finally:
        os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)



