"""GameForge IDE — Diff Review Panel.

Shows a side-by-side (or unified) diff and approve/reject controls.
Communicates directly with ToolGateway via ToolService — no HTTP.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..services.tool_service import ToolService
from ..styles.dark_theme import theme_color


class DiffView(QPlainTextEdit):
    """Read-only diff display with syntax colouring for +/- lines."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont_mono()
        self.setStyleSheet(
            "background: #0f1219; border: none; font-family: 'Consolas', 'Cascadia Code', monospace;"
            " font-size: 12px; color: #e8eaf6;"
        )

    def setFont_mono(self):
        from PySide6.QtGui import QFont
        f = QFont("Consolas")
        f.setPointSize(11)
        self.setFont(f)

    def display_patch(self, patch: str) -> None:
        self.clear()
        cursor = self.textCursor()
        normalized = (patch or "").replace("\r\n", "\n")
        for line in normalized.splitlines(keepends=True):
            fmt = QTextCharFormat()
            if line.startswith("+") and not line.startswith("+++"):
                fmt.setForeground(QColor(theme_color("#00d9a3")))
                fmt.setBackground(QColor(theme_color("#001a11")))
            elif line.startswith("-") and not line.startswith("---"):
                fmt.setForeground(QColor(theme_color("#ff6b6b")))
                fmt.setBackground(QColor(theme_color("#1a0000")))
            elif line.startswith("@@"):
                fmt.setForeground(QColor(theme_color("#6c63ff")))
                fmt.setBackground(QColor(theme_color("#0d0a1f")))
            elif line.startswith("---") or line.startswith("+++"):
                fmt.setForeground(QColor(theme_color("#8891aa")))
            else:
                fmt.setForeground(QColor(theme_color("#e8eaf6")))
            cursor.insertText(line, fmt)
        cursor.movePosition(QTextCursor.Start)
        self.setTextCursor(cursor)


