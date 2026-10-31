"""ProblemsTable: diagnostics table for compiler, automation, and scenario failures (spec §4.4, WI-4.7)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..styles import tokens


class ProblemsTable(QTableWidget):
    """Displays diagnostics with severity, file:line location, and message."""

    openLocationRequested = Signal(str, int)  # (file_path, line)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("buildProblemsTable")
        self.setAccessibleName("Build problems and diagnostics table")

        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Severity", "Location", "Message"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)

        self.setStyleSheet(
            f"QTableWidget#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
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

            item_sev = QTableWidgetItem(sev)
            col_str = tokens.ACCENT_ERROR if "ERR" in sev else tokens.ACCENT_WARNING
            item_sev.setForeground(QColor(col_str))
            self.setItem(r, 0, item_sev)

            item_loc = QTableWidgetItem(loc)
            item_loc.setData(Qt.UserRole, (file_path, line_no))
            self.setItem(r, 1, item_loc)

            item_msg = QTableWidgetItem(msg)
            self.setItem(r, 2, item_msg)

    @Slot(QModelIndex)
    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        row = index.row()
        item = self.item(row, 1)
        if item:
            data = item.data(Qt.UserRole)
            if data and isinstance(data, tuple) and len(data) == 2:
                file_path, line = data
                if file_path:
                    self.openLocationRequested.emit(file_path, line)
