"""Unit tests for Studio UX Build view, Timeline delegate, LogView, and ProblemsTable (spec §4.4, WI-4.7)."""
from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import Any, Dict

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.views.build_view import (
    BuildView,
    TimelineListModel,
)
from src.gameforge_ide.desktop.widgets.log_view import LogView
from src.gameforge_ide.desktop.widgets.problems_table import ProblemsTable
from src.gameforge_ide.desktop.widgets.step_row import (
    STEP_ROLE,
    StepRowDelegate,
    format_step_duration,
)
from src.gameforge_ide.forge.model import (
    ArtifactRef,
    RunSpec,
    RunState,
    StepKind,
    StepRecord,
    StepSpec,
    StepStatus,
)
from src.gameforge_ide.forge.store import RunStore


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_build_view_hierarchy(qapp):
    """Verify BuildView constructs all required child widgets with objectNames."""
    view = BuildView()
    try:
        assert view.objectName() == "buildView"
        assert view.accessibleName() == "GameForge Build View"

        assert view.findChild(object, "buildRunsCombo") is not None
        assert view.findChild(object, "btnBuildCancel") is not None
        assert view.findChild(object, "btnBuildResume") is not None
        assert view.findChild(object, "btnBuildRollback") is not None
        assert view.findChild(object, "buildSummaryBanner") is not None
        assert view.findChild(object, "buildTimelineView") is not None
        assert view.findChild(object, "buildLogView") is not None
        assert view.findChild(object, "buildLowerTabs") is not None
        assert view.findChild(object, "buildProblemsTable") is not None
        assert view.findChild(object, "buildArtifactsText") is not None
    finally:
        view.deleteLater()


def test_step_row_delegate_and_formatting():
    """Verify duration formatting and status icons in StepRowDelegate."""
    assert format_step_duration(100.0, 105.4) == "5.4 s"
    assert format_step_duration(100.0, 165.0) == "01:05"
    assert format_step_duration(None, None) == ""

    delegate = StepRowDelegate()
    assert delegate._get_status_icon("DONE")[0] == "✓"
    assert delegate._get_status_icon("RUNNING")[0] == "◉"
    assert delegate._get_status_icon("FAILED")[0] == "✕"
    assert delegate._get_status_icon("PENDING")[0] == "○"
    assert delegate._get_status_icon("WAITING_APPROVAL")[0] == "⏸"


def test_log_view_batched_flush(qapp):
    """Verify LogView batches appends and caps maximum block count."""
    log_view = LogView()
    try:
        assert log_view.objectName() == "buildLogView"
        assert log_view._edit.maximumBlockCount() == 5000

        log_view.append_log("line 1\n")
        log_view.append_log("line 2\n")
        assert len(log_view._queue) == 2

        # Trigger flush
        log_view._flush_queue()
        assert len(log_view._queue) == 0
        plain = log_view._edit.toPlainText()
        assert "line 1" in plain
        assert "line 2" in plain

        # Clear
        log_view.clear()
        assert log_view._edit.toPlainText() == ""
    finally:
        log_view.deleteLater()


def test_problems_table_and_navigation(qapp):
    """Verify ProblemsTable populates diagnostics and emits navigation signal on double-click."""
    table = ProblemsTable()
    try:
        problems = [
            {"severity": "Error", "file": "Source/MyGame/MyActor.cpp", "line": 42, "message": "Undefined symbol"},
            {"severity": "Warning", "file": "Source/MyGame/MyGame.Build.cs", "line": 10, "message": "Deprecated module"},
        ]
        table.set_problems(problems)
        assert table.rowCount() == 2
        assert table.item(0, 0).text() == "ERROR"
        assert table.item(0, 1).text() == "Source/MyGame/MyActor.cpp:42"
        assert table.item(0, 2).text() == "Undefined symbol"

        # Double click navigation
        nav_signals = []
        table.openLocationRequested.connect(lambda f, l: nav_signals.append((f, l)))
        table._on_row_double_clicked(table.model().index(0, 1))

        assert len(nav_signals) == 1
        assert nav_signals[0] == ("Source/MyGame/MyActor.cpp", 42)
    finally:
        table.deleteLater()


