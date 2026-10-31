"""Unit tests for Studio UX Play view (spec §4.5, WI-4.8)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.views.play_view import PlayView
from src.gameforge_ide.qa.scenario import ScenarioResult


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_play_view_widget_hierarchy(qapp):
    """Verify PlayView creates required objectNames and accessible names."""
    view = PlayView()
    try:
        assert view.objectName() == "playView"
        assert view.accessibleName() == "GameForge Play View"

        assert view.findChild(object, "lblPlayTitle") is not None
        assert view.findChild(object, "btnPlayRefresh") is not None
        assert view.findChild(object, "btnPlayLaunch") is not None
        assert view.findChild(object, "playSummaryFrame") is not None
        assert view.findChild(object, "lblPlaySummary") is not None
        assert view.findChild(object, "playResultsTable") is not None
        assert view.findChild(object, "playDetailText") is not None
        assert view.findChild(object, "lblPlayDetailHeader") is not None
    finally:
        view.deleteLater()


def test_play_view_scenario_results_display(qapp, tmp_path):
    """Verify PlayView populates scenario results table from files."""
    # Create scenario result files
    sc_dir = tmp_path / "TestProject" / "Saved" / "GameForge" / "scenarios"
    sc_dir.mkdir(parents=True, exist_ok=True)

    result1 = {
        "schema": "scenario_result/1",
        "scenario_id": "collect_3_coins",
        "passed": True,
        "duration_s": 4.2,
        "start_delay_s": 0.5,
        "build": {"configuration": "Development", "engine": "5.7.4"},
        "steps": [
            {"i": 0, "kind": "navigate_to", "status": "DONE", "t0": 0.0, "t1": 1.5},
            {"i": 1, "kind": "wait_event", "status": "DONE", "t0": 1.5, "t1": 4.0},
        ],
        "expect": [
            {"expect": "event_count PickedUp >= 3", "ok": True, "observed": 3}
        ],
        "failures": [],
    }
    result2 = {
        "schema": "scenario_result/1",
        "scenario_id": "impossible_quest",
        "passed": False,
        "duration_s": 10.0,
        "start_delay_s": 0.3,
        "failures": ["Expected event CompletedQuest but got none"],
    }

    (sc_dir / "collect_3_coins_result.json").write_text(json.dumps(result1), encoding="utf-8")
    (sc_dir / "impossible_quest_result.json").write_text(json.dumps(result2), encoding="utf-8")

    view = PlayView(workspace_root=tmp_path)
    try:
        # Directly load results from directory
        for f in sorted(sc_dir.glob("*_result.json")):
            view._results.append(ScenarioResult.from_file(f))
        view._populate_table()

        assert view._results_table.rowCount() == 2

        # Check pass/fail items
        status_0 = view._results_table.item(0, 0).text()
        status_1 = view._results_table.item(1, 0).text()
        assert "PASS" in status_0
        assert "FAIL" in status_1

        # Check scenario IDs
        assert view._results_table.item(0, 1).text() == "collect_3_coins"
        assert view._results_table.item(1, 1).text() == "impossible_quest"

        # Check summary contains count
        assert "2" in view._lbl_summary.text()
        assert "1" in view._lbl_summary.text()  # 1 passed out of 2
    finally:
        view.deleteLater()


def test_play_view_detail_display(qapp, tmp_path):
    """Verify PlayView shows detail for selected scenario."""
    view = PlayView(workspace_root=tmp_path)
    try:
        result = ScenarioResult.model_validate({
            "schema": "scenario_result/1",
            "scenario_id": "guard_patrol",
            "passed": True,
            "duration_s": 7.3,
            "start_delay_s": 0.2,
            "build": {"configuration": "Shipping", "engine": "5.7.4"},
            "steps": [
                {"i": 0, "kind": "navigate_to", "status": "DONE", "t0": 0.0, "t1": 3.5},
            ],
            "legs": [
                {"target": "Guard1", "distance_cm": 500.0, "seconds": 3.5, "max_step_cm": 15.0, "result": "OK"},
            ],
            "expect": [
                {"expect": "event SpottedByGuard", "ok": True, "observed": 1}
            ],
            "failures": [],
        })
        view._results = [result]
        view._populate_table()

        # Select the row
        view._results_table.setCurrentCell(0, 0)
        view._on_result_selected()

        detail = view._detail_text.toPlainText()
        assert "guard_patrol" in view._lbl_detail_header.text()
        assert "Shipping" in detail
        assert "navigate_to" in detail
        assert "Guard1" in detail
        assert "SpottedByGuard" in detail
    finally:
        view.deleteLater()


def test_play_view_launch_signal(qapp):
    """Verify PlayView emits launchRequested with project name."""
    view = PlayView()
    try:
        view._current_project = "MyGame"
        signals = []
        view.launchRequested.connect(lambda p: signals.append(p))
        view._on_launch()
        assert signals == ["MyGame"]
    finally:
        view.deleteLater()


def test_play_view_no_raw_hex_colors():
    """Verify zero raw hex colors in play view source."""
    pattern = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    f = Path("src/gameforge_ide/desktop/views/play_view.py")
    assert f.is_file(), f"Missing file {f}"
    text = f.read_text(encoding="utf-8")
    matches = pattern.findall(text)
    assert not matches, f"Raw hex color literals found in {f}: {matches}"
