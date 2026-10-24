"""GameForge IDE — Premium High-Contrast Dark Theme Stylesheet.

Engineered specifically for Windows 11 desktop IDE environments.
Ensures maximum text legibility, balanced contrast hierarchy, and robust DPI scaling.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit

GAMEFORGE_DARK_QSS = """
/* ────────────────────────────────────────────────────────────────
   GameForge IDE — Studio Dark Theme
   Palette:
     bg-root:       #0c0e14    app background
     bg-panel:      #121622    dock panel background
     bg-surface:    #181f30    cards, bubbles, text fields
     bg-hover:      #222a42    hover states
     bg-active:     #2b3553    active/pressed states
     border:        #26304a    panel & container borders
     border-focus:  #6366f1    focus outline
     text-primary:  #f3f4f8    primary high-contrast text (contrast ratio > 12:1)
     text-secondary:#9ca3af    readable secondary labels & muted info
     text-muted:    #6b7280    subtle hints & timestamps
     accent-pri:    #6366f1    vibrant indigo (buttons, selection, branding)
     accent-succ:   #00d9a3    teal (assistant role, ready state, UE detected)
     accent-warn:   #f59e0b    amber (tool invocations, busy states)
     accent-err:    #ef4444    coral red (error role, failure indicators)
──────────────────────────────────────────────────────────────────*/

/* ── Global window & container defaults ── */
QMainWindow, QDialog {
    background-color: #0c0e14;
    color: #f3f4f8;
}

/* Base font and text color without overriding child widget transparency */
QWidget {
    color: #f3f4f8;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* ── Dock widgets ── */
QDockWidget {
    background-color: #121622;
    border: 1px solid #26304a;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}

QDockWidget > QWidget {
    background-color: #121622;
}

QDockWidget::title {
    background: #0f131d;
    padding: 7px 12px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #9ca3af;
    border-bottom: 1px solid #26304a;
}

QDockWidget::close-button, QDockWidget::float-button {
    background: transparent;
    border: none;
    padding: 2px;
}

/* ── Splitters ── */
QSplitter::handle {
    background: #1f273d;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

/* ── Menu bar ── */
QMenuBar {
    background-color: #0c0e14;
    border-bottom: 1px solid #26304a;
    padding: 2px 6px;
    font-size: 12px;
}

QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
    color: #f3f4f8;
}

QMenuBar::item:selected {
    background: #181f30;
    color: #7c75ff;
}

QMenu {
    background-color: #121622;
    border: 1px solid #26304a;
    padding: 6px;
    border-radius: 6px;
}

QMenu::item {
    padding: 6px 26px 6px 12px;
    border-radius: 4px;
    color: #f3f4f8;
    font-size: 12px;
}

QMenu::item:selected {
    background-color: #222a42;
    color: #7c75ff;
}

QMenu::separator {
    height: 1px;
    background: #26304a;
    margin: 4px 8px;
}

/* ── Status bar ── */
QStatusBar {
    background-color: #0c0e14;
    border-top: 1px solid #26304a;
    color: #9ca3af;
    font-size: 12px;
    padding: 2px 8px;
}

/* ── Toolbar ── */
QToolBar {
    background-color: #121622;
    border-bottom: 1px solid #26304a;
    padding: 4px 8px;
    spacing: 6px;
}

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    padding: 5px 10px;
    border-radius: 5px;
    color: #f3f4f8;
    font-size: 12px;
    font-weight: 500;
}

QToolButton:hover {
    background: #181f30;
    border-color: #6366f1;
    color: #7c75ff;
}

QToolButton:pressed {
    background: #222a42;
}

/* ── Standard Push Buttons ── */
QPushButton {
    background-color: #181f30;
    border: 1px solid #2d3752;
    border-radius: 6px;
    padding: 6px 14px;
    color: #f3f4f8;
    font-size: 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #222a42;
    border-color: #6366f1;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #141a29;
}

QPushButton:disabled {
    background-color: #111520;
    border-color: #1e2436;
    color: #555c70;
}

/* Styled Action Buttons */
QPushButton#btn_send {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366f1, stop:1 #4f46e5);
    border: 1px solid #7c75ff;
    border-radius: 6px;
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    min-width: 84px;
    min-height: 28px;
}

QPushButton#btn_send:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7579ff, stop:1 #5e56ee);
    border-color: #a5b4fc;
}

QPushButton#btn_send:disabled {
    background: #181f30;
    border-color: #26304a;
    color: #555c70;
}

QPushButton#btn_stop {
    background-color: #1e2333;
    border: 1px solid #374151;
    border-radius: 6px;
    color: #f87171;
    font-weight: 600;
    font-size: 13px;
    min-width: 84px;
    min-height: 28px;
}

