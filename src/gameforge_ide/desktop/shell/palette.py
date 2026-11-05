"""CommandPalette: Modal command palette dialog for Studio UX (WI-4.3)."""

from __future__ import annotations

import logging
import re
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens

logger = logging.getLogger(__name__)


class CommandPalette(QDialog):
    """Fuzzy-searchable command palette dialog."""

    def __init__(
        self,
        commands: List[Tuple[str, Callable[[], None]]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("command_palette_dialog")
        self.setWindowTitle("GameForge Commands")
        self.setModal(True)
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.search = QLineEdit(self)
        self.search.setObjectName("command_palette_search")
        self.search.setPlaceholderText("Type a command… (e.g. View: Design, Theme, Cancel)")
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER_FOCUS};
                border-radius: {tokens.RADIUS}px;
                padding: 6px 10px;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.search)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("command_palette_commands")
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background: {tokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background: {tokens.ACCENT_PRIMARY};
                color: {tokens.TEXT_PRIMARY};
            }}
        """)
        layout.addWidget(self.list_widget)

        for label, callback in commands:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, callback)
            self.list_widget.addItem(item)

        self.search.textChanged.connect(self._filter_commands)
        self.list_widget.itemActivated.connect(self._execute_item)
        self.search.installEventFilter(self)

        self._filter_commands("")
        self.search.setFocus()

    def _filter_commands(self, query: str) -> None:
        q = query.strip().casefold()
        first_visible = -1
        tokens_list = q.split()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            target = item.text().casefold()
            if not q:
                visible = True
            elif q in target:
                visible = True
            elif all(t in target for t in tokens_list):
                visible = True
            else:
                # Acronym matching e.g. "vd" for "View: Design"
                words = [w for w in re.split(r"[\s:_\-]+", target) if w]
                acronym = "".join(w[0] for w in words)
                q_compact = "".join(tokens_list)
                if q_compact in acronym:
                    visible = True
                else:
                    # Subsequence matching
                    t_idx = 0
                    matched = True
                    for ch in q_compact:
                        t_idx = target.find(ch, t_idx)
                        if t_idx == -1:
                            matched = False
                            break
                        t_idx += 1
                    visible = matched
            item.setHidden(not visible)
            if visible and first_visible < 0:
                first_visible = index
        self.list_widget.setCurrentRow(first_visible)

    def _execute_item(self, item: QListWidgetItem) -> None:
        callback = item.data(Qt.UserRole)
        self.accept()
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                logger.exception("Error executing command '%s': %s", item.text(), exc)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched == self.search and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Down, Qt.Key_Up):
                visible_rows = [
                    i for i in range(self.list_widget.count()) if not self.list_widget.item(i).isHidden()
                ]
                if visible_rows:
                    current = self.list_widget.currentRow()
                    if current in visible_rows:
                        position = visible_rows.index(current)
                        step = 1 if event.key() == Qt.Key_Down else -1
                        new_pos = (position + step) % len(visible_rows)
                    else:
                        new_pos = 0 if event.key() == Qt.Key_Down else len(visible_rows) - 1
                    self.list_widget.setCurrentRow(visible_rows[new_pos])
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                item = self.list_widget.currentItem()
                if item and not item.isHidden():
                    self._execute_item(item)
                return True
        return super().eventFilter(watched, event)
