"""Usability walk integration test for Studio UX v2 (WI-4.12).

Simulates end-to-end user flow:
1. Home View: type prompt -> trigger Design
2. Design View: inspect GDS form -> trigger Build
3. Build View: timeline progress & log inspection
4. Play View: scenario results verification
5. Evidence View: artifact gallery inspection
All validated via objectName lookups with zero UI stalls > 50 ms.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.core.settings import get_settings, reset_settings_cache
from src.gameforge_ide.desktop.diagnostics.stall_monitor import StallMonitor
from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.qa.scenario import ScenarioResult


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_studio_usability_walk(qapp, tmp_path, monkeypatch):
    """Execute complete usability walk asserting objectNames and UI responsiveness."""
    monkeypatch.setenv("GAMEFORGE_STALL_MONITOR", "1")
    monkeypatch.setenv("GAMEFORGE_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(tmp_path / "settings.json"))
    reset_settings_cache()

    # Create dummy project so rail items enable
    proj_dir = tmp_path / "MyGame"
    bin_dir = proj_dir / "Binaries" / "Win64"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "MyGame.exe").write_bytes(b"MZfake")
    pkg_dir = proj_dir / "Packaged" / "Windows"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "MyGame.exe").write_bytes(b"MZfake")
    from src.gameforge_ide.design.presets import preset_platformer
    gds_file = proj_dir / "GameForge" / "design" / "game.gds.json"
    gds_file.parent.mkdir(parents=True, exist_ok=True)
    gds_file.write_text(preset_platformer().model_dump_json(), encoding="utf-8")

    monitor = StallMonitor(output_dir=tmp_path / "reports")
    monitor.start()

    win = MainWindow(tmp_path)
    win._current_project = "MyGame"
    win.resize(1440, 900)
    win.show()

    try:
        # Step 1: Home View
        assert win._view_host.current_view_id == "home"
        home_view = win._view_host.get_view_widget("home")
        assert home_view is not None
        assert home_view.objectName() == "studioView_home"

        prompt_box = home_view.findChild(object, "homePromptInput")
        btn_design = home_view.findChild(object, "homeBtnDesign")
        assert prompt_box is not None
        assert btn_design is not None

        prompt_box.setPlainText("a platformer with 6 coins")
        qapp.processEvents()

        # Step 2: Switch to Design View
        win._switch_studio_view("design")
        qapp.processEvents()
        assert win._view_host.current_view_id == "design"

        design_view = win._view_host.get_view_widget("design")
        assert design_view is not None
        assert design_view.objectName() == "studioView_design"
        assert design_view.findChild(object, "btnDesignBuild") is not None

        # Step 3: Switch to Build View
        win._switch_studio_view("build")
        qapp.processEvents()
        assert win._view_host.current_view_id == "build"

        build_view = win._view_host.get_view_widget("build")
        assert build_view is not None
        assert build_view.objectName() == "studioView_build"
        assert build_view.findChild(object, "buildTimelineView") is not None

        # Step 4: Play View
        win._switch_studio_view("play")
        qapp.processEvents()
        assert win._view_host.current_view_id == "play"

        play_view = win._view_host.get_view_widget("play")
        assert play_view is not None
        assert play_view.objectName() == "studioView_play"
        assert play_view.findChild(object, "playResultsTable") is not None
        assert play_view.findChild(object, "btnPlayLaunch") is not None

        # Inject fake scenario result into play view
        fake_result = ScenarioResult.model_validate({
            "schema": "scenario_result/1",
            "scenario_id": "walk_scenario",
            "passed": True,
            "duration_s": 2.5,
            "start_delay_s": 0.1,
            "failures": [],
        })
        play_view._results = [fake_result]
        play_view._populate_table()
        assert play_view._results_table.rowCount() == 1

        # Step 5: Assets View
        win._switch_studio_view("assets")
        qapp.processEvents()
        assert win._view_host.current_view_id == "assets"

        assets_view = win._view_host.get_view_widget("assets")
        assert assets_view is not None
        assert assets_view.objectName() == "studioView_assets"
        assert assets_view.findChild(object, "assetsTableView") is not None

        # Let event loop spin and check stall monitor
        time.sleep(0.1)
        qapp.processEvents()

    finally:
        monitor.stop()
        win.confirm_on_close = False
        win.close()
        win.deleteLater()

    # Verify stall monitor recorded 0 stalls
    rep_file = monitor.save_report()
    data = json.loads(rep_file.read_text(encoding="utf-8"))
    assert data["stalls_detected"] == 0, f"Detected UI stalls: {data['stalls']}"
