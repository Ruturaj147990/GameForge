"""Token-coloured SVG icons (no third-party packs). icon("play", role="primary") -> QIcon."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .styles import tokens
from .styles.dark_theme import theme_color

ICON_DIR = Path(__file__).parent / "assets" / "icons"

ROLE_COLOURS: Dict[str, str] = {
    "primary": tokens.TEXT_PRIMARY,
    "secondary": tokens.TEXT_SECONDARY,
    "accent": tokens.ACCENT_HOVER,
    "success": tokens.ACCENT_SUCCESS,
    "warning": tokens.ACCENT_WARNING,
    "error": tokens.ACCENT_ERROR,
}


@lru_cache(maxsize=256)
def _pixmap(name: str, colour: str, size: int, dpr: float) -> QPixmap:
    svg_path = ICON_DIR / f"{name}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(f"Icon not found: {name}.svg at {svg_path}")
    svg = svg_path.read_text(encoding="utf-8").replace("currentColor", colour)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def clear_icon_cache() -> None:
    """Clear the cached rendered pixmaps on theme change."""
    _pixmap.cache_clear()


def icon(name: str, role: str = "secondary", size: int = 20) -> QIcon:
    """Return a styled QIcon with active theme tokens."""
    screen = QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    ic = QIcon()

    base_color = ROLE_COLOURS.get(role, tokens.TEXT_SECONDARY)
    normal_color = theme_color(base_color)
    accent_color = theme_color(ROLE_COLOURS["accent"])
    disabled_color = theme_color(tokens.TEXT_SECONDARY)

    ic.addPixmap(_pixmap(name, normal_color, size, dpr), QIcon.Normal, QIcon.Off)
    ic.addPixmap(_pixmap(name, accent_color, size, dpr), QIcon.Normal, QIcon.On)
    ic.addPixmap(_pixmap(name, disabled_color, size, dpr), QIcon.Disabled, QIcon.Off)
    return ic
