"""GameForge IDE — Desktop Theme Module.

Unified theme access and switching for Studio UX components.
Exposes style tokens, theme stylesheets, and theme application helpers.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QApplication

from .styles.dark_theme import (
    GAMEFORGE_DARK_QSS,
    GAMEFORGE_LIGHT_QSS,
    apply_theme as _apply_theme_internal,
    get_theme_display_name,
    normalize_theme_name,
    theme_color,
    theme_stylesheet,
)
from .icons import clear_icon_cache


def apply_theme(app: Optional[QApplication] = None, theme: str = "dark") -> str:
    """Apply a studio theme (dark or light) and update active widget styles."""
    target_app = app or QApplication.instance()
    if target_app is None:
        return normalize_theme_name(theme)
    result = _apply_theme_internal(target_app, theme)
    clear_icon_cache()
    return result


def toggle_theme(app: Optional[QApplication] = None) -> str:
    """Toggle between dark and light themes."""
    target_app = app or QApplication.instance()
    current = current_theme(target_app)
    new_theme = "light" if current == "dark" else "dark"
    return apply_theme(target_app, new_theme)


def current_theme(app: Optional[QApplication] = None) -> str:
    """Return the currently active theme name ('dark' or 'light')."""
    target_app = app or QApplication.instance()
    if target_app is None:
        return "dark"
    theme = target_app.property("gameforgeTheme")
    return str(theme) if theme else "dark"


def is_dark_theme(app: Optional[QApplication] = None) -> bool:
    """Return True if active theme is dark."""
    return current_theme(app) != "light"


def is_light_theme(app: Optional[QApplication] = None) -> bool:
    """Return True if active theme is light."""
    return current_theme(app) == "light"


def clear_theme_caches() -> None:
    """Clear icon pixmap and theme-related caches."""
    clear_icon_cache()


__all__ = [
    "GAMEFORGE_DARK_QSS",
    "GAMEFORGE_LIGHT_QSS",
    "apply_theme",
    "clear_theme_caches",
    "current_theme",
    "get_theme_display_name",
    "is_dark_theme",
    "is_light_theme",
    "normalize_theme_name",
    "theme_color",
    "theme_stylesheet",
    "toggle_theme",
]
