"""Rail: 56px Studio UX activity rail with vector icons (WI-4.3)."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..styles import tokens

RAIL_ITEMS = [
    ("home", "Home", "Ctrl+1"),
    ("games", "Games", "Ctrl+2"),
    ("design", "Design", "Ctrl+3"),
    ("build", "Build", "Ctrl+4"),
    ("play", "Play", "Ctrl+5"),
    ("evidence", "Evidence", "Ctrl+6"),
    ("assets", "Assets", "Ctrl+7"),
    ("separator", "", ""),
    ("code", "Code", "Ctrl+8"),
    ("settings", "Settings", "Ctrl+,"),
]


class RailButton(QToolButton):
    """Custom rail button with 3px left indicator when active/checked."""

    def __init__(self, view_id: str, label: str, shortcut: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.label = label
        self.shortcut_text = shortcut
        self.setObjectName(f"railButton_{view_id}")
        self.setAccessibleName(f"{label} ({shortcut})" if shortcut else label)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedSize(56, 48)
        self.setIconSize(QSize(22, 22))
        self.setIcon(icon(view_id, role="secondary", size=22))
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(f"{label} ({shortcut})" if shortcut else label)

        self.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                padding: 0px;
                margin: 0px;
            }}
            QToolButton:hover {{
                background: {tokens.BG_HOVER};
            }}
            QToolButton:checked {{
                background: {tokens.BG_ACTIVE};
                border-left: 3px solid {tokens.ACCENT_PRIMARY};
            }}
            QToolButton:disabled {{
                opacity: 0.35;
            }}
        """)


class Rail(QWidget):
    """Vertical activity rail with navigation tool buttons."""

    viewRequested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("studioRail")
        self.setFixedWidth(56)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self._buttons: Dict[str, RailButton] = {}

        for item in RAIL_ITEMS:
            view_id, label, shortcut = item
            if view_id == "separator":
                sep = QFrame(self)
                sep.setFrameShape(QFrame.HLine)
                sep.setFrameShadow(QFrame.Plain)
                sep.setFixedWidth(36)
                sep.setStyleSheet(f"background-color: {tokens.BORDER}; border: none; max-height: 1px;")
                layout.addWidget(sep, alignment=Qt.AlignCenter)
                continue

            btn = RailButton(view_id, label, shortcut, self)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.viewRequested.emit(vid))
            layout.addWidget(btn)
            self._buttons[view_id] = btn

        layout.addStretch(1)

        self.setStyleSheet(f"""
            QWidget#studioRail {{
                background: {tokens.BG_ROOT};
                border-right: 1px solid {tokens.BORDER};
            }}
        """)

    def set_active_view(self, view_id: str) -> None:
        """Mark the corresponding rail button checked without triggering signals."""
        btn = self._buttons.get(view_id)
        if btn is not None:
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)

    def update_enabled_states(self, guard_lookup: Callable[[str], Tuple[bool, str]]) -> None:
        """Update enable state and tooltip reason for each rail button."""
        for vid, btn in self._buttons.items():
            enabled, reason = guard_lookup(vid)
            btn.setEnabled(enabled)
            base_tip = f"{btn.label} ({btn.shortcut_text})" if btn.shortcut_text else btn.label
            if not enabled and reason:
                btn.setToolTip(f"{base_tip}\n({reason})")
            else:
                btn.setToolTip(base_tip)

    def button(self, view_id: str) -> Optional[RailButton]:
        return self._buttons.get(view_id)
