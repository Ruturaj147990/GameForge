"""GameForge IDE — Asset Registry Panel.

Visualizes and filters assets recorded in the workspace asset registry
(<workspace>/.gameforge/assets.db), including stage, provenance, hash,
and licensing info.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...backend.assets.registry import AssetRegistry


class AssetPanel(QWidget):
    """Panel displaying assets from SQLite registry with filtering and inspect."""

    asset_selected = Signal(str)

    def __init__(self, workspace_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workspace = Path(workspace_root).resolve()
        self._registry: Optional[AssetRegistry] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel("📦 Asset Registry")
        lbl_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #f5f3ff;")
        header.addWidget(lbl_title)
        header.addStretch()

        self._btn_refresh = QPushButton("🔄 Refresh")
        self._btn_refresh.setObjectName("btn_refresh_assets")
        self._btn_refresh.setStyleSheet(
            "QPushButton { background: #120f1d; border: 1px solid #231c34; border-radius: 4px; padding: 3px 8px; font-size: 11px; } "
            "QPushButton:hover { background: #1a1528; border-color: #7c3aed; }"
        )
        self._btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self._btn_refresh)
        layout.addLayout(header)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)

        self._search = QLineEdit()
        self._search.setObjectName("asset_search_input")
        self._search.setPlaceholderText("Filter assets…")
        self._search.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._search, 1)

        self._type_combo = QComboBox()
        self._type_combo.setObjectName("asset_type_filter")
        self._type_combo.addItems(["All Types", "static_mesh", "skeletal_mesh", "texture", "material", "audio", "vfx"])
        self._type_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._type_combo)
        layout.addLayout(filter_row)

        # Splitter between list and detail
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)

        # Assets list
        self._list = QListWidget()
        self._list.setObjectName("asset_list")
        self._list.setAlternatingRowColors(True)
        self._list.itemClicked.connect(self._on_item_clicked)
        splitter.addWidget(self._list)

        # Detail pane
        self._detail = QTextBrowser()
        self._detail.setObjectName("asset_detail_view")
        self._detail.setOpenExternalLinks(False)
        self._detail.setPlaceholderText("Select an asset to view provenance, stage, and license metadata.")
        splitter.addWidget(self._detail)

        splitter.setSizes([260, 160])
        layout.addWidget(splitter, 1)

        self.refresh()

    def set_workspace(self, workspace_root: Path) -> None:
        self._workspace = Path(workspace_root).resolve()
        self._registry = None
        self.refresh()

    def _ensure_registry(self) -> Optional[AssetRegistry]:
        db_path = self._workspace / ".gameforge" / "assets.db"
        if not db_path.exists():
            return None
        if self._registry is None:
            try:
                self._registry = AssetRegistry(self._workspace)
            except Exception:
                return None
        return self._registry

    @Slot()
    def refresh(self) -> None:
        self._list.clear()
        reg = self._ensure_registry()
        if not reg:
            item = QListWidgetItem("No registered assets yet.\n(Use /asset or /material in chat to create assets)")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            self._detail.setPlainText("Asset registry database (.gameforge/assets.db) has no entries.")
            return

        text = self._search.text().strip()
        t_filter = self._type_combo.currentText()
        asset_type = None if t_filter == "All Types" else t_filter

        try:
            records = reg.search(text=text, asset_type=asset_type)
        except Exception:
            records = []

        if not records:
            item = QListWidgetItem("No assets match filter.")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            self._detail.clear()
            return

        type_icons = {
            "static_mesh": "🧊",
            "skeletal_mesh": "🏃",
            "texture": "🖼",
            "material": "🎨",
            "audio": "🔊",
            "vfx": "✨",
        }

        for row in records:
            icon = type_icons.get(row["asset_type"], "📦")
            stage = row["stage"] or "SPEC"
            item_text = f"{icon} {row['name']}  [{stage}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, row["asset_id"])
            item.setToolTip(f"ID: {row['asset_id']}\nType: {row['asset_type']}\nStage: {stage}\nProvenance: {row['provenance']}")
            self._list.addItem(item)

    @Slot()
    def _on_filter_changed(self) -> None:
        self.refresh()

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        asset_id = item.data(Qt.UserRole)
        if not asset_id:
            return
        self.asset_selected.emit(asset_id)
        reg = self._ensure_registry()
        if not reg:
            return
        row = reg.get(asset_id)
        if not row:
            self._detail.setPlainText(f"Asset '{asset_id}' not found.")
            return

        history = reg.history(asset_id)
        deps = reg.dependencies(asset_id)

        lines = [
            f"=== {row['name']} ({row['asset_type']}) ===",
            f"ID:         {row['asset_id']}",
            f"Stage:      {row['stage']}",
            f"Purpose:    {row['purpose']}",
            f"Provenance: {row['provenance']} (backend: {row['backend']} {row['backend_version']})",
            f"License:    {row['license']}",
            f"Artifact:   {row['artifact_path'] or 'None'}",
            f"Unreal:     {row['unreal_path'] or 'None'}",
            f"Tags:       {row['tags'] or 'None'}",
            "",
            "--- Dependencies ---",
            ", ".join(deps) if deps else "None",
            "",
            "--- Lifecycle History ---",
        ]
        for ev in history:
            ok_mark = "✔" if ev["ok"] else "✘"
            lines.append(f"{ok_mark} {ev['stage']}: {ev['detail'] or 'done'}")

        self._detail.setPlainText("\n".join(lines))
