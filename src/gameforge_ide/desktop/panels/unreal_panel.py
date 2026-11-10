"""GameForge IDE — Unreal Engine Status Panel.

Displays detected UE5 installation, loopback bridge status, workspace .uproject files,
quick ops launcher, and provides a staged build trigger. All data flows via ToolService
in-process — no HTTP.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..services.tool_service import ToolService
from ..styles import tokens
from ...core.projects import open_folder_in_file_manager
from ...core.settings import get_settings

logger = logging.getLogger(__name__)


class _InfoRow(QWidget):
    """Key-value row widget for the engine info section."""

    def __init__(self, key: str, value: str = "—", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        lbl_key = QLabel(f"{key}:")
        lbl_key.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; min-width: 140px;")
        layout.addWidget(lbl_key)
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;")
        self._val.setWordWrap(True)
        layout.addWidget(self._val, 1)

    def set_value(self, value: str) -> None:
        self._val.setText(value)


class UnrealPanel(QWidget):
    """Unreal Engine 5 integration status, bridge, quick ops, and staged-build trigger."""

    build_requested = Signal(str)   # uproject relative path
    create_game_requested = Signal()

    def __init__(self, tool_service: ToolService, workspace_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setObjectName("unrealPanel")
        self.setAccessibleName("Unreal Engine Status Panel")
        self._tools = tool_service
        self._workspace = Path(workspace_root).resolve()
        self._build_signals = None
        self._build_ui()
        self._tools.tool_result.connect(self._on_tool_result)
        QTimer.singleShot(300, self._refresh)

    def set_workspace(self, tool_service: ToolService, new_workspace: Path) -> None:
        """Switch active workspace directory for Unreal tools."""
        try:
            self._tools.tool_result.disconnect(self._on_tool_result)
        except Exception:
            pass
        self._tools = tool_service
        self._workspace = Path(new_workspace).resolve()
        self._tools.tool_result.connect(self._on_tool_result)
        self._refresh()

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("panel_header")
        header.setStyleSheet(f"background: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};")
        header.setFixedHeight(44)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(10, 4, 10, 4)
        title = QLabel("🎮  Unreal Engine 5")
        title.setStyleSheet(f"color: {tokens.ACCENT_SUCCESS}; font-weight: 700; font-size: {tokens.FONT_HEADING_SM}px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()
        btn_refresh = QPushButton("↻  Refresh")
        btn_refresh.setObjectName("btn_ue_refresh")
        btn_refresh.setAccessibleName("Refresh Unreal installation and bridge status")
        btn_refresh.setFixedHeight(28)
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setStyleSheet(
            f"QPushButton {{"
            f"  background: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        btn_refresh.clicked.connect(self._refresh)
        hdr_layout.addWidget(btn_refresh)
        layout.addWidget(header)

        # Engine info section
        info_section = QFrame()
        info_section.setObjectName("panel_section")
        info_section.setStyleSheet(f"background: {tokens.BG_SURFACE}; border-bottom: 1px solid {tokens.BORDER};")
        info_layout = QVBoxLayout(info_section)
        info_layout.setContentsMargins(0, 6, 0, 6)
        info_layout.setSpacing(2)

        sec_lbl = QLabel("ENGINE INSTALLATION & BRIDGE")
        sec_lbl.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 700; letter-spacing: 0.8px; padding: 4px 10px;"
        )
        info_layout.addWidget(sec_lbl)

        self._row_installed = _InfoRow("Status", "Checking…")
        self._row_version = _InfoRow("Engine Version", "—")
        self._row_path = _InfoRow("Install Path", "—")
        self._row_uat = _InfoRow("UAT Available", "—")
        self._row_bridge = _InfoRow("Loopback Bridge", "Standby")
        for row in (self._row_installed, self._row_version, self._row_path, self._row_uat, self._row_bridge):
            info_layout.addWidget(row)
        layout.addWidget(info_section)

        # Projects section header
        proj_hdr = QWidget()
        proj_hdr.setObjectName("panel_header")
        proj_hdr.setStyleSheet(f"background: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};")
        proj_hdr.setFixedHeight(34)
        proj_hdr_layout = QHBoxLayout(proj_hdr)
        proj_hdr_layout.setContentsMargins(10, 2, 10, 2)
        proj_lbl = QLabel("UPROJECTS IN WORKSPACE")
        proj_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 700; letter-spacing: 0.8px;")
        proj_hdr_layout.addWidget(proj_lbl)
        proj_hdr_layout.addStretch()

        # Quick ops buttons in project header
        btn_open_folder = QPushButton("📁 Folder")
        btn_open_folder.setObjectName("btn_ue_open_folder")
        btn_open_folder.setAccessibleName("Open project directory in file explorer")
        btn_open_folder.setToolTip("Open selected project directory in Windows Explorer")
        btn_open_folder.setFixedHeight(24)
        btn_open_folder.setStyleSheet(
            f"QPushButton {{ background: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY}; border: 1px solid {tokens.BORDER}; border-radius: 4px; padding: 1px 6px; font-size: 11px; }} "
            f"QPushButton:hover {{ background: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        btn_open_folder.clicked.connect(self._on_open_folder)
        proj_hdr_layout.addWidget(btn_open_folder)

        layout.addWidget(proj_hdr)

        # Projects section container / stacked widget
        self._projects_stack = QStackedWidget()
        self._projects_stack.setFixedHeight(140)

        # Empty state for projects
        self._empty_projects_card = QFrame()
        self._empty_projects_card.setObjectName("panel_section")
        self._empty_projects_card.setStyleSheet(
            f"background: {tokens.BG_PANEL}; border: 1px dashed {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 10px;"
        )
        ep_layout = QVBoxLayout(self._empty_projects_card)
        ep_layout.setContentsMargins(10, 12, 10, 12)
        ep_layout.setSpacing(6)
        ep_layout.setAlignment(Qt.AlignCenter)

        lbl_ep_msg = QLabel("No .uproject in this workspace.\nCreate one with /game")
        lbl_ep_msg.setAlignment(Qt.AlignCenter)
        lbl_ep_msg.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600; background: transparent;")
        ep_layout.addWidget(lbl_ep_msg)

        btn_create_game = QPushButton("✨  Create with /game")
        btn_create_game.setObjectName("btn_create_game_hint")
        btn_create_game.setFixedHeight(28)
        btn_create_game.setCursor(Qt.PointingHandCursor)
        btn_create_game.setStyleSheet(
            f"QPushButton {{ background: {tokens.BG_SURFACE}; border: 1px solid {tokens.ACCENT_PRIMARY}; color: {tokens.ACCENT_HOVER}; border-radius: {tokens.RADIUS}px; font-weight: 600; padding: 4px 12px; }} "
            f"QPushButton:hover {{ background: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        btn_create_game.clicked.connect(self.create_game_requested.emit)
        ep_layout.addWidget(btn_create_game, 0, Qt.AlignCenter)

        # Project list
        self._project_list = QListWidget()
        self._project_list.setObjectName("ue_project_list")
        self._project_list.setAccessibleName("Unreal projects list")
        self._project_list.setStyleSheet(f"background: {tokens.BG_PANEL}; color: {tokens.TEXT_PRIMARY}; border: none;")

        self._projects_stack.addWidget(self._empty_projects_card)  # Index 0
        self._projects_stack.addWidget(self._project_list)          # Index 1
        layout.addWidget(self._projects_stack)

        # Build output section
        build_hdr = QWidget()
        build_hdr.setObjectName("panel_header")
        build_hdr.setStyleSheet(f"background: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};")
        build_hdr.setFixedHeight(40)
        build_hdr_layout = QHBoxLayout(build_hdr)
        build_hdr_layout.setContentsMargins(10, 4, 10, 4)
        build_lbl = QLabel("BUILD OUTPUT")
        build_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 700; letter-spacing: 0.8px;")
        build_hdr_layout.addWidget(build_lbl)
        build_hdr_layout.addStretch()
        self._btn_build = QPushButton("⚙  Staged Build")
        self._btn_build.setObjectName("btn_ue_build")
        self._btn_build.setAccessibleName("Trigger staged Unreal build")
        self._btn_build.setEnabled(False)
        self._btn_build.setFixedHeight(28)
        self._btn_build.setCursor(Qt.PointingHandCursor)
        self._btn_build.setStyleSheet(
            f"QPushButton {{"
            f"  background: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px; padding: 4px {tokens.SPACE_MD}px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background: {tokens.ACCENT_HOVER}; }}"
            f"QPushButton:disabled {{ background: {tokens.BG_SURFACE}; color: {tokens.TEXT_MUTED}; }}"
        )
        self._btn_build.clicked.connect(self._on_build)
        build_hdr_layout.addWidget(self._btn_build)
        layout.addWidget(build_hdr)

        # Build output stacked container (empty state vs output text)
        self._build_stack = QStackedWidget()

        self._empty_build_card = QFrame()
        self._empty_build_card.setObjectName("panel_section")
        self._empty_build_card.setStyleSheet(
            f"background: {tokens.BG_ROOT}; border: 1px dashed {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 16px;"
        )
        eb_layout = QVBoxLayout(self._empty_build_card)
        eb_layout.setContentsMargins(16, 24, 16, 24)
        eb_layout.setSpacing(6)
        eb_layout.setAlignment(Qt.AlignCenter)

        lbl_eb_icon = QLabel("⚙")
        lbl_eb_icon.setAlignment(Qt.AlignCenter)
        lbl_eb_icon.setStyleSheet(f"font-size: 24px; color: {tokens.ACCENT_PRIMARY}; background: transparent;")
        eb_layout.addWidget(lbl_eb_icon)

        lbl_eb_title = QLabel("No build output yet")
        lbl_eb_title.setAlignment(Qt.AlignCenter)
        lbl_eb_title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 700; background: transparent;")
        eb_layout.addWidget(lbl_eb_title)

        lbl_eb_desc = QLabel("Select a project above and click 'Staged Build' to compile.")
        lbl_eb_desc.setAlignment(Qt.AlignCenter)
        lbl_eb_desc.setWordWrap(True)
        lbl_eb_desc.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; background: transparent;")
        eb_layout.addWidget(lbl_eb_desc)

        lbl_eb_sub = QLabel("Build logs, compiler warnings, and cook diagnostics will stream here.")
        lbl_eb_sub.setAlignment(Qt.AlignCenter)
        lbl_eb_sub.setWordWrap(True)
        lbl_eb_sub.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px; background: transparent;")
        eb_layout.addWidget(lbl_eb_sub)

        self._build_output = QTextEdit()
        self._build_output.setObjectName("ue_build_output")
        self._build_output.setAccessibleName("Unreal build output console")
        self._build_output.setReadOnly(True)
        self._build_output.setStyleSheet(
            f"background: {tokens.BG_ROOT}; color: {tokens.TEXT_SECONDARY}; border: none;"
            f" font-family: 'Consolas', monospace; font-size: 11px;"
        )
        self._build_output.setPlaceholderText("Select a project and press 'Staged Build' to compile…")

        self._build_stack.addWidget(self._empty_build_card)  # Index 0
        self._build_stack.addWidget(self._build_output)      # Index 1
        layout.addWidget(self._build_stack, 1)

    # ── Refresh ─────────────────────────────────────────────────────────────

    @Slot()
    def _refresh(self) -> None:
        self._tools.execute("unreal_engine_info")
        self._tools.execute("unreal_find_projects")

        # Probe loopback Unreal bridge status
        try:
            from ...backend.tools.game_tools import GameTools
            links = GameTools.all_links()
            if links:
                self._row_bridge.set_value(f"✅ Active ({len(links)} bridge session{'s' if len(links) > 1 else ''})")
            else:
                self._row_bridge.set_value(f"⚪ Standby (127.0.0.1:{get_settings().bridge_port})")
        except Exception:
            self._row_bridge.set_value("⚪ Standby")

    @Slot(str, dict)
    def _on_tool_result(self, tool_name: str, result: dict) -> None:
        if tool_name == "unreal_engine_info":
            installed = result.get("installed", False)
            self._row_installed.set_value("✅ Detected" if installed else "❌ Not found")
            self._row_version.set_value(result.get("version", "—"))
            path_val = result.get("install_path") or result.get("engine_root") or "—"
            self._row_path.set_value(path_val)
            uat_ok = result.get("uat_available") or bool(result.get("uat_path"))
            self._row_uat.set_value("✅ Yes (RunUAT)" if uat_ok else "❌ No")
        elif tool_name == "unreal_find_projects":
            projects = result.get("projects", [])
            self._project_list.clear()
            for p in projects:
                name = p.get("name", "Unknown")
                parent_dir = p.get("relative_dir", "")
                if parent_dir:
                    display = f"{name} [{parent_dir}]"
                else:
                    display = name
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, p.get("path", ""))
                item.setToolTip(p.get("full_path", ""))
                self._project_list.addItem(item)
            if projects:
                self._btn_build.setEnabled(True)
                self._project_list.setCurrentRow(0)
                self._projects_stack.setCurrentWidget(self._project_list)
            else:
                self._btn_build.setEnabled(False)
                self._projects_stack.setCurrentWidget(self._empty_projects_card)

    @Slot()
    def _on_open_folder(self) -> None:
        item = self._project_list.currentItem()
        if not item:
            return
        rel_path = item.data(Qt.UserRole)
        if not rel_path:
            return
        p = Path(rel_path)
        if not p.is_absolute():
            p = self._workspace / rel_path
        if "PYTEST_CURRENT_TEST" not in os.environ:
            open_folder_in_file_manager(p)

    def deleteLater(self) -> None:
        try:
            self._tools.tool_result.disconnect(self._on_tool_result)
        except Exception:
            pass
        super().deleteLater()


    @Slot()
    def _on_build(self) -> None:
        self._build_stack.setCurrentWidget(self._build_output)
        item = self._project_list.currentItem()
        if not item:
            if self._project_list.count() > 0:
                item = self._project_list.item(0)
            else:
                self._build_output.setText("No .uproject found in workspace.")
                return

        rel_path = item.data(Qt.UserRole)
        self._build_output.setText(f"[Staged Build] Starting build for: {rel_path}\n")
        self._btn_build.setEnabled(False)
        self._btn_build.setText("Building…")

        # Run via thread pool — non-blocking
        def _run():
            result = self._tools.execute_approved_sync(
                "unreal_build", {"uproject_rel_path": rel_path}
            )
            return result

        class _BuildSignals(QObject):
            done = Signal(dict)

        class _BuildRunnable(QRunnable):
            def __init__(self_, r, signals):
                super().__init__()
                self_._runner = r
                self_._signals = signals

            def run(self_):
                try:
                    result = self_._runner()
                except Exception as exc:
                    result = {"status": "ERROR", "error": str(exc)}
                try:
                    self_._signals.done.emit(result)
                except (RuntimeError, Exception):
                    pass

        self._build_signals = _BuildSignals(self)
        self._build_signals.done.connect(self._on_build_done)
        QThreadPool.globalInstance().start(_BuildRunnable(_run, self._build_signals))
        self.build_requested.emit(rel_path)

    @Slot(dict)
    def _on_build_done(self, result: dict) -> None:
        status = result.get("status", "ERROR")
        output = result.get("output", result.get("error", "No output"))
        self._build_output.append(f"\n[{status}]\n{output}")
        self._btn_build.setEnabled(True)
        self._btn_build.setText("⚙  Staged Build")
