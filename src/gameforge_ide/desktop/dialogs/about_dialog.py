"""About Dialog: Studio UX About GameForge IDE dialog (spec §4, WI-4.4)."""
from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_stylesheet
from ...core.settings import get_settings


class AboutDialog(QDialog):
    """Studio UX About dialog displaying version, models, engine, and host configuration."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setWindowTitle("About GameForge IDE")
        self.setModal(True)
        self.resize(520, 360)
        self.setStyleSheet(theme_stylesheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        ))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG)
        layout.setSpacing(tokens.SPACE_MD)

        # Header Title
        title_box = QHBoxLayout()
        logo_lbl = QLabel("◆ GameForge IDE", self)
        logo_lbl.setStyleSheet(
            f"color: {tokens.ACCENT_PRIMARY}; font-size: {tokens.FONT_HEADING}px; font-weight: 800;"
        )
        version_lbl = QLabel("v1.0.0", self)
        version_lbl.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;"
        )
        title_box.addWidget(logo_lbl)
        title_box.addWidget(version_lbl)
        title_box.addStretch(1)
        layout.addLayout(title_box)

        # Description
        desc_lbl = QLabel(
            "Agentic game-development platform that turns natural-language ideas into playable, "
            "verified Unreal Engine 5.7.4 games and keeps refining them through interactive prompt sessions.",
            self,
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        layout.addWidget(desc_lbl)

        # Info Box
        info_frame = QFrame(self)
        info_frame.setStyleSheet(
            f"background-color: {tokens.BG_PANEL};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: {tokens.SPACE_SM}px;"
        )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(4)

        info_text = (
            f"• <b>Engine Channel:</b> Unreal Engine 5.7.4 (pinned, CL 51494982)<br>"
            f"• <b>Local Models:</b> gameforge-qwen3.5-9b, 4b, 27b-sft, llama3.1:8b<br>"
            f"• <b>Runtime:</b> Python {sys.version.split()[0]} on Windows 11 Native PySide6<br>"
            f"• <b>Security Architecture:</b> Contained workspace, shell-free command allowlist<br>"
            f"• <b>License & Copyright:</b> © 2026 GameForge Project"
        )
        lbl_info = QLabel(info_text, info_frame)
        lbl_info.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY_SM}px;")
        info_layout.addWidget(lbl_info)
        layout.addWidget(info_frame)

        layout.addStretch(1)

        # Buttons Row
        btn_layout = QHBoxLayout()

        self._btn_copy = QPushButton("Copy System Info", self)
        self._btn_copy.setObjectName("btnCopySystemInfo")
        self._btn_copy.setAccessibleName("Copy system information to clipboard")
        self._btn_copy.setCursor(Qt.PointingHandCursor)
        self._btn_copy.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover, QPushButton:focus {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
        )
        self._btn_copy.clicked.connect(self._copy_system_info)
        btn_layout.addWidget(self._btn_copy)

        btn_layout.addStretch(1)

        self._btn_close = QPushButton("Close", self)
        self._btn_close.setObjectName("btnCloseAbout")
        self._btn_close.setAccessibleName("Close about dialog")
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"  font-weight: 600;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover, QPushButton:focus {{"
            f"  background-color: {tokens.ACCENT_HOVER};"
            f"  outline: none;"
            f"}}"
        )
        self._btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_close)

        layout.addLayout(btn_layout)

    def _copy_system_info(self) -> None:
        settings = get_settings()
        info = (
            f"GameForge IDE v1.0.0\n"
            f"Python: {sys.version}\n"
            f"Platform: {sys.platform}\n"
            f"Engine: Unreal Engine 5.7.4\n"
            f"Projects Root: {getattr(settings, 'projects_root', 'default')}\n"
            f"Ollama URL: {getattr(settings, 'ollama_url', 'http://127.0.0.1:11434')}\n"
        )
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(info)
            self._btn_copy.setText("Copied! ✓")
