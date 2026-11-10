"""CommandPalette: Modal command palette dialog for Studio UX (WI-4.3)."""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, QObject, Qt, Slot
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_stylesheet

logger = logging.getLogger(__name__)

_WORD_SPLIT_RE = re.compile(r"[\s:_\-/]+")
_SEARCH_META_ROLE = Qt.UserRole + 1


class CommandPalette(QDialog):
    """Fuzzy-searchable command palette dialog."""

    def __init__(
        self,
        commands: Sequence[Tuple[str, Callable[[], None]]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("command_palette_dialog")
        self.setWindowTitle("GameForge Commands")
        self.setAccessibleName("GameForge Command Palette")
        self.setModal(True)
        self.resize(560, 360)

        self.setStyleSheet(theme_stylesheet(f"""
            QDialog#command_palette_dialog {{
                background: {tokens.BG_PANEL};
                color: {tokens.TEXT_PRIMARY};
            }}
        """))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.search = QLineEdit(self)
        self.search.setObjectName("command_palette_search")
        self.search.setAccessibleName("Command search filter")
        self.search.setPlaceholderText("Type a command… (e.g. View: Design, Theme, Cancel)")
        self.search.setStyleSheet(theme_stylesheet(f"""
            QLineEdit {{
                background: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER_FOCUS};
                border-radius: {tokens.RADIUS}px;
                padding: 6px 10px;
                font-size: 13px;
            }}
        """))
        layout.addWidget(self.search)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("command_palette_commands")
        self.list_widget.setAccessibleName("Command palette results")
        self.list_widget.setStyleSheet(theme_stylesheet(f"""
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
                background: {tokens.BG_ACTIVE};
                color: {tokens.TEXT_PRIMARY};
                border-left: 3px solid {tokens.ACCENT_PRIMARY};
            }}
        """))
        layout.addWidget(self.list_widget)

        for label, callback in commands:
            label_str = str(label or "").strip()
            if not label_str:
                continue
            target = label_str.casefold()
            words = [w for w in _WORD_SPLIT_RE.split(target) if w]
            acronym = "".join(w[0] for w in words)
            item = QListWidgetItem(label_str)
            item.setData(Qt.UserRole, callback)
            item.setData(_SEARCH_META_ROLE, (target, acronym))
            self.list_widget.addItem(item)

        self.search.textChanged.connect(self._filter_commands)
        self.list_widget.itemActivated.connect(self._execute_item)
        self.search.installEventFilter(self)

        self._filter_commands("")
        self.search.setFocus()

    @Slot(str)
    def _filter_commands(self, query: str) -> None:
        q = (query or "").strip().casefold()
        first_visible = -1
        tokens_list = q.split()
        q_compact = "".join(tokens_list)
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item is None:
                continue
            meta = item.data(_SEARCH_META_ROLE)
            if isinstance(meta, tuple) and len(meta) == 2:
                target, acronym = meta
            else:
                target = item.text().casefold()
                words = [w for w in _WORD_SPLIT_RE.split(target) if w]
                acronym = "".join(w[0] for w in words)

            if not q:
                visible = True
            elif q in target:
                visible = True
            elif all(t in target for t in tokens_list):
                visible = True
            elif q_compact and q_compact in acronym:
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

    @Slot(QListWidgetItem)
    def _execute_item(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        callback = item.data(Qt.UserRole)
        label = item.text()
        self.accept()
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                logger.exception("Error executing command '%s': %s", label, exc)

    def eventFilter(self, watched: Optional[QObject], event: QEvent) -> bool:  # noqa: N802
        if watched is self.search and isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                visible_rows = []
                for i in range(self.list_widget.count()):
                    it = self.list_widget.item(i)
                    if it is not None and not it.isHidden():
                        visible_rows.append(i)
                if visible_rows:
                    current = self.list_widget.currentRow()
                    if current in visible_rows:
                        position = visible_rows.index(current)
                        step = 1 if key == Qt.Key_Down else -1
                        new_pos = (position + step) % len(visible_rows)
                    else:
                        new_pos = 0 if key == Qt.Key_Down else len(visible_rows) - 1
                    self.list_widget.setCurrentRow(visible_rows[new_pos])
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.list_widget.currentItem()
                if item is not None and not item.isHidden():
                    self._execute_item(item)
                return True
            if key == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(watched, event)
