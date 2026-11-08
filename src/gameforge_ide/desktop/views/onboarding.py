"""First-run onboarding wizard for Studio UX v2 (spec §4.10, WI-4.10).

3-step modal QWizard shown when settings file is missing or engine is None:
1. Find Unreal Engine
2. Choose where games are saved (disk space warning)
3. Models & readiness check
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..styles import tokens
from ...core.settings import (
    PINNED_ENGINE,
    discover_engines,
    engine_version,
    get_settings,
    reset_settings_cache,
    user_settings_path,
)

logger = logging.getLogger(__name__)


class EnginePage(QWizardPage):
    """Page 1: Detect and select Unreal Engine 5.7+ install."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingEnginePage")
        self.setTitle("Find Unreal Engine")
        self.setSubTitle(f"GameForge requires Unreal Engine {PINNED_ENGINE} (or compatible build).")

        layout = QVBoxLayout(self)
        layout.setSpacing(tokens.SPACE_MD)

        form = QFormLayout()

        self._combo_engines = QComboBox(self)
        self._combo_engines.setObjectName("onboardingEngineCombo")
        self._combo_engines.setAccessibleName("Select detected Unreal Engine")
        self._combo_engines.setStyleSheet(
            f"QComboBox {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_SM}px;"
            f"}}"
        )

        detected = discover_engines()
        for inst in detected:
            self._combo_engines.addItem(f"UE {inst.version} ({inst.source}) — {inst.root}", str(inst.root))

        self._combo_engines.addItem("Browse / Custom path...", "")
        form.addRow("Detected Installs:", self._combo_engines)

        path_box = QHBoxLayout()
        self._custom_path = QLineEdit(self)
        self._custom_path.setObjectName("onboardingEnginePath")
        self._custom_path.setAccessibleName("Custom engine root path")
        self._custom_path.setPlaceholderText("E.g. E:\\UE\\UE_5.7")
        self._custom_path.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_SM}px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
        )
        if detected:
            self._custom_path.setText(str(detected[0].root))
        path_box.addWidget(self._custom_path, 1)

        self._btn_browse = QPushButton("Browse...", self)
        self._btn_browse.setObjectName("btnBrowseEngine")
        self._btn_browse.setAccessibleName("Browse engine root directory")
        self._btn_browse.setCursor(Qt.PointingHandCursor)
        self._btn_browse.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_MD}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"}}"
        )
        self._btn_browse.clicked.connect(self._browse_engine)
        path_box.addWidget(self._btn_browse)

        form.addRow("Engine Root:", path_box)
        layout.addLayout(form)

        self._lbl_validation = QLabel(self)
        self._lbl_validation.setObjectName("lblEngineValidation")
        layout.addWidget(self._lbl_validation)

        self._combo_engines.currentIndexChanged.connect(self._on_combo_changed)
        self._custom_path.textChanged.connect(self._validate_path)
        self._validate_path()

        layout.addStretch(1)

    def _browse_engine(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Unreal Engine Root Directory")
        if folder:
            self._custom_path.setText(folder)

    def _on_combo_changed(self) -> None:
        data = self._combo_engines.currentData()
        if data:
            self._custom_path.setText(data)

    def _validate_path(self) -> None:
        txt = self._custom_path.text().strip()
        if not txt:
            self._lbl_validation.setText(
                f"<span style='color: {tokens.TEXT_MUTED};'>Select or browse to an Unreal Engine root.</span>"
            )
            return
        p = Path(txt)
        if not p.is_dir():
            self._lbl_validation.setText(f"<span style='color: {tokens.ACCENT_ERROR};'>Directory does not exist.</span>")
            return
        ver = engine_version(p)
        if ver:
            v_str, cl = ver
            self._lbl_validation.setText(
                f"<span style='color: {tokens.ACCENT_SUCCESS};'>✓ Valid Unreal Engine {v_str} (CL {cl})</span>"
            )
        else:
            self._lbl_validation.setText(
                f"<span style='color: {tokens.ACCENT_WARNING};'>UnrealEditor.exe or Build.version missing.</span>"
            )

    def get_engine_root(self) -> str:
        return self._custom_path.text().strip()


class PathsPage(QWizardPage):
    """Page 2: Choose projects and artifacts directory."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingPathsPage")
        self.setTitle("Choose Where Games Are Saved")
        self.setSubTitle("Select directories for project files and build artifacts.")

        layout = QVBoxLayout(self)
        layout.setSpacing(tokens.SPACE_MD)

        form = QFormLayout()

        p_box = QHBoxLayout()
        self._projects_path = QLineEdit(self)
        self._projects_path.setObjectName("onboardingProjectsPath")
        self._projects_path.setAccessibleName("Projects root path")
        self._projects_path.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_SM}px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
        )
        s = get_settings()
        self._projects_path.setText(str(s.projects_root))
        p_box.addWidget(self._projects_path, 1)

        btn_browse_proj = QPushButton("Browse...", self)
        btn_browse_proj.setAccessibleName("Browse projects root directory")
        btn_browse_proj.setCursor(Qt.PointingHandCursor)
        btn_browse_proj.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_MD}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"}}"
        )
        btn_browse_proj.clicked.connect(self._browse_projects)
        p_box.addWidget(btn_browse_proj)
        form.addRow("Projects Root:", p_box)

        layout.addLayout(form)

        self._lbl_disk = QLabel(self)
        self._lbl_disk.setObjectName("lblPathsDiskInfo")
        layout.addWidget(self._lbl_disk)

        self._projects_path.textChanged.connect(self._check_disk)
        self._check_disk()

        layout.addStretch(1)

    def _browse_projects(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Projects Root Directory")
        if folder:
            self._projects_path.setText(folder)

    def _check_disk(self) -> None:
        p = Path(self._projects_path.text().strip())
        # Walk up to existing ancestor for disk usage
        check_path = p
        while not check_path.exists() and check_path.parent != check_path:
            check_path = check_path.parent
        try:
            usage = shutil.disk_usage(check_path)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < 20:
                self._lbl_disk.setText(
                    f"<span style='color: {tokens.ACCENT_ERROR};'>Critical disk space: {free_gb:.1f} GB free. At least 50 GB recommended.</span>"
                )
            elif free_gb < 50:
                self._lbl_disk.setText(
                    f"<span style='color: {tokens.ACCENT_WARNING};'>Warning: Low disk space: {free_gb:.1f} GB free. At least 50 GB recommended.</span>"
                )
            else:
                self._lbl_disk.setText(
                    f"<span style='color: {tokens.ACCENT_SUCCESS};'>✓ Disk space OK: {free_gb:.1f} GB free.</span>"
                )
        except Exception:
            self._lbl_disk.setText("Unable to determine disk usage.")

    def get_projects_root(self) -> str:
        return self._projects_path.text().strip()


class ModelsPage(QWizardPage):
    """Page 3: Model readiness review."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingModelsPage")
        self.setTitle("Local Models & Readiness")
        self.setSubTitle("Review default local models configured for GameForge.")

        layout = QVBoxLayout(self)
        layout.setSpacing(tokens.SPACE_MD)

        self._lbl_info = QLabel(
            "GameForge uses fast local models through Ollama for planning and code gen.<br>"
            "Default recommended model: <b>gameforge-qwen3.5-9b</b>.",
            self,
        )
        self._lbl_info.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px;")
        layout.addWidget(self._lbl_info)

        self._lbl_status = QLabel("Ready to configure settings and launch Studio.", self)
        self._lbl_status.setObjectName("lblModelsStatus")
        self._lbl_status.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        layout.addWidget(self._lbl_status)

        layout.addStretch(1)


