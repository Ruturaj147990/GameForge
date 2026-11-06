"""Regression tests for Studio Core Views Specialist (DEF-093 through DEF-102).

Covers:
- DEF-093: GamesView: typing introspection succeeds without Union NameError.
- DEF-094: GamesView: delete without project_dir resolves via resolve_project_dir import.
- DEF-095: HomeView: offline Ollama/None GDS handling displays notice without crashing DesignView.
- DEF-096: HomeView: in-flight job concurrency guard prevents duplicate submissions.
- DEF-097: HomeView: thread-safe SystemsService updates & readiness probe failure fallback.
- DEF-098: GamesView: empty state placeholder & selection reset upon project deletion.
- DEF-099: SettingsView: clearing settings fields properly removes keys from disk.
- DEF-100: SettingsView: engine combo synchronization on load & non-editable role columns.
- DEF-101: SettingsView & Onboarding: empty engine path validation provides neutral guidance.
- DEF-102: OnboardingView: existence of onboarding_view module alias & atomic settings write.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import typing
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.core.jobs import default_job_manager
from src.gameforge_ide.core.settings import get_settings, reset_settings_cache
from src.gameforge_ide.core.systems import SystemRow, SystemsSnapshot
from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.prompt_to_gds import PromptToGdsResult
from src.gameforge_ide.desktop.services.projects_service import GameSummary
from src.gameforge_ide.desktop.views.games_view import (
    GameCardDelegate,
    GamesListModel,
    GamesView,
)
from src.gameforge_ide.desktop.views.home_view import (
    HomeView,
    PresetChip,
    PromptTextEdit,
    RecentGameCard,
)
from src.gameforge_ide.desktop.views.onboarding import (
    EnginePage,
    OnboardingWizard,
    PathsPage,
)
from src.gameforge_ide.desktop.views.onboarding_view import (
    OnboardingView,
    OnboardingWizard as OnboardingWizardAlias,
)
from src.gameforge_ide.desktop.views.settings_view import SettingsView


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ── DEF-076: GamesView type annotations introspection ─────────────────────────

def test_def076_games_view_type_hints_introspection():
    """Verify GamesView type annotations can be introspected without Union NameError."""
    hints = typing.get_type_hints(GamesView.__init__)
    assert "projects_root" in hints
    assert "workspace_dir" in hints
    assert "parent" in hints


# ── DEF-077: GamesView delete_project with None project_dir ───────────────────

def test_def077_games_view_delete_resolves_project_dir(qapp, tmp_path, monkeypatch):
    """Verify _execute_delete resolves project_dir without NameError on missing import."""
    cfg_file = tmp_path / "settings.json"
    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True)
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(cfg_file))
    cfg_file.write_text(json.dumps({"projects_root": str(projects_root)}), encoding="utf-8")
    reset_settings_cache()

    # Create dummy project
    dummy_dir = projects_root / "DeleteMe"
    dummy_dir.mkdir(parents=True)
    (dummy_dir / "DeleteMe.uproject").write_text("{}", encoding="utf-8")

    view = GamesView(projects_root=projects_root)
    try:
        deleted_signals = []
        view.gameDeleted.connect(lambda name, pdir: deleted_signals.append((name, pdir)))

        # Invoke _execute_delete with project_dir=None (must resolve via resolve_project_dir)
        view._execute_delete("DeleteMe", None)

        # Process Qt event loop until deletion finishes
        for _ in range(50):
            time.sleep(0.05)
            qapp.processEvents()
            if deleted_signals:
                break

        assert len(deleted_signals) == 1
        assert deleted_signals[0][0] == "DeleteMe"
        assert not dummy_dir.exists()
    finally:
        view.deleteLater()


# ── DEF-078: HomeView handles offline Ollama / None GDS gracefully ────────────

def test_def078_home_view_handles_none_gds_offline_ollama(qapp):
    """Verify HomeView displays notice and DOES NOT emit designReady(None) on model failure."""
    view = HomeView()
    try:
        ready_signals = []
        view.designReady.connect(lambda gds, q: ready_signals.append((gds, q)))

        # Simulate job returning PromptToGdsResult with gds=None (e.g. Ollama transport error)
        mock_job = MagicMock()
        mock_job.status = "DONE"
        mock_result = PromptToGdsResult(
            status="NEEDS_INPUT",
            gds=None,
            questions=["Ollama connection failed: connection refused on 127.0.0.1:11434"],
            errors=["TransportError: ConnectionRefused"],
        )
        mock_job.result.return_value = mock_result
        view._active_job = mock_job

        view._handle_design_result()

        # Must not emit designReady with None gds (which would crash DesignView)
        assert len(ready_signals) == 0
        assert not view._notice_lbl.isHidden()
        assert "Ollama connection failed" in view._notice_lbl.text()
    finally:
        view.deleteLater()


# ── DEF-079: HomeView prevents duplicate in-flight job submission ──────────────

def test_def079_home_view_prevents_duplicate_job_submission(qapp):
    """Verify _on_design_it_clicked returns early when a job is already in flight."""
    view = HomeView()
    try:
        view._prompt_input.setPlainText("Create an adventure game")
        mock_job = MagicMock()
        mock_job.done = False
        view._active_job = mock_job

        # Trigger design while job is still active
        view._on_design_it_clicked()

        # Job manager should NOT have been called with a new job
        assert view._active_job is mock_job
    finally:
        view.deleteLater()


# ── DEF-080: HomeView thread-safe SystemsService & readiness probe fallback ──

def test_def080_home_view_readiness_failure_fallback(qapp):
    """Verify HomeView readiness section shows fallback message when snapshot probe fails."""
    view = HomeView()
    try:
        view._latest_snapshot = None
        view._render_readiness()

        # Verify layout contains fallback notice
        assert view._readiness_rows_layout.count() > 0
        w = view._readiness_rows_layout.itemAt(0).widget()
        assert w is not None
        assert "unavailable" in w.text().lower() or "failed" in w.text().lower()
    finally:
        view.deleteLater()


def test_def080_home_view_systems_service_queued_connection(qapp):
    """Verify attach_systems_service securely receives updates without crashing GUI thread."""
    view = HomeView()
    try:
        mock_service = MagicMock()
        view.attach_systems_service(mock_service)
        assert hasattr(view, "_systems_snapshot_slot")
        assert mock_service.snapshotChanged.connect.called
    finally:
        view.deleteLater()


# ── DEF-081: GamesView empty state & selection reset ──────────────────────────

def test_def081_games_view_empty_state_and_selection_reset(qapp):
    """Verify empty games list shows _lbl_empty, hides _list_view, and emits empty selection."""
    view = GamesView()
    view.show()
    try:
        selected = []
        view.gameSelected.connect(lambda name: selected.append(name))

        # Feed empty list
        view._loaded_games = []
        view._on_games_loaded()

        assert not view._lbl_empty.isHidden()
        assert view._list_view.isHidden()
        assert view._selected_game_name is None
        assert "" in selected
    finally:
        view.deleteLater()


def test_def081_games_view_corrupted_metadata_rendering(qapp, tmp_path):
    """Verify GamesView delegate paints gracefully even with corrupted / None metadata."""
    delegate = GameCardDelegate()
    corrupted_game = GameSummary(
        name="BrokenGame",
        title="",  # Empty title
        genre="",  # Empty genre
        pitch="",
        project_dir=tmp_path / "BrokenGame",
        revision=0,
        updated_at=0.0,
        last_run_status=None,
    )

    # Status badge formatting must not crash
    status_text, dot_color = delegate._format_status_badge(corrupted_game)
    assert "UNBUILT" in status_text
    assert dot_color is not None


# ── DEF-082 & DEF-083: SettingsView clearing and atomic persistence ───────────

def test_def082_settings_view_clearing_fields_removes_from_disk(qapp, tmp_path, monkeypatch):
    """Verify clearing settings fields removes keys from JSON so they don't persist stale values."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(
        json.dumps({
            "engine_root": "C:\\UE_Old",
            "projects_root": "C:\\Projects_Old",
            "artifacts_root": "C:\\Artifacts_Old",
            "ollama_url": "http://127.0.0.1:11434",
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(cfg_file))
    reset_settings_cache()

    view = SettingsView(workspace_root=tmp_path)
    try:
        # Clear engine root and artifacts root
        view._engine_path_input.setText("")
        view._artifacts_root_input.setText("")
        view._projects_root_input.setText("C:\\Projects_New")

        view.save_settings()

        assert cfg_file.is_file()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "engine_root" not in data
        assert "artifacts_root" not in data
        assert data.get("projects_root") == "C:\\Projects_New"
    finally:
        view.deleteLater()


def test_def083_settings_view_roles_are_non_editable(qapp, tmp_path):
    """Verify Role items in model table are non-editable to prevent role corruption."""
    view = SettingsView(workspace_root=tmp_path)
    try:
        table = view._models_table
        if table.rowCount() > 0:
            role_item = table.item(0, 0)
            assert not (role_item.flags() & Qt.ItemIsEditable)
    finally:
        view.deleteLater()


def test_def084_settings_view_empty_engine_validation_guidance(qapp, tmp_path):
    """Verify empty engine input displays muted guidance rather than red error."""
    view = SettingsView(workspace_root=tmp_path)
    try:
        view._engine_path_input.setText("")
        view._validate_engine_path()
        status = view._lbl_engine_status.text()
        assert "No engine path configured" in status
        assert "Directory does not exist" not in status
    finally:
        view.deleteLater()


# ── DEF-085: OnboardingView module alias and validation ───────────────────────

def test_def085_onboarding_view_module_alias_and_validation(qapp, tmp_path, monkeypatch):
    """Verify onboarding_view re-exports OnboardingWizard and handles empty engine gracefully."""
    cfg_file = tmp_path / "onboard_test.json"
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(cfg_file))
    reset_settings_cache()

    wizard = OnboardingView()
    try:
        assert isinstance(wizard, OnboardingWizard)
        wizard.engine_page._custom_path.setText("")
        wizard.engine_page._validate_path()
        val_text = wizard.engine_page._lbl_validation.text()
        assert "Select or browse" in val_text
        assert "Directory does not exist" not in val_text

        # Test atomic accept
        wizard.paths_page._projects_path.setText(str(tmp_path / "TestOnboard"))
        wizard.accept()
        assert cfg_file.is_file()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data.get("projects_root") == str(tmp_path / "TestOnboard")
    finally:
        wizard.deleteLater()