QPushButton#btn_stop:hover {
    background-color: #3b1c22;
    border-color: #ef4444;
    color: #ffffff;
}

QPushButton#btn_stop:disabled {
    background-color: #111520;
    border-color: #1e2436;
    color: #4b5563;
}

QPushButton#btn_approve {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #059669, stop:1 #10b981);
    border: 1px solid #34d399;
    border-radius: 6px;
    color: #ffffff;
    font-weight: 700;
    padding: 7px 18px;
}

QPushButton#btn_approve:hover {
    background: #10b981;
}

QPushButton#btn_reject {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #dc2626, stop:1 #ef4444);
    border: 1px solid #f87171;
    border-radius: 6px;
    color: #ffffff;
    font-weight: 700;
    padding: 7px 18px;
}

QPushButton#btn_reject:hover {
    background: #ef4444;
}

/* ── Input controls ── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #141a29;
    border: 1px solid #26304a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f3f4f8;
    selection-background-color: #6366f1;
    selection-color: #ffffff;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #6366f1;
    background-color: #181f30;
}

/* ── Combo box ── */
QComboBox {
    background-color: #181f30;
    border: 1px solid #26304a;
    border-radius: 6px;
    padding: 5px 28px 5px 10px;
    color: #f3f4f8;
    min-width: 140px;
    font-size: 12px;
}

QComboBox:hover {
    border-color: #6366f1;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #121622;
    border: 1px solid #26304a;
    selection-background-color: #222a42;
    selection-color: #7c75ff;
    padding: 4px;
    color: #f3f4f8;
}

