"""Unit tests for Studio UX Design view and GDS form (spec §4.3, WI-4.6)."""
from __future__ import annotations

import os
from pathlib import Path
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.presets import PRESETS
import src.gameforge_ide.design.store as gds_store
from src.gameforge_ide.desktop.views.design_view import (
    DesignView,
    DiffDialog,
    RawJsonDialog,
)
from src.gameforge_ide.desktop.widgets.gds_form import GdsForm
from src.gameforge_ide.desktop.widgets.rule_editor import RuleEditorDialog


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_design_view_widget_hierarchy(qapp):
    """Verify DesignView creates required objectNames and accessible names."""
    view = DesignView()
    try:
        assert view.objectName() == "designView"
        assert view.accessibleName() == "GameForge Design View"

        assert view.findChild(object, "lblDesignStatus") is not None
        assert view.findChild(object, "btnDesignSave") is not None
        assert view.findChild(object, "btnDesignHistory") is not None
        assert view.findChild(object, "btnDesignRawJson") is not None
        assert view.findChild(object, "btnDesignBuild") is not None
        assert view.findChild(object, "designQuestionsPanel") is not None
        assert view.findChild(object, "designChangePanel") is not None
        assert view.findChild(object, "txtDesignChangeRequest") is not None
        assert view.findChild(object, "btnDesignPreviewChange") is not None
        assert view.findChild(object, "btnDesignApplyChange") is not None
        assert view.findChild(object, "btnDesignRebuildChanges") is not None
        assert view.findChild(GdsForm, "gdsForm") is not None
    finally:
        view.deleteLater()


def test_gds_form_population_and_validation(qapp):
    """Verify GdsForm populates from GameDesignSpec and validates edits."""
    form = GdsForm()
    try:
        spec = PRESETS["platformer"]()
        form.set_spec(spec)

        assert form._combo_genre.currentData() == "platformer"
        assert form._spin_session.value() == 10
        assert form._table_entities.rowCount() == len(spec.entities)
        assert form._table_rules.rowCount() == len(spec.rules)

        # Edit pitch
        changed_fired = []
        form.changed.connect(lambda: changed_fired.append(True))
        form._edit_pitch.setPlainText("New updated pitch for platformer")
        assert len(changed_fired) > 0

        # Verify extracted spec has new pitch
        updated_spec = form.get_spec()
        assert updated_spec is not None
        assert updated_spec.overview.pitch == "New updated pitch for platformer"
    finally:
        form.deleteLater()


def test_rule_editor_dialog(qapp):
    """Verify RuleEditorDialog constructs a valid RuleSpec."""
    dlg = RuleEditorDialog(entity_ids=["coin", "player"])
    try:
        dlg._id_input.setText("rule_collect")
        dlg._event_combo.setCurrentText("pickup.collected")
        dlg._source_combo.setCurrentText("coin")
        dlg._delta_spin.setValue(25)
        dlg._desc_input.setText("Award 25 points")

        rule = dlg.get_rule_spec()
        assert rule.rule_id == "rule_collect"
        assert rule.when.event == "pickup.collected"
        assert rule.when.source == "coin"
        assert rule.effects[0].delta == 25.0
        assert rule.description == "Award 25 points"
    finally:
        dlg.deleteLater()


def test_design_view_questions_panel(qapp):
    """Verify opening draft with questions shows questions panel and handles answers."""
    view = DesignView()
    try:
        spec = PRESETS["platformer"]()
        questions = ["Should guards end the game on sight?", "How many relics?"]
        view.open_draft(spec, questions)

        assert not view._questions_panel.isHidden()
        assert view._questions_layout.count() >= 3  # Header + 2 question rows
    finally:
        view.deleteLater()


