"""LogView: read-only text viewer with 5000-block buffer and 100ms batched appends (spec §4.4, WI-4.7)."""
from __future__ import annotations

import collections
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent, QFont, QResizeEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_stylesheet


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
        self._btn_scroll.setAccessibleName("Scroll to latest log entry")
        self._btn_scroll.setCursor(Qt.PointingHandCursor)
        self._btn_scroll.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        self._btn_scroll.clicked.connect(self._scroll_to_bottom)
        header.addWidget(self._btn_scroll)

        btn_clear = QPushButton("Clear", self)
        btn_clear.setObjectName("btnLogClear")
        btn_clear.setAccessibleName("Clear log window")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        btn_clear.clicked.connect(self.clear)
        header.addWidget(btn_clear)

        layout.addLayout(header)

        # Text edit
        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName("buildLogPlainText")
        self._edit.setAccessibleName("Console log text output")
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
            f"QPlainTextEdit#{self._edit.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
            f"}}"
        )
        layout.addWidget(self._edit, 1)

        # Floating Amber Resume Autoscroll Button over log edit
        self._floating_resume_btn = QPushButton("⤓ Resume Autoscroll", self._edit)
        self._floating_resume_btn.setObjectName("btnFloatingResumeScroll")
        self._floating_resume_btn.setAccessibleName("Resume autoscroll to latest logs")
        self._floating_resume_btn.setCursor(Qt.PointingHandCursor)
        self._floating_resume_btn.setStyleSheet(
            f"QPushButton#{self._floating_resume_btn.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  color: {tokens.ACCENT_WARNING};"
            f"  border: 1px solid {tokens.ACCENT_WARNING};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"  font-weight: 700;"
            f"}}"
            f"QPushButton#{self._floating_resume_btn.objectName()}:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"}}"
        )
        self._floating_resume_btn.clicked.connect(self._scroll_to_bottom)
        self._floating_resume_btn.hide()

        self._scrollbar = self._edit.verticalScrollBar()
        self._scrollbar.valueChanged.connect(self._on_scroll_value_changed)

        # 100 ms flush timer
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(100)
        self._flush_timer.timeout.connect(self._flush_queue)
        self._flush_timer.start()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposition_floating_btn()

    @Slot()
    def _reposition_floating_btn(self) -> None:
        if hasattr(self, "_floating_resume_btn") and hasattr(self, "_edit"):
            btn_w = 160
            btn_h = 28
            margin_right = 24
            margin_bottom = 16
            edit_rect = self._edit.rect()
            x = max(10, edit_rect.width() - btn_w - margin_right)
            y = max(10, edit_rect.height() - btn_h - margin_bottom)
            self._floating_resume_btn.setGeometry(x, y, btn_w, btn_h)

    @Slot(str)
    def append_log(self, text: str) -> None:
        """Enqueue text for batched UI update."""
        if text:
            self._queue.append(text)

    @Slot(str)
    @Slot(object)
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

    @Slot()
    def clear(self) -> None:
        self._queue.clear()
        self._edit.clear()
        self._auto_scroll = True
        self._btn_scroll.setText("⤓ Bottom")
        self._btn_scroll.setStyleSheet(theme_stylesheet(f"""
            QPushButton {{
                background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};
                border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;
                padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;
            }}
            QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}
        """))
        if hasattr(self, "_floating_resume_btn"):
            self._floating_resume_btn.hide()

    @Slot()
    def update_theme(self) -> None:
        """Update editor and button styling on theme change."""
        if hasattr(self, "_edit"):
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
                f"QPlainTextEdit#{self._edit.objectName()}:focus {{"
                f"  border: 1px solid {tokens.BORDER_FOCUS};"
                f"}}"
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        if hasattr(self, "_flush_timer") and self._flush_timer.isActive():
            self._flush_timer.stop()
        super().closeEvent(event)

    def deleteLater(self) -> None:
        if hasattr(self, "_flush_timer") and self._flush_timer.isActive():
            self._flush_timer.stop()
        super().deleteLater()

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
                self._btn_scroll.setStyleSheet(theme_stylesheet(f"""
                    QPushButton {{
                        background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_WARNING};
                        border: 1px solid {tokens.ACCENT_WARNING}; border-radius: {tokens.RADIUS}px;
                        padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px; font-weight: bold;
                    }}
                    QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}
                """))
                if hasattr(self, "_floating_resume_btn"):
                    self._reposition_floating_btn()
                    self._floating_resume_btn.show()
                    self._floating_resume_btn.raise_()
        elif value >= max_val - 5:
            if not self._auto_scroll:
                self._auto_scroll = True
                self._btn_scroll.setText("⤓ Bottom")
                self._btn_scroll.setStyleSheet(theme_stylesheet(f"""
                    QPushButton {{
                        background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};
                        border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;
                        padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;
                    }}
                    QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}
                """))
                if hasattr(self, "_floating_resume_btn"):
                    self._floating_resume_btn.hide()

    @Slot()
    def _scroll_to_bottom(self) -> None:
        self._auto_scroll = True
        self._btn_scroll.setText("⤓ Bottom")
        self._btn_scroll.setStyleSheet(theme_stylesheet(f"""
            QPushButton {{
                background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};
                border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;
                padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;
            }}
            QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}
        """))
        if hasattr(self, "_floating_resume_btn"):
            self._floating_resume_btn.hide()
        scrollbar = self._edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
