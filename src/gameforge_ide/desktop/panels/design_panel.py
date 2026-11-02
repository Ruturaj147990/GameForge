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


class DesignPanel(QWidget):
    def __init__(self, workspace_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.workspace_root = Path(workspace_root)
        self._current_gds: Optional[GameDesignSpec] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header with title and refresh button
        header_row = QHBoxLayout()
        self._title_lbl = QLabel("<b>Game Design Spec</b>")
        self._title_lbl.setTextFormat(Qt.RichText)
        header_row.addWidget(self._title_lbl)
        header_row.addStretch()

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self.reload_from_disk)
        header_row.addWidget(self._btn_refresh)
        layout.addLayout(header_row)

        # Tab widget: Markdown (read-only render) and JSON (editor + validate)
        self._tabs = QTabWidget(self)

        # Tab 1: Markdown render
        self._md_browser = QTextBrowser()
        self._md_browser.setOpenExternalLinks(True)
        self._tabs.addTab(self._md_browser, "Design View")

        # Tab 2: JSON edit & validate
        json_widget = QWidget()
        json_layout = QVBoxLayout(json_widget)
        json_layout.setContentsMargins(4, 4, 4, 4)

        self._json_edit = QPlainTextEdit()
        self._json_edit.setPlaceholderText("Paste or edit Game Design Spec JSON here...")
        json_layout.addWidget(self._json_edit)

        val_row = QHBoxLayout()
        self._btn_validate = QPushButton("Validate")
        self._btn_validate.clicked.connect(self._validate_json)
        val_row.addWidget(self._btn_validate)

        self._status_lbl = QLabel("")
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
        self._status_lbl.setText("<span style='color: #4ade80;'>Spec loaded (valid)</span>")

    def reload_from_disk(self) -> None:
        gds = load_gds(self.workspace_root)
        if gds is not None:
            self.set_gds(gds)
        else:
            self._md_browser.setMarkdown(
                "*No `GameForge/design/game.gds.json` found in current workspace root.*"
            )
            self._status_lbl.setText("<span style='color: #9ca3af;'>No spec loaded</span>")

    def _validate_json(self) -> None:
        text = self._json_edit.toPlainText().strip()
        if not text:
            self._status_lbl.setText("<span style='color: #f87171;'>Empty JSON</span>")
            return
        try:
            gds = GameDesignSpec.model_validate_json(text)
            self.set_gds(gds)
            self._status_lbl.setText("<span style='color: #4ade80;'>✔ Valid GDS (gds/1)</span>")
        except Exception as exc:
            self._status_lbl.setText(f"<span style='color: #f87171;'>✖ Invalid: {exc}</span>")