/* ── Scroll bars ── */
QScrollBar:vertical {
    background: #0f131d;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #26304a;
    min-height: 28px;
    border-radius: 5px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #6366f1;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #0f131d;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #26304a;
    min-width: 28px;
    border-radius: 5px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background: #6366f1;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── Tree / List views ── */
QTreeView, QListView, QListWidget {
    background-color: #121622;
    border: none;
    alternate-background-color: #0e121c;
    show-decoration-selected: 1;
    color: #f3f4f8;
    font-size: 13px;
}

QTreeView::item, QListView::item {
    padding: 5px 8px;
    border-radius: 4px;
}

QTreeView::item:hover, QListView::item:hover {
    background-color: #181f30;
}

QTreeView::item:selected, QListView::item:selected {
    background-color: #222a42;
    color: #7c75ff;
}

QTreeView::branch {
    background-color: #121622;
}

/* ── Table view ── */
QTableWidget {
    background-color: #121622;
    border: none;
    gridline-color: #26304a;
    alternate-background-color: #0e121c;
    color: #f3f4f8;
}

QHeaderView::section {
    background-color: #0c0e14;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid #26304a;
    font-size: 11px;
    font-weight: 700;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Tab widget ── */
QTabWidget::pane {
    border: 1px solid #26304a;
    background-color: #121622;
}

QTabBar::tab {
    background-color: #0c0e14;
    border: 1px solid #26304a;
    padding: 7px 18px;
    margin-right: 2px;
    color: #9ca3af;
    border-radius: 6px 6px 0 0;
    font-size: 12px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #121622;
    color: #7c75ff;
    border-bottom-color: #121622;
}

QTabBar::tab:hover {
    color: #f3f4f8;
    background-color: #181f30;
}

/* ── Progress bar ── */
QProgressBar {
    background-color: #181f30;
    border: 1px solid #26304a;
    border-radius: 4px;
    text-align: center;
    color: #f3f4f8;
    height: 10px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366f1, stop:1 #00d9a3);
    border-radius: 4px;
}

/* ── Tooltip ── */
QToolTip {
    background-color: #181f30;
    color: #f3f4f8;
    border: 1px solid #6366f1;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 12px;
}
"""


_DARK_TO_LIGHT = {
    "#0c0e14": "#f6f7fb", "#121622": "#fbfcfe", "#181f30": "#eff2f8",
    "#222a42": "#e1e7f1", "#2b3553": "#d4dced", "#26304a": "#cbd3e1",
    "#0f131d": "#f8f9fc", "#0e121c": "#f4f6fa", "#111520": "#e7ebf3",
    "#141a29": "#f7f8fb", "#1e2333": "#e9edf4", "#1e2436": "#dfe4ed",
    "#1f273d": "#c4ccd9", "#2d3752": "#b9c5d8", "#0b0e15": "#f1f3f8",
    "#111622": "#e9edf5", "#131b26": "#e5eaf2", "#161d2d": "#e0e6f0",
    "#1a1f2b": "#dce2ec", "#1a2236": "#d7dfec", "#1e263d": "#d1dae9",
    "#0d0f14": "#f2f4f8", "#0f1219": "#edf0f5", "#131720": "#e8ecf3",
    "#080a0f": "#e2e7ef", "#0a0c10": "#e6eaf1", "#001a11": "#e2f4ec",
    "#0d0a1f": "#eeeafd", "#1a0000": "#fbe9e8", "#28161a": "#f8e9ea",
    "#2a2f45": "#c5ccd8", "#374151": "#b8c2d1", "#3b1c22": "#f4dfe1",
    "#4b5563": "#788397", "#555c70": "#828da0",
    "#f3f4f8": "#1c2432", "#e8eaf6": "#273246", "#e6edf3": "#253247",
    "#c8d0e8": "#36445a", "#9ca3af": "#5b6575", "#8891aa": "#647085",
    "#6b7280": "#778194", "#64748b": "#6b778c", "#94a3b8": "#758197",
    "#818cf8": "#312e81", "#79c0ff": "#2456a6", "#a5b4fc": "#2e1065",
    "#6366f1": "#4c1d95", "#5e56ee": "#5b21b6", "#7579ff": "#4338ca",
    "#7c75ff": "#3730a3",
    "#00d9a3": "#047857", "#ff6b6b": "#c2413a", "#ef4444": "#b91c1c",
    "#f59e0b": "#a16207", "#f87171": "#a12a22", "#ff9f43": "#9a4d00",
    "#059669": "#065f46", "#10b981": "#0f766e", "#34d399": "#15803d",
    "#dc2626": "#991b1b", "#fbbf24": "#8a5a00",
}
_LIGHT_TO_DARK = {light: dark for dark, light in _DARK_TO_LIGHT.items()}
GAMEFORGE_LIGHT_QSS = GAMEFORGE_DARK_QSS
for _dark_color, _light_color in _DARK_TO_LIGHT.items():
    GAMEFORGE_LIGHT_QSS = GAMEFORGE_LIGHT_QSS.replace(_dark_color, _light_color)


def apply_theme(app, theme: str = "dark") -> str:  # type: ignore[type-arg]
    """Apply a studio palette and convert existing inline widget styles."""
    theme = "light" if str(theme).lower() == "light" else "dark"
    app.setStyle("Fusion")
    app.setStyleSheet(GAMEFORGE_LIGHT_QSS if theme == "light" else GAMEFORGE_DARK_QSS)
    app.setProperty("gameforgeTheme", theme)
    mapping = _DARK_TO_LIGHT if theme == "light" else _LIGHT_TO_DARK
    for widget in QApplication.allWidgets():
        previous = widget.property("gameforgeTheme") or "dark"
        if previous == theme:
            continue
        style = widget.styleSheet()
        for source, target in mapping.items():
            style = style.replace(source, target)
        if style != widget.styleSheet():
            widget.setStyleSheet(style)
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            document = widget.document()
            document_css = widget.property("gameforgeDocumentCss")
            if document_css:
                document.setDefaultStyleSheet(theme_stylesheet(document_css))
            fragments = []
            block = document.begin()
            while block.isValid():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    if fragment.isValid():
                        fragments.append((fragment.position(), fragment.length(), fragment.charFormat()))
                    iterator += 1
                block = block.next()
            for position, length, char_format in fragments:
                color_brush = char_format.foreground()
                background_brush = char_format.background()
                changed = False
                if color_brush.style() != Qt.NoBrush:
                    color = color_brush.color().name().lower()
                    if color in mapping:
                        char_format.setForeground(QColor(mapping[color]))
                        changed = True
                if background_brush.style() != Qt.NoBrush:
                    color = background_brush.color().name().lower()
                    if color in mapping:
                        char_format.setBackground(QColor(mapping[color]))
                        changed = True
                if changed:
                    cursor = QTextCursor(document)
                    cursor.setPosition(position)
                    cursor.setPosition(position + length, QTextCursor.KeepAnchor)
                    cursor.setCharFormat(char_format)
        widget.setProperty("gameforgeTheme", theme)
    return theme


def theme_color(dark_color: str) -> str:
    """Return the palette counterpart for a dark-theme color token."""
    if QApplication.instance() is not None and QApplication.instance().property("gameforgeTheme") == "light":
        return _DARK_TO_LIGHT.get(dark_color.lower(), dark_color)
    return dark_color


def theme_stylesheet(dark_stylesheet: str) -> str:
    """Convert a dark-palette inline stylesheet for the active app theme."""
    if QApplication.instance() is None or QApplication.instance().property("gameforgeTheme") != "light":
        return dark_stylesheet
    for source, target in _DARK_TO_LIGHT.items():
        dark_stylesheet = dark_stylesheet.replace(source, target)
    return dark_stylesheet
