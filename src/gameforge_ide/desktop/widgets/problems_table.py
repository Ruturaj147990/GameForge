"""ProblemsTable: diagnostics table for compiler, automation, and scenario failures (spec §4.4, WI-4.7)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..styles import tokens


def _make_severity_icon(severity: str) -> QIcon:
    """Generate crisp high-contrast icon for Error, Warning, or Info."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    font = painter.font()
    font.setPointSize(9)
    font.setBold(True)
    painter.setFont(font)
    sev = severity.upper()
    if "ERR" in sev:
        painter.setPen(QColor(tokens.ACCENT_ERROR))
        painter.drawText(QRect(0, 0, 16, 16), Qt.AlignCenter, "✕")
    elif "WARN" in sev:
        painter.setPen(QColor(tokens.ACCENT_WARNING))
        painter.drawText(QRect(0, 0, 16, 16), Qt.AlignCenter, "▲")
    else:
        painter.setPen(QColor(tokens.ACCENT_PRIMARY))
        painter.drawText(QRect(0, 0, 16, 16), Qt.AlignCenter, "ℹ")
    painter.end()
    return QIcon(pixmap)


class ProblemsTable(QTableWidget):
    """Displays diagnostics with severity, file:line location, and message."""

    openLocationRequested = Signal(str, int)  # (file_path, line)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("buildProblemsTable")
        self.setAccessibleName("Build problems and diagnostics table")

        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(["Severity", "Location", "Message", "Code", "Source File", "Line"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)

        self.setStyleSheet(
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
        self.doubleClicked.connect(self._on_row_double_clicked)

    def set_problems(self, problems: List[Dict[str, Any]]) -> None:
        """Populate table with problem dicts."""
        self.setRowCount(len(problems))
        for r, p in enumerate(problems):
            sev = str(p.get("severity", "Error")).upper()
            file_path = str(p.get("file", ""))
            line_no = int(p.get("line", 0))
            loc = f"{file_path}:{line_no}" if file_path else "—"
            msg = str(p.get("message", ""))
            code = str(p.get("code") or p.get("error_code") or "—")

            # Col 0: Severity with icon
            item_sev = QTableWidgetItem(sev)
            item_sev.setFlags(item_sev.flags() & ~Qt.ItemIsEditable)
            col_str = tokens.ACCENT_ERROR if "ERR" in sev else (tokens.ACCENT_WARNING if "WARN" in sev else tokens.ACCENT_PRIMARY)
            item_sev.setForeground(QColor(col_str))
            item_sev.setIcon(_make_severity_icon(sev))
            item_sev.setToolTip(f"Severity: {sev}")
            item_sev.setData(Qt.UserRole, (file_path, line_no))
            self.setItem(r, 0, item_sev)

            # Col 1: Location (combined file:line for fast reference)
            item_loc = QTableWidgetItem(loc)
            item_loc.setFlags(item_loc.flags() & ~Qt.ItemIsEditable)
            item_loc.setData(Qt.UserRole, (file_path, line_no))
            item_loc.setToolTip(f"Open {loc}")
            self.setItem(r, 1, item_loc)

            # Col 2: Message
            item_msg = QTableWidgetItem(msg)
            item_msg.setFlags(item_msg.flags() & ~Qt.ItemIsEditable)
            item_msg.setData(Qt.UserRole, (file_path, line_no))
            item_msg.setToolTip(msg)
            self.setItem(r, 2, item_msg)

            # Col 3: Diagnostic Code
            item_code = QTableWidgetItem(code)
            item_code.setFlags(item_code.flags() & ~Qt.ItemIsEditable)
            item_code.setData(Qt.UserRole, (file_path, line_no))
            item_code.setForeground(QColor(tokens.TEXT_SECONDARY))
            self.setItem(r, 3, item_code)

            # Col 4: Source File
            item_file = QTableWidgetItem(file_path or "—")
            item_file.setFlags(item_file.flags() & ~Qt.ItemIsEditable)
            item_file.setData(Qt.UserRole, (file_path, line_no))
            item_file.setForeground(QColor(tokens.TEXT_PRIMARY))
            self.setItem(r, 4, item_file)

            # Col 5: Line
            item_line = QTableWidgetItem(str(line_no) if line_no else "—")
            item_line.setFlags(item_line.flags() & ~Qt.ItemIsEditable)
            item_line.setData(Qt.UserRole, (file_path, line_no))
            item_line.setForeground(QColor(tokens.TEXT_MUTED))
            self.setItem(r, 5, item_line)

    @Slot(QModelIndex)
    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        row = index.row()
        item = self.item(row, index.column()) or self.item(row, 1) or self.item(row, 4)
        if item:
            data = item.data(Qt.UserRole)
            if data and isinstance(data, tuple) and len(data) == 2:
                file_path, line = data
                if file_path:
                    self.openLocationRequested.emit(file_path, line)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            index = self.currentIndex()
            if index.isValid():
                self._on_row_double_clicked(index)
                event.accept()
                return
        super().keyPressEvent(event)