class DiffPanel(QWidget):
    """Panel that presents a pending diff for human approval or rejection."""

    diff_approved = Signal(str)   # diff_id
    diff_rejected = Signal(str)   # diff_id
    diff_rolled_back = Signal(str)  # diff_id

    def __init__(self, tool_service: ToolService, parent=None) -> None:
        super().__init__(parent)
        self._tools = tool_service
        self._current_diff_id: Optional[str] = None
        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setObjectName("panel_header")
        header.setStyleSheet("background: #0d0b14; border-bottom: 1px solid #231c34;")
        header.setFixedHeight(44)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(10, 4, 10, 4)
        title = QLabel("📝  Diff Review")
        title.setStyleSheet("color: #f59e0b; font-weight: 700; font-size: 14px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        self._diff_id_lbl = QLabel("No pending diff")
        self._diff_id_lbl.setStyleSheet("color: #9d95b0; font-size: 11px;")
        hdr_layout.addWidget(self._diff_id_lbl)
        layout.addWidget(header)

        # File path bar
        self._file_bar = QLabel("")
        self._file_bar.setStyleSheet(
            "background: #120f1d; color: #7c3aed; font-size: 11px;"
            " padding: 4px 12px; border-bottom: 1px solid #231c34;"
        )
        layout.addWidget(self._file_bar)

        # Diff view
        self._diff_view = DiffView()
        layout.addWidget(self._diff_view, 1)

        # Action bar
        action_bar = QWidget()
        action_bar.setObjectName("panel_action_bar")
        action_bar.setStyleSheet("background: #0d0b14; border-top: 1px solid #231c34;")
        action_bar.setFixedHeight(52)
        abar_layout = QHBoxLayout(action_bar)
        abar_layout.setContentsMargins(10, 8, 10, 8)
        abar_layout.setSpacing(8)

        self._btn_approve = QPushButton("✅  Approve & Apply")
        self._btn_approve.setObjectName("btn_approve")
        self._btn_approve.setEnabled(False)
        self._btn_approve.clicked.connect(self._on_approve)
        abar_layout.addWidget(self._btn_approve)

        self._btn_reject = QPushButton("❌  Reject")
        self._btn_reject.setObjectName("btn_reject")
        self._btn_reject.setEnabled(False)
        self._btn_reject.clicked.connect(self._on_reject)
        abar_layout.addWidget(self._btn_reject)

        abar_layout.addStretch()

        self._btn_rollback = QPushButton("↩  Rollback Applied")
        self._btn_rollback.setObjectName("btn_rollback")
        self._btn_rollback.setEnabled(False)
        self._btn_rollback.clicked.connect(self._on_rollback)
        abar_layout.addWidget(self._btn_rollback)

        layout.addWidget(action_bar)

    # ── Public API ───────────────────────────────────────────────────────────

    def show_diff(self, diff_id: str, meta: dict) -> None:
        """Called when the agent proposes a diff."""
        self._current_diff_id = diff_id
        self._current_diff_meta = meta
        self._diff_id_lbl.setText(f"ID: {diff_id}")
        self._file_bar.setText(f"  File: {meta.get('file_path', 'unknown')}")
        patch = meta.get("diff_patch") or "(No patch content available)"
        self._diff_view.display_patch(patch)
        self._btn_approve.setEnabled(True)
        self._btn_reject.setEnabled(True)
        self._btn_rollback.setEnabled(False)

    def clear(self) -> None:
        self._current_diff_id = None
        self._current_diff_meta = {}
        self._diff_id_lbl.setText("No pending diff")
        self._file_bar.setText("")
        self._diff_view.clear()
        self._btn_approve.setEnabled(False)
        self._btn_reject.setEnabled(False)
        self._btn_rollback.setEnabled(False)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_approve(self) -> None:
        if not self._current_diff_id:
            return
        # Atomic lock: immediately disable actions to prevent double-click / race conditions
        self._btn_approve.setEnabled(False)
        self._btn_reject.setEnabled(False)

        diff_id = self._current_diff_id
        is_batch = diff_id.startswith("batch_") or getattr(self, "_current_diff_meta", {}).get("is_batch", False)
        tool_name = "apply_batch" if is_batch else "apply_edit"
        param_key = "batch_id" if is_batch else "diff_id"

        try:
            result = self._tools.execute_approved_sync(tool_name, {param_key: diff_id})
        except Exception as exc:
            result = {"status": "ERROR", "error": str(exc)}

        if result.get("status") == "SUCCESS":
            self._diff_view.appendPlainText("\n\n── Applied successfully ──")
            self._btn_approve.setEnabled(False)
            self._btn_reject.setEnabled(False)
            self._btn_rollback.setEnabled(True)
            self.diff_approved.emit(diff_id)
        else:
            self._diff_view.appendPlainText(f"\n\n── Apply FAILED: {result.get('error', '?')} ──")
            # Allow user to reject or retry if apply failed
            self._btn_approve.setEnabled(True)
            self._btn_reject.setEnabled(True)

    @Slot()
    def _on_reject(self) -> None:
        if not self._current_diff_id:
            return
        # Atomic lock: immediately disable to prevent duplicate clicks
        self._btn_approve.setEnabled(False)
        self._btn_reject.setEnabled(False)

        diff_id = self._current_diff_id
        is_batch = diff_id.startswith("batch_") or getattr(self, "_current_diff_meta", {}).get("is_batch", False)
        tool_name = "reject_batch" if is_batch else "reject_edit"
        param_key = "batch_id" if is_batch else "diff_id"

        try:
            self._tools.execute_sync(tool_name, {param_key: diff_id})
        except Exception as exc:
            self._diff_view.appendPlainText(f"\n\n── Reject error: {exc} ──")

        self.diff_rejected.emit(diff_id)
        self.clear()

    @Slot()
    def _on_rollback(self) -> None:
        if not self._current_diff_id:
            return
        self._btn_rollback.setEnabled(False)

        diff_id = self._current_diff_id
        is_batch = diff_id.startswith("batch_") or getattr(self, "_current_diff_meta", {}).get("is_batch", False)
        tool_name = "rollback_batch" if is_batch else "rollback_edit"
        param_key = "batch_id" if is_batch else "diff_id"

        try:
            result = self._tools.execute_approved_sync(tool_name, {param_key: diff_id})
        except Exception as exc:
            result = {"status": "ERROR", "error": str(exc)}

        if result.get("status") == "SUCCESS":
            self._diff_view.appendPlainText("\n\n── Rolled back successfully ──")
            self._btn_rollback.setEnabled(False)
            self.diff_rolled_back.emit(diff_id)
        else:
            self._diff_view.appendPlainText(f"\n\n── Rollback FAILED: {result.get('error', '?')} ──")
            self._btn_rollback.setEnabled(True)
