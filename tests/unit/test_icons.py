"""Unit tests for the icon system (WI-4.1)."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.icons import (
    ICON_DIR,
    ROLE_COLOURS,
    clear_icon_cache,
    icon,
    _pixmap,
)

EXPECTED_ICONS = [
    "home",
    "games",
    "design",
    "build",
    "play",
    "evidence",
    "assets",
    "code",
    "settings",
    "assistant",
    "cancel",
    "resume",
    "rollback",
    "check",
    "warning",
    "search",
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QGuiApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_all_icon_files_exist():
    for name in EXPECTED_ICONS:
        svg_file = ICON_DIR / f"{name}.svg"
        assert svg_file.is_file(), f"Missing icon SVG: {svg_file}"
        content = svg_file.read_text(encoding="utf-8")
        assert "<svg" in content and "</svg>" in content
        assert "currentColor" in content


def test_icons_render_nonzero_pixels(qapp):
    clear_icon_cache()
    for name in EXPECTED_ICONS:
        pm = _pixmap(name, "#f5f3ff", 24, 1.0)
        assert not pm.isNull(), f"Pixmap is null for {name}"
        img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
        non_transparent = 0
        for y in range(img.height()):
            for x in range(img.width()):
                if QColor(img.pixel(x, y)).alpha() > 0:
                    non_transparent += 1
        assert non_transparent > 0, f"Icon {name} rendered 0 visible pixels"
        if name == "home":
            # Handover reference mentions ~638 non-transparent pixels for home
            assert non_transparent > 100, f"Home icon rendered unexpectedly few pixels: {non_transparent}"


def test_icon_qicon_generation(qapp):
    for name in EXPECTED_ICONS:
        ic = icon(name, role="primary", size=20)
        assert isinstance(ic, QIcon)
        assert not ic.isNull()

        # Check normal off pixmap
        pm = ic.pixmap(QSize(20, 20), QIcon.Normal, QIcon.Off)
        assert not pm.isNull()

        # Check normal on pixmap (accent)
        pm_on = ic.pixmap(QSize(20, 20), QIcon.Normal, QIcon.On)
        assert not pm_on.isNull()

        # Check disabled pixmap
        pm_dis = ic.pixmap(QSize(20, 20), QIcon.Disabled, QIcon.Off)
        assert not pm_dis.isNull()


def test_cache_clear(qapp):
    _pixmap("home", "#f5f3ff", 20, 1.0)
    info_before = _pixmap.cache_info()
    assert info_before.currsize > 0
    clear_icon_cache()
    info_after = _pixmap.cache_info()
    assert info_after.currsize == 0

def test_missing_icon_glyph_fallback(qapp):
    """Verify FileNotFoundError invokes _fallback_icon and renders a non-empty QIcon (Section 5C.7)."""
    clear_icon_cache()
    ic_missing = icon("nonexistent_test_action_xyz", role="primary", size=24)
    assert isinstance(ic_missing, QIcon)
    assert not ic_missing.isNull()
    pm = ic_missing.pixmap(QSize(24, 24))
    assert not pm.isNull()
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    non_transparent = 0
    for y in range(img.height()):
        for x in range(img.width()):
            if QColor(img.pixel(x, y)).alpha() > 0:
                non_transparent += 1
    assert non_transparent > 0, "Fallback glyph rendered 0 visible pixels"

