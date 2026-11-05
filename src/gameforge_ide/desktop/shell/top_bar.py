"""TopBar: 48px Studio UX header bar with project switcher, run chip, and systems pill (WI-4.3)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Union

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from ...core.systems import SystemRow, SystemsSnapshot
from ..icons import icon
from ..styles import tokens


class TopBar(QWidget):
    """Studio UX top navigation and status bar."""

    homeRequested = Signal()
    projectSelected = Signal(str)
    openFolderRequested = Signal()
    newProjectRequested = Signal()
    buildViewRequested = Signal()
    assistantToggled = Signal()
    paletteRequested = Signal()
    fixActionRequested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("studioTopBar")
        self.setFixedHeight(48)
        self._current_project: str = ""
        self._current_project_dir: Optional[Path] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        # 1. Logo button
        self.logo_btn = QPushButton("◆ GameForge", self)
        self.logo_btn.setObjectName("topBarLogoBtn")
        self.logo_btn.setAccessibleName("GameForge Home")
        self.logo_btn.setCursor(Qt.PointingHandCursor)
        self.logo_btn.setFocusPolicy(Qt.NoFocus)
        self.logo_btn.setStyleSheet(f"""
            QPushButton {{
                color: {tokens.TEXT_PRIMARY};
                font-weight: bold;
                font-size: 14px;
                background: transparent;
                border: none;
                padding: 4px 8px;
                border-radius: {tokens.RADIUS}px;
            }}
            QPushButton:hover {{
                background: {tokens.BG_HOVER};
            }}
        """)
        self.logo_btn.clicked.connect(self.homeRequested.emit)
        layout.addWidget(self.logo_btn)

        # 2. Project switcher combo
        self.project_combo = QComboBox(self)
        self.project_combo.setObjectName("topBarProjectCombo")
        self.project_combo.setAccessibleName("Select Project")
        self.project_combo.setEditable(True)
        self.project_combo.setInsertPolicy(QComboBox.NoInsert)
        self.project_combo.setMinimumWidth(180)
        self.project_combo.setStyleSheet(f"""
            QComboBox {{
                background: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                padding: 4px 8px;
                font-size: 13px;
            }}
            QComboBox:hover {{
                border-color: {tokens.BORDER_FOCUS};
            }}
        """)
        self.project_combo.currentIndexChanged.connect(self._on_combo_index_changed)
        layout.addWidget(self.project_combo)

        # Hidden project path label (for programmatic status/tests without adding duplicate topbar buttons)
        self.project_path_label = QLabel(self)
        self.project_path_label.setObjectName("topBarProjectPath")
        self.project_path_label.setAccessibleName("Active Project Path")
        self.project_path_label.setVisible(False)

        # 3. Breadcrumb
        self.breadcrumb_label = QLabel("› Home", self)
        self.breadcrumb_label.setObjectName("topBarBreadcrumb")
        self.breadcrumb_label.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 13px;")
        layout.addWidget(self.breadcrumb_label)

        layout.addStretch(1)

        # 4. Active-run chip (hidden unless run is active)
        self.run_chip = QPushButton("◉ Building ...", self)
        self.run_chip.setObjectName("topBarRunChip")
        self.run_chip.setAccessibleName("Active Run Status")
        self.run_chip.setCursor(Qt.PointingHandCursor)
        self.run_chip.setFocusPolicy(Qt.NoFocus)
        self.run_chip.setVisible(False)
        self.run_chip.clicked.connect(self.buildViewRequested.emit)
        layout.addWidget(self.run_chip)

        # 5. Systems pill
        self.systems_btn = QPushButton("● Ready ▾", self)
        self.systems_btn.setObjectName("topBarSystemsBtn")
        self.systems_btn.setAccessibleName("Systems Readiness")
        self.systems_btn.setCursor(Qt.PointingHandCursor)
        self.systems_btn.setFocusPolicy(Qt.NoFocus)
        self._set_pill_style("ok")
        self.systems_menu = QMenu(self)
        self.systems_menu.setObjectName("topBarSystemsMenu")
        self.systems_btn.setMenu(self.systems_menu)
        layout.addWidget(self.systems_btn)

        # 6. Assistant toggle button
        self.assistant_btn = QToolButton(self)
        self.assistant_btn.setObjectName("topBarAssistantBtn")
        self.assistant_btn.setAccessibleName("Toggle Assistant")
        self.assistant_btn.setToolTip("Toggle Assistant (Ctrl+J)")
        self.assistant_btn.setIcon(icon("assistant", role="secondary", size=18))
        self.assistant_btn.setFixedSize(32, 32)
        self.assistant_btn.setCursor(Qt.PointingHandCursor)
        self.assistant_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
            }}
            QToolButton:hover {{
                background: {tokens.BG_HOVER};
                border-color: {tokens.BORDER_FOCUS};
            }}
        """)
        self.assistant_btn.clicked.connect(self.assistantToggled.emit)
        layout.addWidget(self.assistant_btn)

        # 7. Palette button
        self.palette_btn = QToolButton(self)
        self.palette_btn.setObjectName("topBarPaletteBtn")
        self.palette_btn.setAccessibleName("Command Palette")
        self.palette_btn.setToolTip("Command Palette (Ctrl+K)")
        self.palette_btn.setIcon(icon("search", role="secondary", size=18))
        self.palette_btn.setFixedSize(32, 32)
        self.palette_btn.setCursor(Qt.PointingHandCursor)
        self.palette_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
            }}
            QToolButton:hover {{
                background: {tokens.BG_HOVER};
                border-color: {tokens.BORDER_FOCUS};
            }}
        """)
        self.palette_btn.clicked.connect(self.paletteRequested.emit)
        layout.addWidget(self.palette_btn)

        self.setStyleSheet(f"""
            QWidget#studioTopBar {{
                background: {tokens.BG_PANEL};
                border-bottom: 1px solid {tokens.BORDER};
            }}
        """)

    def set_breadcrumb(self, text: str) -> None:
        self.breadcrumb_label.setText(text)

    def set_projects(self, projects: List[str], current: Optional[str] = None) -> None:
        """Populate projects combo with search completer and 'Open project folder...'."""
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for p in projects:
            self.project_combo.addItem(p, userData=p)
        self.project_combo.insertSeparator(self.project_combo.count())
        self.project_combo.addItem("➕ New project…", userData="__new_project__")
        self.project_combo.addItem("📁 Open project folder…", userData="__open_folder__")

        if current and current in projects:
            self._current_project = current
            self.project_combo.setCurrentText(current)
        elif projects:
            self._current_project = projects[0]
            self.project_combo.setCurrentIndex(0)
        else:
            self._current_project = ""

        completer = QCompleter(projects, self.project_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.project_combo.setCompleter(completer)
        self.project_combo.blockSignals(False)

    def set_active_project(self, project_name: str, project_dir: Optional[Union[str, Path]] = None) -> None:
        """Update top bar to reflect the authoritative active project and its path."""
        self._current_project = project_name
        self._current_project_dir = Path(project_dir).resolve() if project_dir else None

        self.project_combo.blockSignals(True)
        idx = self.project_combo.findData(project_name)
        if idx >= 0:
            self.project_combo.setCurrentIndex(idx)
        elif project_name:
            self.project_combo.insertItem(0, project_name, userData=project_name)
            self.project_combo.setCurrentIndex(0)
        self.project_combo.blockSignals(False)

        if self._current_project_dir and project_name:
            p_str = str(self._current_project_dir)
            display_text = f"📁 {self._current_project_dir.name}"
            self.project_combo.setToolTip(f"Active Project: {project_name}\nDirectory: {p_str}")
            self.project_path_label.setText(display_text)
            self.project_path_label.setToolTip(f"Active Project: {project_name}\nDirectory: {p_str}")
        elif project_name:
            self.project_combo.setToolTip(f"Active Project: {project_name}")
            self.project_path_label.setText(f"📁 {project_name}")
            self.project_path_label.setToolTip(f"Active Project: {project_name}")
        else:
            self.project_combo.setToolTip("No active project selected")
            self.project_path_label.setText("📁 No Project")
            self.project_path_label.setToolTip("No active project selected")

    def _on_project_path_clicked(self) -> None:
        """Reveal active project folder in Windows File Explorer or trigger open."""
        if self._current_project_dir and self._current_project_dir.is_dir():
            from ...core.projects import open_folder_in_file_manager
            open_folder_in_file_manager(self._current_project_dir)
        else:
            self.openFolderRequested.emit()

    def _on_combo_index_changed(self, index: int) -> None:
        data = self.project_combo.itemData(index)
        if data == "__new_project__":
            prev_idx = self.project_combo.findText(self._current_project) if getattr(self, "_current_project", None) else 0
            self.project_combo.blockSignals(True)
            self.project_combo.setCurrentIndex(max(0, prev_idx))
            self.project_combo.blockSignals(False)
            self.newProjectRequested.emit()
        elif data == "__open_folder__":
            prev_idx = self.project_combo.findText(self._current_project) if getattr(self, "_current_project", None) else 0
            self.project_combo.blockSignals(True)
            self.project_combo.setCurrentIndex(max(0, prev_idx))
            self.project_combo.blockSignals(False)
            self.openFolderRequested.emit()
        elif data:
            self._current_project = str(data)
            self.projectSelected.emit(str(data))
        elif index >= 0:
            text = self.project_combo.currentText().strip()
            if text and "Open project folder" not in text and "New project" not in text:
                self._current_project = text
                self.projectSelected.emit(text)

    def update_run_chip(self, active: bool, game_name: str = "", done: int = 0, total: int = 0,
                        elapsed_s: float = 0.0, waiting_approval: bool = False) -> None:
        """Update active-run chip display."""
        if not active:
            self.run_chip.setVisible(False)
            return

        mins = int(elapsed_s // 60)
        secs = int(elapsed_s % 60)
        time_str = f"{mins:02d}:{secs:02d}"
        counts = f"{done}/{total}" if total > 0 else ""
        label = f"◉ Building {game_name} · {counts} · {time_str}" if counts else f"◉ Building {game_name} · {time_str}"
        if waiting_approval:
            label = f"◉ Approval Needed · {game_name} · {time_str}"

        self.run_chip.setText(label)
        bg = tokens.ACCENT_WARNING if waiting_approval else tokens.ACCENT_PRIMARY
        self.run_chip.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {tokens.TEXT_PRIMARY};
                border: none;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        self.run_chip.setVisible(True)

    def update_systems(self, snapshot: SystemsSnapshot) -> None:
        """Update systems pill state and popover menu."""
        state = snapshot.overall
        label_text = "● Ready ▾" if state == "ok" else "● Degraded ▾" if state == "degraded" else "● Offline ▾"
        self.systems_btn.setText(label_text)
        self._set_pill_style(state)

        self.systems_menu.clear()
        self.systems_menu.setStyleSheet(f"""
            QMenu {{
                background: {tokens.BG_PANEL};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                padding: 6px;
            }}
        """)

        for row in snapshot.rows:
            self._add_system_menu_item(row)

    def _set_pill_style(self, state: str) -> None:
        color = tokens.ACCENT_SUCCESS if state == "ok" else tokens.ACCENT_WARNING if state == "degraded" else tokens.ACCENT_ERROR
        self.systems_btn.setStyleSheet(f"""
            QPushButton {{
                background: {tokens.BG_SURFACE};
                color: {color};
                border: 1px solid {tokens.BORDER};
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {tokens.BORDER_FOCUS};
            }}
        """)

    def refresh_icons(self) -> None:
        """Refresh toolbar icons to match active theme."""
        self.assistant_btn.setIcon(icon("assistant", role="secondary", size=18))
        self.palette_btn.setIcon(icon("search", role="secondary", size=18))

    def _add_system_menu_item(self, row: SystemRow) -> None:
        dot = "●" if row.state == "ok" else "▲" if row.state == "degraded" else "■"
        title = f"{dot} {row.key.capitalize()}: {row.summary}"
        action = self.systems_menu.addAction(title)
        if row.fix_action:
            fix_title = f"   ↳ Action: {row.fix_action.replace('_', ' ').capitalize()}"
            fix_act = self.systems_menu.addAction(fix_title)
            action_key = str(row.fix_action)
            fix_act.triggered.connect(lambda checked=False, k=action_key: self.fixActionRequested.emit(k))

    def update_theme(self) -> None:
        """Repaint top bar background and tool button icons with active theme tokens."""
        self.setStyleSheet(f"""
            QWidget#studioTopBar {{
                background: {tokens.BG_ROOT};
                border-bottom: 1px solid {tokens.BORDER};
            }}
        """)
        if hasattr(self, "assistant_btn"):
            self.assistant_btn.setIcon(icon("assistant", role="secondary", size=18))
        if hasattr(self, "palette_btn"):
            self.palette_btn.setIcon(icon("search", role="secondary", size=18))
