"""GameForge IDE — Native QMainWindow.

Assembles all dockable panels into a cohesive desktop IDE experience.
There is no localhost, no browser, no WebSocket — all services are
called in-process via AgentService and ToolService.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QSize, Signal, Slot
from PySide6.QtGui import (
    QShortcut,
    QAction,
    QCloseEvent,
    QFont,
    QIcon,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QTabBar,
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import get_settings
from ..core.projects import (
    find_packaged_executable,
    find_uproject,
    find_gds,
    is_gameforge_project,
    list_all_project_dirs,
    open_folder_in_file_manager,
    resolve_project_dir,
)
from .panels.chat_panel import ChatPanel
from .panels.diff_panel import DiffPanel
from .panels.explorer_panel import ExplorerPanel
from .panels.mission_panel import MissionPanel
from .panels.plan_panel import PlanPanel
from .panels.asset_panel import AssetPanel
from .panels.design_panel import DesignPanel
from .panels.terminal_panel import TerminalPanel
from .panels.unreal_panel import UnrealPanel
from .services.agent_service import AgentService
from .services.tool_service import ToolService
from .styles.dark_theme import apply_theme, theme_stylesheet
from .shell import (
    AssistantPanel,
    CommandPalette,
    Rail,
    ToastOverlay,
    TopBar,
    ViewHost,
)
from .views import (
    AssetsView,
    BuildView,
    DesignView,
    EvidenceView,
    GamesView,
    HomeView,
    PlayView,
    SettingsView,
)
from .views.code_view import CodeView
from .services.systems_service import SystemsService
from .services.forge_service import ForgeService


class MainWindow(QMainWindow):
    """GameForge IDE native main window.

    Layout:
        ┌─────────────────────────────────────────────────────┐
        │  Menu Bar                                           │
        ├─────────────────────────────────────────────────────┤
        │  Tool Bar                                           │
        ├──────────┬──────────────────────────┬──────────────┤
        │ Explorer │        Chat Panel        │ Unreal / Diff│
        │  (dock)  │     (central widget)     │   (dock)     │
        ├──────────┴──────────────────────────┴──────────────┤
        │              Terminal (bottom dock)                 │
        ├─────────────────────────────────────────────────────┤
        │  Status Bar                                         │
        └─────────────────────────────────────────────────────┘
    """

    # Ollama health result from the background check: (reachable, error text). Queued onto the UI thread.
    _ollama_status_ready = Signal(bool, str)

    def __init__(self, workspace_root: Path) -> None:
        super().__init__()
        self._workspace = workspace_root
        self._current_project: Optional[str] = None
        self._current_project_dir: Optional[Path] = None
        self._ollama_check_running = False
        self._ollama_status_ready.connect(self._apply_ollama_status)
        settings_path = workspace_root / ".gameforge" / "ide_settings.ini"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = QSettings(str(settings_path), QSettings.IniFormat)
        self._theme = "light" if self._settings.value("appearance/theme", "dark") == "light" else "dark"

        # ── Services (in-process, no HTTP) ───────────────────────────────
        self._agent = AgentService(workspace_root, parent=self)
        self._tools = ToolService(workspace_root, parent=self)

        # ── Window meta ──────────────────────────────────────────────────
        self._update_window_title()
        self.setMinimumSize(1280, 780)
        self.resize(1600, 960)

        # ── Build UI ─────────────────────────────────────────────────────
        import os
        self._is_legacy_shell = os.environ.get("GAMEFORGE_LEGACY_SHELL") == "1"
        if self._is_legacy_shell:
            self._build_menu()
            self._build_toolbar()
            self._build_activity_rail()
            self._build_central()
            self._build_docks()
            self._build_status_bar()
            self._default_layout = self.saveState()
            saved_geometry = self._settings.value("window/geometry")
            saved_layout = self._settings.value("window/layout")
            if saved_geometry:
                self.restoreGeometry(saved_geometry)
            if saved_layout:
                self.restoreState(saved_layout)
        else:
            self._build_studio_shell()
            saved_geometry = self._settings.value("window/geometry")
            if saved_geometry:
                self.restoreGeometry(saved_geometry)
        apply_theme(QApplication.instance(), self._theme)
        # Storage hygiene 10 s after start, off the UI thread: only policy-safe actions
        # (log rotation, items past retention). Cap-based cleanup is user-confirmed in Mission Control.
        QTimer.singleShot(10_000, self._run_storage_hygiene)
        # Tabified docks showed "Unreal Engi..." / "Mission Con...": show full titles.
        QTimer.singleShot(0, self._unelide_dock_tabs)
        self.tabifiedDockWidgetActivated.connect(lambda _dock: self._unelide_dock_tabs())

        # ── Connect cross-panel signals ──────────────────────────────────
        self._chat_panel.diff_pending.connect(self._on_diff_pending)
        self._chat_panel.slash_command_executed.connect(self._on_slash_command)
        self._chat_panel.model_changed.connect(self._on_chat_model_changed)
        self._chat_panel.open_project_requested.connect(self._open_folder)
        self._chat_panel.unreal_status_changed.connect(self._apply_unreal_status)

        # ── Deferred startup health-check ────────────────────────────────
        self._health_timer = QTimer(self)
        self._health_timer.setSingleShot(True)
        self._health_timer.timeout.connect(self._check_ollama_status)
        self._health_timer.start(800)

        # ── Logical Tab focus order ───────────────────────────────────────
        if hasattr(self, "_tb_workspace_btn") and hasattr(self, "_tb_model_combo"):
            self.setTabOrder(self._tb_workspace_btn, self._tb_model_combo)
        if hasattr(self, "_tb_model_combo") and hasattr(self, "_chat_panel") and hasattr(self._chat_panel, "_composer"):
            self.setTabOrder(self._tb_model_combo, self._chat_panel._composer)
        if hasattr(self, "_chat_panel") and hasattr(self._chat_panel, "_composer") and hasattr(self._chat_panel, "_btn_send"):
            self.setTabOrder(self._chat_panel._composer, self._chat_panel._btn_send)
        if hasattr(self, "_chat_panel") and hasattr(self._chat_panel, "_btn_send") and hasattr(self, "_terminal") and hasattr(self._terminal, "_cmd_input"):
            self.setTabOrder(self._chat_panel._btn_send, self._terminal._cmd_input)
        if hasattr(self, "_terminal") and hasattr(self._terminal, "_cmd_input") and hasattr(self, "_unreal_panel") and hasattr(self._unreal_panel, "_btn_build"):
            self.setTabOrder(self._terminal._cmd_input, self._unreal_panel._btn_build)

    # ── Menu bar ─────────────────────────────────────────────────────────────

    def _unelide_dock_tabs(self) -> None:
        # QMainWindow creates the dock-area tab bars lazily as direct children of the window.
        for bar in self.findChildren(QTabBar):
            if bar.parent() is self:
                bar.setElideMode(Qt.ElideNone)
                bar.setExpanding(False)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        act_open = QAction("Open Folder…", self)
        act_open.setObjectName("file_open_folder")
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.setToolTip("Open workspace folder (Ctrl+O)")
        act_open.triggered.connect(self._open_folder)
        file_menu.addAction(act_open)

        act_new = QAction("New Session", self)
        act_new.setObjectName("file_new_session")
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._new_session)
        file_menu.addAction(act_new)
        file_menu.addSeparator()
        act_hosted = QAction("Hosted Models…", self)
        act_hosted.setObjectName("file_hosted_models")
        act_hosted.triggered.connect(self._open_hosted_settings)
        file_menu.addAction(act_hosted)
        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setObjectName("file_quit")
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # View
        view_menu = mb.addMenu("&View")
        self._act_show_explorer = QAction("Explorer", self, checkable=True, checked=True)
        self._act_show_explorer.setObjectName("view_explorer")
        self._act_show_explorer.setShortcut("Ctrl+Shift+E")
        self._act_show_explorer.triggered.connect(
            lambda c: self._dock_explorer.setVisible(c)
        )
        view_menu.addAction(self._act_show_explorer)

        self._act_show_unreal = QAction("Unreal Panel", self, checkable=True, checked=True)
        self._act_show_unreal.setObjectName("view_unreal")
        self._act_show_unreal.setShortcut("Ctrl+Shift+U")
        self._act_show_unreal.triggered.connect(
            lambda c: self._dock_unreal.setVisible(c)
        )
        view_menu.addAction(self._act_show_unreal)

        self._act_show_diff = QAction("Diff Review", self, checkable=True, checked=False)
        self._act_show_diff.setObjectName("view_diff")
        self._act_show_diff.setShortcut("Ctrl+Shift+D")
        self._act_show_diff.triggered.connect(
            lambda c: self._dock_diff.setVisible(c)
        )
        view_menu.addAction(self._act_show_diff)

        self._act_show_terminal = QAction("Terminal", self, checkable=True, checked=True)
        self._act_show_terminal.setObjectName("view_terminal")
        self._act_show_terminal.setShortcut("Ctrl+`")
        self._act_show_terminal.triggered.connect(
            lambda c: self._dock_terminal.setVisible(c)
        )
        view_menu.addAction(self._act_show_terminal)

        self._act_show_mission = QAction("Mission Control", self, checkable=True, checked=False)
        self._act_show_mission.setObjectName("view_mission")
        self._act_show_mission.setShortcut("Ctrl+Shift+M")
        self._act_show_mission.triggered.connect(
            lambda c: (self._dock_mission.setVisible(c), c and self._dock_mission.raise_())
        )
        view_menu.addAction(self._act_show_mission)
        self._act_show_plans = QAction("Execution Plans", self, checkable=True, checked=False)
        self._act_show_plans.setObjectName("view_plans")
        self._act_show_plans.triggered.connect(lambda: self._on_rail_action_clicked(2))
        view_menu.addAction(self._act_show_plans)

        self._act_show_assets = QAction("Asset Registry", self, checkable=True, checked=False)
        self._act_show_assets.setObjectName("view_assets")
        self._act_show_assets.triggered.connect(lambda: self._on_rail_action_clicked(3))
        view_menu.addAction(self._act_show_assets)

        view_menu.addSeparator()
        self._act_theme = QAction("Toggle Studio Dark/Light Theme", self)
        self._act_theme.setObjectName("view_toggle_theme")
        self._act_theme.setShortcut(QKeySequence("Ctrl+T"))
        self._act_theme.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._act_theme)
        self._act_reset_layout = QAction("Reset Layout", self)
        self._act_reset_layout.setObjectName("view_reset_layout")
        self._act_reset_layout.triggered.connect(self._reset_layout)
        view_menu.addAction(self._act_reset_layout)

        # Help
        help_menu = mb.addMenu("&Help")
        act_about = QAction("About GameForge IDE", self)
        act_about.setObjectName("help_about")
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

        self._act_command_palette = QAction("Command Palette…", self)
        self._act_command_palette.setObjectName("command_palette")
        self._act_command_palette.setShortcut(QKeySequence("Ctrl+K"))
        self._act_command_palette.setShortcuts([QKeySequence("Ctrl+K"), QKeySequence("Ctrl+Shift+P")])
        self._act_command_palette.setShortcutContext(Qt.WindowShortcut)
        self._act_command_palette.triggered.connect(self._open_command_palette)
        help_menu.addAction(self._act_command_palette)
        self.addAction(self._act_command_palette)

    # ── Toolbar ──────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar", self)
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.TopToolBarArea, tb)

        # Logo / brand label
        brand = QLabel("  🎮 GameForge IDE ")
        brand.setObjectName("brand_label")
        brand.setStyleSheet("color: #7c3aed; font-weight: 800; font-size: 14px; letter-spacing: 0.5px;")
        tb.addWidget(brand)

        # Workspace badge / switch button (like VS Code / Antigravity)
        self._tb_workspace_btn = QPushButton(f"📁 {self._workspace.name}")
        self._tb_workspace_btn.setObjectName("tb_workspace_badge")
        self._tb_workspace_btn.setToolTip(f"Active Workspace: {self._workspace}\nClick to choose another folder…")
        self._tb_workspace_btn.setStyleSheet(
            "QPushButton { background: #1a1f2c; color: #a5b4fc; border: 1px solid #374151; "
            "border-radius: 4px; padding: 4px 10px; font-weight: 600; font-size: 11px; margin-right: 6px; } "
            "QPushButton:hover { background: #262f45; border-color: #6366f1; color: #ffffff; }"
        )
        self._tb_workspace_btn.clicked.connect(self._open_folder)
        tb.addWidget(self._tb_workspace_btn)

        act_open_folder = QAction("📂 Open Folder…", self)
        act_open_folder.setObjectName("tb_open_folder")
        act_open_folder.setToolTip("Open workspace folder (Ctrl+O)")
        act_open_folder.triggered.connect(self._open_folder)
        tb.addAction(act_open_folder)

        sep = QWidget()
        sep.setFixedWidth(8)
        tb.addWidget(sep)

        act_new_session = QAction("＋ New Session", self)
        act_new_session.setObjectName("tb_new_session")
        act_new_session.setToolTip("Create a new chat session (Ctrl+N)")
        act_new_session.triggered.connect(self._new_session)
        tb.addAction(act_new_session)

        act_clear = QAction("🗑 Clear Chat", self)
        act_clear.setObjectName("tb_clear_chat")
        act_clear.triggered.connect(lambda: self._chat_panel._clear_chat())
        tb.addAction(act_clear)

        tb.addSeparator()

        act_ollama = QAction("⚡ Check Ollama", self)
        act_ollama.setObjectName("tb_check_ollama")
        act_ollama.triggered.connect(self._check_ollama_status)
        tb.addAction(act_ollama)

        tb.addSeparator()

        self._act_tb_terminal = QAction("⬛ Terminal", self)
        self._act_tb_terminal.setObjectName("tb_toggle_terminal")
        self._act_tb_terminal.setCheckable(True)
        self._act_tb_terminal.setChecked(True)
        self._act_tb_terminal.setToolTip("Toggle PowerShell Terminal dock (Ctrl+`)")
        self._act_tb_terminal.triggered.connect(
            lambda c: self._dock_terminal.setVisible(c)
        )
        tb.addAction(self._act_tb_terminal)

        tb.addSeparator()

        lbl_model = QLabel("Model: ")
        lbl_model.setStyleSheet("color: #9d95b0; font-size: 11px; font-weight: 600; margin-left: 4px;")
        tb.addWidget(lbl_model)

        self._tb_model_combo = QComboBox()
        self._tb_model_combo.setObjectName("tb_model_combo")
        self._tb_model_combo.setMinimumWidth(220)
        self._tb_model_combo.setStyleSheet(
            "QComboBox { background: #1a1f2c; color: #a5b4fc; border: 1px solid #374151; "
            "border-radius: 4px; padding: 3px 8px; font-weight: 600; font-size: 11px; } "
            "QComboBox:hover { border-color: #6366f1; } "
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        self._tb_model_combo.addItem(get_settings().model_for("chat"))
        self._tb_model_combo.currentTextChanged.connect(self._on_top_model_changed)
        tb.addWidget(self._tb_model_combo)

        # Spacer to push status to right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        # Ollama status indicator
        self._ollama_indicator = QLabel("● Ollama: checking…")
        self._ollama_indicator.setObjectName("ollama_indicator")
        self._ollama_indicator.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 600; padding-right: 12px;")
        tb.addWidget(self._ollama_indicator)
        self._unreal_indicator = QLabel("● Unreal: disconnected")
        self._unreal_indicator.setObjectName("unreal_indicator")
        self._unreal_indicator.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 600; padding-right: 12px;")
        tb.addWidget(self._unreal_indicator)

    # ── Left Activity Rail ───────────────────────────────────────────────────

    def _build_activity_rail(self) -> None:
        rail = QToolBar("Activity Rail", self)
        rail.setObjectName("activity_rail")
        rail.setMovable(False)
        rail.setIconSize(QSize(20, 20))
        rail.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(Qt.LeftToolBarArea, rail)

        self._act_rail_explorer = QAction("📁", self)
        self._act_rail_explorer.setObjectName("rail_act_explorer")
        self._act_rail_explorer.setCheckable(True)
        self._act_rail_explorer.setChecked(True)
        self._act_rail_explorer.setToolTip("Explorer (Files) — Ctrl+Shift+E")
        self._act_rail_explorer.triggered.connect(lambda: self._on_rail_action_clicked(0))
        rail.addAction(self._act_rail_explorer)

        self._act_rail_games = QAction("🎮", self)
        self._act_rail_games.setObjectName("rail_act_games")
        self._act_rail_games.setCheckable(True)
        self._act_rail_games.setToolTip("Games & Mission Control — Ctrl+Shift+M")
        self._act_rail_games.triggered.connect(lambda: self._on_rail_action_clicked(1))
        rail.addAction(self._act_rail_games)

        self._act_rail_plans = QAction("📋", self)
        self._act_rail_plans.setObjectName("rail_act_plans")
        self._act_rail_plans.setCheckable(True)
        self._act_rail_plans.setToolTip("Execution Plans")
        self._act_rail_plans.triggered.connect(lambda: self._on_rail_action_clicked(2))
        rail.addAction(self._act_rail_plans)

        self._act_rail_assets = QAction("📦", self)
        self._act_rail_assets.setObjectName("rail_act_assets")
        self._act_rail_assets.setCheckable(True)
        self._act_rail_assets.setToolTip("Asset Registry")
        self._act_rail_assets.triggered.connect(lambda: self._on_rail_action_clicked(3))
        rail.addAction(self._act_rail_assets)

        self._act_rail_design = QAction("📐", self)
        self._act_rail_design.setObjectName("rail_act_design")
        self._act_rail_design.setCheckable(True)
        self._act_rail_design.setToolTip("Game Design Spec (Design)")
        self._act_rail_design.triggered.connect(lambda: self._on_rail_action_clicked(4))
        rail.addAction(self._act_rail_design)

    @Slot(int)
    def _on_sidebar_tab_changed(self, index: int) -> None:
        if hasattr(self, "_left_stack"):
            self._left_stack.setCurrentIndex(index)
        self._sync_rail_actions(index)
        if hasattr(self, "_dock_explorer") and not self._dock_explorer.isVisible():
            self._dock_explorer.show()

    def _sync_rail_actions(self, active_index: int) -> None:
        actions = [
            getattr(self, "_act_rail_explorer", None),
            getattr(self, "_act_rail_games", None),
            getattr(self, "_act_rail_plans", None),
            getattr(self, "_act_rail_assets", None),
            getattr(self, "_act_rail_design", None),
        ]
        is_vis = getattr(self, "_dock_explorer", None) and self._dock_explorer.isVisible()
        for i, act in enumerate(actions):
            if act is not None:
                act.setChecked(i == active_index and bool(is_vis))

    @Slot(int)
    def _on_rail_action_clicked(self, index: int) -> None:
        if hasattr(self, "_dock_explorer"):
            if self._dock_explorer.isVisible() and hasattr(self, "_left_stack") and self._left_stack.currentIndex() == index:
                self._dock_explorer.hide()
                self._sync_rail_actions(-1)
            else:
                self._dock_explorer.show()
                self._dock_explorer.raise_()
                if hasattr(self, "_sidebar_tabbar"):
                    self._sidebar_tabbar.setCurrentIndex(index)
                if hasattr(self, "_left_stack"):
                    self._left_stack.setCurrentIndex(index)
                self._sync_rail_actions(index)

    # ── Central widget (Chat) ─────────────────────────────────────────────────

    def _build_central(self) -> None:
        self._chat_panel = ChatPanel(self._agent, workspace_root=self._workspace, parent=self)
        self.setCentralWidget(self._chat_panel)

    # ── Dock panels ───────────────────────────────────────────────────────────

    def _build_docks(self) -> None:
        # Corner configurations so left/right docks can extend cleanly
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)

        # ── Left Activity Views (Explorer, Games, Plans, Assets) ─────────
        self._explorer = ExplorerPanel(self._tools, self._workspace, parent=self)
        self._explorer.open_folder_requested.connect(self._open_folder)

        self._mission = MissionPanel(self._workspace, parent=self)
        self._mission.play_requested.connect(self._chat_panel._on_play_game)
        self._mission.open_approval.connect(self._chat_panel.show_approval)
        self._chat_panel.action_finished.connect(lambda *_: self._mission.refresh_lists())

        self._plan_panel = PlanPanel(self._workspace, parent=self)
        self._plan_panel.approval_review_requested.connect(self._chat_panel.show_approval)
        self._chat_panel.action_finished.connect(lambda *_: self._plan_panel.refresh_from_disk())

        self._asset_panel = AssetPanel(self._workspace, parent=self)
        self._design_panel = DesignPanel(self._workspace, parent=self)

        # Assemble left sidebar container with collapsed tabs
        self._left_sidebar_container = QWidget()
        sidebar_layout = QVBoxLayout(self._left_sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self._sidebar_tabbar = QTabBar()
        self._sidebar_tabbar.setObjectName("sidebar_tabbar")
        self._sidebar_tabbar.addTab("📁 Explorer")
        self._sidebar_tabbar.addTab("🎮 Games")
        self._sidebar_tabbar.addTab("📋 Plans")
        self._sidebar_tabbar.addTab("📦 Assets")
        self._sidebar_tabbar.addTab("📐 Design")
        self._sidebar_tabbar.currentChanged.connect(self._on_sidebar_tab_changed)
        sidebar_layout.addWidget(self._sidebar_tabbar)

        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._explorer)
        self._left_stack.addWidget(self._mission)
        self._left_stack.addWidget(self._plan_panel)
        self._left_stack.addWidget(self._asset_panel)
        self._left_stack.addWidget(self._design_panel)
        sidebar_layout.addWidget(self._left_stack, 1)

        self._dock_explorer = self._make_dock("Explorer", self._left_sidebar_container, Qt.LeftDockWidgetArea)
        self._dock_explorer.setMinimumWidth(220)
        self._dock_explorer.setMaximumWidth(450)
        self._dock_mission = self._dock_explorer  # alias for backward compat

        # ── Unreal Engine (right) ─────────────────────────────────────────
        self._unreal_panel = UnrealPanel(self._tools, self._workspace, parent=self)
        self._unreal_panel.create_game_requested.connect(self._on_create_game_from_unreal)
        self._dock_unreal = self._make_dock("Unreal Engine 5", self._unreal_panel, Qt.RightDockWidgetArea)
        self._dock_unreal.setMinimumWidth(300)
        self._dock_unreal.setMaximumWidth(460)

        # ── Diff Review (right, tabbed with Unreal) ───────────────────────
        self._diff_panel = DiffPanel(self._tools, parent=self)
        self._diff_panel.diff_approved.connect(self._on_diff_applied)
        self._diff_panel.diff_rejected.connect(self._on_diff_rejected)
        self._diff_panel.diff_rolled_back.connect(self._on_diff_rolled_back)
        self._dock_diff = self._make_dock("Diff Review", self._diff_panel, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(self._dock_unreal, self._dock_diff)
        self._dock_diff.hide()  # Hidden until a diff is pending
        self._dock_unreal.raise_()

        # ── Terminal (bottom) ─────────────────────────────────────────────
        self._terminal = TerminalPanel(self._workspace, parent=self)
        self._dock_terminal = self._make_dock("Terminal", self._terminal, Qt.BottomDockWidgetArea)
        self._dock_terminal.setMinimumHeight(120)
        self._dock_terminal.setMaximumHeight(350)

        # Proportional initial dock geometry allocation
        self.resizeDocks([self._dock_explorer], [260], Qt.Horizontal)
        self.resizeDocks([self._dock_unreal], [340], Qt.Horizontal)
        self.resizeDocks([self._dock_terminal], [160], Qt.Vertical)

        # ── Visibility sync with menu & toolbar items ─────────────────────
        self._dock_explorer.visibilityChanged.connect(
            lambda v: (
                self._act_show_explorer.setChecked(v and self._left_stack.currentIndex() == 0),
                self._act_show_mission.setChecked(v and self._left_stack.currentIndex() == 1),
                self._act_show_plans.setChecked(v and self._left_stack.currentIndex() == 2),
                self._act_show_assets.setChecked(v and self._left_stack.currentIndex() == 3),
                self._sync_rail_actions(self._left_stack.currentIndex() if v else -1),
            )
        )
        self._dock_unreal.visibilityChanged.connect(
            lambda v: self._act_show_unreal.setChecked(v)
        )
        self._dock_diff.visibilityChanged.connect(
            lambda v: self._act_show_diff.setChecked(v)
        )
        self._dock_terminal.visibilityChanged.connect(
            lambda v: (self._act_show_terminal.setChecked(v), self._act_tb_terminal.setChecked(v))
        )

    def _make_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock_{title.lower().replace(' ', '_')}")
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetClosable)
        empty_title = QWidget()
        empty_title.setFixedHeight(0)
        dock.setTitleBarWidget(empty_title)
        self.addDockWidget(area, dock)
        return dock

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        sb.setObjectName("main_status_bar")
        self.setStatusBar(sb)

        self._status_lbl = QLabel(f"Workspace: {self._workspace.name}")
        self._status_lbl.setObjectName("status_workspace")
        self._status_lbl.setToolTip(str(self._workspace))
        sb.addWidget(self._status_lbl)

        # (no separator before the first permanent widget: it rendered as an orphan "|" on the right)
        self._model_status = QLabel("Model: " + get_settings().model_for("chat"))
        self._model_status.setObjectName("status_model")
        self._model_status.setStyleSheet("color: #7c3aed;")
        sb.addPermanentWidget(self._model_status)

        sb.addPermanentWidget(QLabel("|"))

        self._version_lbl = QLabel("GameForge IDE v1.0.0")
        self._version_lbl.setObjectName("status_version")
        self._version_lbl.setStyleSheet("color: #9d95b0; font-size: 11px;")
        sb.addPermanentWidget(self._version_lbl)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _update_window_title(self) -> None:
        self.setWindowTitle(f"GameForge IDE — {self._workspace.name} — [{self._workspace}]")

    @Slot()
    def _open_folder(self) -> None:
        """Prompt user with native directory picker dialog and switch workspace or open project."""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Open Project or Workspace Folder",
            str(self._current_project_dir or self._workspace),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if chosen:
            self.open_project_folder(Path(chosen))

    def open_project_folder(self, folder: Path) -> None:
        """Handle opening a specific project or workspace folder."""
        target = folder.resolve()
        if not target.exists():
            QMessageBox.warning(self, "Invalid Directory", f"The directory does not exist:\n{target}")
            return

        if is_gameforge_project(target):
            # Target is a project itself!
            p_name = target.name
            parent_ws = target.parent if target.parent != target else target
            self.switch_workspace(parent_ws)
            self.refresh_projects(select_project=p_name)
            self._on_project_selected(p_name)
            if hasattr(self, "_toasts"):
                self._toasts.info("Project Opened", f"Opened project '{p_name}' from {target}")
            self.statusBar().showMessage(f"Opened project: {p_name} ({target})", 4000)
            self._switch_studio_view("design")
        else:
            # Target is a workspace folder containing projects or general workspace
            self.switch_workspace(target)
            self.refresh_projects()
            projects = self._list_projects()
            if projects:
                self._on_project_selected(projects[0])

    def switch_workspace(self, new_workspace: Path | str) -> None:
        """Switch active workspace directory across all panels and services."""
        target = Path(new_workspace).resolve()
        if not target.exists():
            QMessageBox.warning(self, "Invalid Workspace", f"The directory does not exist:\n{target}")
            return

        self._workspace = target
        self._update_window_title()

        # Persist chosen workspace in local settings
        settings_path = self._workspace / ".gameforge" / "ide_settings.ini"
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings = QSettings(str(settings_path), QSettings.IniFormat)
            self._settings.setValue("workspace/last_opened", str(self._workspace))
            self._settings.sync()
        except Exception:
            pass

        # Reconfigure services
        self._agent.set_workspace(self._workspace)
        self._tools.set_workspace(self._workspace)

        # Reconfigure panels
        self._explorer.set_workspace(self._workspace, tool_service=self._tools)
        self._unreal_panel.set_workspace(self._tools, self._workspace)
        self._chat_panel.set_workspace(self._agent, self._workspace)
        self._terminal.set_workspace(self._workspace)
        self._mission.set_workspace(self._workspace)
        if hasattr(self, "_plan_panel"):
            self._plan_panel._workspace = self._workspace
            self._plan_panel.refresh_from_disk()
        if hasattr(self, "_asset_panel") and hasattr(self._asset_panel, "set_workspace"):
            self._asset_panel.set_workspace(self._workspace)
        if hasattr(self, "_design_panel") and hasattr(self._design_panel, "set_workspace"):
            self._design_panel.set_workspace(self._workspace)
        self._diff_panel.clear()
        self._apply_unreal_status(False, "", "")

        # Update toolbar and status bar labels
        if hasattr(self, "_tb_workspace_btn"):
            self._tb_workspace_btn.setText(f"📁 {self._workspace.name}")
            self._tb_workspace_btn.setToolTip(f"Active Workspace: {self._workspace}\nClick to choose another folder…")
        if hasattr(self, "_status_lbl"):
            self._status_lbl.setText(f"Workspace: {self._workspace.name}")
            self._status_lbl.setToolTip(str(self._workspace))

        self.statusBar().showMessage(f"Switched workspace to: {self._workspace.name}", 4000)

    @Slot()
    def _run_storage_hygiene(self) -> None:
        import threading
        ws = self._workspace

        def work():
            try:
                from ..backend import storage_hygiene as sh
                sh.apply(ws, sh.plan(ws, cap_bytes=1 << 62))  # retention + rotation only
            except Exception:
                pass
        threading.Thread(target=work, name="gf-storage-hygiene", daemon=True).start()

    def _open_hosted_settings(self) -> None:
        from .dialogs.hosted_settings import HostedSettingsDialog  # lazy: keeps startup fast
        HostedSettingsDialog(self._workspace, parent=self).exec()

    @Slot(str)
    def _handle_fix_action(self, action_key: str) -> None:
        """Handle readiness probe fix actions across HomeView and TopBar."""
        if action_key == "start_ollama":
            self._open_ollama_setup()
        elif action_key == "open_hosted":
            self._open_hosted_settings()
        elif action_key == "set_engine":
            self._switch_studio_view("settings")
            if hasattr(self, "_toasts"):
                self._toasts.info("Engine Setup", "Configure Unreal Engine 5.7 root path in Settings.")

    def _open_ollama_setup(self) -> None:
        from .dialogs.ollama_setup import OllamaSetupDialog
        dlg = OllamaSetupDialog(
            workspace_root=self._workspace,
            systems_service=getattr(self, "_systems_service", None),
            parent=self,
        )
        dlg.settingsRequested.connect(lambda: self._switch_studio_view("settings"))
        dlg.serviceStarted.connect(self._check_ollama_status)
        dlg.exec()

    def _new_session(self) -> None:
        self._chat_panel._new_session()
        self.statusBar().showMessage("New session started.", 3000)

    @Slot()
    def _toggle_theme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        apply_theme(QApplication.instance(), self._theme)
        self._settings.setValue("appearance/theme", self._theme)
        self._settings.sync()
        from .styles.dark_theme import get_theme_display_name
        self.statusBar().showMessage(f"{get_theme_display_name(self._theme)} theme enabled.", 3000)

    @Slot()
    def _reset_layout(self) -> None:
        self.restoreState(self._default_layout)
        self.resize(1600, 960)
        self.statusBar().showMessage("Default panel layout restored.", 3000)

    @Slot()
    def _check_ollama_status(self) -> None:
        """Probe Ollama off the UI thread: is_available() is an HTTP call with a 3 s timeout, which used to freeze the
        window at startup and on every "Check Ollama" click when the host did not answer."""
        if self._ollama_check_running or getattr(self, "_ollama_indicator", None) is None:
            return
        self._ollama_check_running = True
        self._ollama_indicator.setText("● Ollama: checking…")

        def work() -> None:
            try:
                from ..backend.providers.ollama_provider import OllamaProvider
                ok, err = bool(OllamaProvider().is_available()), ""
            except Exception as exc:  # noqa: BLE001 - reported in the indicator
                ok, err = False, str(exc)
            try:
                self._ollama_status_ready.emit(ok, err)
            except RuntimeError:
                pass  # the window was closed while the probe was waiting

        import threading
        threading.Thread(target=work, name="gf-ollama-health", daemon=True).start()

    @Slot(bool, str)
    def _apply_ollama_status(self, ok: bool, error: str) -> None:
        self._ollama_check_running = False
        self._chat_panel.set_model_server_available(ok)
        try:
            if error:
                raise RuntimeError(error)
            if ok:
                self._ollama_indicator.setText("● Ollama: online")
                self._ollama_indicator.setStyleSheet(theme_stylesheet(
                    "color: #00d9a3; font-size: 12px; padding-right: 12px; font-weight: 600;"
                ))
                self._sync_models_to_toolbar()
            else:
                self._ollama_indicator.setText("● Ollama: offline")
                self._ollama_indicator.setStyleSheet(theme_stylesheet(
                    "color: #ff6b6b; font-size: 12px; padding-right: 12px; font-weight: 600;"
                ))
        except Exception as exc:
            self._ollama_indicator.setText(f"● Ollama: error ({exc})")
            self._ollama_indicator.setStyleSheet(theme_stylesheet(
                "color: #ff6b6b; font-size: 12px; padding-right: 12px;"
            ))

    @Slot(bool, str, str)
    def _apply_unreal_status(self, connected: bool, project_name: str = "", active_asset: str = "") -> None:
        if not hasattr(self, "_unreal_indicator"):
            return
        if connected:
            txt = f"● UE: {project_name}" if project_name else "● UE: connected"
            if active_asset:
                txt += f" ({Path(active_asset).name})"
            self._unreal_indicator.setText(txt)
            self._unreal_indicator.setStyleSheet(theme_stylesheet(
                "color: #00d9a3; font-size: 12px; padding-right: 12px; font-weight: 600;"
            ))
        else:
            self._unreal_indicator.setText("● Unreal: disconnected")
            self._unreal_indicator.setStyleSheet(theme_stylesheet(
                "color: #9ca3af; font-size: 12px; padding-right: 12px; font-weight: 600;"
            ))

    def _sync_models_to_toolbar(self) -> None:
        """Populate the top toolbar model combo with available models."""
        try:
            models = self._agent.list_models()
        except Exception:
            return
        current = self._tb_model_combo.currentText() or self._chat_panel._current_model
        self._tb_model_combo.blockSignals(True)
        try:  # always unblock: an exception here used to leave the toolbar combo's signals blocked
            self._tb_model_combo.clear()
            for m in models:
                self._tb_model_combo.addItem(m.get("id", m.get("name", "unknown")))
            idx = self._tb_model_combo.findText(current)
            if idx >= 0:
                self._tb_model_combo.setCurrentIndex(idx)
            elif self._tb_model_combo.count() > 0:
                self._tb_model_combo.setCurrentIndex(0)
        finally:
            self._tb_model_combo.blockSignals(False)

    @Slot(str)
    def _on_top_model_changed(self, model_name: str) -> None:
        """When user selects a model from the top main toolbar."""
        if not model_name:
            return
        if hasattr(self, "_model_status"):
            self._model_status.setText(f"Model: {model_name}")
        self._chat_panel.set_model(model_name)
        self.statusBar().showMessage(f"Active model set to: {model_name}", 3000)

    @Slot(str)
    def _on_chat_model_changed(self, model_name: str) -> None:
        """When model is changed inside ChatPanel (e.g. via combo or /model command)."""
        if not hasattr(self, "_tb_model_combo") or not model_name:
            return
        if hasattr(self, "_model_status"):
            self._model_status.setText(f"Model: {model_name}")
        if self._tb_model_combo.currentText() != model_name:
            self._tb_model_combo.blockSignals(True)
            idx = self._tb_model_combo.findText(model_name)
            if idx >= 0:
                self._tb_model_combo.setCurrentIndex(idx)
            else:
                self._tb_model_combo.addItem(model_name)
                self._tb_model_combo.setCurrentText(model_name)
            self._tb_model_combo.blockSignals(False)

    @Slot(str, dict)
    def _on_diff_pending(self, diff_id: str, meta: dict) -> None:
        self._diff_panel.show_diff(diff_id, meta)
        self._dock_diff.show()
        self._dock_diff.raise_()
        self.statusBar().showMessage(f"Diff pending review: {diff_id}", 5000)

    @Slot(str)
    def _on_diff_applied(self, diff_id: str) -> None:
        self.statusBar().showMessage(f"✅ Diff {diff_id} applied successfully. Resuming task...", 4000)
        session_id = getattr(self._chat_panel, "_session_id", None)
        if session_id and hasattr(self, "_agent"):
            self._agent.resume_after_diff(session_id, diff_id, approved=True)

    @Slot(str)
    def _on_diff_rejected(self, diff_id: str) -> None:
        self.statusBar().showMessage(f"❌ Diff {diff_id} rejected.", 4000)
        session_id = getattr(self._chat_panel, "_session_id", None)
        if session_id and hasattr(self, "_agent"):
            self._agent.resume_after_diff(session_id, diff_id, approved=False)

    @Slot(str)
    def _on_diff_rolled_back(self, diff_id: str) -> None:
        self.statusBar().showMessage(f"↩️ Diff {diff_id} rolled back.", 4000)

    def _on_create_game_from_unreal(self) -> None:
        if hasattr(self, "_chat_panel") and hasattr(self._chat_panel, "_composer"):
            self._chat_panel._composer.setText("/game ")
            self._chat_panel._composer.setFocus()

    @Slot(str, str)
    def _on_slash_command(self, cmd: str, full_cmd: str) -> None:
        """Handle slash command actions triggered from ChatPanel."""
        if cmd in ("/mission", "mission"):
            self._on_rail_action_clicked(1)
            return
        if cmd == "/build":
            self._dock_unreal.show()
            self._dock_unreal.raise_()
            self._unreal_panel._on_build()
            self.statusBar().showMessage("⚙️ Staged build triggered via /build command.", 4000)
        elif cmd == "/diff":
            self._dock_diff.setVisible(not self._dock_diff.isVisible())
            if self._dock_diff.isVisible():
                self._dock_diff.raise_()
        elif cmd == "/terminal":
            self._dock_terminal.setVisible(not self._dock_terminal.isVisible())
            if self._dock_terminal.isVisible():
                self._dock_terminal.raise_()
        elif cmd == "/explorer":
            self._dock_explorer.setVisible(not self._dock_explorer.isVisible())
            if self._dock_explorer.isVisible():
                self._dock_explorer.raise_()
        elif cmd in ("/ue", "/context"):
            self._dock_unreal.show()
            self._dock_unreal.raise_()
            self._unreal_panel._refresh()
            self.statusBar().showMessage("🎮 Unreal Engine context synced.", 3000)
        elif cmd == "/undo":
            if self._diff_panel._btn_rollback.isEnabled():
                self._dock_diff.show()
                self._dock_diff.raise_()
                self._diff_panel._on_rollback()
                self.statusBar().showMessage("↩️ Rollback initiated via /undo.", 4000)
            else:
                self.statusBar().showMessage("ℹ️ No active applied diff available to rollback.", 4000)
        elif cmd == "/test":
            self._dock_terminal.show()
            self._dock_terminal.raise_()
            self._terminal.run_command("pytest tests/unit/ -q")
            self.statusBar().showMessage("🧪 Test verification started in terminal.", 4000)


    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GameForge IDE",
            "<h3>GameForge IDE v1.0.0</h3>"
            "<p>Agentic game-development environment powered by<br>"
            "local Ollama models (gameforge-qwen3.5-9b, gameforge-qwen3.5-4b, gameforge-27b-sft, llama3.1:8b) "
            "or an opt-in hosted provider.</p>"
            "<p>Supports Unreal Engine 5.7, Unity 6, Godot 4.3.</p>"
            "<p>© 2026 GameForge Project — Windows 11 Native PySide6 Desktop</p>",
        )

    def _command_palette_commands(self):
        """Return only currently implemented user-facing commands."""
        return [
            ("File: Open Workspace Folder…", self._open_folder),
            ("New Session", self._new_session),
            ("Clear Chat", self._chat_panel._clear_chat),
            ("Check Ollama", self._check_ollama_status),
            ("Toggle Studio Dark/Light Theme", self._toggle_theme),
            ("Reset Layout", self._reset_layout),
            ("Toggle Explorer", lambda: self._dock_explorer.setVisible(not self._dock_explorer.isVisible())),
            ("Toggle Unreal Panel", lambda: self._dock_unreal.setVisible(not self._dock_unreal.isVisible())),
            ("Toggle Diff Review", lambda: self._dock_diff.setVisible(not self._dock_diff.isVisible())),
            ("Toggle Terminal", lambda: self._dock_terminal.setVisible(not self._dock_terminal.isVisible())),
            ("View: Home", lambda: self._switch_studio_view("home")),
            ("View: Games Catalog", lambda: self._switch_studio_view("games")),
            ("View: Design", lambda: self._switch_studio_view("design")),
            ("View: Build", lambda: self._switch_studio_view("build")),
            ("View: Play", lambda: self._switch_studio_view("play")),
            ("View: Evidence", lambda: self._switch_studio_view("evidence")),
            ("View: Settings", lambda: self._switch_studio_view("settings")),
            ("Unreal: Run Staged Build", self._unreal_panel._on_build),
            ("Unreal: Refresh Engine Status", self._unreal_panel._refresh),
            ("About GameForge IDE", self._show_about),
        ]

    @Slot()
    def _open_command_palette(self) -> None:
        palette = CommandPalette(self._command_palette_commands(), self)
        palette.exec()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched.objectName() == "command_palette_search" and event.type() == QEvent.KeyPress:
            commands = watched.property("commandPaletteList")
            dialog = watched.property("commandPaletteDialog")
            if event.key() in (Qt.Key_Down, Qt.Key_Up) and commands is not None:
                visible_rows = [
                    i for i in range(commands.count()) if not commands.item(i).isHidden()
                ]
                if visible_rows:
                    current = commands.currentRow()
                    try:
                        position = visible_rows.index(current)
                    except ValueError:
                        position = 0
                    step = 1 if event.key() == Qt.Key_Down else -1
                    commands.setCurrentRow(visible_rows[(position + step) % len(visible_rows)])
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and commands is not None:
                item = commands.currentItem()
                if item is not None and not item.isHidden():
                    callback = item.data(Qt.UserRole)
                    dialog.accept()
                    callback()
                return True
            if event.key() == Qt.Key_Escape and dialog is not None:
                dialog.reject()
                return True
        return super().eventFilter(watched, event)

    # ── Window lifecycle ──────────────────────────────────────────────────────


    # ── Studio UX Shell (WI-4.3) ─────────────────────────────────────────────

    def _build_studio_shell(self) -> None:
        self.setObjectName("studioMainWindow")

        # In Studio shell, menu bar is hidden (accessible via Palette Ctrl+K and shortcuts)
        self.menuBar().setVisible(False)

        # Services
        self._systems_service = SystemsService(workspace_root=self._workspace, parent=self)
        self._forge_service = ForgeService(workspace_root=self._workspace, parent=self)

        # Pre-instantiate CodeView so all dock attributes and panels are available
        self._get_or_create_code_view()

        # Top bar
        self._top_bar = TopBar(self)
        self._top_bar.homeRequested.connect(lambda: self._switch_studio_view("home"))
        self._top_bar.buildViewRequested.connect(lambda: self._switch_studio_view("build"))
        self._top_bar.assistantToggled.connect(self._toggle_assistant)
        self._top_bar.paletteRequested.connect(self._open_command_palette)
        self._top_bar.projectSelected.connect(self._on_project_selected)
        self._top_bar.openFolderRequested.connect(self._open_folder)
        self._top_bar.fixActionRequested.connect(self._handle_fix_action)
        self._systems_service.snapshotChanged.connect(self._top_bar.update_systems)

        # Activity rail (56px)
        self._rail = Rail(self)
        self._rail.viewRequested.connect(self._switch_studio_view)

        # View host (lazily created views)
        self._view_host = ViewHost(self)
        self._register_studio_views()
        self._view_host.viewChanged.connect(self._on_studio_view_changed)

        # Assistant panel (collapsible right drawer)
        self._chat_panel = ChatPanel(self._agent, workspace_root=self._workspace, parent=self)
        self._assistant_panel = AssistantPanel(self._chat_panel, self)
        self._assistant_panel.closeRequested.connect(lambda: self._set_assistant_visible(False))
        self._assistant_panel.modelChanged.connect(self._on_chat_model_changed)
        self._assistant_panel.openDesignRequested.connect(self._on_assistant_open_design)
        models = [get_settings().model_for("chat")]
        self._assistant_panel.set_models(models, models[0])

        # Center splitter: ViewHost + AssistantPanel
        self._center_splitter = QSplitter(Qt.Horizontal, self)
        self._center_splitter.setObjectName("studioCenterSplitter")
        self._center_splitter.addWidget(self._view_host)
        self._center_splitter.addWidget(self._assistant_panel)
        self._center_splitter.setCollapsible(0, False)
        self._center_splitter.setCollapsible(1, True)

        saved_assistant_w = int(self._settings.value("studio/assistant_width", 380))
        self._center_splitter.setSizes([1600 - saved_assistant_w - 56, saved_assistant_w])

        # Main central widget assembly
        central = QWidget(self)
        central.setObjectName("studioCentralWidget")
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._top_bar)

        body = QWidget(central)
        hbox = QHBoxLayout(body)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(self._rail)
        hbox.addWidget(self._center_splitter, 1)
        vbox.addWidget(body, 1)

        self.setCentralWidget(central)

        # Status bar
        self._build_status_bar()

        # Toasts overlay
        self._toasts = ToastOverlay(self)

        # Switch to initial view
        last_view = str(self._settings.value("studio/last_view", "home"))
        if not self._switch_studio_view(last_view):
            self._switch_studio_view("home")

        # Shortcuts
        self._register_studio_shortcuts()

    def _get_or_create_code_view(self) -> CodeView:
        if not hasattr(self, "_code_view") or self._code_view is None:
            self._code_view = CodeView(self._workspace, self._tools, parent=self)
            self._dock_explorer = self._code_view._dock_explorer
            self._dock_unreal = self._code_view._dock_unreal
            self._dock_diff = self._code_view._dock_diff
            self._dock_terminal = self._code_view._dock_terminal
            self._explorer = self._code_view._explorer
            self._unreal_panel = self._code_view._unreal_panel
            self._diff_panel = self._code_view._diff_panel
            self._terminal = self._code_view._terminal
            self._mission = self._code_view._mission
            self._plan_panel = self._code_view._plan_panel
            self._asset_panel = self._code_view._asset_panel
            self._design_panel = self._code_view._design_panel
            self._explorer.open_folder_requested.connect(self._open_folder)
        return self._code_view

    def _register_studio_views(self) -> None:
        self._current_project: Optional[str] = None
        projects = self._list_projects()
        if projects:
            self._current_project = projects[0]
            self._top_bar.set_projects(projects, self._current_project)

        def create_home_view() -> HomeView:
            view = HomeView(parent=self)
            if hasattr(self, "_systems_service"):
                view.attach_systems_service(self._systems_service)
            view.projectSelected.connect(self._on_games_open_requested)
            view.designReady.connect(self._on_home_design_ready)
            view.fixActionRequested.connect(self._handle_fix_action)
            view.openAssistantRequested.connect(lambda: self._set_assistant_visible(True))
            return view

        def create_games_view() -> GamesView:
            view = GamesView(parent=self)
            view.openGameRequested.connect(self._on_games_open_requested)
            view.playGameRequested.connect(self._on_games_play_requested)
            view.buildGameRequested.connect(self._on_games_build_requested)
            view.newProjectRequested.connect(self._on_new_project_requested)
            view.openProjectRequested.connect(self._on_open_project_directory_requested)
            view.gameDeleted.connect(self._on_game_deleted)
            return view

        self._view_host.register("home", create_home_view)
        self._view_host.register("games", create_games_view)
        def create_design_view() -> DesignView:
            view = DesignView(parent=self)
            view.buildRequested.connect(self._on_games_build_requested)
            if self._current_project:
                view.load_project(self._current_project)
            return view

        self._view_host.register(
            "design",
            create_design_view,
            enabled_when=lambda: (bool(self._current_project), "Select a game first")
        )

        def create_build_view() -> BuildView:
            view = BuildView(
                forge_service=getattr(self, "_forge_service", None),
                workspace_root=self._workspace,
                parent=self,
            )
            view.playRequested.connect(self._on_games_play_requested)
            view.openCodeRequested.connect(lambda f, l: self._switch_studio_view("code"))
            if self._current_project:
                view.set_project(self._current_project)
            return view

        self._view_host.register("build", create_build_view)

        def create_play_view() -> PlayView:
            view = PlayView(
                workspace_root=self._workspace,
                parent=self,
            )
            view.launchRequested.connect(self._on_launch_game)
            if self._current_project:
                view.set_project(self._current_project)
            return view

        self._view_host.register(
            "play",
            create_play_view,
            enabled_when=lambda: (self._current_project_has_package(), "No packaged build found")
        )

        def create_evidence_view() -> EvidenceView:
            view = EvidenceView(
                workspace_root=self._workspace,
                parent=self,
            )
            view.openFileRequested.connect(lambda p: self._switch_studio_view("code"))
            if self._current_project:
                view.set_project(self._current_project)
            return view

        self._view_host.register(
            "evidence",
            create_evidence_view,
            enabled_when=lambda: (bool(self._current_project), "Select a game first")
        )
        self._view_host.register(
            "assets",
            lambda: AssetsView(workspace_root=self._workspace, parent=self),
        )
        self._view_host.register("code", lambda: self._get_or_create_code_view())

        def create_settings_view() -> SettingsView:
            view = SettingsView(workspace_root=self._workspace, parent=self)
            if hasattr(self, "_systems_service") and self._systems_service:
                view.settingsChanged.connect(self._systems_service.refresh_now)
            view.settingsChanged.connect(self._on_settings_saved)
            return view

        self._view_host.register("settings", create_settings_view)

    def _register_studio_shortcuts(self) -> None:
        view_shortcuts = [
            ("Ctrl+1", "home"),
            ("Ctrl+2", "games"),
            ("Ctrl+3", "design"),
            ("Ctrl+4", "build"),
            ("Ctrl+5", "play"),
            ("Ctrl+6", "evidence"),
            ("Ctrl+7", "assets"),
            ("Ctrl+8", "code"),
            ("Ctrl+,", "settings"),
        ]
        self._studio_shortcuts = []
        for key, vid in view_shortcuts:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(lambda v=vid: self._switch_studio_view(v))
            self._studio_shortcuts.append(sc)

        sc_j = QShortcut(QKeySequence("Ctrl+J"), self)
        sc_j.setContext(Qt.WindowShortcut)
        sc_j.activated.connect(self._toggle_assistant)
        self._studio_shortcuts.append(sc_j)

        for key in ("Ctrl+K", "Ctrl+Shift+P"):
            sc_pal = QShortcut(QKeySequence(key), self)
            sc_pal.setContext(Qt.WindowShortcut)
            sc_pal.activated.connect(self._open_command_palette)
            self._studio_shortcuts.append(sc_pal)

        sc_t = QShortcut(QKeySequence("Ctrl+T"), self)
        sc_t.setContext(Qt.WindowShortcut)
        sc_t.activated.connect(self._toggle_theme)
        self._studio_shortcuts.append(sc_t)

        sc_dot = QShortcut(QKeySequence("Ctrl+."), self)
        sc_dot.setContext(Qt.WindowShortcut)
        sc_dot.activated.connect(self._cancel_active_run)
        self._studio_shortcuts.append(sc_dot)

    def _switch_studio_view(self, view_id: str) -> bool:
        if not hasattr(self, "_view_host"):
            return False
        if self._view_host.show_view(view_id):
            self._rail.set_active_view(view_id)
            title = view_id.capitalize()
            self._top_bar.set_breadcrumb(f"› {title}")
            self._settings.setValue("studio/last_view", view_id)
            proj_str = f" [Project: '{self._current_project}']" if getattr(self, "_current_project", None) else ""
            print(f"[GameForge Studio] Navigated to view: '{view_id}'{proj_str}", flush=True)
            return True
        return False

    def _on_studio_view_changed(self, view_id: str) -> None:
        if hasattr(self, "_rail"):
            self._rail.set_active_view(view_id)
            self._rail.update_enabled_states(self._view_host.is_enabled)
        if hasattr(self, "_top_bar"):
            self._top_bar.set_breadcrumb(f"› {view_id.capitalize()}")

    def _toggle_assistant(self) -> None:
        if hasattr(self, "_assistant_panel"):
            vis = not self._assistant_panel.isHidden()
            self._set_assistant_visible(not vis)

    def _set_assistant_visible(self, visible: bool) -> None:
        if not hasattr(self, "_assistant_panel") or not hasattr(self, "_center_splitter"):
            return
        self._assistant_panel.setVisible(visible)
        if visible:
            w = int(self._settings.value("studio/assistant_width", 380))
            sizes = self._center_splitter.sizes()
            total = sum(sizes)
            self._center_splitter.setSizes([max(400, total - w), w])

    def _list_projects(self) -> List[str]:
        dirs_map = list_all_project_dirs(self._workspace)
        return list(dirs_map.keys())

    def _resolve_project_dir(self, project_name: str) -> Optional[Path]:
        return resolve_project_dir(project_name, self._workspace)

    def refresh_projects(self, select_project: Optional[str] = None) -> None:
        projects = self._list_projects()
        target = select_project or self._current_project
        if target and target not in projects:
            projects.insert(0, target)
        if hasattr(self, "_top_bar"):
            self._top_bar.set_projects(projects, target)
        if hasattr(self, "_view_host"):
            gv = self._view_host.get_view_widget("games")
            if gv and hasattr(gv, "refresh_games"):
                gv.refresh_games()
            hv = self._view_host.get_view_widget("home")
            if hv and hasattr(hv, "refresh_recent_games"):
                hv.refresh_recent_games()

    @Slot(str, Path)
    def _on_game_deleted(self, project_name: str, project_dir: Path) -> None:
        norm_del = str(project_dir.resolve()).lower() if project_dir and project_dir != Path() else None
        curr_del = str(self._current_project_dir.resolve()).lower() if self._current_project_dir else None

        if self._current_project == project_name or (norm_del and curr_del == norm_del):
            self._current_project = None
            self._current_project_dir = None
            self.refresh_projects(None)
            self._switch_studio_view("games")
        else:
            self.refresh_projects(None)

        if hasattr(self, "_toasts"):
            self._toasts.info("Project Deleted", f"Project '{project_name}' has been permanently deleted.")

    def _on_project_selected(self, project_name: str) -> None:
        self._current_project = project_name
        p_dir = self._resolve_project_dir(project_name)
        self._current_project_dir = p_dir
        print(f"[GameForge Studio] Selected project: '{project_name}' -> {p_dir}", flush=True)

        # Synchronize active project directory across backend services, agent, and panels
        if p_dir and p_dir.is_dir():
            self._agent.set_workspace(p_dir)
            self._tools.set_workspace(p_dir)
            if hasattr(self, "_chat_panel"):
                self._chat_panel.set_workspace(self._agent, p_dir)
            if hasattr(self, "_explorer"):
                self._explorer.set_workspace(p_dir, self._tools)
            if hasattr(self, "_terminal"):
                self._terminal.set_workspace(p_dir)
            if hasattr(self, "_unreal_panel") and hasattr(self._unreal_panel, "set_workspace"):
                self._unreal_panel.set_workspace(self._tools, p_dir)
            if hasattr(self, "_design_panel") and hasattr(self._design_panel, "set_workspace"):
                self._design_panel.set_workspace(p_dir)
            if hasattr(self, "_asset_panel") and hasattr(self._asset_panel, "set_workspace"):
                self._asset_panel.set_workspace(p_dir)

        if hasattr(self, "_rail") and hasattr(self, "_view_host"):
            self._rail.update_enabled_states(self._view_host.is_enabled)
            current = self._view_host.current_view_id
            if current and not self._view_host.is_enabled(current)[0]:
                self._switch_studio_view("home")
            dv = self._view_host.get_view_widget("design")
            if dv and hasattr(dv, "load_project"):
                dv.load_project(project_name, project_dir=p_dir)
            bv = self._view_host.get_view_widget("build")
            if bv and hasattr(bv, "set_project"):
                bv.set_project(project_name, project_dir=p_dir)
            pv = self._view_host.get_view_widget("play")
            if pv and hasattr(pv, "set_project"):
                pv.set_project(project_name, project_dir=p_dir)
            ev = self._view_host.get_view_widget("evidence")
            if ev and hasattr(ev, "set_project"):
                ev.set_project(project_name, project_dir=p_dir)

        # Ensure top bar reflects the active project
        if hasattr(self, "_top_bar") and hasattr(self._top_bar, "project_combo"):
            combo = self._top_bar.project_combo
            idx = combo.findData(project_name)
            if idx >= 0 and combo.currentIndex() != idx:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

    def _on_assistant_open_design(self, prompt: str) -> None:
        p_dir = getattr(self, "_current_project_dir", None)
        has_active_gds = p_dir and (p_dir / "GameForge" / "design" / "game.gds.json").is_file()

        if has_active_gds and getattr(self, "_current_project", None):
            # Apply design change / completion directly to active project
            self._switch_studio_view("design")
            dv = self._view_host.get_view_widget("design")
            if dv and hasattr(dv, "load_project"):
                dv.load_project(self._current_project, project_dir=p_dir)
                if hasattr(dv, "_txt_change"):
                    dv._txt_change.setText(prompt)
                if hasattr(dv, "_on_propose_change"):
                    dv._on_propose_change()
            if hasattr(self, "_toasts"):
                self._toasts.info("Design Updated", f"Applied prompt update to '{self._current_project}' in Design View.")
            return

        self._switch_studio_view("home")
        hv = self._view_host.get_view_widget("home")
        if hv:
            edit = getattr(hv, "_prompt_input", getattr(hv, "_prompt_box", None))
            if edit:
                edit.setPlainText(prompt)
            fn = getattr(hv, "_on_design_it_clicked", getattr(hv, "_on_design_clicked", None))
            if fn:
                fn()

    def _on_home_design_ready(self, gds: Any, questions: List[str]) -> None:
        p_dir = None
        if gds and hasattr(gds, "meta"):
            p_name = getattr(gds.meta, "project_name", None) or getattr(gds.meta, "title", "MyGame")
            p_dir_str = getattr(gds.meta, "project_dir", None)
            if p_dir_str:
                p_dir = Path(p_dir_str).resolve()
            else:
                p_dir = self._resolve_project_dir(p_name)
            self._current_project = p_name
            self._current_project_dir = p_dir
            self.refresh_projects(select_project=p_name)
            self._on_project_selected(p_name)
        self._switch_studio_view("design")
        design_view = self._view_host.get_view_widget("design")
        if design_view and hasattr(design_view, "open_draft"):
            design_view.open_draft(gds, questions, project_dir=p_dir)

    def _on_new_project_requested(self, project_name: str, project_dir: Path) -> None:
        pdir = Path(project_dir).resolve()
        self._current_project = project_name
        self._current_project_dir = pdir
        self.refresh_projects(select_project=project_name)
        self._switch_studio_view("design")
        dv = self._view_host.get_view_widget("design")
        if dv and hasattr(dv, "load_project"):
            if not dv.load_project(project_name, project_dir=pdir):
                from ..design.gds import GameDesignSpec, Meta, Overview, TechSpec
                spec = GameDesignSpec(
                    meta=Meta(title=project_name, project_name=project_name, project_dir=str(pdir)),
                    overview=Overview(genre="action", pitch=f"{project_name} project"),
                    tech=TechSpec(),
                )
                dv.open_draft(spec, project_dir=pdir)

    def _on_open_project_directory_requested(self, project_dir: Path) -> None:
        pdir = Path(project_dir).resolve()
        name = pdir.name
        self._current_project = name
        self._current_project_dir = pdir
        self.refresh_projects(select_project=name)
        self._switch_studio_view("design")
        dv = self._view_host.get_view_widget("design")
        if dv and hasattr(dv, "load_project"):
            if not dv.load_project(name, project_dir=pdir):
                from ..design.gds import GameDesignSpec, Meta, Overview, TechSpec
                spec = GameDesignSpec(
                    meta=Meta(title=name, project_name=name, project_dir=str(pdir)),
                    overview=Overview(genre="action", pitch=f"{name} project"),
                    tech=TechSpec(),
                )
                dv.open_draft(spec, project_dir=pdir)

    def _on_games_open_requested(self, project_name: str) -> None:
        self._on_project_selected(project_name)
        self._switch_studio_view("design")

    def _on_games_play_requested(self, project_name: str) -> None:
        self._on_project_selected(project_name)
        self._switch_studio_view("play")

    def _on_games_build_requested(self, project_name: str) -> None:
        self._on_project_selected(project_name)
        self._switch_studio_view("build")
        bv = self._view_host.get_view_widget("build")
        dv = self._view_host.get_view_widget("design")
        spec = getattr(dv, "_current_spec", None) if dv else None
        p_dir = self._current_project_dir or self._resolve_project_dir(project_name)
        if bv and hasattr(bv, "start_build"):
            bv.start_build(project_name, spec, project_dir=p_dir)

    def _on_settings_saved(self) -> None:
        new_theme = "light" if self._settings.value("appearance/theme", "dark") == "light" else "dark"
        if new_theme != self._theme:
            self._theme = new_theme
            apply_theme(QApplication.instance(), self._theme)
            from .styles.dark_theme import get_theme_display_name
            self.statusBar().showMessage(f"{get_theme_display_name(self._theme)} theme enabled.", 3000)

    def _find_packaged_exe(self, project_name: str) -> Optional[Path]:
        p_dir = self._resolve_project_dir(project_name)
        if not p_dir:
            return None
        return find_packaged_executable(p_dir, project_name)

    def _current_project_has_package(self) -> bool:
        if not getattr(self, "_current_project", None):
            return False
        return self._find_packaged_exe(self._current_project) is not None

    def _on_launch_game(self, project_name: str) -> None:
        exe = self._find_packaged_exe(project_name)
        if exe:
            from PySide6.QtCore import QProcess
            ok = QProcess.startDetached(str(exe), [])
            if ok:
                if hasattr(self, "_toasts"):
                    self._toasts.info("Launching Game", f"Launching {project_name} ({exe.name})...")
                self.statusBar().showMessage(f"Launched {project_name} ({exe})", 5000)
            else:
                if hasattr(self, "_toasts"):
                    self._toasts.error("Launch Failed", f"Failed to start {exe}")
        else:
            if hasattr(self, "_toasts"):
                self._toasts.warning("Executable Not Found", f"No packaged build found for {project_name}. Build the project first.")

    def _cancel_active_run(self) -> None:
        if not hasattr(self, "_forge_service"):
            return
        active = self._forge_service.active_runs()
        if not active:
            if hasattr(self, "_toasts"):
                self._toasts.info("No Active Run", "There is no run currently in progress.")
            return
        run = active[0]
        run_id = run.get("run_id", "active_run")
        if getattr(self, "confirm_on_close", True):
            reply = QMessageBox.question(
                self,
                "Cancel Run",
                f"Are you sure you want to cancel active run '{run_id}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        if hasattr(self, "_toasts"):
            self._toasts.warning("Run Cancelled", f"Cancelled run {run_id}")

    def closeEvent(self, event: QCloseEvent) -> None:
        chat = getattr(self, "_chat_panel", None)
        building = bool(chat is not None and getattr(getattr(chat, "_runner", None), "_threads", None))
        busy = building or bool(getattr(self._agent, "is_busy", False))
        if getattr(self, "confirm_on_close", True) and busy:
            reply = QMessageBox.question(
                self,
                "Quit GameForge IDE",
                ("A game build is still running and will be stopped. Exit anyway?" if building
                 else "The agent is still working. Exit anyway?"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

        if hasattr(self, "_health_timer") and self._health_timer is not None:
            self._health_timer.stop()
        if hasattr(self, "_terminal") and self._terminal is not None:
            try:
                self._terminal.closeEvent(event)
            except Exception:
                pass
        self._settings.setValue("appearance/theme", self._theme)
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/layout", self.saveState())
        self._settings.sync()
        chat = getattr(self, "_chat_panel", None)
        if chat is not None and hasattr(chat, "_runner"):
            chat._runner.shutdown()
        self._agent.shutdown()
        if hasattr(self, "_center_splitter"):
            sizes = self._center_splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                self._settings.setValue("studio/assistant_width", sizes[1])
        if hasattr(self, "_view_host") and self._view_host.current_view_id:
            self._settings.setValue("studio/last_view", self._view_host.current_view_id)
        if hasattr(self, "_systems_service"):
            self._systems_service.stop()
        event.accept()
