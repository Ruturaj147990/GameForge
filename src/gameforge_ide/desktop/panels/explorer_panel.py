"""GameForge IDE — Workspace Explorer Panel.

Native file-system tree view bound directly to ToolService (no HTTP).
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.tool_service import ToolService


class ExplorerPanel(QWidget):
    """Workspace file-system explorer with lazy directory expansion."""

    file_selected = Signal(str)   # absolute path of selected file

    def __init__(self, tool_service: ToolService, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._tools = tool_service
        self._workspace = workspace_root
        self._build_ui()
        QTimer.singleShot(200, self._populate_root)

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #0d0f14; border-bottom: 1px solid #2a2f45;")
        header.setFixedHeight(36)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("📁  Explorer")
        lbl.setStyleSheet("color: #8891aa; font-size: 11px; font-weight: 600; letter-spacing: 0.6px;")
        hdr_layout.addWidget(lbl)
        hdr_layout.addStretch()

        btn_refresh = QPushButton("↻")
        btn_refresh.setObjectName("btn_explorer_refresh")
        btn_refresh.setFixedSize(24, 24)
        btn_refresh.setToolTip("Refresh workspace tree")
        btn_refresh.clicked.connect(self._populate_root)
        hdr_layout.addWidget(btn_refresh)
        layout.addWidget(header)

        # Search bar
        self._search = QLineEdit()
        self._search.setObjectName("explorer_search")
        self._search.setPlaceholderText("Search files…")
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setObjectName("explorer_tree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.itemExpanded.connect(self._on_expand)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._tree, 1)

        # Bottom status
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #8891aa; font-size: 10px; padding: 2px 8px;")
        layout.addWidget(self._status_lbl)

    # ── Tree Population ─────────────────────────────────────────────────────

    def _populate_root(self) -> None:
        self._tree.clear()
        root_item = QTreeWidgetItem([self._workspace.name])
        root_item.setData(0, Qt.UserRole, str(self._workspace))
        root_item.setData(0, Qt.UserRole + 1, "dir")
        root_item.setToolTip(0, str(self._workspace))
        self._tree.addTopLevelItem(root_item)
        self._populate_children(root_item, self._workspace)
        root_item.setExpanded(True)

    def _populate_children(self, parent_item: QTreeWidgetItem, dir_path: Path) -> None:
        """Populate one directory level (called lazily on expand)."""
        # Remove placeholder
        for i in reversed(range(parent_item.childCount())):
            child = parent_item.child(i)
            if child.data(0, Qt.UserRole + 1) == "placeholder":
                parent_item.removeChild(child)

        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        # Skip hidden and virtual env folders at root
        SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", ".agents"}
        for entry in entries:
            if entry.name in SKIP:
                continue
            item = QTreeWidgetItem([entry.name])
            item.setData(0, Qt.UserRole, str(entry))
            if entry.is_dir():
                item.setData(0, Qt.UserRole + 1, "dir")
                # Placeholder so expand arrow appears
                placeholder = QTreeWidgetItem(["…"])
                placeholder.setData(0, Qt.UserRole + 1, "placeholder")
                item.addChild(placeholder)
            else:
                item.setData(0, Qt.UserRole + 1, "file")
                item.setToolTip(0, str(entry))
                size = entry.stat().st_size if entry.exists() else 0
                item.setData(0, Qt.StatusTipRole, _human_size(size))
            parent_item.addChild(item)

        count = parent_item.childCount()
        self._status_lbl.setText(f"{count} items in {dir_path.name}/")

    @Slot(QTreeWidgetItem)
    def _on_expand(self, item: QTreeWidgetItem) -> None:
        path = Path(item.data(0, Qt.UserRole) or "")
        if item.data(0, Qt.UserRole + 1) == "dir" and path.is_dir():
            # Only re-populate if showing placeholder
            if item.childCount() == 1 and item.child(0).data(0, Qt.UserRole + 1) == "placeholder":
                self._populate_children(item, path)

    @Slot(QTreeWidgetItem, int)
    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.data(0, Qt.UserRole + 1) == "file":
            path = item.data(0, Qt.UserRole)
            if path:
                self.file_selected.emit(path)

    @Slot(str)
    def _on_search(self, text: str) -> None:
        text = text.strip().lower()
        self._filter_items(self._tree.invisibleRootItem(), text)

    def _filter_items(self, parent: QTreeWidgetItem, query: str) -> bool:
        visible_child = False
        for i in range(parent.childCount()):
            child = parent.child(i)
            name = child.text(0).lower()
            child_has_match = self._filter_items(child, query)
            if not query or query in name or child_has_match:
                child.setHidden(False)
                visible_child = True
            else:
                child.setHidden(True)
        return visible_child


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
