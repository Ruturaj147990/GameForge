"""GameForge IDE — Workspace Explorer Panel.

Native file-system tree view bound directly to ToolService (no HTTP).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

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
    open_folder_requested = Signal()

    def __init__(self, tool_service: ToolService, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._tools = tool_service
        self._workspace = workspace_root
        self._build_ui()
        QTimer.singleShot(200, self._populate_root)

    def set_workspace(self, new_workspace: Path, tool_service: Optional[ToolService] = None) -> None:
        """Switch active workspace directory and reload tree."""
        if tool_service is not None:
            self._tools = tool_service
        self._workspace = Path(new_workspace).resolve()
        self._populate_root()

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

        btn_open = QPushButton("📂")
        btn_open.setObjectName("btn_explorer_open")
        btn_open.setFixedSize(24, 24)
        btn_open.setToolTip("Open Folder / Switch Workspace…")
        btn_open.clicked.connect(self.open_folder_requested.emit)
        hdr_layout.addWidget(btn_open)

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

    # Large folders (Blueprint v2 §8.1/§9): the first SYNC_BATCH entries appear immediately, the rest
    # are appended in timer batches so the UI thread never blocks, and at most MAX_ITEMS rows are
    # materialised per folder to bound memory. os.scandir entries carry cached metadata on Windows,
    # so no extra stat call is made per file.
    SYNC_BATCH = 500
    ASYNC_BATCH = 500
    MAX_ITEMS = 5000
    SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", ".agents"}

    def _populate_children(self, parent_item: QTreeWidgetItem, dir_path: Path) -> None:
        """Populate one directory level (called lazily on expand)."""
        for i in reversed(range(parent_item.childCount())):
            child = parent_item.child(i)
            if child.data(0, Qt.UserRole + 1) == "placeholder":
                parent_item.removeChild(child)
        try:
            with os.scandir(dir_path) as it:
                entries = [e for e in it if e.name not in self.SKIP]
        except OSError:
            return
        entries.sort(key=lambda e: (not _is_dir(e), e.name.lower()))
        total = len(entries)
        shown = entries[: self.MAX_ITEMS]
        self._add_entries(parent_item, shown[: self.SYNC_BATCH])
        rest = shown[self.SYNC_BATCH:]
        if rest:
            self._schedule_batches(parent_item, rest, total)
        elif total > self.MAX_ITEMS:
            self._add_more_marker(parent_item, total)
        self._status_lbl.setText(f"{total} items in {dir_path.name}/")

    def _schedule_batches(self, parent_item: QTreeWidgetItem, remaining: list, total: int) -> None:
        def step():
            try:
                parent_item.text(0)  # raises if the item was deleted (tree cleared)
            except RuntimeError:
                return
            batch, rest = remaining[: self.ASYNC_BATCH], remaining[self.ASYNC_BATCH:]
            self._add_entries(parent_item, batch)
            if rest:
                remaining[:] = rest
                QTimer.singleShot(0, step)
            elif total > self.MAX_ITEMS:
                self._add_more_marker(parent_item, total)
        QTimer.singleShot(0, step)

    def _add_more_marker(self, parent_item: QTreeWidgetItem, total: int) -> None:
        more = QTreeWidgetItem([f"… {total - self.MAX_ITEMS} more items (use search or open a subfolder)"])
        more.setData(0, Qt.UserRole + 1, "more")
        more.setFlags(Qt.ItemIsEnabled)
        parent_item.addChild(more)

    def _add_entries(self, parent_item: QTreeWidgetItem, entries: list) -> None:
        items = []
        for entry in entries:
            item = QTreeWidgetItem([entry.name])
            item.setData(0, Qt.UserRole, entry.path)
            if _is_dir(entry):
                item.setData(0, Qt.UserRole + 1, "dir")
                placeholder = QTreeWidgetItem(["…"])
                placeholder.setData(0, Qt.UserRole + 1, "placeholder")
                item.addChild(placeholder)
            else:
                item.setData(0, Qt.UserRole + 1, "file")
                item.setToolTip(0, entry.path)
                try:
                    item.setData(0, Qt.StatusTipRole, _human_size(entry.stat().st_size))
                except OSError:
                    pass
            items.append(item)
        parent_item.addChildren(items)

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


def _is_dir(entry) -> bool:
    try:
        return entry.is_dir()
    except OSError:
        return False


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