def test_raw_json_dialog_apply(qapp):
    """Verify RawJsonDialog validates and provides parsed spec on apply."""
    spec = PRESETS["tic_tac_toe"]()
    dlg = RawJsonDialog(spec)
    try:
        # Valid edit
        raw = spec.model_dump_json(indent=2).replace("Tic-Tac-Toe", "Super Tic-Tac-Toe")
        dlg._edit.setPlainText(raw)
        dlg._on_apply()
        assert dlg.validated_spec is not None
        assert dlg.validated_spec.meta.title == "Super Tic-Tac-Toe"

        # Invalid edit shows error label
        dlg._edit.setPlainText("{ invalid_json: true ")
        dlg._on_apply()
        assert not dlg._err_lbl.isHidden()
    finally:
        dlg.deleteLater()


def test_design_save_and_history_diff(qapp, tmp_path, monkeypatch):
    """Verify saving increments revision and history diff works."""
    monkeypatch.setattr(
        "src.gameforge_ide.desktop.views.design_view.get_settings",
        lambda: type("SettingsMock", (), {"projects_root": str(tmp_path)})(),
    )
    proj_dir = tmp_path / "SaveTestGame"
    proj_dir.mkdir(parents=True)

    spec = PRESETS["platformer"]()
    spec.meta.project_name = "SaveTestGame"
    spec.meta.title = "SaveTestGame"
    spec.meta.revision = 1

    # Save revision 1
    gds_store.save(proj_dir, spec)

    view = DesignView()
    try:
        assert view.load_project("SaveTestGame") is True
        assert view._current_spec.meta.revision == 1

        # Edit form and save
        view._form._spin_session.setValue(20)
        assert view.save_spec() is True
        assert view._current_spec.meta.revision == 2

        # Check revisions history
        revs = gds_store.history(proj_dir)
        assert revs == [1, 2]

        # Verify diff
        r1_spec = gds_store.load_revision(proj_dir, 1)
        r2_spec = gds_store.load_revision(proj_dir, 2)
        diff_ops = gds_store.diff(r1_spec, r2_spec)
        assert len(diff_ops) > 0
    finally:
        view.deleteLater()


def test_design_view_change_request_workflow(qapp, tmp_path, monkeypatch):
    """Verify change request input, preview diff, and apply to new revision (WI-8.1)."""
    monkeypatch.setattr(
        "src.gameforge_ide.desktop.views.design_view.get_settings",
        lambda: type("SettingsMock", (), {"projects_root": str(tmp_path)})(),
    )

    proj_dir = tmp_path / "ChangeReqGame"
    proj_dir.mkdir(parents=True)
    from src.gameforge_ide.design.presets import preset_relic_hunt
    spec = preset_relic_hunt(title="ChangeReqGame")
    spec.meta.project_name = "ChangeReqGame"
    spec.meta.revision = 1
    gds_store.save(proj_dir, spec)

    view = DesignView()
    view.show()
    try:
        assert view.load_project("ChangeReqGame") is True
        assert view._current_spec.meta.revision == 1

        # Propose faster guards
        view._txt_change.setText("make guards faster")
        view._btn_preview_change.click()

        assert not view._diff_preview_box.isHidden()
        assert "500.0" in view._lbl_diff_preview.text()

        # Apply change
        view._btn_apply_change.click()

        # Spec revision should bump to 2
        assert view._current_spec.meta.revision == 2
        assert view._diff_preview_box.isHidden()

        p_guard = next(e for e in view._current_spec.entities if e.entity_id == "guard")
        assert p_guard.props["move_speed"] == 500.0
    finally:
        view.deleteLater()


def test_no_hardcoded_hex_colors_in_design_view():
    """Verify normative rule: colours come only from tokens; zero hex literals."""
    views_dir = Path("src/gameforge_ide/desktop/views")
    widgets_dir = Path("src/gameforge_ide/desktop/widgets")
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")

    for p in [views_dir / "design_view.py", widgets_dir / "gds_form.py", widgets_dir / "rule_editor.py"]:
        content = p.read_text(encoding="utf-8")
        matches = hex_pattern.findall(content)
        assert matches == [], f"Found hardcoded hex literals in {p.name}: {matches}"
