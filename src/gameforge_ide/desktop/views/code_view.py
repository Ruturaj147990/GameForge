"""CodeView: Developer mode hosting dock widgets inside a nested QMainWindow (WI-4.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from ..panels.asset_panel import AssetPanel
from ..panels.design_panel import DesignPanel
from ..panels.diff_panel import DiffPanel
from ..panels.explorer_panel import ExplorerPanel
from ..panels.mission_panel import MissionPanel
from ..panels.plan_panel import PlanPanel
from ..panels.terminal_panel import TerminalPanel
from ..panels.unreal_panel import UnrealPanel
from ..services.tool_service import ToolService
from ..styles import tokens


class CodeView(QMainWindow):
    """Developer view hosting code explorer, unreal, diff, and terminal docks."""

    def __init__(
        self,
        workspace_root: Path,
        tools: ToolService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("studioView_code")
        self.setWindowFlags(Qt.Widget)
        self._workspace = Path(workspace_root).resolve()
        self._tools = tools

        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)

        # Central placeholder in code view
        center = QWidget(self)
        center.setObjectName("codeViewCenter")
        self.setCentralWidget(center)

        # Panels
        self._explorer = ExplorerPanel(self._tools, self._workspace, parent=self)
        self._mission = MissionPanel(self._workspace, parent=self)
        self._plan_panel = PlanPanel(self._workspace, parent=self)
        self._asset_panel = AssetPanel(self._workspace, parent=self)
        self._design_panel = DesignPanel(self._workspace, parent=self)
        self._unreal_panel = UnrealPanel(self._tools, self._workspace, parent=self)
        self._diff_panel = DiffPanel(self._tools, parent=self)
        self._terminal = TerminalPanel(self._workspace, parent=self)

        # Docks
        self._dock_explorer = self._create_dock("Explorer", "dock_explorer", self._explorer, Qt.LeftDockWidgetArea)
        self._dock_unreal = self._create_dock("Unreal Engine", "dock_unreal", self._unreal_panel, Qt.RightDockWidgetArea)
        self._dock_diff = self._create_dock("Diff Review", "dock_diff", self._diff_panel, Qt.RightDockWidgetArea)
        self._dock_terminal = self._create_dock("Terminal", "dock_terminal", self._terminal, Qt.BottomDockWidgetArea)

        self._dock_explorer.setMinimumWidth(200)
        self._dock_unreal.setMinimumWidth(280)
        self._dock_terminal.setMinimumHeight(120)

        self.tabifyDockWidget(self._dock_unreal, self._dock_diff)
        self._dock_unreal.raise_()
        self._default_dock_layout = self.saveState()

    def _create_dock(self, title: str, obj_name: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(obj_name)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(area, dock)
        return dock

    def save_dock_state(self, settings: QSettings) -> None:
        """Persist dock positions and sizes."""
        settings.setValue("studio/code_view_layout", self.saveState())

    def restore_dock_state(self, settings: QSettings) -> bool:
        """Restore dock positions and sizes if saved."""
        saved = settings.value("studio/code_view_layout")
        if saved:
            return self.restoreState(saved)
        return False

    def reset_dock_layout(self) -> None:
        """Reset docks back to default layout."""
        if hasattr(self, "_default_dock_layout"):
            self.restoreState(self._default_dock_layout)