def test_build_view_load_run_and_banner(qapp, tmp_path):
    """Verify BuildView loads run from RunStore and updates banner on success."""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    store = RunStore(project_dir=None, workspace_dir=ws)
    s1 = StepSpec(step_id="step_gen", kind=StepKind.DESIGN, title="Generate Game")
    s2 = StepSpec(step_id="step_pkg", kind=StepKind.PACKAGE, title="Package Game", depends_on=["step_gen"])
    run_spec = RunSpec(
        run_id="run_test_001",
        title="Test Build Run",
        workspace_dir=str(ws),
        steps=[s1, s2],
    )
    state = RunState.new(run_spec)

    now = time.time()
    state.records["step_gen"].status = StepStatus.DONE
    state.records["step_gen"].started_at = now - 5
    state.records["step_gen"].finished_at = now - 2
    state.records["step_gen"].checkpoint = "abc1234def5678"
    state.records["step_gen"].data = {"stdout": "Generated assets successfully"}

    state.records["step_pkg"].status = StepStatus.DONE
    state.records["step_pkg"].started_at = now - 2
    state.records["step_pkg"].finished_at = now
    state.records["step_pkg"].checkpoint = "def5678abc1234"
    state.records["step_pkg"].data = {"stdout": "Packaging succeeded", "diagnostics": []}
    state.records["step_pkg"].artifacts = [ArtifactRef(path="package_ship/Windows/MyTestProject.exe")]

    state.status = StepStatus.DONE
    store.save(state)

    view = BuildView(workspace_root=ws)
    try:
        view._store = store
        view.refresh_runs()

        assert view._runs_combo.count() >= 1
        assert "run_test_001" in view._runs_combo.itemData(0)

        # Verify summary banner is visible and indicates completion
        assert not view._summary_banner.isHidden()
        assert "Ready to play" in view._lbl_banner_msg.text()

        # Check playRequested signal emission
        play_signals = []
        view.playRequested.connect(lambda p: play_signals.append(p))
        view._btn_banner_action.click()
        assert len(play_signals) == 1

        # Check timeline populated
        assert view._timeline_model.rowCount() == 2

        # Select second step and verify artifacts tab
        view._timeline_view.setCurrentIndex(view._timeline_model.index(1, 0))
        view._on_step_selected(view._timeline_model.index(1, 0))
        assert "package_ship" in view._artifacts_text.toPlainText()
    finally:
        view.deleteLater()


def test_build_view_failed_run_show_problems_action(qapp, tmp_path):
    """Verify that clicking Show Problems navigates to the failed step and populates problems table."""
    ws = tmp_path / "ws_fail"
    ws.mkdir(parents=True, exist_ok=True)
    store = RunStore(project_dir=None, workspace_dir=ws)

    s1 = StepSpec(step_id="design", kind=StepKind.DESIGN, title="Design Step")
    s2 = StepSpec(step_id="automation", kind=StepKind.AUTOMATION, title="Automation Step", depends_on=["design"])
    run_spec = RunSpec(
        run_id="run_fail_001",
        title="Failed Build Run",
        workspace_dir=str(ws),
        steps=[s1, s2],
    )
    state = RunState.new(run_spec)
    now = time.time()
    state.records["design"].status = StepStatus.DONE
    state.records["design"].started_at = now - 10
    state.records["design"].finished_at = now - 8
    state.records["design"].data = {"engine": "5.7.4", "params": {"project_name": "DarkLadder"}}

    state.records["automation"].status = StepStatus.FAILED
    state.records["automation"].started_at = now - 8
    state.records["automation"].finished_at = now
    state.records["automation"].errors = ["no automation report written (tests did not run)"]
    state.records["automation"].data = {"exit_code": 255}

    state.status = StepStatus.FAILED
    store.save(state)

    view = BuildView(workspace_root=ws)
    try:
        view._store = store
        view.refresh_runs()

        # Failed run should show banner with "Show Problems"
        assert not view._summary_banner.isHidden()
        assert "Show Problems" in view._btn_banner_action.text()
        assert "no automation report written" in view._lbl_banner_msg.text()

        # Auto-selection on failed run should select automation step (index 1)
        cur_idx = view._timeline_view.currentIndex()
        assert cur_idx.row() == 1

        # Now simulate user having navigated to design step (index 0)
        view._timeline_view.setCurrentIndex(view._timeline_model.index(0, 0))
        view._on_step_selected(view._timeline_model.index(0, 0))
        assert "design" in view._lbl_step_header.text().lower()

        # User clicks "Show Problems" in banner
        view._btn_banner_action.click()

        # Should jump back to automation step and show problems
        assert view._timeline_view.currentIndex().row() == 1
        assert "automation" in view._lbl_step_header.text().lower()
        assert view._lower_tabs.currentIndex() == 0
        assert view._problems_table.rowCount() == 1
        assert "no automation report written" in view._problems_table.item(0, 2).text()
    finally:
        view.deleteLater()


def test_build_view_display_step_structured_logs(qapp, tmp_path):
    """Verify procedural steps like design and scaffold display structured logs."""
    ws = tmp_path / "ws_logs"
    ws.mkdir(parents=True, exist_ok=True)
    view = BuildView(workspace_root=ws)
    try:
        # Step: Design
        rec_design = StepRecord(
            step_id="design",
            status=StepStatus.DONE,
            started_at=100.0,
            finished_at=101.5,
            checkpoint="git_hash_abc",
            data={"engine": "5.7.4", "params": {"project_name": "TestGame", "board_size": 3}},
        )
        view._display_step(rec_design)
        log_text = view._log_view._edit.toPlainText()
        assert "Design specification validated" in log_text
        assert "Target Unreal Engine: 5.7.4" in log_text
        assert "project_name: TestGame" in log_text
        assert "Git Checkpoint: git_hash_abc" in log_text

        # Step: Scaffold
        rec_scaffold = StepRecord(
            step_id="scaffold",
            status=StepStatus.DONE,
            started_at=102.0,
            finished_at=103.0,
            data={"uproject": "C:/Games/TestGame.uproject", "files": ["TestGame.uproject", "Source/Game.cpp"]},
        )
        view._display_step(rec_scaffold)
        scaffold_text = view._log_view._edit.toPlainText()
        assert "C++ project scaffolding complete" in scaffold_text
        assert "C:/Games/TestGame.uproject" in scaffold_text
        assert "Generated files (2)" in scaffold_text
    finally:
        view.deleteLater()


