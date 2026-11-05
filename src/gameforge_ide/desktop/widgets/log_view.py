"""LogView: read-only text viewer with 5000-block buffer and 100ms batched appends (spec §4.4, WI-4.7)."""
from __future__ import annotations

import collections
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens


class LogView(QWidget):
    """Log viewer with ring buffer, batched UI appends, and auto-scroll control."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("buildLogView")
        self.setAccessibleName("Build step log viewer")

        self._queue: collections.deque[str] = collections.deque()
        self._auto_scroll: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)
        lbl_title = QLabel("Log (live, last 5,000 lines)", self)
        lbl_title.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        header.addWidget(lbl_title)
        header.addStretch(1)

        self._btn_scroll = QPushButton("⤓ Bottom", self)
        self._btn_scroll.setObjectName("btnLogScrollBottom")
        self._btn_scroll.setCursor(Qt.PointingHandCursor)
        self._btn_scroll.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: 3px;"
            f"  padding: 1px 6px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ color: {tokens.TEXT_PRIMARY}; }}"
        )
        self._btn_scroll.clicked.connect(self._scroll_to_bottom)
        header.addWidget(self._btn_scroll)

        btn_clear = QPushButton("Clear", self)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: 3px;"
            f"  padding: 1px 6px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ color: {tokens.TEXT_PRIMARY}; }}"
        )
        btn_clear.clicked.connect(self.clear)
        header.addWidget(btn_clear)

        layout.addLayout(header)

        # Text edit
        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName("buildLogPlainText")
        self._edit.setReadOnly(True)
        self._edit.setMaximumBlockCount(5000)
        self._edit.setStyleSheet(
            f"QPlainTextEdit#{self._edit.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px;"
            f"  font-family: monospace;"
            f"  font-size: 11px;"
            f"}}"
        )
        layout.addWidget(self._edit, 1)

        self._scrollbar = self._edit.verticalScrollBar()
        self._scrollbar.valueChanged.connect(self._on_scroll_value_changed)

        # 100 ms flush timer
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(100)
        self._flush_timer.timeout.connect(self._flush_queue)
        self._flush_timer.start()

    def append_log(self, text: str) -> None:
        """Enqueue text for batched UI update."""
        if text:
            self._queue.append(text)

    def set_text(self, text: Any) -> None:
        """Replace log text immediately."""
        self._queue.clear()
        if not isinstance(text, str):
            import json
            try:
                text = json.dumps(text, indent=2)
            except Exception:
                text = str(text)
        self._edit.setPlainText(text)
        if self._auto_scroll:
            self._scroll_to_bottom()

    def clear(self) -> None:
        self._queue.clear()
        self._edit.clear()
        self._auto_scroll = True
        self._btn_scroll.setText("⤓ Bottom")
        self._btn_scroll.setStyleSheet(f"""
            QPushButton {{
                background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};
                border: 1px solid {tokens.BORDER}; border-radius: 3px;
                padding: 1px 6px; font-size: {tokens.FONT_BODY_SM}px;
            }}
            QPushButton:hover {{ color: {tokens.TEXT_PRIMARY}; }}
        """)

    def closeEvent(self, event) -> None:
        if hasattr(self, "_flush_timer") and self._flush_timer.isActive():
            self._flush_timer.stop()
        super().closeEvent(event)

    @Slot()
    def _flush_queue(self) -> None:
        if not self._queue:
            return
        chunk = "".join(self._queue)
        self._queue.clear()

        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(chunk if chunk.endswith("\n") else chunk + "\n")

        if self._auto_scroll:
            self._scroll_to_bottom()

    @Slot(int)
    def _on_scroll_value_changed(self, value: int) -> None:
        max_val = self._scrollbar.maximum()
        if max_val > 0 and value < max_val - 20:
            if self._auto_scroll:
                self._auto_scroll = False
                self._btn_scroll.setText("⤓ Resume Auto-Scroll")
                self._btn_scroll.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_WARNING};
                        border: 1px solid {tokens.ACCENT_WARNING}; border-radius: 3px;
                        padding: 1px 6px; font-size: {tokens.FONT_BODY_SM}px; font-weight: bold;
                    }}
                    QPushButton:hover {{ color: {tokens.TEXT_PRIMARY}; }}
                """)
        elif value >= max_val - 5:
            if not self._auto_scroll:
                self._auto_scroll = True
                self._btn_scroll.setText("⤓ Bottom")
                self._btn_scroll.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};
                        border: 1px solid {tokens.BORDER}; border-radius: 3px;
                        padding: 1px 6px; font-size: {tokens.FONT_BODY_SM}px;
                    }}
                    QPushButton:hover {{ color: {tokens.TEXT_PRIMARY}; }}
                """)

    @Slot()
    def _scroll_to_bottom(self) -> None:
        self._auto_scroll = True
        self._btn_scroll.setText("⤓ Bottom")
        self._btn_scroll.setStyleSheet(f"""
            QPushButton {{
                background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};
                border: 1px solid {tokens.BORDER}; border-radius: 3px;
                padding: 1px 6px; font-size: {tokens.FONT_BODY_SM}px;
            }}
            QPushButton:hover {{ color: {tokens.TEXT_PRIMARY}; }}
        """)
        scrollbar = self._edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
