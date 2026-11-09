"""Assets view for Studio UX v2 (spec §4.7, WI-4.10).

QTableView over AssetRegistry.search() with filters by type and stage,
and a detail drawer showing lifecycle events, thumbnail preview, and evidence.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QObject, QRect, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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
from ..styles.dark_theme import theme_color, theme_stylesheet
from ...backend.assets.registry import ASSET_TYPES, STAGES, AssetRegistry

logger = logging.getLogger(__name__)

COLUMNS = ["Name", "Type", "Stage", "Size", "License", "Provenance", "Backend", "Updated"]


def _calc_size(row: Dict[str, Any], workspace: Optional[Path]) -> Tuple[int, str]:
    """Return numeric size and human-readable string for an asset row."""
    art = row.get("artifact_path")
    if art:
        p = Path(art)
        if not p.is_absolute() and workspace:
            p = workspace / art
        if p.is_file():
            try:
                sz = p.stat().st_size
                if sz < 1024:
                    return sz, f"{sz} B"
                elif sz < 1024 * 1024:
                    return sz, f"{sz / 1024:.1f} KB"
                else:
                    return sz, f"{sz / (1024 * 1024):.1f} MB"
            except Exception:
                pass

    spec = row.get("spec")
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception:
            spec = {}
    if isinstance(spec, dict):
        if "poly_count" in spec:
            cnt = int(spec["poly_count"])
            return cnt, f"{cnt:,} polys"
        if "resolution" in spec:
            res = int(spec["resolution"])
            return res, f"{res}x{res}"

    return 0, "—"


class AssetsTableModel(QAbstractTableModel):
    """Table model wrapping AssetRegistry rows with sortable columns."""

    def __init__(self, workspace: Optional[Path] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._rows: List[Dict[str, Any]] = []

    def set_workspace(self, workspace: Optional[Path]) -> None:
        self._workspace = workspace

    def set_rows(self, rows: List[Any]) -> None:
        self.beginResetModel()
        processed: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            sz_bytes, sz_disp = _calc_size(d, self._workspace)
            d["_size_bytes"] = sz_bytes
            d["_size_display"] = sz_disp
            processed.append(d)
        self._rows = processed
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
                return row.get("_size_display") or _calc_size(row, self._workspace)[1]
            elif col == 4:
                return row.get("license", "")
            elif col == 5:
                return row.get("provenance", "")
            elif col == 6:
                return row.get("backend", "")
            elif col == 7:
                ts = row.get("updated_at", 0)
                if ts:
                    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                return ""
        elif role == Qt.ForegroundRole:
            if col == 2:
                stage = row.get("stage", "")
                if stage == "PROMOTE":
                    return QColor(theme_color(tokens.ACCENT_SUCCESS))
                elif stage in ("QUARANTINE", "REJECTED"):
                    return QColor(theme_color(tokens.ACCENT_ERROR))
                elif stage in ("VALIDATE", "ENGINE_VERIFY"):
                    return QColor(theme_color(tokens.ACCENT_PRIMARY))
            elif col == 3:
                return QColor(theme_color(tokens.TEXT_SECONDARY))
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
            3: "size",
            4: "license",
            5: "provenance",
            6: "backend",
            7: "updated_at",
        }
        key = col_key_map.get(column, "name")
        reverse = (order == Qt.DescendingOrder)

        def _sort_key(r: Dict[str, Any]) -> Any:
            if key == "size":
                return r.get("_size_bytes", _calc_size(r, self._workspace)[0])
            elif key == "updated_at":
                return r.get("updated_at", 0) or 0
            else:
                return str(r.get(key, "")).lower()

        self._rows.sort(key=_sort_key, reverse=reverse)
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
        self._search_input.setToolTip("Search registered assets by keyword or tag")
        self._search_input.setPlaceholderText("Search assets...")
        self._search_input.setStyleSheet(
            f"QLineEdit#{self._search_input.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"  min-width: 180px;"
            f"}}"
            f"QLineEdit#{self._search_input.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
            f"}}"
        )
        self._search_input.textChanged.connect(self._on_filter_changed)
        header.addWidget(self._search_input)

        # Type filter
        self._type_combo = QComboBox(self)
        self._type_combo.setObjectName("assetsTypeCombo")
        self._type_combo.setAccessibleName("Filter by asset type")
        self._type_combo.setToolTip("Filter table rows by asset type")
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
        self._stage_combo.setToolTip("Filter table rows by lifecycle stage")
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
        self._btn_refresh.setToolTip("Reload assets from SQLite registry")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton#{self._btn_refresh.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_refresh.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
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
        self._model = AssetsTableModel(workspace=self._workspace, parent=self)
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
            f"  gridline-color: {tokens.BORDER};"
            f"  selection-background-color: {tokens.BG_ACTIVE}; selection-color: {tokens.TEXT_PRIMARY};"
            f"}}"
            f"QTableView#{self._table.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; padding: 4px {tokens.SPACE_SM}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;"
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

        # Thumbnail Preview Widget
        self._lbl_thumbnail = QLabel(detail_widget)
        self._lbl_thumbnail.setObjectName("assetsThumbnailPreview")
        self._lbl_thumbnail.setAccessibleName("Asset thumbnail preview")
        self._lbl_thumbnail.setAlignment(Qt.AlignCenter)
        self._lbl_thumbnail.setFixedHeight(120)
        self._lbl_thumbnail.setStyleSheet(
            f"QLabel#{self._lbl_thumbnail.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  font-size: {tokens.FONT_HEADING}px;"
            f"}}"
        )
        self._lbl_thumbnail.setText("No Asset Selected")
        detail_layout.addWidget(self._lbl_thumbnail)

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
            f"QTextEdit#{self._detail_text.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
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
        self._model.set_workspace(self._workspace)
        self._registry = AssetRegistry(self._workspace)
        self.refresh_assets()

    def set_project(self, project_name: str, project_dir: Optional[Path] = None) -> None:
        """Update active project context and workspace registry."""
        self._current_project = project_name
        p_dir = project_dir or self._workspace
        if p_dir and Path(p_dir).is_dir():
            self._workspace = Path(p_dir).resolve()
            self._model.set_workspace(self._workspace)
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
        self._lbl_thumbnail.setText("No Asset Selected")
        self._lbl_thumbnail.setPixmap(QPixmap())

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
        asset_type = row.get("asset_type", "")
        self._lbl_detail_header.setText(f"Asset: {name} ({asset_type})")

        # Update thumbnail preview
        thumb_loaded = False
        img_cands = [row.get("preview_path"), row.get("artifact_path")]
        for cand in img_cands:
            if cand:
                p = Path(cand)
                if not p.is_absolute():
                    p = self._workspace / cand
                if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                    pm = QPixmap(str(p))
                    if not pm.isNull():
                        scaled = pm.scaled(
                            QSize(220, 110),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                        self._lbl_thumbnail.setPixmap(scaled)
                        thumb_loaded = True
                        break

        if not thumb_loaded:
            type_icons = {
                "mesh": "🧊 Static Mesh",
                "skeletal_mesh": "🏃 Skeletal Mesh",
                "texture": "🖼 Texture",
                "material": "🎨 Material",
                "audio": "🔊 Audio",
                "sound": "🔊 Sound",
                "animation": "🎬 Animation",
                "vfx": "✨ Niagara VFX",
                "level": "🗺 Level Map",
                "blueprint": "📐 Blueprint",
            }
            symbol = type_icons.get(asset_type, "📦 Asset")
            self._lbl_thumbnail.setPixmap(QPixmap())
            self._lbl_thumbnail.setText(f"{symbol}\n{name}")

        sz_num, sz_str = _calc_size(row, self._workspace)
        lines = [
            f"ID:          {asset_id}",
            f"Name:        {name}",
            f"Type:        {asset_type}",
            f"Stage:       {row.get('stage', '')}",
            f"Size:        {sz_str}",
            f"Provenance:  {row.get('provenance', '')}",
            f"License:     {row.get('license', '')}",
            f"Backend:     {row.get('backend', '')} (v{row.get('backend_version', '')})",
            f"Purpose:     {row.get('purpose', '')}",
            f"Tags:        {row.get('tags', '') or '—'}",
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
