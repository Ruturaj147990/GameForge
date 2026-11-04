"""Assets view for Studio UX v2 (spec §4.7, WI-4.10).

QTableView over AssetRegistry.search() with filters by type and stage,
and a detail drawer showing lifecycle events and evidence.
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from src.gameforge_ide.backend.assets.registry import ASSET_TYPES, STAGES, AssetRegistry

logger = logging.getLogger(__name__)

COLUMNS = ["Name", "Type", "Stage", "Provenance", "License", "Backend", "Updated"]


class AssetsTableModel(QAbstractTableModel):
    """Table model wrapping AssetRegistry rows."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []

    def set_rows(self, rows: List[Any]) -> None:
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return row.get("name", "")
            elif col == 1:
                return row.get("asset_type", "")
            elif col == 2:
                return row.get("stage", "")
            elif col == 3:
                return row.get("provenance", "")
            elif col == 4:
                return row.get("license", "")
            elif col == 5:
                return row.get("backend", "")
            elif col == 6:
                ts = row.get("updated_at", 0)
                if ts:
                    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                return ""
        elif role == Qt.ForegroundRole:
            if col == 2:
                stage = row.get("stage", "")
                if stage == "PROMOTE":
                    return QColor(tokens.ACCENT_SUCCESS)
                elif stage in ("QUARANTINE", "REJECTED"):
                    return QColor(tokens.ACCENT_ERROR)
                elif stage in ("VALIDATE", "ENGINE_VERIFY"):
                    return QColor(tokens.ACCENT_PRIMARY)
        return None

    def get_row_dict(self, row_idx: int) -> Optional[Dict[str, Any]]:
        if 0 <= row_idx < len(self._rows):
            return self._rows[row_idx]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        self.beginResetModel()
        col_key_map = {
            0: "name",
            1: "asset_type",
            2: "stage",
            3: "provenance",
            4: "license",
            5: "backend",
            6: "updated_at",
        }
        key = col_key_map.get(column, "name")
        reverse = (order == Qt.DescendingOrder)
        self._rows.sort(
            key=lambda r: str(r.get(key, "")).lower() if key != "updated_at" else (r.get(key, 0) or 0),
            reverse=reverse,
        )
        self.endResetModel()