def test_build_view_no_raw_hex_colors():
    """Verify zero raw hex colors in build view and widgets."""
    pattern = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    files = [
        Path("src/gameforge_ide/desktop/views/build_view.py"),
        Path("src/gameforge_ide/desktop/widgets/step_row.py"),
        Path("src/gameforge_ide/desktop/widgets/log_view.py"),
        Path("src/gameforge_ide/desktop/widgets/problems_table.py"),
    ]
    for f in files:
        assert f.is_file(), f"Missing file {f}"
        text = f.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        assert not matches, f"Raw hex color literals found in {f}: {matches}"


def test_problems_table_extended_columns_and_icons(qapp):
    """Verify ProblemsTable has 6 columns, severity icons, and navigation from any cell."""
    table = ProblemsTable()
    try:
        assert table.columnCount() == 6
        assert [table.horizontalHeaderItem(i).text() for i in range(6)] == [
            "Severity", "Location", "Message", "Code", "Source File", "Line"
        ]

        problems = [
            {
                "severity": "Error",
                "file": "Source/Game/Player.cpp",
                "line": 105,
                "message": "Undefined reference to AHeroCharacter",
                "code": "C2065",
            },
            {
                "severity": "Warning",
                "file": "Config/DefaultEngine.ini",
                "line": 12,
                "message": "Deprecated render setting",
                "code": "W1002",
            },
            {
                "severity": "Info",
                "file": "Source/Game.Build.cs",
                "line": 5,
                "message": "Module optimization enabled",
                "code": "I0010",
            },
        ]
        table.set_problems(problems)
        assert table.rowCount() == 3

        # Row 0 (Error)
        assert table.item(0, 0).text() == "ERROR"
        assert not table.item(0, 0).icon().isNull()
        assert table.item(0, 1).text() == "Source/Game/Player.cpp:105"
        assert table.item(0, 2).text() == "Undefined reference to AHeroCharacter"
        assert table.item(0, 3).text() == "C2065"
        assert table.item(0, 4).text() == "Source/Game/Player.cpp"
        assert table.item(0, 5).text() == "105"

        # Row 1 (Warning)
        assert table.item(1, 0).text() == "WARNING"
        assert not table.item(1, 0).icon().isNull()
        assert table.item(1, 3).text() == "W1002"

        # Row 2 (Info)
        assert table.item(2, 0).text() == "INFO"
        assert not table.item(2, 0).icon().isNull()
        assert table.item(2, 3).text() == "I0010"

        # Navigation signal triggered from double clicking Message cell (col 2)
        nav_received = []
        table.openLocationRequested.connect(lambda f, l: nav_received.append((f, l)))
        table._on_row_double_clicked(table.model().index(0, 2))
        assert nav_received == [("Source/Game/Player.cpp", 105)]

        # Navigation triggered from Source File cell (col 4)
        table._on_row_double_clicked(table.model().index(1, 4))
        assert nav_received[-1] == ("Config/DefaultEngine.ini", 12)
    finally:
        table.deleteLater()


def test_log_view_floating_autoscroll_button(qapp):
    """Verify LogView creates amber floating resume autoscroll button and manages visibility."""
    log_view = LogView()
    try:
        log_view.resize(500, 350)
        log_view.show()

        assert hasattr(log_view, "_floating_resume_btn")
        assert log_view._floating_resume_btn.isHidden()

        # Add lines to populate scrollbar
        for i in range(150):
            log_view.append_log(f"Line {i:03d} execution trace log output\n")
        log_view._flush_queue()

        # Scroll up
        scrollbar = log_view._scrollbar
        assert log_view._auto_scroll is True
        scrollbar.setValue(10)

        # Trigger value changed
        log_view._on_scroll_value_changed(10)
        assert log_view._auto_scroll is False
        assert not log_view._floating_resume_btn.isHidden()

        # Click floating button
        log_view._floating_resume_btn.click()
        assert log_view._auto_scroll is True
        assert log_view._floating_resume_btn.isHidden()
        assert scrollbar.value() == scrollbar.maximum()
    finally:
        log_view.deleteLater()


def test_build_view_splitter_minimum_heights_and_collapsible(qapp):
    """Verify vertical QSplitter enforces minimum heights and prevents collapse."""
    view = BuildView()
    try:
        assert view._right_splitter.isCollapsible(0) is False
        assert view._right_splitter.isCollapsible(1) is False
        assert view._log_view.minimumHeight() >= 160
        assert view._lower_tabs.minimumHeight() >= 160
    finally:
        view.deleteLater()

