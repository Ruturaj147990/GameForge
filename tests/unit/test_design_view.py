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
    parse_question_options,
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


def test_parse_question_options():
    """Verify parse_question_options extracts choices or defaults to Yes/No."""
    assert parse_question_options("Do you want to play as a ghost or a human?") == ["Ghost", "Human"]
    assert parse_question_options("Is the board haunted or just dark?") == ["Haunted", "Just dark"]
    assert parse_question_options("Should the player roll dice or move automatically?") == ["Roll dice", "Move automatically"]
    assert parse_question_options("Do you want single-player, co-op, or versus?") == ["Single-player", "Co-op", "Versus"]
    assert parse_question_options("Which camera style: third person, first person, or top-down?") == ["Third person", "First person", "Top-down"]
    assert parse_question_options("Do you want jump scares?") == ["Yes", "No"]


def test_design_view_questions_panel(qapp):
    """Verify opening draft with questions shows custom option buttons, Other input, and records answers."""
    view = DesignView()
    try:
        spec = PRESETS["platformer"]()
        questions = [
            "Do you want to play as a ghost or a human?",
            "Is the board haunted or just dark?",
        ]
        view.open_draft(spec, questions)

        assert not view._questions_panel.isHidden()
        assert view._questions_layout.count() == 3  # Header + 2 question rows

        # Row 1: "Do you want to play as a ghost or a human?"
        row1 = view._questions_layout.itemAt(1).widget()
        assert row1 is not None

        # Inspect buttons in row 1
        from PySide6.QtWidgets import QPushButton, QLineEdit, QLabel
        buttons_row1 = row1.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons_row1]
        assert "Ghost" in btn_texts
        assert "Human" in btn_texts
        assert "Submit" in btn_texts

        # Click "Ghost" button
        btn_ghost = next(b for b in buttons_row1 if b.text() == "Ghost")
        btn_ghost.click()

        # Check row 1 state after answer
        assert view._answered_questions.get("Do you want to play as a ghost or a human?") == "Ghost"
        assert view._is_dirty is True
        badges_row1 = [lbl.text() for lbl in row1.findChildren(QLabel) if "✓ Ghost" in lbl.text()]
        assert len(badges_row1) == 1

        # Row 2: "Is the board haunted or just dark?"
        row2 = view._questions_layout.itemAt(2).widget()
        assert row2 is not None

        txt_other = row2.findChild(QLineEdit)
        assert txt_other is not None
        assert txt_other.placeholderText() == "Other…"

        # Type custom answer in Other and submit
        txt_other.setText("Foggy cemetery")
        btn_submit = next(b for b in row2.findChildren(QPushButton) if b.text() == "Submit")
        btn_submit.click()

        # Check row 2 state after answer
        assert view._answered_questions.get("Is the board haunted or just dark?") == "Foggy cemetery"
        badges_row2 = [lbl.text() for lbl in row2.findChildren(QLabel) if "✓ Foggy cemetery" in lbl.text()]
        assert len(badges_row2) == 1

        # All questions answered -> header updated
        assert "answered ✓" in view._lbl_q_head.text()
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


def test_design_view_build_game_triggers_without_name_error(qapp, tmp_path, monkeypatch):
    """Verify build_game checks impact analysis safely without NameError and emits buildRequested."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        "src.gameforge_ide.desktop.views.design_view.get_settings",
        lambda: type("SettingsMock", (), {"projects_root": str(tmp_path)})(),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    proj_dir = tmp_path / "BuildTestGame"
    proj_dir.mkdir(parents=True)
    spec = PRESETS["platformer"]()
    spec.meta.project_name = "BuildTestGame"
    gds_store.save(proj_dir, spec)

    view = DesignView()
    try:
        assert view.load_project("BuildTestGame") is True
        emitted = []
        view.buildRequested.connect(emitted.append)
        view.build_game()
        assert emitted == ["BuildTestGame"]
    finally:
        view.deleteLater()


def test_collapsible_section_safe_stylesheet(qapp):
    """Verify CollapsibleSection object names and selectors do not contain invalid characters like '&'."""
    from src.gameforge_ide.desktop.widgets.gds_form import CollapsibleSection
    sec = CollapsibleSection("Look & Sound", object_name="secLookSound")
    assert sec.objectName() == "secLookSound"
    assert "&" not in sec.styleSheet()

    sec2 = CollapsibleSection("HUD & Menus")
    assert "&" not in sec2.objectName()
    assert "&" not in sec2.styleSheet()


def test_no_hardcoded_hex_colors_in_design_view():
    """Verify normative rule: colours come only from tokens; zero hex literals."""
    views_dir = Path("src/gameforge_ide/desktop/views")
    widgets_dir = Path("src/gameforge_ide/desktop/widgets")
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")

    for p in [views_dir / "design_view.py", widgets_dir / "gds_form.py", widgets_dir / "rule_editor.py"]:
        content = p.read_text(encoding="utf-8")
        matches = hex_pattern.findall(content)
        assert matches == [], f"Found hardcoded hex literals in {p.name}: {matches}"


def test_gds_form_player_count_support(qapp):
    """Verify GdsForm cleanly accepts players=4 without pydantic ValidationError crash."""
    from src.gameforge_ide.design.gds import Overview, Genre, CameraKind
    form = GdsForm()
    try:
        spec = PRESETS["tic_tac_toe"]()
        form.set_spec(spec)

        # Set players spinbox to 4
        form._spin_players.setValue(4)
        form._apply_inputs_to_spec()

        updated = form.get_spec()
        assert updated is not None
        assert updated.overview.players == 4

        # Validate form doesn't raise exception
        form._validate_form()
    finally:
        form.deleteLater()


def test_overview_players_range_validation():
    """Verify Overview accepts players between 1 and 8 and rejects out-of-range values."""
    from src.gameforge_ide.design.gds import Overview, Genre, CameraKind
    import pydantic

    # Valid values
    for count in [1, 2, 4, 8]:
        o = Overview(genre=Genre.GRID_BOARD, camera=CameraKind.FIXED_BOARD, players=count)
        assert o.players == count

    # Out of range
    with pytest.raises(pydantic.ValidationError):
        Overview(genre=Genre.GRID_BOARD, camera=CameraKind.FIXED_BOARD, players=0)

    with pytest.raises(pydantic.ValidationError):
        Overview(genre=Genre.GRID_BOARD, camera=CameraKind.FIXED_BOARD, players=9)

