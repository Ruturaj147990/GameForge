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
   GameForge IDE — Midnight Purple Dark Theme
   Dominant: Black / Deep Void (#08070d, #0d0b14, #120f1d)
   Accents: Refined dark purple (#7c3aed, #8b5cf6, #231c34) used sparingly
   Palette:
     bg-root:       #08070d    deep black app background
     bg-panel:      #0d0b14    midnight dock panel background
     bg-surface:    #120f1d    cards, bubbles, text fields
     bg-hover:      #1a1528    hover states
     bg-active:     #251d38    active/pressed states
     border:        #231c34    subtle purple-tinted borders
     border-focus:  #8b5cf6    focus outline
     text-primary:  #f5f3ff    primary high-contrast crisp text (ratio > 14:1)
     text-secondary:#9d95b0    readable secondary labels & muted info
     text-muted:    #675f78    subtle hints & timestamps
     accent-pri:    #7c3aed    refined midnight purple (buttons, selection, branding)
     accent-hover:  #8b5cf6    vibrant purple hover
     accent-succ:   #00d9a3    teal (assistant role, ready state, UE detected)
     accent-warn:   #f59e0b    amber (tool invocations, busy states)
     accent-err:    #ef4444    coral red (error role, failure indicators)
     legacy-ref:    #0c0e14    compat token
──────────────────────────────────────────────────────────────────*/

/* ── Global window & container defaults ── */
QMainWindow, QDialog {
    background-color: #08070d;
    color: #f5f3ff;
}

/* Base font and text color without overriding child widget transparency */
QWidget {
    color: #f5f3ff;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* ── Dock widgets ── */
QDockWidget {
    background-color: #0d0b14;
    border: 1px solid #231c34;
}

QDockWidget > QWidget {
    background-color: #0d0b14;
}

QDockWidget::title {
    background: #090810;
    padding: 7px 12px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #9d95b0;
    border-bottom: 1px solid #231c34;
}

QDockWidget::close-button, QDockWidget::float-button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 0px;
    image: none;
    subcontrol-position: top right;
    subcontrol-origin: margin;
    position: absolute;
    top: 5px;
    width: 14px;
    height: 14px;
    max-width: 14px;
    max-height: 14px;
}

QDockWidget::close-button {
    right: 6px;
    image: none;
}

QDockWidget::float-button {
    right: 22px;
    image: none;
}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {
    background: #1a1528;
    border-color: #3d2f59;
    border-radius: 3px;
}

QDockWidget::close-button:pressed, QDockWidget::float-button:pressed {
    background: #251d38;
}

/* ── Splitters ── */
QSplitter::handle {
    background: #181326;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

/* ── Menu bar ── */
QMenuBar {
    background-color: #08070d;
    border-bottom: 1px solid #231c34;
    padding: 4px 8px;
    font-size: 13px;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 8px;
    border-radius: 6px;
    color: #f5f3ff;
}

QMenuBar::item:selected {
    background: #120f1d;
    color: #a78bfa;
}

QMenu {
    background-color: #0d0b14;
    border: 1px solid #231c34;
    padding: 6px;
    border-radius: 6px;
}

QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 6px;
    color: #f5f3ff;
    font-size: 13px;
}

QMenu::item:selected {
    background-color: #1a1528;
    color: #a78bfa;
}

QMenu::separator {
    height: 1px;
    background: #231c34;
    margin: 4px 8px;
}

/* ── Status bar ── */
QStatusBar {
    background-color: #08070d;
    border-top: 1px solid #231c34;
    color: #9d95b0;
    font-size: 11px;
    padding: 4px 8px;
}

QStatusBar::item {
    border: none;
}

/* ── Toolbar ── */
QToolBar {
    background-color: #0d0b14;
    border-bottom: 1px solid #231c34;
    padding: 4px 8px;
    spacing: 6px;
}

QToolBar::separator {
    width: 1px;
    background: #231c34;
    margin: 4px 6px;
    border: none;
}

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    padding: 4px 8px;
    border-radius: 6px;
    color: #f5f3ff;
    font-size: 13px;
    font-weight: 500;
}

QToolButton:hover {
    background: #120f1d;
    border-color: #7c3aed;
    color: #a78bfa;
}

QToolButton:pressed {
    background: #1a1528;
}

/* ── Left Activity Rail ── */
QToolBar#activity_rail {
    background-color: #090810;
    border-right: 1px solid #231c34;
    border-top: none;
    border-bottom: none;
    border-left: none;
    padding: 6px 0px;
    spacing: 6px;
    min-width: 48px;
    max-width: 48px;
}

QToolBar#activity_rail QToolButton {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    padding: 10px 4px;
    color: #9d95b0;
    font-size: 16px;
    min-width: 40px;
    max-width: 40px;
}

QToolBar#activity_rail QToolButton:hover {
    color: #f5f3ff;
    background: #141022;
    border-color: transparent;
}

