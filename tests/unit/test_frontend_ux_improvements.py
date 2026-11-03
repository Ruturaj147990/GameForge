"""Unit tests for GameForge IDE Frontend, UI Components & UX Specialist improvements."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from PySide6.QtCore import QEvent, QPoint, QSettings, QSize, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QListWidgetItem, QWidget

from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.shell.palette import CommandPalette
from src.gameforge_ide.desktop.shell.rail import Rail
from src.gameforge_ide.desktop.shell.toasts import ToastOverlay
from src.gameforge_ide.desktop.shell.top_bar import TopBar
from src.gameforge_ide.desktop.shell.assistant_panel import AssistantPanel
from src.gameforge_ide.desktop.views.code_view import CodeView
from src.gameforge_ide.desktop.views.games_view import GamesView
from src.gameforge_ide.desktop.views.evidence_view import EvidenceView
from src.gameforge_ide.desktop.views.assets_view import AssetsView
from src.gameforge_ide.desktop.widgets.log_view import LogView
from src.gameforge_ide.desktop.widgets.problems_table import ProblemsTable
from src.gameforge_ide.desktop.services.tool_service import ToolService
from src.gameforge_ide.desktop.services.projects_service import GameSummary


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def disposable_workspace(tmp_path):
    ws = tmp_path / "ux_ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def test_toast_overlay_reposition_on_parent_resize(qapp):
    """Verify ToastOverlay anchors to bottom-right and updates on parent resize."""
    parent = QWidget()
    parent.resize(800, 600)
    parent.show()

    toasts = ToastOverlay(parent)
    toasts.show_toast("info", "Test Toast", "Message")
    
    # Check bottom-right positioning (width 340, margin 20 from right, 30 from bottom)
    assert toasts.geometry().right() <= 800
    assert toasts.geometry().bottom() <= 600

    # Resize parent to 1200x900
    parent.resize(1200, 900)
    # Event filter triggers _reposition()
    assert toasts.x() == 1200 - 340 - 20
    assert toasts.y() == 900 - toasts.height() - 30


def test_command_palette_fuzzy_and_token_search(qapp):
    """Verify CommandPalette matches acronyms, tokens, and case-insensitive substrings."""
    actions_called = []
    commands = [
        ("View: Design", lambda: actions_called.append("design")),
        ("View: Build", lambda: actions_called.append("build")),
        ("Toggle Studio Dark/Light Theme", lambda: actions_called.append("theme")),
        ("Forge: Cancel Active Run", lambda: actions_called.append("cancel")),
    ]
    pal = CommandPalette(commands)
    
    # 1. Acronym match: "vd" should match "View: Design"
    pal._filter_commands("vd")
    visible_items = [pal.list_widget.item(i).text() for i in range(pal.list_widget.count()) if not pal.list_widget.item(i).isHidden()]
    assert "View: Design" in visible_items
    assert "Toggle Studio Dark/Light Theme" not in visible_items

    # 2. Token match: "view des" should match "View: Design"
    pal._filter_commands("view des")
    visible_items = [pal.list_widget.item(i).text() for i in range(pal.list_widget.count()) if not pal.list_widget.item(i).isHidden()]
    assert "View: Design" in visible_items
    assert len(visible_items) == 1

    # 3. Substring match: "cancel" matches "Forge: Cancel Active Run"
    pal._filter_commands("cancel")
    visible_items = [pal.list_widget.item(i).text() for i in range(pal.list_widget.count()) if not pal.list_widget.item(i).isHidden()]
    assert "Forge: Cancel Active Run" in visible_items


def test_log_view_auto_scroll_lock(qapp):
    """Verify LogView auto-scroll pauses on user scroll up and resumes on button click."""
    lv = LogView()
    lv.resize(400, 300)
    lv.show()
    # Add many lines
    for i in range(200):
        lv.append_log(f"Line {i}: compilation output in progress...")
    lv._flush_queue()

    scrollbar = lv._scrollbar
    assert lv._auto_scroll is True
    assert scrollbar.value() == scrollbar.maximum()

    # User scrolls up
    scrollbar.setValue(10)
    assert lv._auto_scroll is False
    assert "Resume Auto-Scroll" in lv._btn_scroll.text()

    # New log arriving while paused does NOT force scroll to bottom
    lv.append_log("New line while user is inspecting earlier log")
    lv._flush_queue()
    assert scrollbar.value() != scrollbar.maximum()

    # User clicks Resume Auto-Scroll / Bottom button
    lv._btn_scroll.click()
    assert lv._auto_scroll is True
    assert scrollbar.value() == scrollbar.maximum()
    assert lv._btn_scroll.text() == "⤓ Bottom"


def test_rail_running_and_refresh_icons(qapp):
    """Verify Rail displays running state and refreshes icons."""
    rail = Rail()
    assert rail.button("build") is not None

    # Set running
    rail.set_running("build", True)
    assert "Building" in rail.button("build").toolTip()

    # Set stopped
    rail.set_running("build", False)
    assert "Building" not in rail.button("build").toolTip()

    # Theme refresh
    rail.refresh_icons()
    rail.update_theme()


def test_top_bar_and_assistant_icons_refresh(qapp):
    """Verify TopBar and AssistantPanel icon update methods."""
    tb = TopBar()
    tb.refresh_icons()
    tb.update_theme()

    chat_mock = QWidget()
    ap = AssistantPanel(chat_mock)
    ap.refresh_icons()
    ap.update_theme()


def test_code_view_dock_persistence(qapp, disposable_workspace):
    """Verify CodeView saves, restores, and resets dock layouts."""
    tools = ToolService(disposable_workspace)
    cv = CodeView(disposable_workspace, tools)
    
    settings_file = disposable_workspace / "test_dock_settings.ini"
    settings = QSettings(str(settings_file), QSettings.IniFormat)

    # Save state
    cv.save_dock_state(settings)
    assert settings.value("studio/code_view_layout") is not None

    # Restore state
    restored = cv.restore_dock_state(settings)
    assert restored is True

    # Reset layout
    cv.reset_dock_layout()


def test_problems_table_keyboard_navigation(qapp):
    """Verify ProblemsTable emits openLocationRequested on Enter key."""
    pt = ProblemsTable()
    problems = [
        {"severity": "Error", "file": "Source/Game.cpp", "line": 42, "message": "Syntax error"}
    ]
    pt.set_problems(problems)
    pt.setCurrentCell(0, 1)

    received = []
    pt.openLocationRequested.connect(lambda f, l: received.append((f, l)))

    # Press Enter
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    pt.keyPressEvent(event)

    assert len(received) == 1
    assert received[0] == ("Source/Game.cpp", 42)


def test_games_view_keyboard_navigation(qapp, disposable_workspace):
    """Verify GamesView opens game on Enter key in list view."""
    gv = GamesView()
    game = GameSummary(
        name="TestGame",
        title="Test Game Title",
        pitch="A test action game",
        genre="action",
        project_dir=disposable_workspace / "TestGame",
        updated_at=1000.0,
    )
    gv._model.set_games([game])
    gv._list_view.setCurrentIndex(gv._model.index(0, 0))

    opened = []
    gv.openGameRequested.connect(lambda name: opened.append(name))

    # Send Return key to list view
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    gv.eventFilter(gv._list_view, event)

    assert opened == ["TestGame"]


def test_evidence_view_keyboard_navigation(qapp, disposable_workspace):
    """Verify EvidenceView opens file on Enter key in gallery."""
    ev = EvidenceView(disposable_workspace)
    test_file = disposable_workspace / "artifact_test.png"
    test_file.write_bytes(b"dummy image")
    
    item = QListWidgetItem("artifact_test.png")
    item.setData(Qt.UserRole, str(test_file))
    ev._gallery.addItem(item)
    ev._gallery.setCurrentItem(item)

    opened = []
    ev.openFileRequested.connect(lambda p: opened.append(p))

    # Send Return key
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    ev.eventFilter(ev._gallery, event)

    assert opened == [str(test_file)]


def test_assets_view_keyboard_navigation(qapp, disposable_workspace):
    """Verify AssetsView selects asset on Enter key in table."""
    av = AssetsView(disposable_workspace)
    av._model.set_rows([{"name": "SM_Crate", "asset_type": "mesh", "stage": "PROMOTE"}])
    av._table.setCurrentIndex(av._model.index(0, 0))

    # Send Return key
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    res = av.eventFilter(av._table, event)
    assert res is True
    assert "SM_Crate" in av._lbl_detail_header.text()


def test_main_window_forge_event_and_command_palette(qapp, disposable_workspace):
    """Verify MainWindow handles forge events and registers all studio commands."""
    os.environ.pop("GAMEFORGE_LEGACY_SHELL", None)
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    try:
        commands = [cmd[0] for cmd in win._command_palette_commands()]
        assert "View: Assets Registry" in commands
        assert "View: Code Developer" in commands
        assert "Forge: Cancel Active Run" in commands
        assert "View: Toggle Assistant" in commands

        # Verify Forge event triggers status bar and toasts
        win._on_forge_run_event({
            "kind": "step_started",
            "project_name": "EmberVale",
            "step_id": "assemble_levels",
        })
        assert "Assemble levels" in win.statusBar().currentMessage()

        # Run finished success
        win._on_forge_run_event({
            "kind": "run_finished",
            "project_name": "EmberVale",
            "status": "DONE",
        })
        assert "complete" in win.statusBar().currentMessage().lower()
    finally:
        win.close()
