"""Dialog for selecting and validating the authoritative project directory (Two-Location Storage Architecture)."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Optional, Tuple, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ...core.settings import get_settings
from ...core.projects import is_gameforge_project, find_uproject


class NewProjectDialog(QDialog):
    """Dialog prompting the user to name the project and select its authoritative root directory."""

    projectConfirmed = Signal(str, Path)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        initial_name: str = "MyNewGame",
        initial_parent_dir: Optional[Path] = None,
        projects_root: Optional[Union[str, Path]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("newProjectDialog")
        self.setAccessibleName("Create or Open Project dialog")
        self.setWindowTitle("Create or Open Project — GameForge")
        self.setMinimumWidth(560)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        )

        parent_dir = projects_root or initial_parent_dir
        self._default_parent = Path(
            parent_dir or get_settings().projects_root or (Path.home() / "Documents" / "GameForge" / "Projects")
        ).resolve()

        self._init_ui(initial_name)
        self._update_resolution()

    def _init_ui(self, initial_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(tokens.SPACE_MD)
        layout.setContentsMargins(tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG)

        # Title / Header
        lbl_title = QLabel("Select Authoritative Project Directory", self)
        lbl_title.setStyleSheet(
            f"font-size: {tokens.FONT_HEADING_SM}px; font-weight: bold; color: {tokens.TEXT_PRIMARY};"
        )
        layout.addWidget(lbl_title)

        # Architectural Notice (The Two-Location Requirement)
        notice_box = QFrame(self)
        notice_box.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE}; border: 1px solid {tokens.BORDER}; "
            f"border-radius: {tokens.RADIUS}px; padding: {tokens.SPACE_SM}px;"
        )
        notice_layout = QVBoxLayout(notice_box)
        notice_layout.setContentsMargins(8, 8, 8, 8)
        lbl_notice = QLabel(
            "<b>GameForge Strict Two-Location Architecture:</b><br>"
            "The selected directory becomes the single authoritative root for all Unreal Engine files "
            "(.uproject, Config, Content, Source, Plugins) and GameForge files (Design, Reports, Packaged Builds). "
            "No hidden or duplicate project copies exist elsewhere.",
            notice_box,
        )
        lbl_notice.setWordWrap(True)
        lbl_notice.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        notice_layout.addWidget(lbl_notice)
        layout.addWidget(notice_box)

        # Project Name Row
        name_layout = QVBoxLayout()
        lbl_name = QLabel("Project Name (C++ identifier):", self)
        lbl_name.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 500;")
        self._edit_name = QLineEdit(initial_name, self)
        self._edit_name.setObjectName("newProjectNameInput")
        self._edit_name.setAccessibleName("Project Name identifier input")
        self._edit_name.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY}; "
            f"border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 6px;"
        )
        self._edit_name.textChanged.connect(self._on_name_changed)
        self._edit_name.returnPressed.connect(self._on_confirm_clicked)
        name_layout.addWidget(lbl_name)
        name_layout.addWidget(self._edit_name)
        layout.addLayout(name_layout)

        # Destination Directory Row
        dir_layout = QVBoxLayout()
        lbl_dir = QLabel("Project Folder Location:", self)
        lbl_dir.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 500;")
        dir_input_row = QHBoxLayout()
        self._edit_dir = QLineEdit(str(self._default_parent), self)
        self._edit_dir.setObjectName("newProjectDirInput")
        self._edit_dir.setAccessibleName("Project Folder Location input")
        self._edit_dir.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY}; "
            f"border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 6px;"
        )
        self._edit_dir.textChanged.connect(self._update_resolution)
        self._edit_dir.returnPressed.connect(self._on_confirm_clicked)

        btn_browse = QPushButton("Browse…", self)
        btn_browse.setObjectName("btnBrowseNewProjectDir")
        btn_browse.setAccessibleName("Browse project directory")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY}; "
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 6px 14px;"
            f"}}"
            f"QPushButton:hover, QPushButton:focus {{"
            f"  background-color: {tokens.BG_HOVER}; border-color: {tokens.BORDER_FOCUS}; outline: none;"
            f"}}"
        )
        btn_browse.clicked.connect(self._on_browse_clicked)

        dir_input_row.addWidget(self._edit_dir, 1)
        dir_input_row.addWidget(btn_browse)
        dir_layout.addWidget(lbl_dir)
        dir_layout.addLayout(dir_input_row)
        layout.addLayout(dir_layout)

        # Resolved Path Display
        res_box = QFrame(self)
        res_box.setStyleSheet(
            f"background-color: {tokens.BG_PANEL}; border: 1px dashed {tokens.BORDER}; "
            f"border-radius: {tokens.RADIUS}px; padding: 8px;"
        )
        res_layout = QVBoxLayout(res_box)
        res_layout.setContentsMargins(6, 6, 6, 6)
        self._lbl_resolved = QLabel("", res_box)
        self._lbl_resolved.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-family: monospace; font-size: {tokens.FONT_BODY_SM}px;"
        )
        self._lbl_resolved.setWordWrap(True)
        res_layout.addWidget(self._lbl_resolved)

        self._lbl_status = QLabel("", res_box)
        self._lbl_status.setStyleSheet(f"font-size: {tokens.FONT_BODY_SM}px;")
        res_layout.addWidget(self._lbl_status)
        layout.addWidget(res_box)

        # Buttons Row
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("btnCancelNewProject")
        self._btn_cancel.setAccessibleName("Cancel project creation")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.setStyleSheet(
            f"QPushButton#{self._btn_cancel.objectName()} {{"
            f"  background-color: transparent; color: {tokens.TEXT_SECONDARY}; "
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 6px {tokens.SPACE_LG}px;"
            f"}}"
            f"QPushButton#{self._btn_cancel.objectName()}:hover, QPushButton#{self._btn_cancel.objectName()}:focus {{"
            f"  background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; border-color: {tokens.BORDER_FOCUS}; outline: none;"
            f"}}"
        )
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_confirm = QPushButton("Confirm Project Root", self)
        self._btn_confirm.setObjectName("btnConfirmNewProject")
        self._btn_confirm.setAccessibleName("Confirm project root directory")
        self._btn_confirm.setCursor(Qt.PointingHandCursor)
        self._btn_confirm.setStyleSheet(
            f"QPushButton#{self._btn_confirm.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY}; "
            f"  border: none; border-radius: {tokens.RADIUS}px; padding: 6px 18px; font-weight: 600;"
            f"}}"
            f"QPushButton#{self._btn_confirm.objectName()}:hover, QPushButton#{self._btn_confirm.objectName()}:focus {{"
            f"  background-color: {tokens.ACCENT_HOVER}; outline: none;"
            f"}}"
            f"QPushButton#{self._btn_confirm.objectName()}:disabled {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_MUTED};"
            f"}}"
        )
        self._btn_confirm.clicked.connect(self._on_confirm_clicked)

        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_confirm)
        layout.addLayout(btn_row)

    def _sanitize_name(self, name: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "", name.strip())
        if clean and clean[0].isdigit():
            clean = "G" + clean
        return clean

    def _on_name_changed(self) -> None:
        self._update_resolution()

    def _on_browse_clicked(self) -> None:
        current_text = self._edit_dir.text().strip()
        start_dir = current_text if (current_text and Path(current_text).is_dir()) else str(self._default_parent)
        selected = QFileDialog.getExistingDirectory(self, "Choose Project Directory", start_dir)
        if selected:
            # If the selected directory itself already is a project (has .uproject or gds), set it directly
            sel_path = Path(selected).resolve()
            if is_gameforge_project(sel_path):
                self._edit_dir.setText(str(sel_path.parent))
                self._edit_name.setText(sel_path.name)
            else:
                self._edit_dir.setText(str(sel_path))
            self._update_resolution()

    def get_resolved_project_dir(self) -> Tuple[str, Path]:
        name = self._sanitize_name(self._edit_name.text())
        parent_dir = Path(self._edit_dir.text().strip() or str(self._default_parent)).resolve()
        # If parent_dir already ends with name, don't duplicate
        if parent_dir.name.lower() == name.lower():
            return name, parent_dir
        return name, parent_dir / name

    def project_name(self) -> str:
        """Convenience accessor for project name."""
        name, _ = self.get_resolved_project_dir()
        return name

    def project_dir(self) -> Path:
        """Convenience accessor for authoritative project directory."""
        _, pdir = self.get_resolved_project_dir()
        return pdir

    def _update_resolution(self) -> None:
        name, pdir = self.get_resolved_project_dir()
        self._lbl_resolved.setText(f"Authoritative Root:\n{pdir}")

        # Validation
        if not name:
            self._lbl_status.setText(f"<font color='{tokens.ACCENT_ERROR}'>✕ Please enter a valid project name.</font>")
            self._btn_confirm.setEnabled(False)
            return

        try:
            parent_path = pdir.parent
            parent_exists = parent_path.is_dir()
        except Exception:
            parent_exists = False

        if not parent_exists:
            self._lbl_status.setText(f"<font color='{tokens.ACCENT_WARNING}'>⚠️ Parent directory does not exist yet (will be created).</font>")
            self._btn_confirm.setEnabled(True)
            return

        if pdir.is_dir():
            if is_gameforge_project(pdir):
                self._lbl_status.setText(
                    f"<font color='{tokens.ACCENT_SUCCESS}'>✓ Existing GameForge/Unreal project detected. Will open directly.</font>"
                )
            else:
                items = list(pdir.iterdir())
                if not items:
                    self._lbl_status.setText(
                        f"<font color='{tokens.ACCENT_SUCCESS}'>✓ Directory exists and is empty. Ready for project creation.</font>"
                    )
                else:
                    self._lbl_status.setText(
                        f"<font color='{tokens.ACCENT_WARNING}'>⚠️ Directory is not empty. Existing files may be modified.</font>"
                    )
        else:
            self._lbl_status.setText(
                f"<font color='{tokens.ACCENT_SUCCESS}'>✓ New project directory will be created at this location.</font>"
            )

        self._btn_confirm.setEnabled(True)

    def _on_confirm_clicked(self) -> None:
        name, pdir = self.get_resolved_project_dir()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid project name.")
            return

        try:
            pdir.mkdir(parents=True, exist_ok=True)
            test_file = pdir / ".gf_write_test"
            test_file.write_text("ok", encoding="utf-8")
            try:
                test_file.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as exc:
            QMessageBox.critical(self, "Directory Error", f"Cannot write to selected project directory:\n{exc}")
            return

        self.projectConfirmed.emit(name, pdir)
        self.accept()