QToolBar#activity_rail QToolButton:checked,
QToolBar#activity_rail QToolButton[active="true"] {
    color: #a78bfa;
    border-left: 3px solid #7c3aed;
    background: #141022;
}

/* ── Standard Push Buttons ── */
QPushButton {
    background-color: #120f1d;
    border: 1px solid #2a223d;
    border-radius: 6px;
    padding: 6px 14px;
    color: #f5f3ff;
    font-size: 13px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1a1528;
    border-color: #7c3aed;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #0d0a17;
}

QPushButton:disabled {
    background-color: #0b0912;
    border-color: #1a1524;
    color: #524b61;
}

/* Styled Action Buttons */
QPushButton#btn_send {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c3aed, stop:1 #6d28d9);
    border: 1px solid #8b5cf6;
    border-radius: 6px;
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    min-width: 84px;
    min-height: 28px;
}

QPushButton#btn_send:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #8b5cf6, stop:1 #7c3aed);
    border-color: #c4b5fd;
}

QPushButton#btn_send:disabled {
    background: #120f1d;
    border-color: #231c34;
    color: #524b61;
}

QPushButton#btn_stop {
    background-color: #17111c;
    border: 1px solid #33243a;
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
    background-color: #0b0912;
    border-color: #1a1524;
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
    background-color: #0f0c1a;
    border: 1px solid #231c34;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f5f3ff;
    selection-background-color: #7c3aed;
    selection-color: #ffffff;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #8b5cf6;
    background-color: #120f1d;
}

/* ── Combo box ── */
QComboBox {
    background-color: #120f1d;
    border: 1px solid #231c34;
    border-radius: 6px;
    padding: 4px 28px 4px 12px;
    color: #f5f3ff;
    min-width: 140px;
    font-size: 13px;
}

QComboBox:hover {
    border-color: #7c3aed;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #0d0b14;
    border: 1px solid #231c34;
    selection-background-color: #1a1528;
    selection-color: #a78bfa;
    padding: 4px;
    color: #f5f3ff;
}

/* ── Scroll bars ── */
QScrollBar:vertical {
    background: #090810;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #231c34;
    min-height: 28px;
    border-radius: 5px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #7c3aed;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #090810;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #231c34;
    min-width: 28px;
    border-radius: 5px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background: #7c3aed;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── Tree / List views ── */
QTreeView, QListView, QListWidget {
    background-color: #0d0b14;
    border: none;
    alternate-background-color: #090810;
    show-decoration-selected: 1;
    color: #f5f3ff;
    font-size: 13px;
}

QTreeView::item, QListView::item {
    padding: 5px 8px;
    border-radius: 4px;
}

QTreeView::item:hover, QListView::item:hover {
    background-color: #120f1d;
}

QTreeView::item:selected, QListView::item:selected {
    background-color: #1a1528;
    color: #a78bfa;
}

QTreeView::branch {
    background-color: #0d0b14;
}

/* ── Table view ── */
QTableWidget {
    background-color: #0d0b14;
    border: none;
    gridline-color: #231c34;
    alternate-background-color: #090810;
    color: #f5f3ff;
}

QHeaderView::section {
    background-color: #08070d;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid #231c34;
    font-size: 11px;
    font-weight: 700;
    color: #9d95b0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Tab widget ── */
QTabWidget::pane {
    border: 1px solid #231c34;
    background-color: #0d0b14;
}

QTabBar::tab {
    background-color: #08070d;
    border: 1px solid #231c34;
    padding: 6px 16px;
    margin-right: 2px;
    color: #9d95b0;
    border-radius: 6px 6px 0 0;
    font-size: 11px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #0d0b14;
    color: #a78bfa;
    border-bottom-color: #0d0b14;
}

QTabBar::tab:hover {
    color: #f5f3ff;
    background-color: #120f1d;
}

/* ── Left Sidebar Internal Tab Bar ── */
QTabBar#sidebar_tabbar {
    background: #090810;
    border-bottom: 1px solid #231c34;
}

QTabBar#sidebar_tabbar::tab {
    background-color: #090810;
    border: 1px solid #231c34;
    border-bottom: none;
    padding: 6px 12px;
    margin-right: 2px;
    color: #9d95b0;
    border-radius: 6px 6px 0 0;
    font-size: 11px;
    font-weight: 600;
}

QTabBar#sidebar_tabbar::tab:selected {
    background-color: #120f1d;
    color: #a78bfa;
    border-bottom: 2px solid #7c3aed;
}

QTabBar#sidebar_tabbar::tab:hover {
    color: #f5f3ff;
    background-color: #141022;
}

/* ── Start Screen ── */
QWidget#start_screen {
    background-color: #08070d;
}

QFrame#start_action_card {
    background-color: #120f1d;
    border: 1px solid #231c34;
    border-radius: 6px;
    padding: 16px;
}

