"""Build view for Studio UX v2 (spec §4.4, WI-4.7).

Displays:
- Runs dropdown selector
- Action buttons: Cancel (with >30s confirmation), Resume, Roll back (with checkpoint list and link check)
- Timeline QListView with StepRowDelegate
- Right pane: Step details, live LogView (100ms batched appends), Problems table, Artifacts
- Summary banner: PASS -> "Ready to play" [Play], FAILED -> "Failed at <step>: <first error>"
"""
from __future__ import annotations

import copy

import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    QTimer,
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..services.forge_service import ForgeService
from ..styles import tokens
from ..styles.dark_theme import theme_stylesheet
from ..widgets.log_view import LogView
from ..widgets.problems_table import ProblemsTable
from ..widgets.step_row import STEP_ROLE, StepRowDelegate, format_step_duration
from ...core.jobs import JobHandle, default_job_manager
from ...core.settings import get_settings
from ...core.projects import resolve_project_dir, open_folder_in_file_manager
from ...forge.checkpoints import ProjectRepo
from ...forge.model import RunState, StepRecord
from ...forge.store import RunStore

logger = logging.getLogger(__name__)


def _project_editor_running(project_dir: Path) -> bool:
    """True when an Unreal Editor process has this project's .uproject open (best effort, never raises).

    Rolling back while the editor holds the project's files corrupts the checkpoint, so ProjectRepo.reset_to
    refuses in that case; previously the call omitted the flag entirely and every roll back failed with TypeError.
    """
    try:
        import psutil  # optional dependency
    except Exception:
        return False
    try:
        uprojects = {p.name.lower() for p in Path(project_dir).glob("*.uproject")}
        if not uprojects:
            return False
        for proc in psutil.process_iter(["name", "cmdline"]):
            name = (proc.info.get("name") or "").lower()
            if not name.startswith("unrealeditor"):
                continue
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if any(u in cmd for u in uprojects):
                return True
    except Exception:
        return False
    return False


