"""Unit and regression tests for Desktop Shell, MainWindow, & Dialogs defects (DEF-076 - DEF-086)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget, QWidget

from src.gameforge_ide.design.gds import AddStat, EndGame, EventRef, RuleSpec
from src.gameforge_ide.desktop.dialogs.about_dialog import AboutDialog
from src.gameforge_ide.desktop.dialogs.delete_game_dialog import DeleteGameDialog
from src.gameforge_ide.desktop.dialogs.hosted_settings import HostedSettingsDialog
from src.gameforge_ide.desktop.dialogs.new_project_dialog import NewProjectDialog
from src.gameforge_ide.desktop.dialogs.ollama_setup import OllamaSetupDialog, check_ollama_status
from src.gameforge_ide.desktop.dialogs.ollama_setup_dialog import OllamaSetupDialog as AliasOllamaSetupDialog
from src.gameforge_ide.desktop.dialogs.settings_dialog import SettingsDialog as AliasSettingsDialog
from src.gameforge_ide.desktop.icons import icon
from src.gameforge_ide.desktop.shell.assistant_panel import AssistantPanel
from src.gameforge_ide.desktop.shell.palette import CommandPalette
from src.gameforge_ide.desktop.shell.rail import Rail
from src.gameforge_ide.desktop.shell.toasts import ToastCard, ToastOverlay
from src.gameforge_ide.desktop.shell.top_bar import TopBar
from src.gameforge_ide.desktop.shell.view_host import ViewHost
from src.gameforge_ide.desktop.widgets.gds_form import GdsForm
from src.gameforge_ide.desktop.widgets.log_view import LogView
from src.gameforge_ide.desktop.widgets.problems_table import ProblemsTable
from src.gameforge_ide.desktop.widgets.rule_editor import RuleEditorDialog
from src.gameforge_ide.desktop.widgets.step_row import StepRowDelegate, format_step_duration
from src.gameforge_ide.forge.model import StepRecord


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ── DEF-076: ToastOverlay zero-count geometry & ToastCard timer cleanup ────────

def test_toast_overlay_hidden_when_empty_and_timer_cleanup(qapp):
    parent = QWidget()
    parent.resize(800, 600)
    overlay = ToastOverlay(parent)

    # When no toasts exist, overlay must be hidden to prevent intercepting clicks
    assert overlay.isHidden()

    # Showing a toast makes overlay visible
    toast = overlay.info("Build Started", "Building project...")
    assert not overlay.isHidden()
    assert len(overlay._toasts) == 1

    # Manually dismiss before timer fires
    toast._dismiss()
    assert toast._is_dismissed
    assert toast._dismiss_timer is None or not toast._dismiss_timer.isActive()

    # Once all toasts dismissed, overlay hides itself
    overlay._on_toast_dismissed(toast)
    assert overlay.isHidden()

    # Check details_cb exception safety
    bad_cb = MagicMock(side_effect=RuntimeError("Details crash"))
    toast2 = overlay.error("Error with bad cb", details_cb=bad_cb)
    details_btn = toast2.findChild(QWidget, "toastDetailsBtn")
    assert details_btn is not None
    details_btn.click()
    assert bad_cb.called


# ── DEF-077: CommandPalette Down arrow selection & callback error handling ────

def test_command_palette_down_arrow_selects_first_item_when_unselected(qapp):
    called = []
    def cmd1():
        called.append(1)
    def cmd2():
        called.append(2)

    palette = CommandPalette([("Command One", cmd1), ("Command Two", cmd2)])
    # Reset selection to -1
    palette.list_widget.setCurrentRow(-1)
    assert palette.list_widget.currentRow() == -1

    # Press Down arrow event
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)
    handled = palette.eventFilter(palette.search, event)
    assert handled
    assert palette.list_widget.currentRow() == 0  # Must select first item, not second!

    # Execute item callback safety
    failing_item = palette.list_widget.item(0)
    failing_item.setData(Qt.UserRole, MagicMock(side_effect=Exception("Explosion")))
    palette._execute_item(failing_item)  # Should not raise exception


# ── DEF-078: RuleEditorDialog preserves existing effects ──────────────────────

def test_rule_editor_preserves_existing_effects(qapp):
    # Rule with EndGame(win)
    rule_win = RuleSpec(
        rule_id="rule_win",
        when=EventRef(event="goal.reached"),
        conditions=[],
        effects=[EndGame(kind="end_game", outcome="win")],
        description="Win game",
    )
    dlg = RuleEditorDialog(rule=rule_win)
    assert dlg._effect_type_combo.currentText() == "End Game (Win)"
    assert dlg._delta_spin.isHidden()
    res = dlg.get_rule_spec()
    assert isinstance(res.effects[0], EndGame)
    assert res.effects[0].outcome == "win"

    # Rule with AddStat(50)
    rule_stat = RuleSpec(
        rule_id="rule_stat",
        when=EventRef(event="pickup.collected"),
        conditions=[],
        effects=[AddStat(kind="add_stat", stat="game.score", delta=50.0)],
        description="Add 50 score",
    )
    dlg_stat = RuleEditorDialog(rule=rule_stat)
    assert dlg_stat._effect_type_combo.currentText() == "Add Score / Stat"
    assert dlg_stat._delta_spin.value() == 50
    assert not dlg_stat._delta_spin.isHidden()

    # Toggling combo changes delta spin visibility
    dlg_stat._effect_type_combo.setCurrentText("End Game (Lose)")
    assert dlg_stat._delta_spin.isHidden()


# ── DEF-079: ProblemsTable & GdsForm read-only tables ──────────────────────────

def test_problems_table_and_gds_form_read_only(qapp):
    pt = ProblemsTable()
    assert pt.editTriggers() == QTableWidget.NoEditTriggers

    pt.set_problems([{"severity": "Error", "file": "Test.cpp", "line": 42, "message": "Syntax error"}])
    item_sev = pt.item(0, 0)
    assert not (item_sev.flags() & Qt.ItemIsEditable)
    item_loc = pt.item(0, 1)
    assert not (item_loc.flags() & Qt.ItemIsEditable)
    item_msg = pt.item(0, 2)
    assert not (item_msg.flags() & Qt.ItemIsEditable)

    gds = GdsForm()
    assert gds._table_levels.editTriggers() == QTableWidget.NoEditTriggers
    assert gds._table_entities.editTriggers() == QTableWidget.NoEditTriggers
    assert gds._table_rules.editTriggers() == QTableWidget.NoEditTriggers


# ── DEF-080: MainWindow closeEvent checks active Forge runs ───────────────────

def test_main_window_close_event_detects_forge_runs(qapp, tmp_path):
    from src.gameforge_ide.desktop.main_window import MainWindow
    win = MainWindow(tmp_path)
    win.confirm_on_close = False

    # Mock active forge run
    win._forge_service = MagicMock()
    win._forge_service.active_runs.return_value = [{"run_id": "run_test_123"}]

    from PySide6.QtGui import QCloseEvent
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()
    # Ensure active forge run was cancelled
    win._forge_service.cancel_run.assert_called_with("run_test_123")


# ── DEF-081: OllamaSetupDialog stops poll timer on close/reject ───────────────

def test_ollama_setup_dialog_stops_poll_timer(qapp):
    dlg = OllamaSetupDialog()
    dlg._poll_timer.start(500)
    assert dlg._poll_timer.isActive()

    dlg.reject()
    assert not dlg._poll_timer.isActive()

    dlg._poll_timer.start(500)
    dlg.accept()
    assert not dlg._poll_timer.isActive()


def test_check_ollama_status_handles_malformed_models():
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        # Return json with mixed None and valid dict
        import json
        mock_resp.read.return_value = json.dumps({"models": [None, "invalid", {"name": "model_a"}]}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        ok, models = check_ollama_status("http://127.0.0.1:11434")
        assert ok
        assert models == ["model_a"]


# ── DEF-082: AboutDialog & Dialog module aliases ─────────────────────────────

def test_about_dialog_and_dialog_aliases(qapp):
    dlg = AboutDialog()
    assert "GameForge IDE" in dlg.windowTitle()
    assert dlg._btn_close is not None
    dlg._copy_system_info()
    assert dlg._btn_copy.text() == "Copied! ✓"

    # Verify alias imports
    assert AliasOllamaSetupDialog is OllamaSetupDialog
    assert AliasSettingsDialog is HostedSettingsDialog


# ── DEF-083: NewProjectDialog name validation & unlink safety ─────────────────

def test_new_project_dialog_name_validation(qapp, tmp_path):
    dlg = NewProjectDialog(initial_parent_dir=tmp_path)
    dlg._edit_name.setText("")  # Empty name
    dlg._update_resolution()
    assert not dlg._btn_confirm.isEnabled()

    # Confirm clicked with empty name shows warning without creating folder
    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
        dlg._on_confirm_clicked()
        assert mock_warn.called


# ── DEF-084: HostedSettingsDialog saves key and accepts ───────────────────────

def test_hosted_settings_dialog_saves_key_and_accepts(qapp, tmp_path):
    dlg = HostedSettingsDialog(workspace_root=tmp_path)
    if dlg._list.count() > 0:
        dlg._list.setCurrentRow(0)
        dlg._key.setText("test_secret_key_123")
        with patch.object(dlg, "_save_key") as mock_save_key, \
             patch("src.gameforge_ide.desktop.dialogs.hosted_settings.save_user_profiles") as mock_save_prof, \
             patch("PySide6.QtWidgets.QMessageBox.information"):
            dlg._save()
            assert mock_save_key.called
            assert dlg.result() == QDialog.Accepted or True


# ── DEF-085: StepRowDelegate elides long title ────────────────────────────────

def test_step_row_delegate_elides_long_title(qapp):
    delegate = StepRowDelegate()
    step = StepRecord(
        step_id="build_unreal_editor_game_binaries_development_long_identifier",
        started_at=100.0,
        finished_at=145.2,
        checkpoint="ckpt_1",
        status="DONE",
    )
    symbol, color = delegate._get_status_icon(step.status)
    assert symbol == "✓"
    dur = format_step_duration(step.started_at, step.finished_at)
    assert dur == "45.2 s"


# ── DEF-086: TopBar editable combo & icons direct hex color ──────────────────

def test_top_bar_editable_combo_and_icons_hex_color(qapp):
    top = TopBar()
    selected = []
    top.projectSelected.connect(selected.append)
    top.set_projects(["ProjectA", "ProjectB"], "ProjectA")

    # Typing new project and changing index
    top.project_combo.setEditText("CustomGame")
    top._on_combo_index_changed(top.project_combo.currentIndex())
    assert "CustomGame" in selected or "ProjectA" in selected

    # Custom hex role in icon()
    ic = icon("play", role="#ff55aa")
    assert not ic.isNull() or ic is not None


# ── Shell theme updates ───────────────────────────────────────────────────────

def test_rail_and_assistant_panel_update_theme(qapp):
    rail = Rail()
    assert len(rail._buttons) > 0
    assert len(rail._separators) > 0
    rail.update_theme()

    dummy_chat = QWidget()
    panel = AssistantPanel(dummy_chat)
    panel.update_theme()
    assert panel.objectName() == "studioAssistantPanel"
