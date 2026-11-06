"""GameForge IDE — Workspace Explorer Panel.

Native file-system tree view bound directly to ToolService (no HTTP).
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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
from ..styles import tokens


@lru_cache(maxsize=32)
def _make_type_icon(label: str, bg_color: str, fg_color: str = "#ffffff") -> QIcon:
    """Generate a sharp, high-contrast 16x16 badge icon for file types."""
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(bg_color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 1, 16, 14, 3, 3)
    p.setPen(QColor(fg_color))
    font = p.font()
    font.setPixelSize(7 if len(label) > 2 else 8)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, label)
    p.end()
    return QIcon(pm)


def _get_entry_icon(name: str, is_dir: bool) -> QIcon:
    """Return crisp icon badge for directory or specific file type."""
    if is_dir:
        return _make_type_icon("DIR", tokens.BG_ACTIVE, tokens.ACCENT_PRIMARY)
    lower = name.lower()
    if lower.endswith((".cpp", ".cxx", ".cc")):
        return _make_type_icon("C++", tokens.ACCENT_PRIMARY)
    if lower.endswith((".h", ".hpp", ".inl")):
        return _make_type_icon(".H", tokens.ACCENT_HOVER)
    if lower.endswith(".py"):
        return _make_type_icon("PY", tokens.ACCENT_SUCCESS, tokens.BG_ROOT)
    if lower.endswith((".uproject", ".uplugin")):
        return _make_type_icon("UE", tokens.ACCENT_WARNING, tokens.BG_ROOT)
    if lower.endswith((".umap", ".uasset")):
        return _make_type_icon("MAP" if lower.endswith(".umap") else "AST", tokens.ACCENT_WARNING, tokens.BG_ROOT)
    if lower.endswith((".json", ".ini", ".cfg", ".toml", ".yaml", ".yml")):
        return _make_type_icon("{}", tokens.BORDER_FOCUS)
    if lower.endswith((".md", ".txt", ".rst")):
        return _make_type_icon("MD", tokens.BG_ACTIVE, tokens.TEXT_SECONDARY)
    if lower.endswith((".hlsl", ".usf", ".ush")):
        return _make_type_icon("FX", tokens.ACCENT_HOVER)
    if lower.endswith((".bat", ".ps1", ".sh", ".cmd")):
        return _make_type_icon("CMD", tokens.ACCENT_ERROR)
    return _make_type_icon("FILE", tokens.BG_SURFACE, tokens.TEXT_MUTED)


class ExplorerPanel(QWidget):
    """Workspace file-system explorer with lazy directory expansion."""

    file_selected = Signal(str)   # absolute path of selected file
    open_folder_requested = Signal()

    def __init__(self, tool_service: ToolService, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("explorerPanel")
        self.setAccessibleName("Workspace file explorer")
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
        header.setObjectName("panel_header")
        header.setStyleSheet(f"background: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};")
        header.setFixedHeight(36)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("📁  Explorer")
        lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600; letter-spacing: 0.6px;")
        hdr_layout.addWidget(lbl)
        hdr_layout.addStretch()

        btn_refresh = QPushButton("↻")
        btn_refresh.setObjectName("btn_explorer_refresh")
        btn_refresh.setAccessibleName("Refresh workspace files")
        btn_refresh.setFixedSize(24, 24)
        btn_refresh.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 0px; font-size: 14px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        btn_refresh.setToolTip("Refresh workspace tree")
        btn_refresh.clicked.connect(self._populate_root)
        hdr_layout.addWidget(btn_refresh)
        layout.addWidget(header)

        # Search bar
        self._search = QLineEdit()
        self._search.setObjectName("explorer_search")
        self._search.setAccessibleName("Filter files")
        self._search.setPlaceholderText("Search files…")
        self._search.setFixedHeight(30)
        self._search.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px 8px; font-size: {tokens.FONT_BODY}px; margin: 4px 6px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {tokens.BORDER_FOCUS}; }}"
        )
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setObjectName("explorer_tree")
        self._tree.setAccessibleName("File hierarchy tree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setStyleSheet(
            f"QTreeWidget {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  padding: 2px 4px;"
            f"}}"
            f"QTreeWidget::item {{"
            f"  padding: 3px 2px;"
            f"  border-radius: 4px;"
            f"}}"
            f"QTreeWidget::item:hover {{ background-color: {tokens.BG_HOVER}; }}"
            f"QTreeWidget::item:selected {{ background-color: {tokens.BG_ACTIVE}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        self._tree.itemExpanded.connect(self._on_expand)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._tree, 1)

        # Bottom status
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; padding: 4px 8px; background: {tokens.BG_PANEL};")
        layout.addWidget(self._status_lbl)

    # ── Tree Population ─────────────────────────────────────────────────────

    def _populate_root(self) -> None:
        self._tree.clear()
        root_item = QTreeWidgetItem([self._workspace.name])
        root_item.setIcon(0, _get_entry_icon(self._workspace.name, is_dir=True))
        root_item.setData(0, Qt.UserRole, str(self._workspace))
        root_item.setData(0, Qt.UserRole + 1, "dir")
        root_item.setToolTip(0, str(self._workspace))
        self._tree.addTopLevelItem(root_item)
        self._populate_children(root_item, self._workspace)
        root_item.setExpanded(True)

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
        self._status_lbl.setText(f"{total} item{'' if total == 1 else 's'} in {dir_path.name}/")

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
            is_directory = _is_dir(entry)
            item = QTreeWidgetItem([entry.name])
            item.setIcon(0, _get_entry_icon(entry.name, is_dir=is_directory))
            item.setData(0, Qt.UserRole, entry.path)
            if is_directory:
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
                if query and child_has_match:
                    child.setExpanded(True)
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
