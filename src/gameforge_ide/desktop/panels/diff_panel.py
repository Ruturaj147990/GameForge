"""GameForge IDE — Diff Review Panel.

Shows unified and side-by-side (split) diffs with chunk navigation and approve/reject controls.
Communicates directly with ToolGateway via ToolService — no HTTP.
"""

from __future__ import annotations

import re
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..services.tool_service import ToolService
from ..styles import tokens


class DiffView(QPlainTextEdit):
    """Read-only diff display with syntax colouring for +/- lines using design tokens."""

    def __init__(self, parent=None, is_left: bool = False, is_right: bool = False) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont_mono()
        self._is_left = is_left
        self._is_right = is_right
        self.setStyleSheet(
            f"background-color: {tokens.BG_ROOT};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"font-family: 'Cascadia Code', 'Consolas', monospace;"
            f"font-size: 12px;"
            f"color: {tokens.TEXT_PRIMARY};"
        )

    def setFont_mono(self):
        f = QFont("Cascadia Code")
        if not f.exactMatch():
            f = QFont("Consolas")
        f.setPointSize(10)
        self.setFont(f)

    def display_patch(self, patch: str) -> None:
        self.clear()
        cursor = self.textCursor()
        normalized = (patch or "").replace("\r\n", "\n")
        from ..styles.dark_theme import theme_color
        for line in normalized.splitlines(keepends=True):
            fmt = QTextCharFormat()
            if line.startswith("+") and not line.startswith("+++"):
                fmt.setForeground(QColor(theme_color("#00d9a3")))
                fmt.setBackground(QColor(theme_color("#001a11")))
            elif line.startswith("-") and not line.startswith("---"):
                fmt.setForeground(QColor(theme_color("#ff6b6b")))
                fmt.setBackground(QColor(theme_color("#1a0000")))
            elif line.startswith("@@"):
                fmt.setForeground(QColor(theme_color("#a78bfa")))
                fmt.setBackground(QColor(theme_color("#0d0a1f")))
                fmt.setFontWeight(QFont.Bold)
            elif line.startswith("---") or line.startswith("+++"):
                fmt.setForeground(QColor(theme_color(tokens.TEXT_MUTED)))
            else:
                fmt.setForeground(QColor(theme_color(tokens.TEXT_PRIMARY)))
            cursor.insertText(line, fmt)
        cursor.movePosition(QTextCursor.Start)
        self.setTextCursor(cursor)


