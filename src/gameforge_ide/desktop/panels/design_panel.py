"""Game Design Spec panel for the desktop IDE (P1 WI-1.10)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...design.gds import GameDesignSpec
from ...design.render import render_markdown
from ...design.store import load as load_gds
from ..styles import tokens


class DesignPanel(QWidget):
    def __init__(self, workspace_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("designPanel")
        self.setAccessibleName("Game Design Spec Panel")
        self.workspace_root = Path(workspace_root)
        self._current_gds: Optional[GameDesignSpec] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(tokens.SPACE_SM)

        # Header with title and refresh button
        header_row = QHBoxLayout()
        self._title_lbl = QLabel("<b>Game Design Spec</b>", self)
        self._title_lbl.setTextFormat(Qt.RichText)
        self._title_lbl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px;")
        header_row.addWidget(self._title_lbl)
        header_row.addStretch()

        self._btn_refresh = QPushButton("Refresh", self)
        self._btn_refresh.setObjectName("btn_design_panel_refresh")
        self._btn_refresh.setAccessibleName("Reload spec from disk")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 3px 10px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_refresh.clicked.connect(self.reload_from_disk)
        header_row.addWidget(self._btn_refresh)
        layout.addLayout(header_row)

        # Tab widget: Markdown (read-only render) and JSON (editor + validate)
        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("designPanelTabs")
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  background-color: {tokens.BG_PANEL};"
            f"}}"
            f"QTabBar::tab {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-bottom: none;"
            f"  padding: 4px 12px; font-size: {tokens.FONT_BODY_SM}px; border-top-left-radius: 4px; border-top-right-radius: 4px;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_PRIMARY}; border-color: {tokens.ACCENT_PRIMARY};"
            f"}}"
        )

        # Tab 1: Markdown render
        self._md_browser = QTextBrowser(self)
        self._md_browser.setObjectName("designMdBrowser")
        self._md_browser.setAccessibleName("Markdown Design Spec View")
        self._md_browser.setOpenExternalLinks(True)
        self._md_browser.setStyleSheet(
            f"QTextBrowser {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  padding: 8px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
        )
        self._tabs.addTab(self._md_browser, "Design View")

        # Tab 2: JSON edit & validate
        json_widget = QWidget(self)
        json_layout = QVBoxLayout(json_widget)
        json_layout.setContentsMargins(6, 6, 6, 6)
        json_layout.setSpacing(6)

        self._json_edit = QPlainTextEdit(json_widget)
        self._json_edit.setObjectName("designJsonEdit")
        self._json_edit.setAccessibleName("Raw GDS JSON editor")
        self._json_edit.setPlaceholderText("Paste or edit Game Design Spec JSON here...")
        self._json_edit.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  font-family: 'Cascadia Code', 'Consolas', monospace;"
            f"  font-size: 12px;"
            f"  padding: 6px;"
            f"}}"
        )
        json_layout.addWidget(self._json_edit)

        val_row = QHBoxLayout()
        self._btn_validate = QPushButton("Validate", json_widget)
        self._btn_validate.setObjectName("btn_validate_json")
        self._btn_validate.setAccessibleName("Validate GDS JSON schema")
        self._btn_validate.setCursor(Qt.PointingHandCursor)
        self._btn_validate.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px 12px; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; border-color: {tokens.ACCENT_PRIMARY}; }}"
        )
        self._btn_validate.clicked.connect(self._validate_json)
        val_row.addWidget(self._btn_validate)

        self._status_lbl = QLabel("", json_widget)
        self._status_lbl.setObjectName("lbl_design_status")
        self._status_lbl.setWordWrap(True)
        val_row.addWidget(self._status_lbl)
        val_row.addStretch()
        json_layout.addLayout(val_row)

        self._tabs.addTab(json_widget, "JSON")
        layout.addWidget(self._tabs)

        self.reload_from_disk()

    def set_workspace(self, workspace_root: Path) -> None:
        """Switch active workspace directory and reload GDS."""
        self.workspace_root = Path(workspace_root)
        self.reload_from_disk()

    def set_gds(self, gds: GameDesignSpec) -> None:
        self._current_gds = gds
        md_text = render_markdown(gds)
        self._md_browser.setMarkdown(md_text)
        self._json_edit.setPlainText(gds.to_json())
        self._status_lbl.setText(f"<span style='color: {tokens.ACCENT_SUCCESS};'>Spec loaded (valid)</span>")

    def reload_from_disk(self) -> None:
        gds = load_gds(self.workspace_root)
        if gds is not None:
            self.set_gds(gds)
        else:
            self._current_gds = None
            self._md_browser.setMarkdown(
                "*No `GameForge/design/game.gds.json` found in current workspace root.*"
            )
            self._status_lbl.setText(f"<span style='color: {tokens.TEXT_MUTED};'>No spec loaded</span>")

    def _validate_json(self) -> None:
        text = self._json_edit.toPlainText().strip()
        if not text:
            self._status_lbl.setText(f"<span style='color: {tokens.ACCENT_ERROR};'>Empty JSON</span>")
            return
        try:
            gds = GameDesignSpec.model_validate_json(text)
            self.set_gds(gds)
            self._status_lbl.setText(f"<span style='color: {tokens.ACCENT_SUCCESS};'>✔ Valid GDS (gds/1)</span>")
        except Exception as exc:
            self._status_lbl.setText(f"<span style='color: {tokens.ACCENT_ERROR};'>✖ Invalid: {exc}</span>")