QFrame#start_action_card:hover {
    background-color: #1a1528;
    border-color: #7c3aed;
}

QLabel#start_hero_title {
    color: #f5f3ff;
    font-size: 18px;
    font-weight: 800;
}

QLabel#start_hero_subtitle {
    color: #9d95b0;
    font-size: 13px;
}

QLabel#start_card_title {
    color: #f5f3ff;
    font-size: 14px;
    font-weight: 700;
}

QLabel#start_card_desc {
    color: #9d95b0;
    font-size: 11px;
}

QPushButton#start_card_btn {
    background-color: #231c34;
    border: 1px solid #3d2f59;
    border-radius: 6px;
    padding: 8px 16px;
    color: #f5f3ff;
    font-weight: 600;
    font-size: 13px;
}

QPushButton#start_card_btn:hover {
    background-color: #7c3aed;
    border-color: #8b5cf6;
    color: #ffffff;
}


/* ── Panel Common Sections & Utility Tokens ── */
QWidget#panel_header {
    background-color: #0d0b14;
    border-bottom: 1px solid #231c34;
}

QWidget#panel_section {
    background-color: #120f1d;
    border-bottom: 1px solid #231c34;
}

QWidget#panel_action_bar {
    background-color: #0d0b14;
    border-top: 1px solid #231c34;
}

/* ── Progress bar ── */
QProgressBar {
    background-color: #120f1d;
    border: 1px solid #231c34;
    border-radius: 4px;
    text-align: center;
    color: #f5f3ff;
    height: 10px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c3aed, stop:1 #00d9a3);
    border-radius: 4px;
}

/* ── Tooltip ── */
QToolTip {
    background-color: #120f1d;
    color: #f5f3ff;
    border: 1px solid #7c3aed;
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 11px;
}
"""


_DARK_TO_LIGHT = {
    # Midnight Purple Dark -> Glossy Purple Light (Dominant Crisp White, subtle glossy purple borders/accents)
    "#08070d": "#faf9fe", "#7c3aed": "#5b21b6", "#8b5cf6": "#6d28d9", "#6d28d9": "#4c1d95", "#141022": "#ede8f7", "#0d0b14": "#ffffff", "#120f1d": "#f5f3fa",
    "#1a1528": "#ede9f7", "#251d38": "#e4dcf4", "#231c34": "#e2daf0",
    "#090810": "#f8f6fc", "#0f0c1a": "#ffffff", "#181326": "#e0d7ee",
    "#2a223d": "#dcd0f0", "#17111c": "#f5f0f8", "#33243a": "#e3d2ea",
    "#0b0912": "#f3effa", "#1a1524": "#e4ddf0", "#3d2f59": "#cfbee6",
    "#524b61": "#857b9c", "#9d95b0": "#5e5473", "#675f78": "#786e8e",
    "#f5f3ff": "#181226", "#a78bfa": "#5b21b6", "#c4b5fd": "#3b0764",

    # Preserved backward-compatible tokens from prior Studio Dark for inline styles & test assertions
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
    "#6c63ff": "#5b21b6",

    # Status / diff colors
    "#00d9a3": "#047857", "#ff6b6b": "#c2413a", "#ef4444": "#b91c1c",
    "#f59e0b": "#a16207", "#f87171": "#a12a22", "#ff9f43": "#9a4d00",
    "#059669": "#065f46", "#10b981": "#0f766e", "#34d399": "#15803d",
    "#dc2626": "#991b1b", "#fbbf24": "#8a5a00",

    # Additional panel & toolbar inline styles
    "#262f45": "#cbd5e1", "#182030": "#ede8f7", "#28354f": "#d8cee8",
    "#232e46": "#dfd5f0", "#e2e8f0": "#1f182c", "#0e2922": "#e2f7f0",
    "#161c28": "#ede8f5",
}
_LIGHT_TO_DARK = {light: dark for dark, light in _DARK_TO_LIGHT.items()}
GAMEFORGE_LIGHT_QSS = GAMEFORGE_DARK_QSS
for _dark_color, _light_color in _DARK_TO_LIGHT.items():
    GAMEFORGE_LIGHT_QSS = GAMEFORGE_LIGHT_QSS.replace(_dark_color, _light_color)


def normalize_theme_name(theme: str) -> str:
    """Normalize user-facing or internal theme identifiers to 'dark' or 'light'."""
    t = str(theme).strip().lower()
    if t in ("light", "glossy", "glossy_purple_light", "glossy_light", "glossy purple light"):
        return "light"
    return "dark"


def get_theme_display_name(theme: str) -> str:
    """Return the official user-facing display name for a theme."""
    norm = normalize_theme_name(theme)
    return "Glossy Purple Light" if norm == "light" else "Midnight Purple Dark"


def apply_theme(app, theme: str = "dark") -> str:  # type: ignore[type-arg]
    """Apply a studio palette and convert existing inline widget styles."""
    theme = normalize_theme_name(theme)
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

