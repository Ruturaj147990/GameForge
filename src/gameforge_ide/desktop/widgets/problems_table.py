"""ProblemsTable: diagnostics table for compiler, automation, and scenario failures (spec §4.4, WI-4.7)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Optional, Sequence

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_color, theme_stylesheet


@lru_cache(maxsize=16)
def _make_severity_icon_cached(sev_kind: str, color_hex: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(color_hex))
        glyph = "✕" if sev_kind == "ERR" else ("▲" if sev_kind == "WARN" else "ℹ")
        painter.drawText(QRect(0, 0, 16, 16), Qt.AlignCenter, glyph)
    finally:
        painter.end()
    return QIcon(pixmap)


def _severity_role(severity: str) -> tuple[str, str]:
    sev = (severity or "").upper()
    if "ERR" in sev:
        return "ERR", tokens.ACCENT_ERROR
    if "WARN" in sev:
        return "WARN", tokens.ACCENT_WARNING
    return "INFO", tokens.ACCENT_PRIMARY


def _make_severity_icon(severity: str) -> QIcon:
    """Generate crisp high-contrast icon for Error, Warning, or Info."""
    sev_kind, raw_col = _severity_role(severity)
    return _make_severity_icon_cached(sev_kind, theme_color(raw_col))


def _parse_line_number(raw_line: Any) -> int:
    if raw_line is None or isinstance(raw_line, bool):
        return 0
    if isinstance(raw_line, int):
        return max(0, raw_line)
    text = str(raw_line).strip()
    if not text:
        return 0
    try:
        return max(0, int(text))
    except ValueError:
        return 0


class ProblemsTable(QTableWidget):
    """Displays diagnostics with severity, file:line location, and message."""

    openLocationRequested = Signal(str, int)  # (file_path, line)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("buildProblemsTable")
        self.setAccessibleName("Build problems and diagnostics table")

        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(["Severity", "Location", "Message", "Code", "Source File", "Line"])
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)

        self._apply_stylesheet()
        self.doubleClicked.connect(self._on_row_double_clicked)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            theme_stylesheet(
                f"QTableWidget#{self.objectName()} {{"
                f"  background-color: {tokens.BG_ROOT};"
                f"  color: {tokens.TEXT_PRIMARY};"
                f"  border: 1px solid {tokens.BORDER};"
                f"  border-radius: {tokens.RADIUS}px;"
                f"  gridline-color: {tokens.BORDER};"
                f"  selection-background-color: {tokens.BG_ACTIVE};"
                f"  selection-color: {tokens.TEXT_PRIMARY};"
                f"}}"
                f"QTableWidget#{self.objectName()}:focus {{"
                f"  border: 1px solid {tokens.BORDER_FOCUS};"
                f"}}"
                f"QHeaderView::section {{"
                f"  background-color: {tokens.BG_PANEL};"
                f"  color: {tokens.TEXT_SECONDARY};"
                f"  border: 1px solid {tokens.BORDER};"
                f"  padding: 4px {tokens.SPACE_SM}px;"
                f"  font-size: {tokens.FONT_BODY_SM}px;"
                f"  font-weight: 600;"
                f"}}"
            )
        )

    def update_theme(self) -> None:
        """Refresh stylesheet and row icon/foreground colors for the active theme."""
        self._apply_stylesheet()
        for r in range(self.rowCount()):
            item_sev = self.item(r, 0)
            if item_sev is not None:
                sev = item_sev.text()
                _, col_str = _severity_role(sev)
                item_sev.setForeground(QColor(theme_color(col_str)))
                item_sev.setIcon(_make_severity_icon(sev))
            item_code = self.item(r, 3)
            if item_code is not None:
                item_code.setForeground(QColor(theme_color(tokens.TEXT_SECONDARY)))
            item_file = self.item(r, 4)
            if item_file is not None:
                item_file.setForeground(QColor(theme_color(tokens.TEXT_PRIMARY)))
            item_line = self.item(r, 5)
            if item_line is not None:
                item_line.setForeground(QColor(theme_color(tokens.TEXT_MUTED)))

    def set_problems(self, problems: Sequence[Dict[str, Any]]) -> None:
        """Populate table with problem dicts."""
        valid_problems = [p for p in (problems or ()) if isinstance(p, dict)]
        self.setUpdatesEnabled(False)
        try:
            self.clearContents()
            self.setRowCount(len(valid_problems))
            for r, p in enumerate(valid_problems):
                raw_sev = p.get("severity")
                sev = (str(raw_sev).strip() if raw_sev is not None else "") or "Error"
                sev = sev.upper()

                raw_file = p.get("file")
                file_path = str(raw_file).strip() if raw_file is not None else ""
                line_no = _parse_line_number(p.get("line", 0))
                if file_path:
                    loc = f"{file_path}:{line_no}" if line_no > 0 else file_path
                else:
                    loc = "—"

                raw_msg = p.get("message")
                msg = str(raw_msg) if raw_msg is not None else ""

                raw_code = p.get("code") if p.get("code") is not None else p.get("error_code")
                code = str(raw_code).strip() if raw_code is not None and str(raw_code).strip() else "—"

                payload = (file_path, line_no)

                # Col 0: Severity with icon
                item_sev = QTableWidgetItem(sev)
                item_sev.setFlags(item_sev.flags() & ~Qt.ItemIsEditable)
                _, col_str = _severity_role(sev)
                item_sev.setForeground(QColor(theme_color(col_str)))
                item_sev.setIcon(_make_severity_icon(sev))
                item_sev.setToolTip(f"Severity: {sev}")
                item_sev.setData(Qt.UserRole, payload)
                self.setItem(r, 0, item_sev)

                # Col 1: Location (combined file:line for fast reference)
                item_loc = QTableWidgetItem(loc)
                item_loc.setFlags(item_loc.flags() & ~Qt.ItemIsEditable)
                item_loc.setData(Qt.UserRole, payload)
                item_loc.setToolTip(f"Open {loc}" if file_path else "No source location")
                self.setItem(r, 1, item_loc)

                # Col 2: Message
                item_msg = QTableWidgetItem(msg)
                item_msg.setFlags(item_msg.flags() & ~Qt.ItemIsEditable)
                item_msg.setData(Qt.UserRole, payload)
                item_msg.setToolTip(msg)
                self.setItem(r, 2, item_msg)

                # Col 3: Diagnostic Code
                item_code = QTableWidgetItem(code)
                item_code.setFlags(item_code.flags() & ~Qt.ItemIsEditable)
                item_code.setData(Qt.UserRole, payload)
                item_code.setForeground(QColor(theme_color(tokens.TEXT_SECONDARY)))
                self.setItem(r, 3, item_code)

                # Col 4: Source File
                item_file = QTableWidgetItem(file_path or "—")
                item_file.setFlags(item_file.flags() & ~Qt.ItemIsEditable)
                item_file.setData(Qt.UserRole, payload)
                item_file.setForeground(QColor(theme_color(tokens.TEXT_PRIMARY)))
                if file_path:
                    item_file.setToolTip(file_path)
                self.setItem(r, 4, item_file)

                # Col 5: Line
                item_line = QTableWidgetItem(str(line_no) if line_no > 0 else "—")
                item_line.setFlags(item_line.flags() & ~Qt.ItemIsEditable)
                item_line.setData(Qt.UserRole, payload)
                item_line.setForeground(QColor(theme_color(tokens.TEXT_MUTED)))
                self.setItem(r, 5, item_line)
        finally:
            self.setUpdatesEnabled(True)

    @Slot(QModelIndex)
    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = index.row()
        if row < 0 or row >= self.rowCount():
            return
        item = self.item(row, index.column()) or self.item(row, 1) or self.item(row, 4)
        if item is not None:
            data = item.data(Qt.UserRole)
            if isinstance(data, tuple) and len(data) == 2:
                file_path, line = data
                if isinstance(file_path, str) and file_path:
                    self.openLocationRequested.emit(file_path, int(line) if isinstance(line, int) else 0)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            index = self.currentIndex()
            if index.isValid():
                self._on_row_double_clicked(index)
                event.accept()
                return
        super().keyPressEvent(event)
