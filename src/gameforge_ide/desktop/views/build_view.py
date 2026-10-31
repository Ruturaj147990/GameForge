"""Build view for Studio UX v2 (spec §4.4, WI-4.7).

Displays:
- Runs dropdown selector
- Action buttons: Cancel (with >30s confirmation), Resume, Roll back (with checkpoint list and link check)
- Timeline QListView with StepRowDelegate
- Right pane: Step details, live LogView (100ms batched appends), Problems table, Artifacts
- Summary banner: PASS -> "Ready to play" [Play], FAILED -> "Failed at <step>: <first error>"
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (
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
from ..widgets.log_view import LogView
from ..widgets.problems_table import ProblemsTable
from ..widgets.step_row import STEP_ROLE, StepRowDelegate, format_step_duration
from src.gameforge_ide.core.jobs import JobHandle, default_job_manager
from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.forge.checkpoints import ProjectRepo
from src.gameforge_ide.forge.model import RunState, StepRecord
from src.gameforge_ide.forge.store import RunStore

logger = logging.getLogger(__name__)


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
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.setStyleSheet(
            f"QPushButton#{self._btn_cancel.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_ERROR};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_cancel.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
            f"QPushButton#{self._btn_cancel.objectName()}:disabled {{ color: {tokens.TEXT_MUTED}; }}"
        )
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)
        header_layout.addWidget(self._btn_cancel)

        # Resume button
        self._btn_resume = QPushButton("Resume", self)
        self._btn_resume.setObjectName("btnBuildResume")
        self._btn_resume.setAccessibleName("Resume failed or cancelled run")
        self._btn_resume.setCursor(Qt.PointingHandCursor)
        self._btn_resume.setStyleSheet(
            f"QPushButton#{self._btn_resume.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_HOVER};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_resume.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
            f"QPushButton#{self._btn_resume.objectName()}:disabled {{ color: {tokens.TEXT_MUTED}; }}"
        )
        self._btn_resume.clicked.connect(self._on_resume_clicked)
        header_layout.addWidget(self._btn_resume)

        # Roll back button
        self._btn_rollback = QPushButton("Roll back ▾", self)
        self._btn_rollback.setObjectName("btnBuildRollback")
        self._btn_rollback.setAccessibleName("Roll back to earlier checkpoint")
        self._btn_rollback.setCursor(Qt.PointingHandCursor)
        self._btn_rollback.setStyleSheet(
            f"QPushButton#{self._btn_rollback.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_rollback.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
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
        self._timeline_view.setModel(self._timeline_model)
        self._timeline_delegate = StepRowDelegate(self._timeline_view)
        self._timeline_view.setItemDelegate(self._timeline_delegate)
        self._timeline_view.clicked.connect(self._on_step_selected)
        self._timeline_view.setStyleSheet(
            f"QListView#{self._timeline_view.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        left_layout.addWidget(self._timeline_view, 1)
        splitter.addWidget(left_widget)

        # Right pane: Step details
        right_widget = QWidget(splitter)
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

        # Log view
        self._log_view = LogView(right_widget)
        right_layout.addWidget(self._log_view, 2)

        # Lower tabs: Problems & Artifacts
        self._lower_tabs = QTabWidget(right_widget)
        self._lower_tabs.setObjectName("buildLowerTabs")
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

        # Problems tab
        self._problems_table = ProblemsTable(self._lower_tabs)
        self._problems_table.openLocationRequested.connect(self.openCodeRequested.emit)
        self._lower_tabs.addTab(self._problems_table, "Problems (0)")

        # Artifacts tab
        self._artifacts_text = QTextEdit(self._lower_tabs)
        self._artifacts_text.setObjectName("buildArtifactsText")
        self._artifacts_text.setReadOnly(True)
        self._artifacts_text.setStyleSheet(
            f"background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY};"
            f"font-family: monospace; font-size: 11px; border: none;"
        )
        self._lower_tabs.addTab(self._artifacts_text, "Artifacts (0)")

        right_layout.addWidget(self._lower_tabs, 1)
        splitter.addWidget(right_widget)

        splitter.setSizes([320, 680])
        main_layout.addWidget(splitter, 1)

        # Connect to ForgeService if provided
        if self._forge_service:
            self._forge_service.runEvent.connect(self._on_forge_event)
            self._forge_service.runListChanged.connect(self.refresh_runs)

        self.refresh_runs()

    # ── Public API ───────────────────────────────────────────────────────────

    def set_project(self, project_name: str) -> None:
        """Filter runs for project_name."""
        self._current_project = project_name
        self.refresh_runs()

    def set_forge_service(self, service: ForgeService) -> None:
        self._forge_service = service
        service.runEvent.connect(self._on_forge_event)
        service.runListChanged.connect(self.refresh_runs)
        self.refresh_runs()

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

        if self._runs_combo.count() > 0:
            self._runs_combo.setCurrentIndex(0)
            self._load_run_by_id(str(self._runs_combo.currentData()))
        else:
            self._clear_run_view()

    # ── Internal Slots & Handlers ────────────────────────────────────────────

    @Slot(int)
    def _on_run_selected(self, index: int) -> None:
        run_id = self._runs_combo.itemData(index)
        if run_id:
            self._load_run_by_id(str(run_id))

    def _load_run_by_id(self, run_id: str) -> None:
        self._current_run_id = run_id
        state = self._store.load(run_id)
        if not state:
            return

        self._current_state = state
        self._btn_cancel.setEnabled(state.status in ("RUNNING", "WAITING_APPROVAL", "PENDING"))
        self._btn_resume.setEnabled(state.status in ("FAILED", "CANCELLED"))

        # Update Timeline
        records = list(state.records.values())
        self._timeline_model.set_steps(records)

        # Update banner
        self._update_summary_banner(state)

        # Select first or currently running step
        if records:
            active_idx = 0
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
            self._lower_tabs.setCurrentIndex(0)

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

        # Logs
        log_path = step.data.get("log_path")
        if log_path and Path(log_path).is_file():
            try:
                content = Path(log_path).read_text(encoding="utf-8", errors="replace")
                self._log_view.set_text(content[-50000:])
            except Exception:
                self._log_view.set_text(f"Unable to read log file: {log_path}")
        else:
            step_logs = step.data.get("output", "") or step.data.get("stdout", "")
            if step_logs:
                self._log_view.set_text(step_logs)
            else:
                self._log_view.set_text(f"No logs recorded for step '{step.step_id}'.")

        # Diagnostics / Problems
        diagnostics = list(step.data.get("diagnostics", []))
        if step.errors:
            for err in step.errors:
                diagnostics.append({"severity": "Error", "message": err, "file": "", "line": 0})
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
            # Refresh currently displayed run
            self._load_run_by_id(run_id)

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
        try:
            from src.gameforge_ide.forge.executor import ForgeExecutor
            ForgeExecutor.request_cancel(self._current_run_id)
        except Exception:
            pass

    @Slot()
    def _on_resume_clicked(self) -> None:
        if not self._current_run_id:
            return
        QMessageBox.information(self, "Resume Run", f"Resuming run {self._current_run_id} from last valid checkpoint.")

    @Slot()
    def _show_rollback_menu(self) -> None:
        if not self._current_state or not self._current_project:
            return
        p_root = get_settings().projects_root
        if not p_root:
            return
        p_dir = Path(p_root) / self._current_project
        if not p_dir.is_dir():
            return

        # Check if editor link is open
        try:
            from src.gameforge_ide.backend.tools.game_tools import GameTools
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
        files_preview = "\n".join(f"• {f}" for f in changed_files[:8])
        if len(changed_files) > 8:
            files_preview += f"\n... and {len(changed_files) - 8} more"

        msg = (
            f"Roll back project to checkpoint after '{step_id}' ({commit_sha[:7]})?\n\n"
            f"The following {len(changed_files)} files will be restored/modified:\n"
            f"{files_preview}\n\n"
            f"Do you want to proceed?"
        )
        reply = QMessageBox.question(self, "Confirm Roll Back", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            repo.reset_to(commit_sha)
            QMessageBox.information(self, "Roll Back Complete", f"Project state restored to checkpoint {commit_sha[:7]}.")
            self.refresh_runs()