class OnboardingWizard(QWizard):
    """3-page first-run wizard (spec §4.10)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingWizard")
        self.setAccessibleName("GameForge First-Run Setup Wizard")
        self.setWindowTitle("GameForge Setup")
        self.resize(600, 420)
        self.setStyleSheet(
            f"QWizard#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"}}"
            f"QWizard QWidget {{"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"}}"
            f"QWizard QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QWizard QPushButton:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"}}"
            f"QWizard QPushButton:disabled {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  color: {tokens.TEXT_MUTED};"
            f"  border-color: {tokens.BORDER};"
            f"}}"
        )

        self.engine_page = EnginePage(self)
        self.paths_page = PathsPage(self)
        self.models_page = ModelsPage(self)

        self.addPage(self.engine_page)
        self.addPage(self.paths_page)
        self.addPage(self.models_page)

        # Accessible names for standard wizard buttons
        btn_next = self.button(QWizard.NextButton)
        if btn_next:
            btn_next.setAccessibleName("Next onboarding step")
        btn_back = self.button(QWizard.BackButton)
        if btn_back:
            btn_back.setAccessibleName("Previous onboarding step")
        btn_finish = self.button(QWizard.FinishButton)
        if btn_finish:
            btn_finish.setAccessibleName("Finish onboarding setup")
        btn_cancel = self.button(QWizard.CancelButton)
        if btn_cancel:
            btn_cancel.setAccessibleName("Cancel onboarding setup")

    def accept(self) -> None:
        """Save settings to user_settings_path()."""
        cfg_path = user_settings_path()
        if cfg_path:
            try:
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                data = {}
                if cfg_path.is_file():
                    try:
                        data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    except Exception:
                        data = {}

                eng = self.engine_page.get_engine_root()
                if eng:
                    data["engine_root"] = eng

                proj = self.paths_page.get_projects_root()
                if proj:
                    data["projects_root"] = proj

                tmp_path = cfg_path.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                tmp_path.replace(cfg_path)
                reset_settings_cache()
            except Exception as exc:
                logger.error("Failed writing onboarding settings to %s: %s", cfg_path, exc)

        super().accept()
