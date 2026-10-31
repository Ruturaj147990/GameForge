"""Unit tests for Studio UX Games view (spec §4.2, WI-4.5)."""
from __future__ import annotations

import os
from pathlib import Path
import re

import pytest
from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtWidgets import QApplication, QDialog, QListView

from src.gameforge_ide.desktop.services.projects_service import GameSummary
from src.gameforge_ide.desktop.views.games_view import (
    GAME_ROLE,
    DeleteGameDialog,
    GameCardDelegate,
    GamesListModel,
    GamesView,
)


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_games_view_widget_hierarchy(qapp):
    """Verify GamesView creates required objectNames and accessible names."""
    view = GamesView()
    try:
        assert view.objectName() == "gamesView"
        assert view.accessibleName() == "GameForge Games View"

        assert view.findChild(object, "gamesTitle") is not None
        assert view.findChild(object, "gamesSearchInput") is not None
        assert view.findChild(object, "gamesFilterCombo") is not None
        assert view.findChild(object, "gamesSortCombo") is not None
        assert view.findChild(object, "gamesBtnViewMode") is not None
        assert view.findChild(object, "gamesBtnRefresh") is not None
        assert view.findChild(QListView, "gamesListView") is not None
    finally:
        view.deleteLater()


def test_games_list_model_filter_and_sort(qapp, tmp_path):
    """Verify filtering by query/status and sorting by date/name."""
    model = GamesListModel()
    games = [
        GameSummary(
            name="Platformer",
            title="Sky Hop",
            genre="platformer",
            pitch="Jump on clouds",
            project_dir=tmp_path / "Platformer",
            updated_at=100.0,
            last_run_status="DONE",
        ),
        GameSummary(
            name="ArenaCombat",
            title="Gladiator Arena",
            genre="combat",
            pitch="Fight beasts",
            project_dir=tmp_path / "ArenaCombat",
            updated_at=200.0,
            last_run_status="FAILED",
        ),
        GameSummary(
            name="CardBattler",
            title="Deck Master",
            genre="card",
            pitch="Play magic cards",
            project_dir=tmp_path / "CardBattler",
            updated_at=150.0,
            last_run_status=None,
        ),
    ]

    model.set_games(games)
    # Default: sorted by updated_at descending
    assert model.rowCount() == 3
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Gladiator Arena"
    assert model.data(model.index(1, 0), Qt.DisplayRole) == "Deck Master"
    assert model.data(model.index(2, 0), Qt.DisplayRole) == "Sky Hop"

    # Sort by name
    model.set_sort_mode("name")
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Deck Master"
    assert model.data(model.index(1, 0), Qt.DisplayRole) == "Gladiator Arena"
    assert model.data(model.index(2, 0), Qt.DisplayRole) == "Sky Hop"

    # Filter by query
    model.set_search_query("clouds")
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Sky Hop"

    # Clear query, filter by status
    model.set_search_query("")
    model.set_status_filter("pass")
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Sky Hop"

    model.set_status_filter("fail")
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Gladiator Arena"

    model.set_status_filter("unbuilt")
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Deck Master"


def test_games_view_toggle_mode_and_signals(qapp, tmp_path):
    """Verify Grid/List toggle and double-click signal emission."""
    view = GamesView()
    try:
        # Toggle mode
        assert view._list_view.viewMode() == QListView.IconMode
        view._btn_mode.click()
        assert view._list_view.viewMode() == QListView.ListMode
        assert view._btn_mode.text() == "List"
        view._btn_mode.click()
        assert view._list_view.viewMode() == QListView.IconMode
        assert view._btn_mode.text() == "Grid"

        # Double click emits openGameRequested
        game = GameSummary(
            name="TestGame",
            title="Test Game",
            genre="action",
            pitch="Test",
            project_dir=tmp_path / "TestGame",
        )
        view._model.set_games([game])

        opened = []
        view.openGameRequested.connect(lambda n: opened.append(n))

        idx = view._model.index(0, 0)
        view._on_item_double_clicked(idx)
        assert opened == ["TestGame"]
    finally:
        view.deleteLater()


def test_delete_game_dialog_safety(qapp, tmp_path):
    """Verify delete dialog requires exact typed name before enabling delete button."""
    game = GameSummary(
        name="AlphaStrike",
        title="Alpha Strike",
        genre="action",
        pitch="Strike first",
        project_dir=tmp_path / "AlphaStrike",
    )
    dlg = DeleteGameDialog(game)
    try:
        assert dlg._btn_delete.isEnabled() is False

        # Incomplete / wrong name
        dlg._confirm_input.setText("alpha")
        assert dlg._btn_delete.isEnabled() is False

        dlg._confirm_input.setText("AlphaStrike ")
        # trimmed matching enables it
        assert dlg._btn_delete.isEnabled() is True

        dlg._confirm_input.setText("AlphaStrike")
        assert dlg._btn_delete.isEnabled() is True
    finally:
        dlg.deleteLater()


def test_no_hardcoded_hex_colors_in_games_view():
    """Verify normative rule: colours come only from tokens; zero hex literals."""
    path = Path("src/gameforge_ide/desktop/views/games_view.py")
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    content = path.read_text(encoding="utf-8")
    matches = hex_pattern.findall(content)
    assert matches == [], f"Found hardcoded hex literals in games_view.py: {matches}"
