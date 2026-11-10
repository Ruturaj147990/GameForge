"""Confirmation dialog for deleting a GameForge project (WI-4.5).

Lists target directories and requires typed project name to prevent accidental deletion.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (

    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..services.projects_service import GameSummary
from ..styles import tokens
from ..styles.dark_theme import theme_stylesheet

logger = logging.getLogger(__name__)


class DeleteGameDialog(QDialog):
    """Confirmation dialog listing target directories and requiring typed project name."""

    def __init__(self, game: GameSummary, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName("deleteGameDialog")
        self.setAccessibleName(f"Delete project {game.name} dialog")
        self.setWindowTitle(f"Delete Game: {game.title}")
        self.setModal(True)
        self.resize(500, 320)
        self.setStyleSheet(theme_stylesheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        ))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG)
        layout.setSpacing(tokens.SPACE_MD)

        title_lbl = QLabel(f"Delete '{game.title}'?", self)
        title_lbl.setObjectName("lblDeleteTitle")
        title_lbl.setStyleSheet(
            f"color: {tokens.ACCENT_ERROR};"
            f"font-size: {tokens.FONT_HEADING_SM}px;"
            f"font-weight: 700;"
        )
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "This action cannot be undone. The entire project directory and all artifacts will be permanently deleted:",
            self,
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        layout.addWidget(desc_lbl)

        # Folder list box
        folders_box = QLabel(self)
        folders_box.setObjectName("deleteFolderList")
        pdir = Path(game.project_dir) if game and getattr(game, "project_dir", None) else Path.cwd()
        folders_text = f"• {pdir}\n• {pdir / 'Saved' / 'GameForge'}\n• {pdir / 'Content'}"
        folders_box.setText(folders_text)
        folders_box.setStyleSheet(
            f"background-color: {tokens.BG_PANEL};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: {tokens.SPACE_SM}px;"
            f"font-family: monospace;"
            f"font-size: {tokens.FONT_BODY_SM}px;"
        )
        layout.addWidget(folders_box)

        # Typing confirmation prompt
        prompt_text = f"Type the project name <font color='{tokens.TEXT_PRIMARY}'><b>{game.name}</b></font> to confirm:"
        if game.title and game.title.strip().lower() != game.name.strip().lower():
            prompt_text = (
                f"Type the project name <font color='{tokens.TEXT_PRIMARY}'><b>{game.name}</b></font> "
                f"(or <font color='{tokens.TEXT_PRIMARY}'><b>{game.title}</b></font>) to confirm:"
            )
        prompt_lbl = QLabel(prompt_text, self)
        prompt_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        layout.addWidget(prompt_lbl)

        # Input row with Fill name action button
        input_layout = QHBoxLayout()
        input_layout.setSpacing(tokens.SPACE_SM)

        self._confirm_input = QLineEdit(self)
        self._confirm_input.setObjectName("deleteConfirmInput")
        self._confirm_input.setAccessibleName("Type project name to confirm deletion")
        self._confirm_input.setPlaceholderText(game.name)
        self._confirm_input.setStyleSheet(
            f"QLineEdit#{self._confirm_input.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_SM}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
        )
        self._confirm_input.textChanged.connect(self._on_text_changed)
        self._confirm_input.returnPressed.connect(self._on_return_pressed)
        input_layout.addWidget(self._confirm_input, 1)

        self._btn_fill = QPushButton("Fill name", self)
        self._btn_fill.setObjectName("btnFillDeleteName")
        self._btn_fill.setAccessibleName("Fill project name automatically")
        self._btn_fill.setToolTip(f"Auto-fill '{game.name}'")
        self._btn_fill.setStyleSheet(
            f"QPushButton#{self._btn_fill.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  color: {tokens.ACCENT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton#{self._btn_fill.objectName()}:hover {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  border-color: {tokens.ACCENT_PRIMARY};"
            f"}}"
        )
        self._btn_fill.clicked.connect(lambda: self._confirm_input.setText(game.name))
        input_layout.addWidget(self._btn_fill)

        layout.addLayout(input_layout)

        # Dynamic status helper
        self._status_lbl = QLabel("Type the name above or click 'Fill name' to confirm.", self)
        self._status_lbl.setObjectName("lblDeleteStatus")
        self._status_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")
        layout.addWidget(self._status_lbl)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("btnCancelDelete")
        self._btn_cancel.setAccessibleName("Cancel deletion")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.setStyleSheet(
            f"QPushButton#{self._btn_cancel.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton#{self._btn_cancel.objectName()}:hover, QPushButton#{self._btn_cancel.objectName()}:focus {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
        )
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_delete = QPushButton("Delete permanently", self)
        self._btn_delete.setObjectName("btnConfirmDelete")
        self._btn_delete.setAccessibleName("Permanently delete project")
        self._btn_delete.setCursor(Qt.PointingHandCursor)
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet(
            f"QPushButton#{self._btn_delete.objectName()} {{"
            f"  background-color: {tokens.ACCENT_ERROR};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton#{self._btn_delete.objectName()}:hover, QPushButton#{self._btn_delete.objectName()}:focus {{"
            f"  background-color: {tokens.ACCENT_WARNING};"
            f"  outline: none;"
            f"}}"
            f"QPushButton#{self._btn_delete.objectName()}:disabled {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_MUTED};"
            f"}}"
        )
        self._btn_delete.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_delete)

        layout.addLayout(btn_layout)

    def _is_name_match(self, text: str) -> bool:
        clean = text.strip().lower()
        if not clean:
            return False

        def simplify(s: str) -> str:
            return "".join(c for c in s.lower() if c.isalnum())

        valid_names = {self.game.name.strip().lower()}
        if self.game.title:
            valid_names.add(self.game.title.strip().lower())

        if clean in valid_names:
            return True

        clean_simple = simplify(clean)
        for vn in valid_names:
            if clean_simple == simplify(vn) and len(clean_simple) > 0:
                return True

        return False

    @Slot(str)
    def _on_text_changed(self, text: str) -> None:
        matched = self._is_name_match(text)
        self._btn_delete.setEnabled(matched)
        if matched:
            self._status_lbl.setText("✓ Project name confirmed. Click 'Delete permanently' or press Enter.")
            self._status_lbl.setStyleSheet(
                f"color: {tokens.ACCENT_SUCCESS}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;"
            )
        else:
            self._status_lbl.setText("Type the project name above or click 'Fill name' to confirm.")
            self._status_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._confirm_input.setFocus()

    @Slot()
    def _on_return_pressed(self) -> None:
        if self._btn_delete.isEnabled():
            self.accept()
