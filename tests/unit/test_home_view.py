"""Unit tests for Studio UX Home view and ProjectsService (spec §4.1, WI-4.4)."""
from __future__ import annotations

import os
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.core.systems import SystemRow, SystemsSnapshot
from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.prompt_to_gds import PromptToGdsResult
from src.gameforge_ide.desktop.services.projects_service import (
    GameSummary,
    check_project_has_package,
    find_project_thumbnail,
    list_games,
)
from src.gameforge_ide.desktop.views.home_view import HomeView, PresetChip, PromptTextEdit


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_home_view_widget_hierarchy(qapp):
    """Verify that HomeView creates all required objectNames and accessible names."""
    view = HomeView(); view.show()
    try:
        assert view.objectName() == "homeView"
        assert view.accessibleName() == "GameForge Home View"

        assert view.findChild(PromptTextEdit, "homePromptInput") is not None
        assert view.findChild(object, "homeTitle") is not None
        assert view.findChild(object, "homeBtnDesign") is not None
        assert view.findChild(object, "homeStatusLabel") is not None
        assert view.findChild(object, "homeBtnCancel") is not None
        assert view.findChild(object, "homeUnsupportedNotice") is not None
        assert view.findChild(object, "homeRecentGamesSection") is not None
        assert view.findChild(object, "homeReadinessSection") is not None

        # Check preset chips
        chip_platformer = view.findChild(PresetChip, "presetChip_platformer")
        assert chip_platformer is not None
        assert chip_platformer.text() == "Platformer"
    finally:
        view.deleteLater()


def test_home_view_prompt_enter_vs_ctrl_enter(qapp):
    """Verify Enter creates newline while Ctrl+Enter requests design."""
    edit = PromptTextEdit()
    try:
        design_fired = []
        edit.designRequested.connect(lambda: design_fired.append(True))

        # 1. Plain Enter
        key_event_enter = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        edit.keyPressEvent(key_event_enter)
        assert len(design_fired) == 0

        # 2. Ctrl+Enter
        key_event_ctrl_enter = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
        edit.keyPressEvent(key_event_ctrl_enter)
        assert len(design_fired) == 1
    finally:
        edit.deleteLater()


def test_home_view_preset_chip_fills_prompt(qapp):
    """Verify clicking preset chips prefills prompt input without starting generation."""
    view = HomeView()
    try:
        chip = view.findChild(PresetChip, "presetChip_tic_tac_toe")
        assert chip is not None

        view._prompt_input.setPlainText("")
        chip.click()
        prompt_text = view._prompt_input.toPlainText()
        assert len(prompt_text) > 5
        assert "tic tac toe" in prompt_text.lower() or "board" in prompt_text.lower()

        # Design job should not have started
        assert view._btn_design.isEnabled() is True
        assert view._btn_cancel.isVisible() is False
    finally:
        view.deleteLater()


def test_home_view_unsupported_prompt_notice(qapp, monkeypatch):
    """Verify unsupported prompt shows inline message directing to assistant."""
    monkeypatch.setattr("src.gameforge_ide.desktop.views.home_view.probe_all", lambda *a, **kw: SystemsSnapshot(rows=()))
    view = HomeView()
    try:
        view._prompt_input.setPlainText("fix the build error in UnrealBuildTool.cs")
        view._on_design_it_clicked()

        # Wait for job completion in event loop
        import time
        for _ in range(100):
            time.sleep(0.05)
            qapp.processEvents()
            if not view._notice_lbl.isHidden():
                break

        qapp.processEvents()
        assert not view._notice_lbl.isHidden()
        assert "That doesn't look like a game request. Try the Assistant." in view._notice_lbl.text()
    finally:
        if view._active_job:
            view._active_job.cancel()
            if hasattr(view._active_job, "_future"):
                try:
                    view._active_job._future.result(timeout=1.0)
                except Exception:
                    pass
        view.deleteLater()
        qapp.processEvents()


def test_home_view_readiness_rows(qapp):
    """Verify readiness section renders system rows."""
    view = HomeView()
    try:
        snap = SystemsSnapshot(
            rows=(
                SystemRow(key="engine", state="ok", summary="5.7.4"),
                SystemRow(key="ollama", state="ok", summary="4 models"),
                SystemRow(key="disk", state="ok", summary="500 GB free"),
            ),
            taken_at=123456.0,
        )
        view._latest_snapshot = snap
        view._render_readiness()

        row_engine = view.findChild(object, "readinessRow_engine")
        assert row_engine is not None
        row_ollama = view.findChild(object, "readinessRow_ollama")
        assert row_ollama is not None
        row_disk = view.findChild(object, "readinessRow_disk")
        assert row_disk is not None
    finally:
        view.deleteLater()


def test_no_hardcoded_hex_colors_in_views():
    """Verify normative rule: colours come only from tokens; zero hex literals in desktop/views/."""
    views_dir = Path("src/gameforge_ide/desktop/views")
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")

    for py_file in views_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        matches = hex_pattern.findall(content)
        assert matches == [], f"Found hardcoded hex literals in {py_file.name}: {matches}"


def test_projects_service_helpers(tmp_path):
    """Verify project summary scanning and thumbnail finder."""
    proj_dir = tmp_path / "MyGame"
    proj_dir.mkdir(parents=True)
    (proj_dir / "MyGame.uproject").write_text("{}", encoding="utf-8")

    # Has package check
    assert check_project_has_package(proj_dir, "MyGame") is False
    bin_dir = proj_dir / "Packaged" / "Windows"
    bin_dir.mkdir(parents=True)
    (bin_dir / "MyGame.exe").write_text("dummy", encoding="utf-8")
    assert check_project_has_package(proj_dir, "MyGame") is True

    # Thumbnail check
    assert find_project_thumbnail(proj_dir) is None
    saved_gf = proj_dir / "Saved" / "GameForge"
    saved_gf.mkdir(parents=True)
    thumb_png = saved_gf / "packaged_gameplay.png"
    thumb_png.write_text("png", encoding="utf-8")
    assert find_project_thumbnail(proj_dir) == thumb_png

    # List games scan
    games = list_games(projects_root=tmp_path)
    assert len(games) == 1
    assert games[0].name == "MyGame"
    assert games[0].has_package is True
    assert games[0].thumbnail_path == thumb_png
