"""Settings view for Studio UX v2 (spec §4.9, WI-4.10).

Comprehensive settings editor with sections for Engine, Paths, Models,
Hosted Providers, Privacy & Egress, Storage, and Appearance.
Writes to user_settings_path(), calls reset_settings_cache(), and emits settingsChanged.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from src.gameforge_ide.core.settings import (
    PINNED_ENGINE,
    discover_engines,
    engine_version,
    get_settings,
    reset_settings_cache,
    user_settings_path,
)

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """Studio settings view with sectioned form."""

    settingsChanged = Signal()

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsView")
        self.setAccessibleName("GameForge Settings View")

        self._workspace = Path(workspace_root or Path.cwd()).resolve()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── Header ───────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(tokens.SPACE_MD)

        lbl_title = QLabel("Settings", self)
        lbl_title.setObjectName("lblSettingsTitle")
        lbl_title.setAccessibleName("Settings title")
        lbl_title.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_HEADING}px; font-weight: 700;"
        )
        header.addWidget(lbl_title)

        header.addStretch(1)

        self._btn_save = QPushButton("Save Settings", self)
        self._btn_save.setObjectName("btnSettingsSave")
        self._btn_save.setAccessibleName("Save settings to disk")
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.setStyleSheet(
            f"QPushButton#{self._btn_save.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton#{self._btn_save.objectName()}:hover {{ background-color: {tokens.ACCENT_HOVER}; }}"
        )
        self._btn_save.clicked.connect(self.save_settings)
        header.addWidget(self._btn_save)

        main_layout.addLayout(header)

        # ── Scroll Area for sections ─────────────────────────────────────────
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {tokens.BG_ROOT}; border: none; }}"
        )

        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 16, 0)
        content_layout.setSpacing(tokens.SPACE_LG)

        # 1. Engine Section
        sec_engine = self._build_engine_section()
        content_layout.addWidget(sec_engine)

        # 2. Paths Section
        sec_paths = self._build_paths_section()
        content_layout.addWidget(sec_paths)

        # 3. Models Section
        sec_models = self._build_models_section()
        content_layout.addWidget(sec_models)

        # 4. Storage & Appearance Section
        sec_app = self._build_appearance_section()
        content_layout.addWidget(sec_app)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        self.load_settings()

    # ── Section Builders ─────────────────────────────────────────────────────

    def _build_engine_section(self) -> QGroupBox:
        box = QGroupBox("Unreal Engine", self)
        box.setObjectName("groupSettingsEngine")
        box.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(box)

        form = QFormLayout()

        self._combo_detected_engine = QComboBox(box)
        self._combo_detected_engine.setObjectName("settingsDetectedEngineCombo")
        self._combo_detected_engine.setAccessibleName("Select detected engine installation")
        detected = discover_engines()
        for inst in detected:
            self._combo_detected_engine.addItem(f"UE {inst.version} ({inst.source}) — {inst.root}", str(inst.root))
        self._combo_detected_engine.addItem("Custom path...", "")
        self._combo_detected_engine.currentIndexChanged.connect(self._on_engine_combo_changed)
        form.addRow("Detected:", self._combo_detected_engine)

        path_row = QHBoxLayout()
        self._engine_path_input = QLineEdit(box)
        self._engine_path_input.setObjectName("settingsEnginePathInput")
        self._engine_path_input.setAccessibleName("Engine root path override")
        self._engine_path_input.textChanged.connect(self._validate_engine_path)
        path_row.addWidget(self._engine_path_input, 1)

        btn_browse = QPushButton("Browse...", box)
        btn_browse.clicked.connect(self._browse_engine)
        path_row.addWidget(btn_browse)
        form.addRow("Engine Root:", path_row)

        layout.addLayout(form)

        self._lbl_engine_status = QLabel(box)
        self._lbl_engine_status.setObjectName("lblSettingsEngineStatus")
        layout.addWidget(self._lbl_engine_status)

        return box

    def _build_paths_section(self) -> QGroupBox:
        box = QGroupBox("Directories & Storage", self)
        box.setObjectName("groupSettingsPaths")
        box.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(box)

        form = QFormLayout()

        # Projects Root
        p_row = QHBoxLayout()
        self._projects_root_input = QLineEdit(box)
        self._projects_root_input.setObjectName("settingsProjectsRootInput")
        self._projects_root_input.setAccessibleName("Projects storage directory")
        p_row.addWidget(self._projects_root_input, 1)
        btn_browse_proj = QPushButton("Browse...", box)
        btn_browse_proj.clicked.connect(self._browse_projects)
        p_row.addWidget(btn_browse_proj)
        form.addRow("Projects Root:", p_row)

        # Artifacts Root
        a_row = QHBoxLayout()
        self._artifacts_root_input = QLineEdit(box)
        self._artifacts_root_input.setObjectName("settingsArtifactsRootInput")
        self._artifacts_root_input.setAccessibleName("Artifacts storage directory")
        a_row.addWidget(self._artifacts_root_input, 1)
        btn_browse_art = QPushButton("Browse...", box)
        btn_browse_art.clicked.connect(self._browse_artifacts)
        a_row.addWidget(btn_browse_art)
        form.addRow("Artifacts Root:", a_row)

        # Ollama URL
        self._ollama_url_input = QLineEdit(box)
        self._ollama_url_input.setObjectName("settingsOllamaUrlInput")
        self._ollama_url_input.setAccessibleName("Ollama service endpoint URL")
        form.addRow("Ollama URL:", self._ollama_url_input)

        layout.addLayout(form)
        return box

    def _build_models_section(self) -> QGroupBox:
        box = QGroupBox("Model Routing", self)
        box.setObjectName("groupSettingsModels")
        box.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(box)

        self._models_table = QTableWidget(box)
        self._models_table.setObjectName("settingsModelsTable")
        self._models_table.setAccessibleName("Model routing configuration table")
        self._models_table.setColumnCount(2)
        self._models_table.setHorizontalHeaderLabels(["Role", "Model Tag"])
        self._models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._models_table.setStyleSheet(
            f"QTableWidget#{self._models_table.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        layout.addWidget(self._models_table)

        return box

    def _build_appearance_section(self) -> QGroupBox:
        box = QGroupBox("Appearance", self)
        box.setObjectName("groupSettingsAppearance")
        box.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(box)

        form = QFormLayout()

        self._theme_combo = QComboBox(box)
        self._theme_combo.setObjectName("settingsThemeCombo")
        self._theme_combo.setAccessibleName("IDE Theme selection")
        self._theme_combo.addItems(["Studio Dark", "Studio Light"])
        form.addRow("Theme:", self._theme_combo)

        self._font_scale_spin = QSpinBox(box)
        self._font_scale_spin.setObjectName("settingsFontScaleSpin")
        self._font_scale_spin.setAccessibleName("UI font scaling percentage")
        self._font_scale_spin.setRange(90, 150)
        self._font_scale_spin.setSingleStep(5)
        self._font_scale_spin.setValue(100)
        self._font_scale_spin.setSuffix("%")
        form.addRow("Font Scale:", self._font_scale_spin)

        layout.addLayout(form)
        return box

    def _group_box_style(self) -> str:
        return (
            f"QGroupBox {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  margin-top: 20px; font-weight: bold; font-size: {tokens.FONT_BODY}px;"
            f"  color: {tokens.TEXT_PRIMARY}; padding: 16px;"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin; subcontrol-position: top left;"
            f"  left: 12px; padding: 0 4px;"
            f"}}"
        )

    # ── Browse Slots ─────────────────────────────────────────────────────────

    def _browse_engine(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Unreal Engine Root")
        if folder:
            self._engine_path_input.setText(folder)

    def _browse_projects(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Projects Root")
        if folder:
            self._projects_root_input.setText(folder)

    def _browse_artifacts(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Artifacts Root")
        if folder:
            self._artifacts_root_input.setText(folder)

    def _on_engine_combo_changed(self) -> None:
        data = self._combo_detected_engine.currentData()
        if data:
            self._engine_path_input.setText(data)

    def _validate_engine_path(self) -> None:
        p = Path(self._engine_path_input.text().strip())
        if not p.is_dir():
            self._lbl_engine_status.setText(f"<span style='color: {tokens.ACCENT_ERROR};'>Directory does not exist.</span>")
            return
        ver = engine_version(p)
        if ver:
            self._lbl_engine_status.setText(
                f"<span style='color: {tokens.ACCENT_SUCCESS};'>✓ Detected UE {ver[0]} (CL {ver[1]})</span>"
            )
        else:
            self._lbl_engine_status.setText(
                f"<span style='color: {tokens.ACCENT_WARNING};'>UnrealEditor.exe missing or invalid build.</span>"
            )

    # ── Data Load & Save ─────────────────────────────────────────────────────

    def load_settings(self) -> None:
        s = get_settings()

        # Engine
        if s.engine:
            self._engine_path_input.setText(str(s.engine.root))
        else:
            self._engine_path_input.setText("")

        # Paths
        self._projects_root_input.setText(str(s.projects_root))
        self._artifacts_root_input.setText(str(s.artifacts_root))
        self._ollama_url_input.setText(str(s.ollama_url))

        # Models
        self._models_table.setRowCount(len(s.models))
        for row, (role, model) in enumerate(sorted(s.models.items())):
            self._models_table.setItem(row, 0, QTableWidgetItem(role))
            self._models_table.setItem(row, 1, QTableWidgetItem(model))

    @Slot()
    def save_settings(self) -> None:
        cfg_path = user_settings_path()
        if not cfg_path:
            logger.error("user_settings_path returned None")
            return

        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if cfg_path.is_file():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        # Update fields
        eng = self._engine_path_input.text().strip()
        if eng:
            data["engine_root"] = eng

        proj = self._projects_root_input.text().strip()
        if proj:
            data["projects_root"] = proj

        art = self._artifacts_root_input.text().strip()
        if art:
            data["artifacts_root"] = art

        ollama = self._ollama_url_input.text().strip()
        if ollama:
            data["ollama_url"] = ollama

        # Models
        models: Dict[str, str] = {}
        for row in range(self._models_table.rowCount()):
            r_item = self._models_table.item(row, 0)
            m_item = self._models_table.item(row, 1)
            if r_item and m_item:
                models[r_item.text()] = m_item.text()
        if models:
            data["models"] = models

        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        reset_settings_cache()
        self.settingsChanged.emit()