class AssetsView(QWidget):
    """Assets view for inspecting the workspace asset registry."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("assetsView")
        self.setAccessibleName("GameForge Assets View")

        self._workspace = Path(workspace_root or Path.cwd()).resolve()
        self._registry = AssetRegistry(self._workspace)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── Header ───────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(tokens.SPACE_MD)

        lbl_title = QLabel("Assets", self)
        lbl_title.setObjectName("lblAssetsTitle")
        lbl_title.setAccessibleName("Assets view title")
        lbl_title.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_HEADING}px; font-weight: 700;"
        )
        header.addWidget(lbl_title)

        header.addStretch(1)

        # Search bar
        self._search_input = QLineEdit(self)
        self._search_input.setObjectName("assetsSearchInput")
        self._search_input.setAccessibleName("Search assets by name or tag")
        self._search_input.setPlaceholderText("Search assets...")
        self._search_input.setStyleSheet(
            f"QLineEdit#{self._search_input.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"  min-width: 180px;"
            f"}}"
        )
        self._search_input.textChanged.connect(self._on_filter_changed)
        header.addWidget(self._search_input)

        # Type filter
        self._type_combo = QComboBox(self)
        self._type_combo.setObjectName("assetsTypeCombo")
        self._type_combo.setAccessibleName("Filter by asset type")
        self._type_combo.addItem("All Types", None)
        for t in ASSET_TYPES:
            self._type_combo.addItem(t, t)
        self._type_combo.setStyleSheet(
            f"QComboBox#{self._type_combo.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
        )
        self._type_combo.currentIndexChanged.connect(self._on_filter_changed)
        header.addWidget(self._type_combo)

        # Stage filter
        self._stage_combo = QComboBox(self)
        self._stage_combo.setObjectName("assetsStageCombo")
        self._stage_combo.setAccessibleName("Filter by asset stage")
        self._stage_combo.addItem("All Stages", None)
        for s in STAGES:
            self._stage_combo.addItem(s, s)
        self._stage_combo.setStyleSheet(
            f"QComboBox#{self._stage_combo.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
        )
        self._stage_combo.currentIndexChanged.connect(self._on_filter_changed)
        header.addWidget(self._stage_combo)

        # Refresh button
        self._btn_refresh = QPushButton("Refresh", self)
        self._btn_refresh.setObjectName("btnAssetsRefresh")
        self._btn_refresh.setAccessibleName("Refresh asset table")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton#{self._btn_refresh.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_refresh.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_refresh.clicked.connect(self.refresh_assets)
        header.addWidget(self._btn_refresh)

        main_layout.addLayout(header)

        # ── Summary Label ────────────────────────────────────────────────────
        self._lbl_summary = QLabel("0 assets registered.", self)
        self._lbl_summary.setObjectName("lblAssetsSummary")
        self._lbl_summary.setAccessibleName("Assets count summary")
        self._lbl_summary.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;"
        )
        main_layout.addWidget(self._lbl_summary)

        # ── Splitter: Table + Detail Drawer ──────────────────────────────────
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("assetsSplitter")

        # Table
        self._model = AssetsTableModel(self)
        self._table = QTableView(splitter)
        self._table.setObjectName("assetsTableView")
        self._table.setAccessibleName("Registered assets table")
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(COLUMNS)):
            self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableView#{self._table.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        self._table.clicked.connect(self._on_asset_selected)
        if self._table.selectionModel():
            self._table.selectionModel().currentChanged.connect(lambda cur, prev: self._on_asset_selected(cur))
        self._table.installEventFilter(self)
        splitter.addWidget(self._table)

        # Detail Drawer
        detail_widget = QWidget(splitter)
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(tokens.SPACE_SM)

        self._lbl_detail_header = QLabel("Select an asset to view details", detail_widget)
        self._lbl_detail_header.setObjectName("lblAssetsDetailHeader")
        self._lbl_detail_header.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;"
        )
        detail_layout.addWidget(self._lbl_detail_header)

        self._detail_text = QTextEdit(detail_widget)
        self._detail_text.setObjectName("assetsDetailText")
        self._detail_text.setAccessibleName("Asset details and history")
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(
            f"QTextEdit#{self._detail_text.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px; font-family: monospace; font-size: 11px;"
            f"}}"
        )
        detail_layout.addWidget(self._detail_text, 1)

        splitter.addWidget(detail_widget)
        splitter.setSizes([600, 400])
        main_layout.addWidget(splitter, 1)

        # Load initial
        self.refresh_assets()

    # ── Public API ───────────────────────────────────────────────────────────

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_assets()

    def set_workspace(self, workspace_root: Path | str) -> None:
        """Switch workspace and re-initialize registry."""
        self._workspace = Path(workspace_root).resolve()
        self._registry = AssetRegistry(self._workspace)
        self.refresh_assets()

    def set_project(self, project_name: str, project_dir: Optional[Path] = None) -> None:
        """Update active project context and workspace registry."""
        self._current_project = project_name
        p_dir = project_dir or self._workspace
        if p_dir and Path(p_dir).is_dir():
            self._workspace = Path(p_dir).resolve()
            self._registry = AssetRegistry(self._workspace)
        self.refresh_assets()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._table and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                index = self._table.currentIndex()
                if index.isValid():
                    self._on_asset_selected(index)
                    return True
        return super().eventFilter(watched, event)

    @Slot()
    def refresh_assets(self) -> None:
        """Search AssetRegistry with active filters and update table."""
        search_text = self._search_input.text().strip()
        asset_type = self._type_combo.currentData()
        stage = self._stage_combo.currentData()

        try:
            rows = self._registry.search(text=search_text, asset_type=asset_type, stage=stage)
        except Exception as e:
            logger.warning("Asset search failed: %s", e)
            rows = []

        self._model.set_rows(rows)
        self._lbl_summary.setText(f"{len(rows)} assets found.")
        self._detail_text.clear()
        self._lbl_detail_header.setText("Select an asset to view details")

    @Slot()
    def _on_filter_changed(self) -> None:
        self.refresh_assets()

    @Slot(QModelIndex)
    def _on_asset_selected(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = self._model.get_row_dict(index.row())
        if not row:
            return

        name = row.get("name", "")
        asset_id = row.get("asset_id", "")
        self._lbl_detail_header.setText(f"Asset: {name} ({row.get('asset_type', '')})")

        lines = [
            f"ID:          {asset_id}",
            f"Name:        {name}",
            f"Type:        {row.get('asset_type', '')}",
            f"Stage:       {row.get('stage', '')}",
            f"Provenance:  {row.get('provenance', '')}",
            f"License:     {row.get('license', '')}",
            f"Backend:     {row.get('backend', '')} (v{row.get('backend_version', '')})",
            f"Purpose:     {row.get('purpose', '')}",
            f"Tags:        {row.get('tags', '')}",
            f"Artifact:    {row.get('artifact_path', 'None')}",
            f"Unreal Path: {row.get('unreal_path', 'None')}",
            "",
            "═══ Lifecycle History ═══",
        ]

        try:
            history_rows = self._registry.history(asset_id)
            if history_rows:
                for h in history_rows:
                    dt = datetime.datetime.fromtimestamp(h["at"]).strftime("%H:%M:%S")
                    status = "OK" if h["ok"] else "FAIL"
                    lines.append(f"  [{dt}] {h['stage']} -> {status}: {h['detail']}")
            else:
                lines.append("  (No lifecycle history recorded)")
        except Exception as e:
            lines.append(f"  Failed to load history: {e}")

        self._detail_text.setPlainText("\n".join(lines))
