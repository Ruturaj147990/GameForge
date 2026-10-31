"""GameForge IDE — Unreal Engine Status Panel.

Displays detected UE5 installation, workspace .uproject files,
and provides a staged build trigger. All data flows via ToolService
in-process — no HTTP.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..services.tool_service import ToolService


class _InfoRow(QWidget):
    """Key-value row widget for the engine info section."""

    def __init__(self, key: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        lbl_key = QLabel(f"{key}:")
        lbl_key.setStyleSheet("color: #9d95b0; font-size: 11px; min-width: 140px;")
        layout.addWidget(lbl_key)
        self._val = QLabel(value)
        self._val.setStyleSheet("color: #f5f3ff; font-size: 11px; font-weight: 600;")
        self._val.setWordWrap(True)
        layout.addWidget(self._val, 1)

    def set_value(self, value: str) -> None:
        self._val.setText(value)


class UnrealPanel(QWidget):
    """Unreal Engine 5 integration status and staged-build trigger."""

    build_requested = Signal(str)   # uproject relative path

    def __init__(self, tool_service: ToolService, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._tools = tool_service
        self._workspace = workspace_root
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
        header.setStyleSheet("background: #0d0b14; border-bottom: 1px solid #231c34;")
        header.setFixedHeight(44)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(10, 4, 10, 4)
        title = QLabel("🎮  Unreal Engine 5")
        title.setStyleSheet("color: #00d9a3; font-weight: 700; font-size: 14px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()
        btn_refresh = QPushButton("↻  Refresh")
        btn_refresh.setObjectName("btn_ue_refresh")
        btn_refresh.setFixedHeight(28)
        btn_refresh.clicked.connect(self._refresh)
        hdr_layout.addWidget(btn_refresh)
        layout.addWidget(header)

        # Engine info section
        info_section = QFrame()
        info_section.setObjectName("panel_section")
        info_section.setStyleSheet("background: #120f1d; border-bottom: 1px solid #231c34;")
        info_layout = QVBoxLayout(info_section)
        info_layout.setContentsMargins(0, 6, 0, 6)
        info_layout.setSpacing(2)

        sec_lbl = QLabel("ENGINE INSTALLATION")
        sec_lbl.setStyleSheet(
            "color: #9d95b0; font-size: 11px; font-weight: 700; letter-spacing: 0.8px;"
            " padding: 4px 10px;"
        )
        info_layout.addWidget(sec_lbl)

        self._row_installed = _InfoRow("Status", "Checking…")
        self._row_version = _InfoRow("Engine Version", "—")
        self._row_path = _InfoRow("Install Path", "—")
        self._row_uat = _InfoRow("UAT Available", "—")
        for row in (self._row_installed, self._row_version, self._row_path, self._row_uat):
            info_layout.addWidget(row)
        layout.addWidget(info_section)

        # Projects section header
        proj_hdr = QWidget()
        proj_hdr.setObjectName("panel_header")
        proj_hdr.setStyleSheet("background: #0d0b14; border-bottom: 1px solid #231c34;")
        proj_hdr.setFixedHeight(30)
        proj_hdr_layout = QHBoxLayout(proj_hdr)
        proj_hdr_layout.setContentsMargins(10, 2, 10, 2)
        proj_lbl = QLabel("UPROJECTS IN WORKSPACE")
        proj_lbl.setStyleSheet("color: #9d95b0; font-size: 11px; font-weight: 700; letter-spacing: 0.8px;")
        proj_hdr_layout.addWidget(proj_lbl)
        layout.addWidget(proj_hdr)

        # Project list
        self._project_list = QListWidget()
        self._project_list.setObjectName("ue_project_list")
        self._project_list.setStyleSheet("background: #0d0b14; border: none;")
        self._project_list.setFixedHeight(150)
        layout.addWidget(self._project_list)

        # Build output section
        build_hdr = QWidget()
        build_hdr.setObjectName("panel_header")
        build_hdr.setStyleSheet("background: #0d0b14; border-bottom: 1px solid #231c34;")
        build_hdr.setFixedHeight(40)
        build_hdr_layout = QHBoxLayout(build_hdr)
        build_hdr_layout.setContentsMargins(10, 4, 10, 4)
        build_lbl = QLabel("BUILD OUTPUT")
        build_lbl.setStyleSheet("color: #9d95b0; font-size: 11px; font-weight: 700; letter-spacing: 0.8px;")
        build_hdr_layout.addWidget(build_lbl)
        build_hdr_layout.addStretch()
        self._btn_build = QPushButton("⚙  Staged Build")
        self._btn_build.setObjectName("btn_ue_build")
        self._btn_build.setEnabled(False)
        self._btn_build.setFixedHeight(28)
        self._btn_build.clicked.connect(self._on_build)
        build_hdr_layout.addWidget(self._btn_build)
        layout.addWidget(build_hdr)

        self._build_output = QTextEdit()
        self._build_output.setObjectName("ue_build_output")
        self._build_output.setReadOnly(True)
        self._build_output.setStyleSheet(
            "background: #08070d; color: #9d95b0; border: none;"
            " font-family: 'Consolas', monospace; font-size: 11px;"
        )
        self._build_output.setPlaceholderText("Select a project and press 'Staged Build' to compile…")
        layout.addWidget(self._build_output, 1)

    # ── Refresh ─────────────────────────────────────────────────────────────

    @Slot()
    def _refresh(self) -> None:
        self._tools.execute("unreal_engine_info")
        self._tools.execute("unreal_find_projects")

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

    @Slot()
    def _on_build(self) -> None:
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

        from PySide6.QtCore import QRunnable, QThreadPool

        class _BuildSignals(QObject):
            done = Signal(dict)

        class _BuildRunnable(QRunnable):
            def __init__(self_, r, signals):
                super().__init__()
                self_._runner = r
                self_._signals = signals

            def run(self_):
                result = self_._runner()
                self_._signals.done.emit(result)

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