class DiffPanel(QWidget):
    """Panel that presents a pending diff for human approval or rejection with unified/split views."""

    diff_approved = Signal(str)     # diff_id
    diff_rejected = Signal(str)     # diff_id
    diff_rolled_back = Signal(str)  # diff_id

    def __init__(self, tool_service: ToolService, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("diffPanel")
        self.setAccessibleName("Diff Review Panel")
        self._tools = tool_service
        self._current_diff_id: Optional[str] = None
        self._current_diff_meta: dict = {}
        self._raw_patch: str = ""
        self._hunk_blocks: List[int] = []
        self._current_hunk_idx: int = -1

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setObjectName("panel_header")
        header.setStyleSheet(
            f"background-color: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};"
        )
        header.setFixedHeight(44)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(10, 4, 10, 4)
        hdr_layout.setSpacing(8)

        title = QLabel("📝  Diff Review")
        title.setStyleSheet(f"color: {tokens.ACCENT_WARNING}; font-weight: 700; font-size: 13px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        self._diff_id_lbl = QLabel("No pending diff")
        self._diff_id_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 11px;")
        hdr_layout.addWidget(self._diff_id_lbl)
        layout.addWidget(header)

        # File & view controls bar
        sub_bar = QWidget()
        sub_bar.setStyleSheet(f"background-color: {tokens.BG_SURFACE}; border-bottom: 1px solid {tokens.BORDER};")
        sub_layout = QHBoxLayout(sub_bar)
        sub_layout.setContentsMargins(10, 4, 10, 4)
        sub_layout.setSpacing(8)

        self._file_bar = QLabel("")
        self._file_bar.setStyleSheet(f"color: {tokens.ACCENT_PRIMARY}; font-size: 11px; font-weight: 600;")
        sub_layout.addWidget(self._file_bar, 1)

        # Chunk navigation
        self._btn_prev_chunk = QPushButton("▲ Prev Chunk")
        self._btn_prev_chunk.setObjectName("btn_prev_chunk")
        self._btn_prev_chunk.setAccessibleName("Go to previous diff hunk")
        self._btn_prev_chunk.setCursor(Qt.PointingHandCursor)
        self._btn_prev_chunk.setStyleSheet(self._chip_button_style())
        self._btn_prev_chunk.clicked.connect(self._on_prev_chunk)
        sub_layout.addWidget(self._btn_prev_chunk)

        self._lbl_chunk_counter = QLabel("0 / 0")
        self._lbl_chunk_counter.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px;")
        sub_layout.addWidget(self._lbl_chunk_counter)

        self._btn_next_chunk = QPushButton("▼ Next Chunk")
        self._btn_next_chunk.setObjectName("btn_next_chunk")
        self._btn_next_chunk.setAccessibleName("Go to next diff hunk")
        self._btn_next_chunk.setCursor(Qt.PointingHandCursor)
        self._btn_next_chunk.setStyleSheet(self._chip_button_style())
        self._btn_next_chunk.clicked.connect(self._on_next_chunk)
        sub_layout.addWidget(self._btn_next_chunk)

        # View Mode Toggle (Unified vs Side-by-Side Split)
        self._btn_view_mode = QPushButton("Side-by-Side ⇄")
        self._btn_view_mode.setObjectName("btn_diff_view_mode")
        self._btn_view_mode.setAccessibleName("Toggle unified and side-by-side split view")
        self._btn_view_mode.setCursor(Qt.PointingHandCursor)
        self._btn_view_mode.setStyleSheet(self._chip_button_style())
        self._btn_view_mode.clicked.connect(self._toggle_view_mode)
        sub_layout.addWidget(self._btn_view_mode)

        layout.addWidget(sub_bar)

        # Views Stack (0: Unified, 1: Split)
        self._stack = QStackedWidget(self)

        # View 0: Unified DiffView (Must keep attribute name `_diff_view` for backward compatibility)
        self._diff_view = DiffView(self)
        self._diff_view.setObjectName("diffUnifiedView")
        self._stack.addWidget(self._diff_view)

        # View 1: Split Diff View (Left: Original/Deletions, Right: Proposed/Additions)
        split_widget = QWidget(self)
        split_layout = QVBoxLayout(split_widget)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(2)

        split_hdr = QHBoxLayout()
        lbl_left = QLabel("Original (Deletions)")
        lbl_left.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: 11px; font-weight: 600; padding: 2px 8px;")
        lbl_right = QLabel("Proposed (Additions)")
        lbl_right.setStyleSheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 11px; font-weight: 600; padding: 2px 8px;")
        split_hdr.addWidget(lbl_left, 1)
        split_hdr.addWidget(lbl_right, 1)
        split_layout.addLayout(split_hdr)

        self._splitter = QSplitter(Qt.Horizontal, split_widget)
        self._split_left = DiffView(self._splitter, is_left=True)
        self._split_right = DiffView(self._splitter, is_right=True)
        self._syncing_scroll = False

        def _sync_left_to_right(val: int) -> None:
            if self._syncing_scroll:
                return
            self._syncing_scroll = True
            try:
                self._split_right.verticalScrollBar().setValue(val)
            finally:
                self._syncing_scroll = False

        def _sync_right_to_left(val: int) -> None:
            if self._syncing_scroll:
                return
            self._syncing_scroll = True
            try:
                self._split_left.verticalScrollBar().setValue(val)
            finally:
                self._syncing_scroll = False

        self._split_left.verticalScrollBar().valueChanged.connect(_sync_left_to_right)
        self._split_right.verticalScrollBar().valueChanged.connect(_sync_right_to_left)
        self._splitter.addWidget(self._split_left)
        self._splitter.addWidget(self._split_right)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        split_layout.addWidget(self._splitter, 1)

        self._stack.addWidget(split_widget)
        layout.addWidget(self._stack, 1)

        # Action bar
        action_bar = QWidget()
        action_bar.setObjectName("panel_action_bar")
        action_bar.setStyleSheet(f"background-color: {tokens.BG_PANEL}; border-top: 1px solid {tokens.BORDER};")
        action_bar.setFixedHeight(52)
        abar_layout = QHBoxLayout(action_bar)
        abar_layout.setContentsMargins(10, 8, 10, 8)
        abar_layout.setSpacing(8)

        self._btn_approve = QPushButton("✅  Approve & Apply")
        self._btn_approve.setObjectName("btn_approve")
        self._btn_approve.setAccessibleName("Approve and apply proposed diff")
        self._btn_approve.setCursor(Qt.PointingHandCursor)
        self._btn_approve.setEnabled(False)
        self._btn_approve.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_SUCCESS};"
            f"  border: 1px solid {tokens.ACCENT_SUCCESS}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px 14px; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_ACTIVE}; }}"
            f"QPushButton:disabled {{ background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_MUTED}; border-color: {tokens.BORDER}; }}"
        )
        self._btn_approve.clicked.connect(self._on_approve)
        abar_layout.addWidget(self._btn_approve)

        self._btn_reject = QPushButton("❌  Reject")
        self._btn_reject.setObjectName("btn_reject")
        self._btn_reject.setAccessibleName("Reject proposed diff")
        self._btn_reject.setCursor(Qt.PointingHandCursor)
        self._btn_reject.setEnabled(False)
        self._btn_reject.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_ERROR};"
            f"  border: 1px solid {tokens.ACCENT_ERROR}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px 14px; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_ACTIVE}; }}"
            f"QPushButton:disabled {{ background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_MUTED}; border-color: {tokens.BORDER}; }}"
        )
        self._btn_reject.clicked.connect(self._on_reject)
        abar_layout.addWidget(self._btn_reject)

        abar_layout.addStretch()

        self._btn_rollback = QPushButton("↩  Rollback Applied")
        self._btn_rollback.setObjectName("btn_rollback")
        self._btn_rollback.setAccessibleName("Rollback previously applied edit")
        self._btn_rollback.setCursor(Qt.PointingHandCursor)
        self._btn_rollback.setEnabled(False)
        self._btn_rollback.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_PRIMARY};"
            f"  border: 1px solid {tokens.ACCENT_PRIMARY}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px 14px; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_ACTIVE}; }}"
            f"QPushButton:disabled {{ background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_MUTED}; border-color: {tokens.BORDER}; }}"
        )
        self._btn_rollback.clicked.connect(self._on_rollback)
        abar_layout.addWidget(self._btn_rollback)

        layout.addWidget(action_bar)

    @staticmethod
    def _chip_button_style() -> str:
        return (
            f"QPushButton {{"
            f"  background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 2px 8px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def show_diff(self, diff_id: str, meta: dict) -> None:
        """Called when the agent proposes a diff."""
        self._current_diff_id = diff_id
        self._current_diff_meta = meta
        self._diff_id_lbl.setText(f"ID: {diff_id}")
        self._file_bar.setText(f"File: {meta.get('file_path', 'unknown')}")
        patch = meta.get("diff_patch") or "(No patch content available)"
        self._raw_patch = patch

        # Populate unified view
        self._diff_view.display_patch(patch)

        # Populate split view
        left_patch, right_patch = self._split_unified_patch(patch)
        self._split_left.display_patch(left_patch)
        self._split_right.display_patch(right_patch)

        # Index hunks for chunk navigation
        self._index_hunks(patch)

        self._btn_approve.setEnabled(True)
        self._btn_approve.setText("✅  Approve & Apply")
        self._btn_reject.setEnabled(True)
        self._btn_reject.setText("❌  Reject")
        self._btn_rollback.setEnabled(False)

    def clear(self) -> None:
        self._current_diff_id = None
        self._current_diff_meta = {}
        self._raw_patch = ""
        self._hunk_blocks.clear()
        self._current_hunk_idx = -1
        self._diff_id_lbl.setText("No pending diff")
        self._file_bar.setText("")
        self._lbl_chunk_counter.setText("0 / 0")
        self._diff_view.clear()
        self._split_left.clear()
        self._split_right.clear()
        self._btn_approve.setEnabled(False)
        self._btn_approve.setText("✅  Approve & Apply")
        self._btn_reject.setEnabled(False)
        self._btn_reject.setText("❌  Reject")
        self._btn_rollback.setEnabled(False)

    # ── Chunk Navigation & Split View ────────────────────────────────────────

    def _index_hunks(self, patch: str) -> None:
        self._hunk_blocks.clear()
        lines = patch.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("@@"):
                self._hunk_blocks.append(i)
        count = len(self._hunk_blocks)
        if count > 0:
            self._current_hunk_idx = 0
            self._lbl_chunk_counter.setText(f"1 / {count}")
            self._btn_prev_chunk.setEnabled(True)
            self._btn_next_chunk.setEnabled(True)
        else:
            self._current_hunk_idx = -1
            self._lbl_chunk_counter.setText("0 / 0")
            self._btn_prev_chunk.setEnabled(False)
            self._btn_next_chunk.setEnabled(False)

    @Slot()
    def _on_next_chunk(self) -> None:
        if not self._hunk_blocks:
            return
        self._current_hunk_idx = (self._current_hunk_idx + 1) % len(self._hunk_blocks)
        self._jump_to_hunk(self._current_hunk_idx)

    @Slot()
    def _on_prev_chunk(self) -> None:
        if not self._hunk_blocks:
            return
        self._current_hunk_idx = (self._current_hunk_idx - 1) % len(self._hunk_blocks)
        self._jump_to_hunk(self._current_hunk_idx)

    def _jump_to_hunk(self, hunk_idx: int) -> None:
        if 0 <= hunk_idx < len(self._hunk_blocks):
            target_line = self._hunk_blocks[hunk_idx]
            self._lbl_chunk_counter.setText(f"{hunk_idx + 1} / {len(self._hunk_blocks)}")
            block = self._diff_view.document().findBlockByLineNumber(target_line)
            if block.isValid():
                cursor = self._diff_view.textCursor()
                cursor.setPosition(block.position())
                self._diff_view.setTextCursor(cursor)
                self._diff_view.centerCursor()
            for split_view in (self._split_left, self._split_right):
                doc = split_view.document()
                seen = -1
                b = doc.begin()
                while b.isValid():
                    if b.text().startswith("@@"):
                        seen += 1
                        if seen == hunk_idx:
                            c = split_view.textCursor()
                            c.setPosition(b.position())
                            split_view.setTextCursor(c)
                            split_view.centerCursor()
                            break
                    b = b.next()

    @Slot()
    def _toggle_view_mode(self) -> None:
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
            self._btn_view_mode.setText("Unified ⇄")
        else:
            self._stack.setCurrentIndex(0)
            self._btn_view_mode.setText("Side-by-Side ⇄")

    @staticmethod
    def _split_unified_patch(patch: str) -> tuple[str, str]:
        """Split a unified diff into left (original) and right (proposed) views."""
        left_lines = []
        right_lines = []
        for line in patch.splitlines():
            if line.startswith("@@"):
                left_lines.append(line)
                right_lines.append(line)
            elif line.startswith("---") or line.startswith("+++"):
                continue
            elif line.startswith("-"):
                left_lines.append(line)
            elif line.startswith("+"):
                right_lines.append(line)
            else:
                left_lines.append(line)
                right_lines.append(line)
        return "\n".join(left_lines), "\n".join(right_lines)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_approve(self) -> None:
        if not self._current_diff_id:
            return
        # Atomic lock: immediately disable actions with loading feedback to prevent race conditions
        self._btn_approve.setEnabled(False)
        self._btn_approve.setText("⏳ Applying…")
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
            self._btn_approve.setText("✅ Applied")
            self._btn_reject.setEnabled(False)
            self._btn_rollback.setEnabled(True)
            self.diff_approved.emit(diff_id)
        else:
            self._diff_view.appendPlainText(f"\n\n── Apply FAILED: {result.get('error', '?')} ──")
            # Allow user to reject or retry if apply failed
            self._btn_approve.setEnabled(True)
            self._btn_approve.setText("✅  Approve & Apply")
            self._btn_reject.setEnabled(True)

    @Slot()
    def _on_reject(self) -> None:
        if not self._current_diff_id:
            return
        # Atomic lock: immediately disable to prevent duplicate clicks
        self._btn_approve.setEnabled(False)
        self._btn_reject.setEnabled(False)
        self._btn_reject.setText("⏳ Rejecting…")

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
        self._btn_rollback.setText("⏳ Rolling back…")

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
            self._btn_rollback.setText("↩ Rolled Back")
            self.diff_rolled_back.emit(diff_id)
        else:
            self._diff_view.appendPlainText(f"\n\n── Rollback FAILED: {result.get('error', '?')} ──")
            self._btn_rollback.setEnabled(True)
            self._btn_rollback.setText("↩  Rollback Applied")