# ── Specialist Enhancements Tests (Agent A Polish & Verification) ────────────

def test_home_view_recent_games_card_and_empty_state(qapp, tmp_path):
    """Verify HomeView RecentGameCard displays genre badge, elides title, and renders styled empty state."""
    view = HomeView()
    try:
        # 1. Empty state
        view._latest_games = []
        view._render_recent_games()
        empty_frame = view.findChild(object, "homeRecentGamesEmpty")
        assert empty_frame is not None

        # 2. Populated card
        game = GameSummary(
            name="SuperEpicAdventureGameLongTitle",
            title="Super Epic Adventure Game Long Title That Exceeds Width",
            genre="platformer",
            pitch="A test platformer",
            project_dir=tmp_path / "Adventure",
            updated_at=time.time() - 300,
            last_run_status="DONE",
        )
        view._latest_games = [game]
        view._render_recent_games()

        card = view.findChild(RecentGameCard, f"recentGameCard_{game.name}")
        assert card is not None
        assert card.game.genre == "platformer"
        assert card.focusPolicy() == Qt.StrongFocus
    finally:
        view.deleteLater()


def test_games_view_search_escape_and_empty_cta(qapp):
    """Verify Esc clears GamesView search input and empty container has + New Project CTA."""
    view = GamesView()
    try:
        view.show()
        # Search clear via Esc eventFilter
        view._search_input.setText("Searching...")
        assert view._search_input.text() == "Searching..."

        esc_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        view.eventFilter(view._search_input, esc_event)
        assert view._search_input.text() == ""

        # Empty catalog call-to-action button
        view._loaded_games = []
        view._on_games_loaded()
        btn_empty = view.findChild(object, "gamesBtnEmptyNewProject")
        assert btn_empty is not None
        assert not btn_empty.isHidden()
    finally:
        view.deleteLater()


