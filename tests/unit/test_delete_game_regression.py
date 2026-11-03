"""Unit and regression tests for Delete Game functionality.

Verifies:
1. Deletion of projects with Windows read-only files (e.g. .git/objects and binaries).
2. Deletion with explicit project_dir parameter.
3. Purging of deleted project entries from runs_index.json.
4. Purging of index SQLite database files.
5. Prevention of deletion when active Unreal Editor link exists.
6. DeleteGameDialog acceptance rules (case-insensitive name and title matching).
7. GamesView deletion execution and signal emission.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.core.projects import is_gameforge_project
from src.gameforge_ide.desktop.services.projects_service import (
    GameSummary,
    delete_project,
    list_games,
)
from src.gameforge_ide.desktop.views.games_view import (
    DeleteGameDialog,
    GamesView,
)


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_delete_project_with_readonly_files(tmp_path: Path):
    """Verify delete_project succeeds even when Windows read-only files (.git objects, binaries) are present."""
    proj_dir = tmp_path / "ReadOnlyGame"
    proj_dir.mkdir(parents=True)
    (proj_dir / "game.gds.json").write_text('{"overview": {"genre": "fps"}}', encoding="utf-8")
    (proj_dir / "ReadOnlyGame.uproject").write_text("{}", encoding="utf-8")

    # Simulate .git/objects with read-only file attribute
    git_dir = proj_dir / ".git" / "objects" / "4b"
    git_dir.mkdir(parents=True)
    ro_file = git_dir / "pack_object_file"
    ro_file.write_text("pack-data-hash", encoding="utf-8")
    os.chmod(ro_file, stat.S_IREAD)

    assert proj_dir.is_dir()
    assert (os.stat(ro_file).st_mode & stat.S_IWRITE) == 0

    # Delete project
    success = delete_project("ReadOnlyGame", project_dir=proj_dir)
    assert success is True
    assert not proj_dir.exists()


def test_delete_project_with_explicit_project_dir_and_different_name(tmp_path: Path):
    """Verify delete_project works when folder name differs from game title or logical name."""
    custom_root = tmp_path / "custom_location"
    proj_dir = custom_root / "FolderAlpha"
    proj_dir.mkdir(parents=True)
    (proj_dir / "game.gds.json").write_text('{"meta": {"title": "Combat Strike"}, "overview": {"genre": "shooter"}}', encoding="utf-8")
    (proj_dir / "CombatStrike.uproject").write_text("{}", encoding="utf-8")

    assert proj_dir.is_dir()

    # Pass explicit project_dir
    success = delete_project("CombatStrike", project_dir=proj_dir)
    assert success is True
    assert not proj_dir.exists()


def test_delete_project_purges_runs_index_and_project_index(tmp_path: Path):
    """Verify deleting a project removes its entries from runs_index.json and index db."""
    projects_root = tmp_path / "projects"
    proj_dir = projects_root / "TrackedGame"
    proj_dir.mkdir(parents=True)
    (proj_dir / "game.gds.json").write_text('{"meta": {"title": "Tracked Game"}, "overview": {"genre": "rpg"}}', encoding="utf-8")
    (proj_dir / "TrackedGame.uproject").write_text("{}", encoding="utf-8")

    # Create runs_index.json with two runs: one for TrackedGame, one for OtherGame
    gf_dir = projects_root / ".gameforge"
    gf_dir.mkdir(parents=True)
    runs_file = gf_dir / "runs_index.json"
    runs_data = [
        {"run_id": "run_01", "project_name": "TrackedGame", "project_dir": str(proj_dir), "status": "DONE"},
        {"run_id": "run_02", "project_name": "OtherGame", "project_dir": str(projects_root / "OtherGame"), "status": "DONE"},
    ]
    runs_file.write_text(json.dumps(runs_data), encoding="utf-8")

    # Create index db
    import hashlib
    key = hashlib.sha1(str(proj_dir.resolve()).encode("utf-8")).hexdigest()
    idx_dir = projects_root / ".gameforge" / "index"
    idx_dir.mkdir(parents=True)
    idx_db = idx_dir / f"{key}.db"
    idx_db.write_text("sqlite-mock", encoding="utf-8")

    assert runs_file.is_file()
    assert idx_db.is_file()

    # Delete project
    success = delete_project("TrackedGame", projects_root=projects_root, project_dir=proj_dir)
    assert success is True
    assert not proj_dir.exists()

    # Check runs_index.json purged TrackedGame run but preserved OtherGame
    updated_runs = json.loads(runs_file.read_text(encoding="utf-8"))
    assert len(updated_runs) == 1
    assert updated_runs[0]["project_name"] == "OtherGame"

    # Check index db removed
    assert not idx_db.exists()


def test_delete_project_blocked_on_active_editor_link(tmp_path: Path):
    """Verify delete_project raises RuntimeError when Unreal Editor link is active."""
    proj_dir = tmp_path / "LockedGame"
    proj_dir.mkdir(parents=True)
    (proj_dir / "game.gds.json").write_text('{"overview": {"genre": "fps"}}', encoding="utf-8")

    mock_link = MagicMock()
    mock_link.project_name = "LockedGame"

    with patch("src.gameforge_ide.backend.tools.game_tools.GameTools.all_links", return_value=[mock_link]):
        with pytest.raises(RuntimeError, match="active Unreal Editor link"):
            delete_project("LockedGame", project_dir=proj_dir)

    assert proj_dir.exists()


def test_delete_game_dialog_name_and_title_tolerance(qapp, tmp_path):
    """Verify dialog enables delete button on typing either directory name or title case-insensitively."""
    game = GameSummary(
        name="CS_Regeneration",
        title="CounterStrikeLite",
        genre="fps",
        pitch="Tactical FPS",
        project_dir=tmp_path / "CS_Regeneration",
    )
    dlg = DeleteGameDialog(game)
    try:
        assert dlg._btn_delete.isEnabled() is False

        # Random mismatch
        dlg._confirm_input.setText("random")
        assert dlg._btn_delete.isEnabled() is False

        # Directory name match (exact and case-insensitive)
        dlg._confirm_input.setText("CS_Regeneration")
        assert dlg._btn_delete.isEnabled() is True

        dlg._confirm_input.setText("cs_regeneration")
        assert dlg._btn_delete.isEnabled() is True

        # Title match (exact and case-insensitive)
        dlg._confirm_input.setText("CounterStrikeLite")
        assert dlg._btn_delete.isEnabled() is True

        dlg._confirm_input.setText("counterstrikelite")
        assert dlg._btn_delete.isEnabled() is True

        # Partial mismatch
        dlg._confirm_input.setText("CounterStrike")
        assert dlg._btn_delete.isEnabled() is False
    finally:
        dlg.deleteLater()


def test_delete_game_dialog_fill_button_and_normalization(qapp, tmp_path):
    """Verify 1-click 'Fill name' button and space/punctuation normalization in DeleteGameDialog."""
    game = GameSummary(
        name="CounterStrike",
        title="Counter-Strike",
        genre="fps",
        pitch="Tactical Shooter",
        project_dir=tmp_path / "CounterStrike",
    )
    dlg = DeleteGameDialog(game)
    try:
        assert dlg._btn_delete.isEnabled() is False
        assert "Type the project name" in dlg._status_lbl.text() or "Type the name" in dlg._status_lbl.text()

        # 1. Test clicking 'Fill name' button
        dlg._btn_fill.click()
        assert dlg._confirm_input.text() == "CounterStrike"
        assert dlg._btn_delete.isEnabled() is True
        assert "confirmed" in dlg._status_lbl.text()

        # 2. Test space normalization
        dlg._confirm_input.setText("counter strike")
        assert dlg._btn_delete.isEnabled() is True

        # 3. Test hyphen normalization
        dlg._confirm_input.setText("counter-strike")
        assert dlg._btn_delete.isEnabled() is True

        # 4. Clear input disables it
        dlg._confirm_input.setText("")
        assert dlg._btn_delete.isEnabled() is False
    finally:
        dlg.deleteLater()


def test_games_view_before_game_deleted_signal(qapp, tmp_path):
    """Verify GamesView emits beforeGameDeleted signal to allow releasing workspace locks."""
    view = GamesView()
    try:
        before_events = []
        view.beforeGameDeleted.connect(lambda name, pdir: before_events.append((name, pdir)))

        game = GameSummary(
            name="TargetGame",
            title="Target Game",
            genre="adventure",
            pitch="A test game",
            project_dir=tmp_path / "TargetGame",
        )

        # Mock DeleteGameDialog to simulate user clicking accept
        from unittest.mock import patch
        from PySide6.QtWidgets import QDialog
        with patch.object(DeleteGameDialog, "exec", return_value=QDialog.Accepted):
            with patch.object(view, "_execute_delete") as mock_exec:
                view._confirm_delete(game)
                assert before_events == [("TargetGame", tmp_path / "TargetGame")]
                mock_exec.assert_called_once_with("TargetGame", tmp_path / "TargetGame")
    finally:
        view.deleteLater()


def test_delete_project_terminates_locking_child_process(tmp_path):
    """Verify delete_project detects and terminates child processes locking the folder on Windows."""
    import subprocess
    proj_dir = tmp_path / "LockedChildProject"
    proj_dir.mkdir(parents=True)
    (proj_dir / "test.uproject").write_text("{}")

    # Spawn child powershell with cwd = proj_dir
    proc = subprocess.Popen(["powershell.exe", "-NoLogo", "-NonInteractive"], cwd=str(proj_dir))
    try:
        # Verify proc is running
        assert proc.poll() is None

        # delete_project should terminate child proc and successfully remove folder
        success = delete_project("LockedChildProject", project_dir=proj_dir)
        assert success is True
        assert not proj_dir.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_games_view_delete_callback_and_signal(qapp, tmp_path):
    """Verify GamesView._on_delete_finished emits gameDeleted and triggers refresh."""
    view = GamesView()
    try:
        deleted_events = []
        view.gameDeleted.connect(lambda name, pdir: deleted_events.append((name, pdir)))

        # Mock refresh_games
        refresh_called = []
        view.refresh_games = lambda: refresh_called.append(True)

        target_dir = tmp_path / "TestDeleted"
        view._on_delete_finished(True, "TestDeleted", "", target_dir)

        assert refresh_called == [True]
        assert deleted_events == [("TestDeleted", target_dir)]
    finally:
        view.deleteLater()
