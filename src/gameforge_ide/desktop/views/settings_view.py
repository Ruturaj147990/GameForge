"""Settings view for Studio UX v2 (spec §4.9, WI-4.10).

Comprehensive settings editor with sections for Engine, Paths, Models,
Hosted Providers, Privacy & Egress, Storage, and Appearance.
Writes to user_settings_path(), calls reset_settings_cache(), and emits settingsChanged.
"""
from __future__ import annotations

import json
import logging
import os
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
        box = QGroupBox("Engine Discovery", self)
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
        box = QGroupBox("Project Storage", self)
        box.setObjectName("groupSettingsPaths")
        box.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(box)

        form = QFormLayout()

        # Projects Root
        p_row = QHBoxLayout()
        self._projects_root_input = QLineEdit(box)
        self._projects_root_input.setObjectName("settingsProjectsRootInput")
        self._projects_root_input.setAccessibleName("Projects storage directory")
        self._projects_root_input.textChanged.connect(self._validate_storage_paths)
        p_row.addWidget(self._projects_root_input, 1)
        btn_browse_proj = QPushButton("Browse...", box)
        btn_browse_proj.clicked.connect(self._browse_projects)
        p_row.addWidget(btn_browse_proj)
        form.addRow("Projects Root:", p_row)

        self._lbl_projects_status = QLabel(box)
        self._lbl_projects_status.setObjectName("lblSettingsProjectsStatus")
        form.addRow("", self._lbl_projects_status)

        # Artifacts Root
        a_row = QHBoxLayout()
        self._artifacts_root_input = QLineEdit(box)
        self._artifacts_root_input.setObjectName("settingsArtifactsRootInput")
        self._artifacts_root_input.setAccessibleName("Artifacts storage directory")
        self._artifacts_root_input.textChanged.connect(self._validate_storage_paths)
        a_row.addWidget(self._artifacts_root_input, 1)
        btn_browse_art = QPushButton("Browse...", box)
        btn_browse_art.clicked.connect(self._browse_artifacts)
        a_row.addWidget(btn_browse_art)
        form.addRow("Artifacts Root:", a_row)

        self._lbl_artifacts_status = QLabel(box)
        self._lbl_artifacts_status.setObjectName("lblSettingsArtifactsStatus")
        form.addRow("", self._lbl_artifacts_status)

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

        self._lbl_routing_source = QLabel(box)
        self._lbl_routing_source.setObjectName("lblSettingsRoutingSource")
        self._lbl_routing_source.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        layout.addWidget(self._lbl_routing_source)

        return box

    def _build_appearance_section(self) -> QGroupBox:
        box = QGroupBox("Appearance", self)
        box.setObjectName("groupSettingsAppearance")
        box.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(box)

        form = QFormLayout()
        form.setContentsMargins(12, 8, 12, 8)
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(16)

        self._theme_combo = QComboBox(box)
        self._theme_combo.setObjectName("settingsThemeCombo")
        self._theme_combo.setAccessibleName("IDE Theme selection")
        self._theme_combo.addItems(["Studio Dark", "Studio Light"])
        self._theme_combo.setMinimumHeight(32)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        form.addRow("Theme:", self._theme_combo)

        self._font_scale_spin = QSpinBox(box)
        self._font_scale_spin.setObjectName("settingsFontScaleSpin")
        self._font_scale_spin.setAccessibleName("UI font scaling percentage")
        self._font_scale_spin.setRange(90, 150)
        self._font_scale_spin.setSingleStep(5)
        self._font_scale_spin.setValue(100)
        self._font_scale_spin.setSuffix("%")
        self._font_scale_spin.setMinimumHeight(32)
        self._font_scale_spin.valueChanged.connect(self._on_font_scale_changed)
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
        txt = self._engine_path_input.text().strip()
        if not txt:
            self._lbl_engine_status.setText(f"<span style='color: {tokens.TEXT_MUTED};'>No engine path configured.</span>")
            return
        p = Path(txt)
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

    def _validate_storage_paths(self) -> None:
        if not hasattr(self, "_lbl_projects_status") or not hasattr(self, "_lbl_artifacts_status"):
            return
        p_txt = self._projects_root_input.text().strip()
        if not p_txt:
            self._lbl_projects_status.setText(
                f"<span style='color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;'>Default projects directory will be used.</span>"
            )
        else:
            p = Path(p_txt)
            if p.is_dir():
                self._lbl_projects_status.setText(
                    f"<span style='color: {tokens.ACCENT_SUCCESS}; font-size: {tokens.FONT_BODY_SM}px;'>✓ Directory exists and accessible.</span>"
                )
            else:
                self._lbl_projects_status.setText(
                    f"<span style='color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;'>Directory does not exist yet (will be created on save).</span>"
                )

        a_txt = self._artifacts_root_input.text().strip()
        if not a_txt:
            self._lbl_artifacts_status.setText(
                f"<span style='color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;'>Default artifacts directory will be used.</span>"
            )
        else:
            a = Path(a_txt)
            if a.is_dir():
                self._lbl_artifacts_status.setText(
                    f"<span style='color: {tokens.ACCENT_SUCCESS}; font-size: {tokens.FONT_BODY_SM}px;'>✓ Directory exists and accessible.</span>"
                )
            else:
                self._lbl_artifacts_status.setText(
                    f"<span style='color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;'>Directory does not exist yet (will be created on save).</span>"
                )

    @Slot(int)
    def _on_theme_changed(self, index: int) -> None:
        new_theme = "light" if index == 1 else "dark"
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from ..styles.dark_theme import apply_theme

        ide_settings = QSettings("GameForge", "GameForgeIDE")
        ide_settings.setValue("appearance/theme", new_theme)

        ws_ini = self._workspace / ".gameforge" / "ide_settings.ini"
        try:
            ws_ini.parent.mkdir(parents=True, exist_ok=True)
            ws_settings = QSettings(str(ws_ini), QSettings.IniFormat)
            ws_settings.setValue("appearance/theme", new_theme)
            ws_settings.sync()
        except Exception as exc:
            logger.debug("Could not write workspace ini settings: %s", exc)

        app_inst = QApplication.instance()
        if app_inst and not os.environ.get("PYTEST_CURRENT_TEST"):
            apply_theme(app_inst, new_theme)

    @Slot(int)
    def _on_font_scale_changed(self, value: int) -> None:
        from PySide6.QtCore import QSettings

        ide_settings = QSettings("GameForge", "GameForgeIDE")
        ide_settings.setValue("appearance/font_scale", value)

        ws_ini = self._workspace / ".gameforge" / "ide_settings.ini"
        try:
            ws_ini.parent.mkdir(parents=True, exist_ok=True)
            ws_settings = QSettings(str(ws_ini), QSettings.IniFormat)
            ws_settings.setValue("appearance/font_scale", value)
            ws_settings.sync()
        except Exception as exc:
            logger.debug("Could not write font scale to workspace ini: %s", exc)

    # ── Data Load & Save ─────────────────────────────────────────────────────

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.load_settings()

    def load_settings(self) -> None:
        s = get_settings()

        # Engine
        eng_root = str(s.engine.root) if s.engine else ""
        self._engine_path_input.setText(eng_root)

        # Sync combo with current engine
        combo_matched = False
        if eng_root:
            for idx in range(self._combo_detected_engine.count()):
                if self._combo_detected_engine.itemData(idx) == eng_root:
                    self._combo_detected_engine.blockSignals(True)
                    self._combo_detected_engine.setCurrentIndex(idx)
                    self._combo_detected_engine.blockSignals(False)
                    combo_matched = True
                    break
        if not combo_matched and self._combo_detected_engine.count() > 0:
            custom_idx = self._combo_detected_engine.count() - 1
            self._combo_detected_engine.blockSignals(True)
            self._combo_detected_engine.setCurrentIndex(custom_idx)
            self._combo_detected_engine.blockSignals(False)

        # Paths
        self._projects_root_input.setText(str(s.projects_root) if s.projects_root else "")
        self._artifacts_root_input.setText(str(s.artifacts_root) if s.artifacts_root else "")
        self._ollama_url_input.setText(str(s.ollama_url) if s.ollama_url else "")

        # Models
        self._models_table.setRowCount(len(s.models))
        for row, (role, model) in enumerate(sorted(s.models.items())):
            role_item = QTableWidgetItem(role)
            role_item.setFlags(role_item.flags() & ~Qt.ItemIsEditable)
            self._models_table.setItem(row, 0, role_item)
            self._models_table.setItem(row, 1, QTableWidgetItem(model))

        # Appearance
        from PySide6.QtCore import QSettings
        ide_settings = QSettings("GameForge", "GameForgeIDE")
        ws_ini = self._workspace / ".gameforge" / "ide_settings.ini"
        if ws_ini.is_file():
            ws_settings = QSettings(str(ws_ini), QSettings.IniFormat)
            current_theme = ws_settings.value("appearance/theme", ide_settings.value("appearance/theme", "dark"))
            try:
                scale_val = int(ws_settings.value("appearance/font_scale", ide_settings.value("appearance/font_scale", 100)))
            except (ValueError, TypeError):
                scale_val = 100
        else:
            current_theme = ide_settings.value("appearance/theme", "dark")
            try:
                scale_val = int(ide_settings.value("appearance/font_scale", 100))
            except (ValueError, TypeError):
                scale_val = 100
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(1 if str(current_theme).lower() == "light" else 0)
        self._theme_combo.blockSignals(False)

        self._font_scale_spin.blockSignals(True)
        self._font_scale_spin.setValue(scale_val)
        self._font_scale_spin.blockSignals(False)

        # Routing Source info
        try:
            r_cfg = Path(__file__).resolve().parents[2] / "config" / "model_routing.json"
            if r_cfg.is_file():
                r_data = json.loads(r_cfg.read_text(encoding="utf-8"))
                src_desc = r_data.get("source", {}).get("description", "Static")
                src_date = r_data.get("source", {}).get("generated_at", "")
                self._lbl_routing_source.setText(f"Routing Source: {src_desc} ({src_date})")
            else:
                self._lbl_routing_source.setText("Routing Source: Default table")
        except Exception:
            self._lbl_routing_source.setText("Routing Source: Default table")

        self._validate_engine_path()
        self._validate_storage_paths()

    @Slot()
    def save_settings(self) -> None:
        cfg_path = user_settings_path()
        if not cfg_path:
            logger.error("user_settings_path returned None")
            return

        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            if cfg_path.is_file():
                try:
                    data = json.loads(cfg_path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}

            # Update fields (remove when cleared so settings reset reliably)
            eng = self._engine_path_input.text().strip()
            if eng:
                data["engine_root"] = eng
            elif "engine_root" in data:
                del data["engine_root"]

            proj = self._projects_root_input.text().strip()
            if proj:
                data["projects_root"] = proj
            elif "projects_root" in data:
                del data["projects_root"]

            art = self._artifacts_root_input.text().strip()
            if art:
                data["artifacts_root"] = art
            elif "artifacts_root" in data:
                del data["artifacts_root"]

            ollama = self._ollama_url_input.text().strip()
            if ollama:
                data["ollama_url"] = ollama
            elif "ollama_url" in data:
                del data["ollama_url"]

            # Models
            models: Dict[str, str] = {}
            for row in range(self._models_table.rowCount()):
                r_item = self._models_table.item(row, 0)
                m_item = self._models_table.item(row, 1)
                if r_item and m_item and r_item.text().strip():
                    models[r_item.text().strip()] = m_item.text().strip()
            if models:
                data["models"] = models

            tmp_path = cfg_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp_path.replace(cfg_path)
            reset_settings_cache()
        except Exception as exc:
            logger.error("Failed to save settings: %s", exc)
            self._btn_save.setText("Save Failed ✗")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self._btn_save.setText("Save Settings"))
            return

        # Appearance persistence and live application
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication
        from ..styles.dark_theme import apply_theme
        new_theme = "light" if self._theme_combo.currentIndex() == 1 else "dark"
        ide_settings = QSettings("GameForge", "GameForgeIDE")
        ide_settings.setValue("appearance/theme", new_theme)
        ide_settings.setValue("appearance/font_scale", self._font_scale_spin.value())

        ws_ini = self._workspace / ".gameforge" / "ide_settings.ini"
        try:
            ws_ini.parent.mkdir(parents=True, exist_ok=True)
            ws_settings = QSettings(str(ws_ini), QSettings.IniFormat)
            ws_settings.setValue("appearance/theme", new_theme)
            ws_settings.setValue("appearance/font_scale", self._font_scale_spin.value())
            ws_settings.sync()
        except Exception as exc:
            logger.debug("Could not write workspace ini settings: %s", exc)

        app_inst = QApplication.instance()
        if app_inst and not os.environ.get("PYTEST_CURRENT_TEST"):
            apply_theme(app_inst, new_theme)

        self._btn_save.setText("Saved ✓")
        QTimer.singleShot(2000, lambda: self._btn_save.setText("Save Settings"))
        print(f"[GameForge Settings] Saved: Theme='{new_theme}', FontScale={self._font_scale_spin.value()}%, Engine='{eng or 'None'}', Projects='{proj}'", flush=True)
        self.settingsChanged.emit()