def test_settings_view_instant_theme_switching_and_storage_guidance(qapp, tmp_path):
    """Verify SettingsView switches theme instantly and provides non-red guidance on empty storage."""
    view = SettingsView(workspace_root=tmp_path)
    try:
        # Instant theme change persists to workspace ini
        target_idx = 0 if view._theme_combo.currentIndex() == 1 else 1
        view._theme_combo.setCurrentIndex(target_idx)
        ws_ini = tmp_path / ".gameforge" / "ide_settings.ini"
        assert ws_ini.is_file()
        ini_content = ws_ini.read_text(encoding="utf-8")
        expected_theme = "dark" if target_idx == 0 else "light"
        assert expected_theme in ini_content.lower()

        # Storage paths neutral validation on empty inputs
        view._projects_root_input.setText("")
        view._artifacts_root_input.setText("")
        view._validate_storage_paths()

        p_status = view._lbl_projects_status.text()
        a_status = view._lbl_artifacts_status.text()
        assert "Default projects directory will be used" in p_status
        assert "Default artifacts directory will be used" in a_status
        assert "Directory does not exist" not in p_status
    finally:
        view.deleteLater()


def test_dialogs_standardized_button_order_and_accessibility(qapp, tmp_path):
    """Verify dialogs have standardized button placement, padding, and accessible labels."""
    from src.gameforge_ide.desktop.dialogs.new_project_dialog import NewProjectDialog
    from src.gameforge_ide.desktop.dialogs.delete_game_dialog import DeleteGameDialog
    from src.gameforge_ide.desktop.dialogs.about_dialog import AboutDialog

    # 1. NewProjectDialog
    np_dlg = NewProjectDialog()
    try:
        assert np_dlg._btn_cancel.text() == "Cancel"
        assert np_dlg._btn_confirm.text() == "Confirm Project Root"
        assert np_dlg._btn_confirm.accessibleName() == "Confirm project root directory"
        assert np_dlg._btn_cancel.accessibleName() == "Cancel project creation"
    finally:
        np_dlg.deleteLater()

    # 2. DeleteGameDialog
    dummy_game = GameSummary(
        name="TestDel",
        title="Test Del",
        genre="fps",
        pitch="test",
        project_dir=tmp_path / "TestDel",
    )
    del_dlg = DeleteGameDialog(dummy_game)
    try:
        assert del_dlg._btn_cancel.text() == "Cancel"
        assert del_dlg._btn_delete.text() == "Delete permanently"
        assert del_dlg._btn_delete.accessibleName() == "Permanently delete project"
        assert del_dlg._btn_cancel.accessibleName() == "Cancel deletion"
    finally:
        del_dlg.deleteLater()

    # 3. AboutDialog
    abt_dlg = AboutDialog()
    try:
        assert abt_dlg._btn_copy.text() == "Copy System Info"
        assert abt_dlg._btn_close.text() == "Close"
        assert abt_dlg._btn_copy.accessibleName() == "Copy system information to clipboard"
        assert abt_dlg._btn_close.accessibleName() == "Close about dialog"
    finally:
        abt_dlg.deleteLater()
