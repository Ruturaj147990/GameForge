"""GameForge IDE — Native QMainWindow.

Assembles all dockable panels into a cohesive desktop IDE experience.
There is no localhost, no browser, no WebSocket — all services are
called in-process via AgentService and ToolService.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QSize, Slot
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QFont,
    QIcon,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .panels.chat_panel import ChatPanel
from .panels.diff_panel import DiffPanel
from .panels.explorer_panel import ExplorerPanel
from .panels.terminal_panel import TerminalPanel
from .panels.unreal_panel import UnrealPanel
from .services.agent_service import AgentService
from .services.tool_service import ToolService
from .styles.dark_theme import apply_theme, theme_stylesheet


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

    def __init__(self, workspace_root: Path) -> None:
        super().__init__()
        self._workspace = workspace_root
        settings_path = workspace_root / ".gameforge" / "ide_settings.ini"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = QSettings(str(settings_path), QSettings.IniFormat)
        self._theme = "light" if self._settings.value("appearance/theme", "dark") == "light" else "dark"

        # ── Services (in-process, no HTTP) ───────────────────────────────
        self._agent = AgentService(workspace_root, parent=self)
        self._tools = ToolService(workspace_root, parent=self)

        # ── Window meta ──────────────────────────────────────────────────
        self.setWindowTitle("GameForge IDE — Agentic Game Development Environment")
        self.setMinimumSize(1280, 780)
        self.resize(1600, 960)

        # ── Build UI ─────────────────────────────────────────────────────
        self._build_menu()
        self._build_toolbar()
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
        apply_theme(QApplication.instance(), self._theme)

        # ── Connect cross-panel signals ──────────────────────────────────
        self._chat_panel.diff_pending.connect(self._on_diff_pending)

        # ── Deferred startup health-check ────────────────────────────────
        QTimer.singleShot(800, self._check_ollama_status)

    # ── Menu bar ─────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        act_new = QAction("New Session", self)
        act_new.setObjectName("file_new_session")
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._new_session)
        file_menu.addAction(act_new)
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
        self.addToolBar(Qt.TopToolBarArea, tb)

        # Logo / brand label
        brand = QLabel("  🎮 GameForge IDE ")
        brand.setStyleSheet("color: #6c63ff; font-weight: 800; font-size: 14px; letter-spacing: 0.5px;")
        tb.addWidget(brand)

        sep = QWidget()
        sep.setFixedWidth(12)
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

        # Spacer to push status to right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        # Ollama status indicator
        self._ollama_indicator = QLabel("● Ollama: checking…")
        self._ollama_indicator.setObjectName("ollama_indicator")
        self._ollama_indicator.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 600; padding-right: 12px;")
        tb.addWidget(self._ollama_indicator)

    # ── Central widget (Chat) ─────────────────────────────────────────────────

    def _build_central(self) -> None:
        self._chat_panel = ChatPanel(self._agent, parent=self)
        self.setCentralWidget(self._chat_panel)

    # ── Dock panels ───────────────────────────────────────────────────────────

    def _build_docks(self) -> None:
        # Corner configurations so left/right docks can extend cleanly
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        # ── Explorer (left) ──────────────────────────────────────────────
        self._explorer = ExplorerPanel(self._tools, self._workspace, parent=self)
        self._dock_explorer = self._make_dock("Explorer", self._explorer, Qt.LeftDockWidgetArea)
        self._dock_explorer.setMinimumWidth(220)
        self._dock_explorer.setMaximumWidth(400)

        # ── Unreal Engine (right) ─────────────────────────────────────────
        self._unreal_panel = UnrealPanel(self._tools, self._workspace, parent=self)
        self._dock_unreal = self._make_dock("Unreal Engine 5", self._unreal_panel, Qt.RightDockWidgetArea)
        self._dock_unreal.setMinimumWidth(300)
        self._dock_unreal.setMaximumWidth(460)

        # ── Diff Review (right, tabbed with Unreal) ───────────────────────
        self._diff_panel = DiffPanel(self._tools, parent=self)
        self._diff_panel.diff_approved.connect(self._on_diff_applied)
        self._diff_panel.diff_rejected.connect(self._on_diff_rejected)
        self._dock_diff = self._make_dock("Diff Review", self._diff_panel, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(self._dock_unreal, self._dock_diff)
        self._dock_diff.hide()  # Hidden until a diff is pending

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
            lambda v: self._act_show_explorer.setChecked(v)
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
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(area, dock)
        return dock

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        sb.setObjectName("main_status_bar")
        self.setStatusBar(sb)

        self._status_lbl = QLabel(f"Workspace: {self._workspace}")
        self._status_lbl.setObjectName("status_workspace")
        sb.addWidget(self._status_lbl)

        sb.addPermanentWidget(QLabel("|"))

        self._model_status = QLabel("Model: gameforge-27b-sft:latest")
        self._model_status.setObjectName("status_model")
        self._model_status.setStyleSheet("color: #6c63ff;")
        sb.addPermanentWidget(self._model_status)

        sb.addPermanentWidget(QLabel("|"))

        self._version_lbl = QLabel("GameForge IDE v1.0.0")
        self._version_lbl.setObjectName("status_version")
        self._version_lbl.setStyleSheet("color: #8891aa;")
        sb.addPermanentWidget(self._version_lbl)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _new_session(self) -> None:
        self._chat_panel._new_session()
        self.statusBar().showMessage("New session started.", 3000)

    @Slot()
    def _toggle_theme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        apply_theme(QApplication.instance(), self._theme)
        self._settings.setValue("appearance/theme", self._theme)
        self._settings.sync()
        self.statusBar().showMessage(f"Studio {self._theme.title()} theme enabled.", 3000)

    @Slot()
    def _reset_layout(self) -> None:
        self.restoreState(self._default_layout)
        self.resize(1600, 960)
        self.statusBar().showMessage("Default panel layout restored.", 3000)

    @Slot()
    def _check_ollama_status(self) -> None:
        try:
            from ..backend.providers.ollama_provider import OllamaProvider
            provider = OllamaProvider()
            ok = provider.is_available()
            if ok:
                self._ollama_indicator.setText("● Ollama: online")
                self._ollama_indicator.setStyleSheet(theme_stylesheet(
                    "color: #00d9a3; font-size: 12px; padding-right: 12px; font-weight: 600;"
                ))
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

    @Slot(str, dict)
    def _on_diff_pending(self, diff_id: str, meta: dict) -> None:
        self._diff_panel.show_diff(diff_id, meta)
        self._dock_diff.show()
        self._dock_diff.raise_()
        self.statusBar().showMessage(f"Diff pending review: {diff_id}", 5000)

    @Slot(str)
    def _on_diff_applied(self, diff_id: str) -> None:
        self.statusBar().showMessage(f"✅ Diff {diff_id} applied successfully.", 4000)

    @Slot(str)
    def _on_diff_rejected(self, diff_id: str) -> None:
        self.statusBar().showMessage(f"❌ Diff {diff_id} rejected.", 4000)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GameForge IDE",
            "<h3>GameForge IDE v1.0.0</h3>"
            "<p>Agentic game-development environment powered by<br>"
            "<b>gameforge-27b-sft:latest</b> (local Ollama, Q4_K_M GGUF).</p>"
            "<p>Supports Unreal Engine 5.7, Unity 6, Godot 4.3.</p>"
            "<p>© 2026 GameForge Project — Windows 11 Native PySide6 Desktop</p>",
        )

    def _command_palette_commands(self):
        """Return only currently implemented user-facing commands."""
        return [
            ("New Session", self._new_session),
            ("Clear Chat", self._chat_panel._clear_chat),
            ("Check Ollama", self._check_ollama_status),
            ("Toggle Studio Dark/Light Theme", self._toggle_theme),
            ("Reset Layout", self._reset_layout),
            ("Toggle Explorer", lambda: self._dock_explorer.setVisible(not self._dock_explorer.isVisible())),
            ("Toggle Unreal Panel", lambda: self._dock_unreal.setVisible(not self._dock_unreal.isVisible())),
            ("Toggle Diff Review", lambda: self._dock_diff.setVisible(not self._dock_diff.isVisible())),
            ("Toggle Terminal", lambda: self._dock_terminal.setVisible(not self._dock_terminal.isVisible())),
            ("About GameForge IDE", self._show_about),
        ]

    @Slot()
    def _open_command_palette(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("command_palette_dialog")
        dialog.setWindowTitle("GameForge Commands")
        dialog.setModal(True)
        dialog.resize(560, 360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search = QLineEdit(dialog)
        search.setObjectName("command_palette_search")
        search.setPlaceholderText("Type a command…")
        layout.addWidget(search)

        commands = QListWidget(dialog)
        commands.setObjectName("command_palette_commands")
        layout.addWidget(commands)

        for label, callback in self._command_palette_commands():
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, callback)
            commands.addItem(item)

        def filter_commands(query: str) -> None:
            normalized = query.strip().casefold()
            first_visible = -1
            for index in range(commands.count()):
                item = commands.item(index)
                visible = normalized in item.text().casefold()
                item.setHidden(not visible)
                if visible and first_visible < 0:
                    first_visible = index
            commands.setCurrentRow(first_visible)

        def activate_current() -> None:
            item = commands.currentItem()
            if item is None or item.isHidden():
                return
            callback = item.data(Qt.UserRole)
            dialog.accept()
            callback()

        search.textChanged.connect(filter_commands)
        commands.itemActivated.connect(lambda _item: activate_current())
        search.installEventFilter(self)
        search.setProperty("commandPaletteList", commands)
        search.setProperty("commandPaletteDialog", dialog)
        filter_commands("")
        search.setFocus()
        dialog.exec()

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

    def closeEvent(self, event: QCloseEvent) -> None:
        if getattr(self, "confirm_on_close", True):
            reply = QMessageBox.question(
                self,
                "Quit GameForge IDE",
                "Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

        if hasattr(self, "_terminal") and self._terminal is not None:
            try:
                self._terminal.closeEvent(event)
            except Exception:
                pass
        self._settings.setValue("appearance/theme", self._theme)
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/layout", self.saveState())
        self._settings.sync()
        self._agent.shutdown()
        event.accept()
