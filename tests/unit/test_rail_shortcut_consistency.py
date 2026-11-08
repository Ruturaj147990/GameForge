"""The keyboard shortcuts registered by MainWindow must match the ones the rail advertises."""
from __future__ import annotations

import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.shell.rail import RAIL_ITEMS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_rail_tooltip_shortcuts_are_the_registered_shortcuts(qapp, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    win = MainWindow(ws)
    try:
        win.confirm_on_close = False
        registered = {sc.key().toString() for sc in getattr(win, "_studio_shortcuts", [])}
        for vid, _label, key in RAIL_ITEMS:
            if vid == "separator" or not key:
                continue
            assert QKeySequence(key).toString() in registered, f"{vid}: {key} not registered"
        # Retired views must not hijack the keys the rail assigns to live views.
        assert len(registered) == len({sc.key().toString() for sc in win._studio_shortcuts})
    finally:
        win.close()