class TimelineListModel(QAbstractListModel):
    """List model backed by a list of StepRecord objects."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._steps: List[StepRecord] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._steps)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._steps)):
            return None
        step = self._steps[index.row()]
        if role == Qt.DisplayRole:
            return step.step_id
        if role == STEP_ROLE:
            return step
        return None

    def set_steps(self, steps: List[StepRecord]) -> None:
        self.beginResetModel()
        self._steps = list(steps)
        self.endResetModel()

    def get_step(self, row: int) -> Optional[StepRecord]:
        if 0 <= row < len(self._steps):
            return self._steps[row]
        return None


class BuildView(QWidget):
    """Build view implementation for Studio UX (spec §4.4, WI-4.7)."""

    playRequested = Signal(str)            # (project_name) -> open Play view
    openCodeRequested = Signal(str, int)   # (file_path, line) -> Code view

    def __init__(
        self,
        forge_service: Optional[ForgeService] = None,
        workspace_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("buildView")
        self.setAccessibleName("GameForge Build View")

        self._workspace = Path(workspace_root or Path.cwd()).resolve()
        self._forge_service = forge_service
        self._store = RunStore(project_dir=None, workspace_dir=self._workspace)
        self._current_project: Optional[str] = None
        self._current_run_id: Optional[str] = None
        self._current_state: Optional[RunState] = None
        self._job_manager = default_job_manager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── 1. Top Header Bar ─────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(tokens.SPACE_MD)

        lbl_runs = QLabel("Runs ▾", self)
        lbl_runs.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;")
        header_layout.addWidget(lbl_runs)

        # Runs selector combo
        self._runs_combo = QComboBox(self)
        self._runs_combo.setObjectName("buildRunsCombo")
        self._runs_combo.setAccessibleName("Select active or past run")
        self._runs_combo.setToolTip("Select a build run to inspect timeline and logs")
        self._runs_combo.setMinimumWidth(320)
        self._runs_combo.setStyleSheet(
            f"QComboBox#{self._runs_combo.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY}px;"
            f"}}"
        )
        self._runs_combo.currentIndexChanged.connect(self._on_run_selected)
        header_layout.addWidget(self._runs_combo)

        header_layout.addStretch(1)

        # Cancel button
        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("btnBuildCancel")
        self._btn_cancel.setAccessibleName("Cancel active run")
        self._btn_cancel.setToolTip("Cancel currently running build")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.setStyleSheet(
            f"QPushButton#{self._btn_cancel.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_ERROR};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_cancel.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
            f"QPushButton#{self._btn_cancel.objectName()}:disabled {{ color: {tokens.TEXT_MUTED}; }}"
            f"QPushButton#{self._btn_cancel.objectName()}:focus {{ border: 1px solid {tokens.BORDER_FOCUS}; }}"
        )
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)
        header_layout.addWidget(self._btn_cancel)

        # Resume button
        self._btn_resume = QPushButton("Resume", self)
        self._btn_resume.setObjectName("btnBuildResume")
        self._btn_resume.setAccessibleName("Resume failed or cancelled run")
        self._btn_resume.setToolTip("Resume failed or cancelled build run")
        self._btn_resume.setCursor(Qt.PointingHandCursor)
        self._btn_resume.setStyleSheet(
            f"QPushButton#{self._btn_resume.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_HOVER};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_resume.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
            f"QPushButton#{self._btn_resume.objectName()}:disabled {{ color: {tokens.TEXT_MUTED}; }}"
            f"QPushButton#{self._btn_resume.objectName()}:focus {{ border: 1px solid {tokens.BORDER_FOCUS}; }}"
        )
        self._btn_resume.clicked.connect(self._on_resume_clicked)
        header_layout.addWidget(self._btn_resume)

        # Roll back button
        self._btn_rollback = QPushButton("Roll back ▾", self)
        self._btn_rollback.setObjectName("btnBuildRollback")
        self._btn_rollback.setAccessibleName("Roll back to earlier checkpoint")
        self._btn_rollback.setToolTip("Select a recorded checkpoint commit to roll back project state")
        self._btn_rollback.setCursor(Qt.PointingHandCursor)
        self._btn_rollback.setStyleSheet(
            f"QPushButton#{self._btn_rollback.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_rollback.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
            f"QPushButton#{self._btn_rollback.objectName()}:focus {{ border: 1px solid {tokens.BORDER_FOCUS}; }}"
        )
        self._btn_rollback.clicked.connect(self._show_rollback_menu)
        header_layout.addWidget(self._btn_rollback)

        main_layout.addLayout(header_layout)

        # ── Summary Banner (Ready to play or Failed) ──────────────────────────
        self._summary_banner = QFrame(self)
        self._summary_banner.setObjectName("buildSummaryBanner")
        self._summary_banner.setStyleSheet(
            f"QFrame#{self._summary_banner.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px {tokens.SPACE_MD}px;"
            f"}}"
        )
        banner_layout = QHBoxLayout(self._summary_banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        self._lbl_banner_msg = QLabel(self._summary_banner)
        self._lbl_banner_msg.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px;")
        banner_layout.addWidget(self._lbl_banner_msg, 1)

        self._btn_banner_action = QPushButton("Action", self._summary_banner)
        self._btn_banner_action.setObjectName("btnBannerAction")
        self._btn_banner_action.setCursor(Qt.PointingHandCursor)
        self._btn_banner_action.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-weight: 600;"
            f"}}"
        )
        self._btn_banner_action.clicked.connect(self._on_banner_action_clicked)
        banner_layout.addWidget(self._btn_banner_action)
        self._summary_banner.setVisible(False)
        main_layout.addWidget(self._summary_banner)

        # ── 2. Splitter: Left Timeline & Right Details ────────────────────────
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("buildSplitter")

        # Left pane: Timeline
        left_widget = QWidget(splitter)
        left_widget.setMinimumWidth(240)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        lbl_tl = QLabel("Timeline", left_widget)
        lbl_tl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;")
        left_layout.addWidget(lbl_tl)

        self._timeline_model = TimelineListModel(self)
        self._timeline_view = QListView(left_widget)
        self._timeline_view.setObjectName("buildTimelineView")
        self._timeline_view.setAccessibleName("Run steps timeline")
        self._timeline_view.setToolTip("Select a step to view execution logs, diagnostics, and artifacts")
        self._timeline_view.setModel(self._timeline_model)
        self._timeline_delegate = StepRowDelegate(self._timeline_view)
        self._timeline_view.setItemDelegate(self._timeline_delegate)
        self._timeline_view.clicked.connect(self._on_step_selected)
        if self._timeline_view.selectionModel():
            self._timeline_view.selectionModel().currentChanged.connect(lambda cur, prev: self._on_step_selected(cur))
        self._timeline_view.setStyleSheet(
            f"QListView#{self._timeline_view.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
            f"QListView#{self._timeline_view.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
            f"}}"
        )
        left_layout.addWidget(self._timeline_view, 1)
        splitter.addWidget(left_widget)

        # Right pane: Step details
        right_widget = QWidget(splitter)
        right_widget.setMinimumWidth(400)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Step header label
        self._lbl_step_header = QLabel("Select a step to view logs and diagnostics", right_widget)
        self._lbl_step_header.setObjectName("lblBuildStepHeader")
        self._lbl_step_header.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;"
        )
        right_layout.addWidget(self._lbl_step_header)

        # Vertical splitter for log view and lower tabs
        right_splitter = QSplitter(Qt.Vertical, right_widget)
        right_splitter.setObjectName("buildRightSplitter")
        self._right_splitter = right_splitter

        # Log view
        self._log_view = LogView(right_splitter)
        self._log_view.setMinimumHeight(160)
        right_splitter.addWidget(self._log_view)

        # Lower tabs: Problems & Artifacts
        self._lower_tabs = QTabWidget(right_splitter)
        self._lower_tabs.setObjectName("buildLowerTabs")
        self._lower_tabs.setAccessibleName("Problems and Artifacts tabs")
        self._lower_tabs.setStyleSheet(
            f"QTabWidget::pane {{"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  background-color: {tokens.BG_PANEL};"
            f"}}"
            f"QTabBar::tab {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  padding: 4px {tokens.SPACE_MD}px; margin-right: 2px;"
            f"  border-top-left-radius: 4px; border-top-right-radius: 4px;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  background-color: {tokens.BG_ACTIVE}; color: {tokens.TEXT_PRIMARY};"
            f"}}"
        )
        self._lower_tabs.setMinimumHeight(160)

        # Problems tab
        self._problems_table = ProblemsTable(self._lower_tabs)
        self._problems_table.openLocationRequested.connect(self.openCodeRequested.emit)
        self._lower_tabs.addTab(self._problems_table, "Problems (0)")

        # Artifacts tab
        self._artifacts_text = QTextEdit(self._lower_tabs)
        self._artifacts_text.setObjectName("buildArtifactsText")
        self._artifacts_text.setAccessibleName("Step artifacts output")
        self._artifacts_text.setReadOnly(True)
        self._artifacts_text.setStyleSheet(
            f"background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY};"
            f"font-family: monospace; font-size: 11px; border: none;"
        )
        self._lower_tabs.addTab(self._artifacts_text, "Artifacts (0)")

        right_splitter.addWidget(self._lower_tabs)
        right_splitter.setSizes([340, 180])
        right_splitter.setCollapsible(0, False)
        right_splitter.setCollapsible(1, False)

        right_layout.addWidget(right_splitter, 1)
        splitter.addWidget(right_widget)

        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([320, 680])
        main_layout.addWidget(splitter, 1)

        self._duration_timer = QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._on_duration_tick)

        # Connect to ForgeService if provided
        if self._forge_service:
            self._forge_service.runEvent.connect(self._on_forge_event)
            self._forge_service.runListChanged.connect(self.refresh_runs)

        self.refresh_runs()

    # ── Public API ───────────────────────────────────────────────────────────

    def showEvent(self, event: Optional[QShowEvent] = None) -> None:
        super().showEvent(event)
        self.refresh_runs()

    @Slot()
    def update_theme(self) -> None:
        """Update view stylesheets for active theme."""
        if hasattr(self, "_runs_combo"):
            self._runs_combo.setStyleSheet(theme_stylesheet(
                f"QComboBox#{self._runs_combo.objectName()} {{"
                f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
                f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
                f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY}px;"
                f"}}"
            ))
        if hasattr(self, "_timeline_view"):
            self._timeline_view.setStyleSheet(theme_stylesheet(
                f"QListView#{self._timeline_view.objectName()} {{"
                f"  background-color: {tokens.BG_PANEL};"
                f"  border: 1px solid {tokens.BORDER};"
                f"  border-radius: {tokens.RADIUS}px;"
                f"}}"
                f"QListView#{self._timeline_view.objectName()}:focus {{"
                f"  border: 1px solid {tokens.BORDER_FOCUS};"
                f"}}"
            ))
        if hasattr(self, "_log_view") and hasattr(self._log_view, "update_theme"):
            self._log_view.update_theme()
        if hasattr(self, "_problems_table") and hasattr(self._problems_table, "update_theme"):
            self._problems_table.update_theme()

    def deleteLater(self) -> None:
        """Clean up background timers and service connections on disposal."""
        if hasattr(self, "_duration_timer") and self._duration_timer.isActive():
            self._duration_timer.stop()
        if self._forge_service is not None:
            try:
                self._forge_service.runEvent.disconnect(self._on_forge_event)
            except Exception:
                pass
            try:
                self._forge_service.runListChanged.disconnect(self.refresh_runs)
            except Exception:
                pass
        super().deleteLater()

    def set_project(self, project_name: str, project_dir: Optional[Path] = None) -> None:
        """Filter runs for project_name and switch store scope."""
        self._current_project = project_name
        p_dir = project_dir or resolve_project_dir(project_name, self._workspace)
        self._project_dir = p_dir
        self._current_project_dir = p_dir
        if p_dir:
            self._store = RunStore(project_dir=p_dir, workspace_dir=self._workspace)
        self.refresh_runs()

    def clear_project(self) -> None:
        """Reset build view when no project is active."""
        self._current_project = None
        self._project_dir = None
        self._current_project_dir = None
        self._current_run_id = None
        self._current_state = None
        if hasattr(self, "_runs_combo"):
            self._runs_combo.blockSignals(True)
            self._runs_combo.clear()
            self._runs_combo.blockSignals(False)
        if hasattr(self, "_timeline_model"):
            self._timeline_model.set_steps([])
        if hasattr(self, "_log_view"):
            self._log_view.clear()
        if hasattr(self, "_problems_table"):
            self._problems_table.set_problems([])
        if hasattr(self, "_artifacts_text"):
            self._artifacts_text.clear()
        if hasattr(self, "_summary_banner"):
            self._summary_banner.setVisible(False)

    def start_build(self, project_name: str, spec: Optional[Any] = None, project_dir: Optional[Path] = None) -> None:
        """Start or resume a Forge build run for project_name in a background thread."""
        self._current_project = project_name
        p_root_cfg = get_settings().projects_root
        p_root = Path(p_root_cfg).expanduser().resolve() if p_root_cfg else self._workspace
        if project_dir is not None:
            p_dir = Path(project_dir).expanduser().resolve()
        else:
            resolved = getattr(self, "_current_project_dir", None) or resolve_project_dir(project_name, self._workspace)
            p_dir = Path(resolved).resolve() if resolved else (p_root / project_name).resolve()
        p_dir.mkdir(parents=True, exist_ok=True)
        self._current_project_dir = p_dir
        self._store = RunStore(project_dir=p_dir, workspace_dir=self._workspace)

        # 1. Obtain spec
        if spec is None:
            try:
                from ...design import store as gds_store
                spec = gds_store.load(p_dir)
            except Exception as exc:
                logger.debug("Could not load design spec from %s: %s", p_dir, exc)

        run_spec = None
        if spec is not None:
            # Try composer first (WI-6.2)
            try:
                from ...composer import compose, composition_to_run_spec
                comp = compose(spec, allow_partial=True)
                run_spec = composition_to_run_spec(comp, str(self._workspace), str(p_dir), origin="prompt")
            except Exception as exc:
                logger.debug("Composer planning failed, falling back to legacy: %s", exc)
                try:
                    from ...design.legacy import to_legacy_params
                    from ...forge.legacy_adapter import plan_legacy
                    params = to_legacy_params(spec)
                    run_spec = plan_legacy(
                        params,
                        projects_root=Path(p_root),
                        engine_root=Path(get_settings().engine_root) if get_settings().engine_root else None,
                    )
                except Exception as exc2:
                    logger.error("Failed to plan build run: %s", exc2)
                    QMessageBox.warning(self, "Build Error", f"Failed to plan build for {project_name}: {exc2}")
                    return
        else:
            # Check if there is an existing run to re-execute
            latest = self._store.latest_for_project(p_dir)
            if latest:
                run_spec = latest.run

        if not run_spec:
            QMessageBox.warning(self, "No Build Plan", f"No design specification or existing run found for '{project_name}'.")
            return

        state = RunState.new(run_spec)
        self._store.save(state)
        self._current_run_id = state.run.run_id
        self._current_state = state
        self.refresh_runs()

        # Run in background daemon thread with an isolated copy of state
        worker_state = copy.deepcopy(state)
        def _worker():
            try:
                from ...forge.executor import ForgeExecutor
                from ...forge.handlers import HANDLERS
                from ...core.events import default_bus
                executor = ForgeExecutor(HANDLERS, bus=default_bus())
                executor.run(worker_state, self._store)
            except Exception as exc:
                logger.error("Background Forge run crashed: %s", exc, exc_info=True)

        t = threading.Thread(target=_worker, daemon=True, name=f"ForgeBuild-{project_name}")
        t.start()

    def set_forge_service(self, service: ForgeService) -> None:
        if self._forge_service is not None:
            try:
                self._forge_service.runEvent.disconnect(self._on_forge_event)
                self._forge_service.runListChanged.disconnect(self.refresh_runs)
            except Exception:
                pass
        self._forge_service = service
        if service is not None:
            service.runEvent.connect(self._on_forge_event)
            service.runListChanged.connect(self.refresh_runs)
        self.refresh_runs()

    @Slot()
    def _on_duration_tick(self) -> None:
        if hasattr(self, "_timeline_view") and self._timeline_view.viewport():
            self._timeline_view.viewport().update()

    @Slot()
    def refresh_runs(self) -> None:
        """Scan recorded runs from RunStore and populate runs combo."""
        index = self._store.get_runs_index()
        self._runs_combo.blockSignals(True)
        self._runs_combo.clear()

        for r in index:
            run_id = r.get("run_id", "")
            title = r.get("title", "")
            status = r.get("status", "")
            display_text = f"{title or run_id} · {status}"
            self._runs_combo.addItem(display_text, userData=run_id)

        self._runs_combo.blockSignals(False)

        target_idx = 0
        if self._current_run_id:
            for i in range(self._runs_combo.count()):
                if self._runs_combo.itemData(i) == self._current_run_id:
                    target_idx = i
                    break

        if self._runs_combo.count() > 0:
            self._runs_combo.setCurrentIndex(target_idx)
            self._load_run_by_id(str(self._runs_combo.itemData(target_idx)))
        else:
            self._clear_run_view()

    # ── Internal Slots & Handlers ────────────────────────────────────────────

    @Slot(int)
    def _on_run_selected(self, index: int) -> None:
        run_id = self._runs_combo.itemData(index)
        if run_id:
            self._load_run_by_id(str(run_id))

    def _load_run_by_id(self, run_id: str, preserve_selection: bool = False) -> None:
        self._current_run_id = run_id
        state = self._store.load(run_id)
        if not state:
            return

        prev_selected_id = None
        if preserve_selection:
            cur_idx = self._timeline_view.currentIndex()
            if cur_idx.isValid():
                prev_step = self._timeline_model.get_step(cur_idx.row())
                if prev_step:
                    prev_selected_id = prev_step.step_id

        self._current_state = state
        self._btn_cancel.setEnabled(state.status in ("RUNNING", "WAITING_APPROVAL", "PENDING"))
        self._btn_resume.setEnabled(state.status in ("FAILED", "CANCELLED"))

        # Update Timeline
        records = list(state.records.values())
        self._timeline_model.set_steps(records)
        if hasattr(self, "_duration_timer"):
            if any(getattr(r, "status", "") == "RUNNING" for r in records):
                if not self._duration_timer.isActive():
                    self._duration_timer.start()
            else:
                self._duration_timer.stop()

        # Update banner
        self._update_summary_banner(state)

        # Select appropriate step
        if records:
            active_idx = 0
            if prev_selected_id:
                for i, rec in enumerate(records):
                    if rec.step_id == prev_selected_id:
                        active_idx = i
                        break
            elif state.status == "FAILED":
                for i, rec in enumerate(records):
                    if rec.status == "FAILED" or rec.errors:
                        active_idx = i
                        break
            else:
                for i, rec in enumerate(records):
                    if rec.status == "RUNNING":
                        active_idx = i
                        break
            self._timeline_view.setCurrentIndex(self._timeline_model.index(active_idx, 0))
            self._display_step(records[active_idx])

    def _update_summary_banner(self, state: RunState) -> None:
        st = state.status
        if st == "DONE":
            self._lbl_banner_msg.setText("Run completed successfully. Ready to play!")
            self._btn_banner_action.setText("Play Now")
            self._summary_banner.setVisible(True)
        elif st == "FAILED":
            first_err = "Check problem details below"
            for rec in state.records.values():
                if rec.errors:
                    first_err = rec.errors[0]
                    break
            self._lbl_banner_msg.setText(f"Run failed: {first_err}")
            self._btn_banner_action.setText("Show Problems")
            self._summary_banner.setVisible(True)
        else:
            self._summary_banner.setVisible(False)

    @Slot()
    def _on_banner_action_clicked(self) -> None:
        if not self._current_state:
            return
        if self._current_state.status == "DONE":
            self.playRequested.emit(self._current_project or "")
        elif self._current_state.status == "FAILED":
            # Jump to the failed step in the timeline
            records = list(self._current_state.records.values())
            failed_idx = None
            for idx, rec in enumerate(records):
                if rec.status == "FAILED" or rec.errors:
                    failed_idx = idx
                    break
            if failed_idx is not None:
                model_idx = self._timeline_model.index(failed_idx, 0)
                self._timeline_view.setCurrentIndex(model_idx)
                self._display_step(records[failed_idx])

            self._lower_tabs.setCurrentIndex(0)
            if hasattr(self, "_right_splitter") and self._right_splitter:
                sizes = self._right_splitter.sizes()
                if len(sizes) == 2 and sizes[1] < 160:
                    self._right_splitter.setSizes([max(180, sizes[0] - 160), max(180, sizes[1] + 160)])

    @Slot(QModelIndex)
    def _on_step_selected(self, index: QModelIndex) -> None:
        step = self._timeline_model.get_step(index.row())
        if step:
            self._display_step(step)

    def _display_step(self, step: StepRecord) -> None:
        title = step.step_id.replace("_", " ").capitalize()
        dur = format_step_duration(step.started_at, step.finished_at)
        lock_info = " · engine lock held" if step.status == "RUNNING" else ""
        self._lbl_step_header.setText(f"Step: {title} (attempt {step.attempts}) — Status {step.status} {dur}{lock_info}")

        # Resolve log path
        log_content: Optional[str] = None
        log_path = step.data.get("log_path") or step.data.get("log")
        if not log_path and step.artifacts:
            for a in step.artifacts:
                p = getattr(a, "path", None) or (a.get("path") if isinstance(a, dict) else None)
                if p and (str(p).endswith(".log") or getattr(a, "kind", "") == "log"):
                    log_path = p
                    break

        # Check standard project locations if log_path still not resolved
        p_dir = getattr(self, "_current_project_dir", None) or resolve_project_dir(self._current_project, self._workspace)
        if not log_path and p_dir and p_dir.is_dir():
            candidate_logs = [
                p_dir / "Saved" / "GameForge" / "logs" / f"{step.step_id}.log",
                p_dir / "Saved" / "GameForge" / f"{step.step_id}.log",
            ]
            if "assemble" in step.step_id:
                candidate_logs.append(p_dir / "Saved" / "GameForge" / "assemble_editor.log")
            if step.step_id == "automation":
                candidate_logs.append(p_dir / "Saved" / "GameForge" / "logs" / "automation.log")
            for c in candidate_logs:
                if c.is_file():
                    log_path = str(c)
                    break

        if log_path and Path(log_path).is_file():
            try:
                raw_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
                log_content = raw_text[-50000:]
            except Exception as exc:
                log_content = f"Unable to read log file ({log_path}): {exc}"

        if not log_content:
            direct_output = step.data.get("output", "") or step.data.get("stdout", "")
            if direct_output:
                log_content = direct_output
            else:
                lines = []
                lines.append("=" * 64)
                lines.append(f" STEP: {step.step_id} (Attempt {step.attempts})")
                lines.append(f" Status: {step.status} | Duration: {dur}")
                if step.checkpoint:
                    lines.append(f" Git Checkpoint: {step.checkpoint}")
                lines.append("=" * 64)
                lines.append("")

                if step.step_id == "design":
                    lines.append("Design specification validated.")
                    if "engine" in step.data:
                        lines.append(f"Target Unreal Engine: {step.data['engine']}")
                    params = step.data.get("params", {})
                    if params:
                        lines.append("\nParameters:")
                        for k, v in params.items():
                            lines.append(f"  • {k}: {v}")

                elif step.step_id == "scaffold":
                    lines.append("C++ project scaffolding complete.")
                    if "uproject" in step.data:
                        lines.append(f"Project descriptor: {step.data['uproject']}")
                    files = step.data.get("files", [])
                    if files:
                        lines.append(f"\nGenerated files ({len(files)}):")
                        for f in files:
                            lines.append(f"  • {f}")

                elif step.step_id == "content":
                    lines.append("Content preparation complete.")
                    packs = step.data.get("installed_packs", [])
                    if packs:
                        lines.append(f"Installed packs: {', '.join(packs)}")
                    dirs = step.data.get("cook_dirs", [])
                    if dirs:
                        lines.append(f"Cook directories: {', '.join(dirs)}")
                    if "artifacts_count" in step.data:
                        lines.append(f"Artifacts generated: {step.data['artifacts_count']}")

                elif "assemble" in step.step_id:
                    lines.append("Level assembly complete.")
                    if "map" in step.data:
                        lines.append(f"Map: {step.data['map']}")
                    calls = step.data.get("calls", [])
                    if calls:
                        lines.append(f"\nOperations executed ({len(calls)}):")
                        for call in calls:
                            status = "OK" if call.get("ok") else f"FAILED: {call.get('errors')}"
                            lines.append(f"  • {call.get('op', 'op')}: {status}")

                elif step.step_id == "scenario_gen":
                    lines.append("Scenario generation complete.")

                # Gather matching events from events.jsonl
                if self._current_run_id:
                    try:
                        events = self._store.load_events(self._current_run_id)
                        step_events = [e for e in events if e.get("step_id") == step.step_id]
                        if step_events:
                            lines.append("\nExecution Events:")
                            for ev in step_events:
                                kind = ev.get("kind", "")
                                if kind == "log":
                                    lines.append(f"  [LOG] {ev.get('line', '')}")
                                elif kind == "step_started":
                                    lines.append(f"  [START] Attempt {ev.get('attempt', 1)}")
                                elif kind == "step_finished":
                                    lines.append(f"  [FINISH] ok={ev.get('ok')} (duration: {ev.get('duration_s', 0)}s)")
                                elif kind == "step_blocked":
                                    lines.append("  [BLOCKED]")
                    except Exception:
                        pass

                if step.errors:
                    lines.append("\nErrors encountered:")
                    for err in step.errors:
                        lines.append(f"  ✗ {err}")

                log_content = "\n".join(lines)

        self._log_view.set_text(log_content)

        # Diagnostics / Problems
        diagnostics = list(step.data.get("diagnostics", []))
        if step.errors:
            for err in step.errors:
                if not any(d.get("message") == err for d in diagnostics if isinstance(d, dict)):
                    diagnostics.append({"severity": "Error", "message": err, "file": step.step_id, "line": 0})
        self._problems_table.set_problems(diagnostics)
        self._lower_tabs.setTabText(0, f"Problems ({len(diagnostics)})")

        # Artifacts
        artifacts = list(step.artifacts)
        if artifacts:
            self._artifacts_text.setPlainText("\n".join(f"• {getattr(a, 'path', str(a))}" for a in artifacts))
        else:
            self._artifacts_text.setPlainText("No artifacts produced.")
        self._lower_tabs.setTabText(1, f"Artifacts ({len(artifacts)})")

    def _clear_run_view(self) -> None:
        self._current_run_id = None
        self._current_state = None
        self._timeline_model.set_steps([])
        self._log_view.clear()
        self._problems_table.set_problems([])
        self._artifacts_text.clear()
        self._lbl_step_header.setText("No runs available.")
        self._summary_banner.setVisible(False)

    @Slot(dict)
    def _on_forge_event(self, event: Dict[str, Any]) -> None:
        run_id = event.get("run_id")
        if run_id and run_id == self._current_run_id:
            kind = event.get("kind")
            step_id = event.get("step_id")
            cur_idx = self._timeline_view.currentIndex()
            current_step = self._timeline_model.get_step(cur_idx.row()) if cur_idx.isValid() else None

            # If live log line arrives for currently selected step, append immediately
            if kind == "log" and step_id and current_step and current_step.step_id == step_id:
                line = event.get("line")
                if line:
                    self._log_view.append_log(line)
                return

            # Refresh currently displayed run while preserving selection
            self._load_run_by_id(run_id, preserve_selection=True)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        if not self._current_state or not self._current_run_id:
            return
        elapsed = time.time() - (self._current_state.run.created_at if hasattr(self._current_state, "run") else time.time())
        if elapsed > 30.0:
            reply = QMessageBox.question(
                self,
                "Cancel Run",
                f"The run has been in progress for {int(elapsed)} seconds. Are you sure you want to cancel it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # Request cancel through forge executor
        cancelled = False
        try:
            from ...forge.executor import ForgeExecutor
            cancelled = ForgeExecutor.cancel_run(self._current_run_id)
        except Exception:
            pass
        if not cancelled:
            # If not running in memory (e.g. orphaned from crash or previous session),
            # mark as CANCELLED directly in store so run does not remain stuck.
            state = self._store.load(self._current_run_id)
            if state and state.status in ("RUNNING", "WAITING_APPROVAL", "PENDING"):
                state.status = "CANCELLED"
                self._store.save(state)
        self.refresh_runs()

    @Slot()
    def _on_resume_clicked(self) -> None:
        if not self._current_run_id or not self._current_project:
            return
        p_dir = getattr(self, "_current_project_dir", None) or resolve_project_dir(self._current_project, self._workspace)
        if not p_dir:
            return
        state = self._store.load(self._current_run_id)
        if not state:
            return
        from ...forge.model import StepStatus
        for rec in state.records.values():
            if rec.status in (StepStatus.SKIPPED, StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.BLOCKED):
                rec.status = StepStatus.PENDING
                rec.errors = []
        state.status = "RUNNING"
        self._store.save(state)
        self._load_run_by_id(self._current_run_id)

        worker_state = copy.deepcopy(state)
        def _worker():
            try:
                from ...forge.executor import ForgeExecutor
                from ...forge.handlers import HANDLERS
                from ...core.events import default_bus
                executor = ForgeExecutor(HANDLERS, bus=default_bus())
                executor.run(worker_state, self._store)
            except Exception as exc:
                logger.error("Background Forge resume crashed: %s", exc, exc_info=True)

        t = threading.Thread(target=_worker, daemon=True, name=f"ForgeResume-{self._current_project}")
        t.start()

    @Slot()
    def _show_rollback_menu(self) -> None:
        if not self._current_state or not self._current_project:
            return
        p_dir = getattr(self, "_current_project_dir", None) or resolve_project_dir(self._current_project, self._workspace)
        if not p_dir or not p_dir.is_dir():
            return

        # Check if editor link is open
        try:
            from ...backend.tools.game_tools import GameTools
            for link in GameTools.all_links():
                if getattr(link, "project_name", "") == self._current_project:
                    QMessageBox.warning(
                        self,
                        "Roll Back Refused",
                        f"Cannot roll back: project '{self._current_project}' is open in an active Unreal Editor session.",
                    )
                    return
        except ImportError:
            pass

        # Collect checkpoints from steps
        ckpts = []
        for step_id, rec in self._current_state.records.items():
            if rec.checkpoint:
                ckpts.append((step_id, rec.checkpoint))

        if not ckpts:
            QMessageBox.information(self, "No Checkpoints", "No step checkpoints recorded for this run.")
            return

        menu = QMenu(self)
        menu.setObjectName("buildRollbackMenu")
        for step_id, commit_sha in ckpts:
            act = menu.addAction(f"Return to after {step_id.capitalize()} ({commit_sha[:7]})")
            act.triggered.connect(lambda _, sha=commit_sha, sid=step_id: self._confirm_rollback(p_dir, sha, sid))
        menu.exec(self._btn_rollback.mapToGlobal(self._btn_rollback.rect().bottomLeft()))

    def _confirm_rollback(self, project_dir: Path, commit_sha: str, step_id: str) -> None:
        repo = ProjectRepo(project_dir)
        changed_files = repo.changed_since(commit_sha)
        if changed_files:
            files_preview = "\n".join(f"• {f}" for f in changed_files[:8])
            if len(changed_files) > 8:
                files_preview += f"\n... and {len(changed_files) - 8} more"
        else:
            files_preview = "• (No files modified since this checkpoint)"

        msg = (
            f"Roll back project to checkpoint after '{step_id}' ({commit_sha[:7]})?\n\n"
            f"The following {len(changed_files)} files will be restored/modified:\n"
            f"{files_preview}\n\n"
            f"Do you want to proceed?"
        )
        reply = QMessageBox.question(self, "Confirm Roll Back", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                repo.reset_to(commit_sha, editor_running=_project_editor_running(project_dir))
                QMessageBox.information(self, "Roll Back Complete", f"Project state restored to checkpoint {commit_sha[:7]}.")
                self.refresh_runs()
            except Exception as exc:
                logger.error("Rollback failed: %s", exc)
                QMessageBox.critical(self, "Roll Back Failed", f"Could not roll back to checkpoint {commit_sha[:7]}:\n{exc}")
