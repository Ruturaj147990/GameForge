"""Inline Diff Approval Card and File Mutation Notification for ChatPanel.

Provides:
- DiffApprovalCard: interactive approval card for diff_pending events (Manual profile).
- FileChangedNotification: sleek inline non-blocking notification for file_changed events
  (Auto-Edit & Agentic profiles).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_color


class DiffApprovalCard(QFrame):
    """Interactive inline approval card for pending diffs (Manual Profile)."""

    diff_approved = Signal(str)  # diff_id
    diff_rejected = Signal(str)  # diff_id

    def __init__(self, diff_id: str, meta: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("diffApprovalCard")
        self.setAccessibleName(f"Diff approval card for {diff_id}")

        self.diff_id = diff_id
        self.meta = meta
        self.file_path = meta.get("file_path", "")
        self.diff_patch = meta.get("diff_patch", "")

        accent = theme_color(tokens.ACCENT_WARNING)
        bg = theme_color(tokens.BG_PANEL)

        self.setStyleSheet(f"""
            QFrame#diffApprovalCard {{
                background-color: {bg};
                border: 1px solid {accent};
                border-left: 4px solid {accent};
                border-radius: {tokens.RADIUS}px;
                margin: 6px 8px;
            }}
            QLabel {{ background: transparent; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # Header
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        lbl_icon = QLabel("📝", self)
        lbl_icon.setStyleSheet("font-size: 14px;")
        top_row.addWidget(lbl_icon)

        title = QLabel(f"Diff Approval Required — {self.file_path or diff_id}", self)
        title.setObjectName("diffApprovalTitle")
        title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 700; font-size: 13px;")
        title.setWordWrap(True)
        top_row.addWidget(title, 1)

        badge = QLabel("MANUAL APPROVAL", self)
        badge.setStyleSheet(f"""
            background-color: #451a03;
            color: #fde68a;
            border: 1px solid #b45309;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 10px;
            font-weight: 700;
        """)
        top_row.addWidget(badge)
        layout.addLayout(top_row)

        # File & Diff ID details
        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(10)

        lbl_file = QLabel(f"File: <code>{self.file_path}</code>", self)
        lbl_file.setTextFormat(Qt.RichText)
        lbl_file.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px;")
        info_row.addWidget(lbl_file)

        lbl_id = QLabel(f"Diff ID: {self.diff_id}", self)
        lbl_id.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 10px;")
        info_row.addWidget(lbl_id)

        # Diff additions / deletions stats
        additions = sum(1 for line in self.diff_patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in self.diff_patch.splitlines() if line.startswith("-") and not line.startswith("---"))
        if additions > 0 or deletions > 0:
            lbl_stats = QLabel(f"<span style='color: #00d9a3;'>+{additions}</span> / <span style='color: #ff6b6b;'>-{deletions}</span> lines", self)
            lbl_stats.setTextFormat(Qt.RichText)
            lbl_stats.setStyleSheet("font-size: 11px; font-weight: 600;")
            info_row.addWidget(lbl_stats)

        info_row.addStretch(1)
        layout.addLayout(info_row)

        # Optional Diff Patch Monospace Viewer
        if self.diff_patch:
            self._diff_view = QPlainTextEdit(self)
            self._diff_view.setReadOnly(True)
            self._diff_view.setMaximumHeight(160)
            self._diff_view.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {tokens.BG_ROOT};
                    border: 1px solid {tokens.BORDER};
                    border-radius: 4px;
                    font-family: 'Cascadia Code', 'Consolas', monospace;
                    font-size: 11px;
                    color: {tokens.TEXT_PRIMARY};
                }}
            """)
            self._render_patch(self.diff_patch)
            layout.addWidget(self._diff_view)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(10)

        self.btn_accept = QPushButton("✓ Accept Diff", self)
        self.btn_accept.setObjectName("btnApproveDiff")
        self.btnApproveDiff = self.btn_accept  # alias for tests
        self.btn_accept.setCursor(Qt.PointingHandCursor)
        self.btn_accept.setStyleSheet(f"""
            QPushButton#btnApproveDiff {{
                background-color: {tokens.ACCENT_SUCCESS};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 700;
                font-size: 12px;
            }}
            QPushButton#btnApproveDiff:hover {{
                opacity: 0.9;
            }}
            QPushButton#btnApproveDiff:disabled {{
                background-color: {tokens.BG_ROOT};
                color: {tokens.TEXT_MUTED};
                border: 1px solid {tokens.BORDER};
            }}
        """)
        self.btn_accept.clicked.connect(self._on_accept)
        btn_row.addWidget(self.btn_accept)

        self.btn_reject = QPushButton("✗ Reject Diff", self)
        self.btn_reject.setObjectName("btnRejectDiff")
        self.btnRejectDiff = self.btn_reject  # alias for tests
        self.btn_reject.setCursor(Qt.PointingHandCursor)
        self.btn_reject.setStyleSheet(f"""
            QPushButton#btnRejectDiff {{
                background-color: {tokens.BG_SURFACE};
                color: {tokens.ACCENT_ERROR};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton#btnRejectDiff:hover {{
                background-color: #450a0a;
                border-color: {tokens.ACCENT_ERROR};
                color: #ffffff;
            }}
            QPushButton#btnRejectDiff:disabled {{
                background-color: {tokens.BG_ROOT};
                color: {tokens.TEXT_MUTED};
                border: 1px solid {tokens.BORDER};
            }}
        """)
        self.btn_reject.clicked.connect(self._on_reject)
        btn_row.addWidget(self.btn_reject)

        self._lbl_status = QLabel("Awaiting your decision to proceed.", self)
        self._lbl_status.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px;")
        btn_row.addWidget(self._lbl_status, 1)

        layout.addLayout(btn_row)

    def _render_patch(self, patch: str) -> None:
        cursor = self._diff_view.textCursor()
        for line in patch.splitlines(keepends=True):
            fmt = QTextCharFormat()
            if line.startswith("+") and not line.startswith("+++"):
                fmt.setForeground(QColor(theme_color("#00d9a3")))
                fmt.setBackground(QColor(theme_color("#001a11")))
            elif line.startswith("-") and not line.startswith("---"):
                fmt.setForeground(QColor(theme_color("#ff6b6b")))
                fmt.setBackground(QColor(theme_color("#1a0000")))
            elif line.startswith("@@"):
                fmt.setForeground(QColor(theme_color("#a78bfa")))
                fmt.setFontWeight(QFont.Bold)
            else:
                fmt.setForeground(QColor(tokens.TEXT_PRIMARY))
            cursor.insertText(line, fmt)
        cursor.movePosition(QTextCursor.Start)
        self._diff_view.setTextCursor(cursor)

    def _on_accept(self) -> None:
        self.btn_accept.setEnabled(False)
        self.btn_reject.setEnabled(False)
        self.btn_accept.setText("✓ Diff Accepted")
        self._lbl_status.setText("Diff approved. Resuming task execution...")
        self._lbl_status.setStyleSheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 11px; font-weight: 600;")
        self.diff_approved.emit(self.diff_id)

    def _on_reject(self) -> None:
        self.btn_accept.setEnabled(False)
        self.btn_reject.setEnabled(False)
        self.btn_reject.setText("✗ Diff Rejected")
        self._lbl_status.setText("Diff rejected by developer.")
        self._lbl_status.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: 11px; font-weight: 600;")
        self.diff_rejected.emit(self.diff_id)


class FileChangedNotification(QFrame):
    """Sleek inline notification for auto-applied file mutations (Auto-Edit and Agentic Profiles)."""

    def __init__(self, content: str, meta: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fileChangedNotification")
        self.setAccessibleName("File modification notification")

        file_path = meta.get("file_path", "")
        diff_id = meta.get("diff_id", "")
        stage = meta.get("engineering_stage", "Code Generation")

        bg = theme_color(tokens.BG_SURFACE)
        accent = theme_color(tokens.ACCENT_SUCCESS)

        self.setStyleSheet(f"""
            QFrame#fileChangedNotification {{
                background-color: {bg};
                border-left: 3px solid {accent};
                border-top: 1px solid {tokens.BORDER};
                border-right: 1px solid {tokens.BORDER};
                border-bottom: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                margin: 4px 10px;
                padding: 8px 12px;
            }}
            QLabel {{ background: transparent; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        lbl_icon = QLabel("⚡", self)
        lbl_icon.setStyleSheet("font-size: 14px;")
        layout.addWidget(lbl_icon)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        title_text = f"<b>File Modified:</b> <code>{file_path}</code>" if file_path else f"<b>File Modified:</b> {content}"
        lbl_title = QLabel(title_text, self)
        lbl_title.setTextFormat(Qt.RichText)
        lbl_title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: 12px;")
        info_box.addWidget(lbl_title)

        detail_text = f"Applied automatically ({stage}) with SHA-256 rollback journal"
        if diff_id:
            detail_text += f" | Diff: {diff_id}"
        patch = meta.get("diff_patch", "")
        if patch:
            additions = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
            deletions = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
            if additions > 0 or deletions > 0:
                detail_text += f" | +{additions}/-{deletions} lines"
        lbl_detail = QLabel(detail_text, self)
        lbl_detail.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 10px;")
        info_box.addWidget(lbl_detail)

        layout.addLayout(info_box, 1)

        lbl_auto = QLabel("AUTO-APPLIED", self)
        lbl_auto.setStyleSheet(f"""
            background-color: #064e3b;
            color: #6ee7b7;
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 700;
        """)
        layout.addWidget(lbl_auto)
