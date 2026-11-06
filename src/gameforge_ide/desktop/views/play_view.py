"""Play view for Studio UX v2 (spec §4.5, WI-4.8).

Displays scenario results from the latest run's scenario step artifacts.
Shows a results table with pass/fail status, duration, and failure details.
Provides a 'Launch Game' action for packaged builds.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.core.projects import (
    find_packaged_executable,
    open_folder_in_file_manager,
    resolve_project_dir,
)
from src.gameforge_ide.forge.model import RunState
from src.gameforge_ide.forge.store import RunStore
from src.gameforge_ide.qa.scenario import ScenarioResult
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


class PlayView(QWidget):
    """Play view showing scenario test results and launch controls."""

    launchRequested = Signal(str)  # (project_name)
    buildRequested = Signal(str)   # (project_name) -> switch to build view / start build

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("playView")
        self.setAccessibleName("GameForge Play View")

        self._workspace = Path(workspace_root or Path.cwd()).resolve()
        self._store = RunStore(project_dir=None, workspace_dir=self._workspace)
        self._current_project: Optional[str] = None
        self._results: List[ScenarioResult] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── Header ───────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(tokens.SPACE_MD)

        lbl_title = QLabel("Scenario Results", self)
        lbl_title.setObjectName("lblPlayTitle")
        lbl_title.setAccessibleName("Scenario results title")
        lbl_title.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_HEADING}px; font-weight: 700;"
        )
        header.addWidget(lbl_title)

        header.addStretch(1)

        self._btn_refresh = QPushButton("Refresh", self)
        self._btn_refresh.setObjectName("btnPlayRefresh")
        self._btn_refresh.setAccessibleName("Refresh scenario results")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton#{self._btn_refresh.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_refresh.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_refresh.clicked.connect(self.refresh_results)
        header.addWidget(self._btn_refresh)

        self._btn_launch = QPushButton("Launch Game", self)
        self._btn_launch.setObjectName("btnPlayLaunch")
        self._btn_launch.setAccessibleName("Launch packaged game")
        self._btn_launch.setCursor(Qt.PointingHandCursor)
        self._btn_launch.setStyleSheet(
            f"QPushButton#{self._btn_launch.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton#{self._btn_launch.objectName()}:hover {{ background-color: {tokens.ACCENT_HOVER}; }}"
        )
        self._btn_launch.clicked.connect(self._on_launch)
        header.addWidget(self._btn_launch)

        main_layout.addLayout(header)

        # ── Summary Banner ───────────────────────────────────────────────────
        self._summary_frame = QFrame(self)
        self._summary_frame.setObjectName("playSummaryFrame")
        self._summary_frame.setStyleSheet(
            f"QFrame#{self._summary_frame.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px {tokens.SPACE_MD}px;"
            f"}}"
        )
        summary_layout = QHBoxLayout(self._summary_frame)
        summary_layout.setContentsMargins(8, 4, 8, 4)

        self._lbl_summary = QLabel("No scenario results loaded.", self._summary_frame)
        self._lbl_summary.setObjectName("lblPlaySummary")
        self._lbl_summary.setAccessibleName("Scenario results summary")
        self._lbl_summary.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px;"
        )
        summary_layout.addWidget(self._lbl_summary, 1)

        main_layout.addWidget(self._summary_frame)

        # ── Splitter: Results Table + Detail ─────────────────────────────────
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("playSplitter")

        # Left: scenario results table
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._results_table = QTableWidget(left_widget)
        self._results_table.setObjectName("playResultsTable")
        self._results_table.setAccessibleName("Scenario test results table")
        self._results_table.setColumnCount(4)
        self._results_table.setHorizontalHeaderLabels(["Status", "Scenario", "Duration", "Failures"])
        self._results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._results_table.setSelectionMode(QTableWidget.SingleSelection)
        self._results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._results_table.setStyleSheet(
            f"QTableWidget#{self._results_table.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  gridline-color: {tokens.BORDER};"
            f"  selection-background-color: {tokens.BG_ACTIVE};"
            f"  selection-color: {tokens.TEXT_PRIMARY};"
            f"}}"
            f"QTableWidget#{self._results_table.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  padding: 4px {tokens.SPACE_SM}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"  font-weight: 600;"
            f"}}"
        )
        self._results_table.clicked.connect(self._on_result_selected)
        self._results_table.itemSelectionChanged.connect(self._on_result_selected)
        self._results_table.currentCellChanged.connect(lambda r, c, pr, pc: self._on_result_selected())
        self._results_table.installEventFilter(self)
        left_layout.addWidget(self._results_table, 1)
        splitter.addWidget(left_widget)

        # Right: detail pane
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self._lbl_detail_header = QLabel("Select a scenario to view details", right_widget)
        self._lbl_detail_header.setObjectName("lblPlayDetailHeader")
        self._lbl_detail_header.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;"
        )
        right_layout.addWidget(self._lbl_detail_header)

        self._detail_text = QTextEdit(right_widget)
        self._detail_text.setObjectName("playDetailText")
        self._detail_text.setAccessibleName("Scenario result details")
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(
            f"QTextEdit#{self._detail_text.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px;"
            f"  font-family: monospace; font-size: 11px;"
            f"}}"
        )
        right_layout.addWidget(self._detail_text, 1)
        splitter.addWidget(right_widget)

        splitter.setSizes([450, 550])
        main_layout.addWidget(splitter, 1)

    # ── Public API ───────────────────────────────────────────────────────────

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_results()

    def set_project(self, project_name: str, project_dir: Optional[Path] = None) -> None:
        self._current_project = project_name
        p_dir = project_dir or resolve_project_dir(project_name, self._workspace)
        self._project_dir = p_dir
        self._current_project_dir = p_dir
        if self._current_project_dir:
            self._store = RunStore(project_dir=self._current_project_dir, workspace_dir=self._workspace)
        self.refresh_results()

    def clear_project(self) -> None:
        """Reset play view when no project is active."""
        self._current_project = None
        self._project_dir = None
        self._current_project_dir = None
        self._results.clear()
        if hasattr(self, "_results_table"):
            self._results_table.setRowCount(0)
        if hasattr(self, "_detail_text"):
            self._detail_text.clear()
        if hasattr(self, "_lbl_summary"):
            self._lbl_summary.setText("No project selected.")
        if hasattr(self, "_lbl_detail_header"):
            self._lbl_detail_header.setText("Select a scenario to view details")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._results_table and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._on_result_selected()
                return True
            elif event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End):
                res = super().eventFilter(watched, event)
                self._on_result_selected()
                return res
        return super().eventFilter(watched, event)

    @Slot()
    def refresh_results(self) -> None:
        """Load scenario results from the latest run's scenario step artifacts."""
        self._results.clear()
        self._results_table.setRowCount(0)
        self._detail_text.clear()
        self._lbl_detail_header.setText("Select a scenario to view details")

        if not self._current_project:
            self._lbl_summary.setText("No project selected.")
            return

        # Find latest run for this project
        project_dir = getattr(self, "_current_project_dir", None) or resolve_project_dir(self._current_project, self._workspace)
        if not project_dir or not project_dir.is_dir():
            self._lbl_summary.setText(f"Project directory not found for '{self._current_project}'.")
            return

        state = self._store.latest_for_project(project_dir)
        if not state:
            exe = self._get_packaged_exe()
            if not exe:
                self._lbl_summary.setText(
                    f"No packaged build or scenario results found for '{self._current_project}'. "
                    f"Run a Forge build to package and test this game."
                )
            else:
                self._lbl_summary.setText(f"Packaged build ready ({exe.name}). No scenario runs recorded.")
            return

        # Collect scenario_result artifacts from all steps
        for step_id, rec in state.records.items():
            for art in rec.artifacts:
                art_path = str(getattr(art, "path", art))
                kind = getattr(art, "kind", "other")
                if (kind == "scenario_result" or art_path.endswith("_result.json")) and art_path.endswith(".json"):
                    full_path = Path(art_path)
                    if not full_path.is_absolute():
                        full_path = project_dir / art_path
                    if full_path.is_file():
                        try:
                            result = ScenarioResult.from_file(full_path)
                            if not any(r.scenario_id == result.scenario_id for r in self._results):
                                self._results.append(result)
                        except Exception as e:
                            logger.warning("Failed to parse scenario result %s: %s", full_path, e)

        # Also scan the project's scenario results directories
        for sc_sub in ("evidence/scenarios", "scenarios"):
            sc_dir = project_dir / "Saved" / "GameForge" / sc_sub
            if sc_dir.is_dir():
                for f in sorted(sc_dir.glob("*_result.json")):
                    try:
                        result = ScenarioResult.from_file(f)
                        # Deduplicate by scenario_id
                        if not any(r.scenario_id == result.scenario_id for r in self._results):
                            self._results.append(result)
                    except Exception:
                        pass

        self._populate_table()

    def _get_packaged_exe(self) -> Optional[Path]:
        if not self._current_project:
            return None
        p_dir = getattr(self, "_current_project_dir", None) or resolve_project_dir(self._current_project, self._workspace)
        if not p_dir or not p_dir.is_dir():
            return None
        return find_packaged_executable(p_dir, self._current_project)

    def _populate_table(self) -> None:
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        exe = self._get_packaged_exe()

        if total == 0:
            if exe:
                self._lbl_summary.setText(f"Packaged build ready ({exe.name} · {exe.resolve()}). No scenario results recorded yet.")
                self._btn_launch.setText(f"Launch {exe.name}")
                self._btn_launch.setToolTip(f"Launch packaged game ({exe.resolve()})")
            else:
                self._lbl_summary.setText(
                    f"No packaged build or scenario results found for '{self._current_project}'. "
                    f"Run a Forge build to package and test this game."
                )
                self._btn_launch.setText("Package Game")
                self._btn_launch.setToolTip("Switch to Build View to package game")
            return

        color = tokens.ACCENT_SUCCESS if passed == total else tokens.ACCENT_ERROR
        if exe:
            pkg_status = f"  ·  <span style='color: {tokens.ACCENT_SUCCESS};'>🎮 {exe.name} ready</span>"
            self._btn_launch.setText(f"Launch {exe.name}")
            self._btn_launch.setToolTip(f"Launch packaged game ({exe.resolve()})")
        else:
            pkg_status = f"  ·  <span style='color: {tokens.ACCENT_WARNING};'>⚠️ Not packaged</span>"
            self._btn_launch.setText("Launch Game")
            self._btn_launch.setToolTip("Packaged game executable not yet created")

        self._lbl_summary.setText(
            f"<span style='color: {color}; font-weight: 600;'>"
            f"{passed}/{total} scenarios passed</span>"
            f"  ·  Total duration: {sum(r.duration_s for r in self._results):.1f}s"
            f"{pkg_status}"
        )

        self._results_table.setRowCount(total)
        for row, result in enumerate(self._results):
            # Status badge (PASS / FAIL / SKIP)
            failures_list = getattr(result, "failures", []) or []
            is_skipped = (
                getattr(result, "skipped", False)
                or str(getattr(result, "status", "")).upper() == "SKIP"
                or (not result.passed and any(f.lower().startswith("skip") or "skipped" in f.lower() for f in failures_list))
            )
            if is_skipped:
                status_text = "↷ SKIP"
                status_col = tokens.ACCENT_WARNING
            elif result.passed:
                status_text = "✓ PASS"
                status_col = tokens.ACCENT_SUCCESS
            else:
                status_text = "✕ FAIL"
                status_col = tokens.ACCENT_ERROR

            from PySide6.QtGui import QColor
            item_status = QTableWidgetItem(status_text)
            item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)
            item_status.setForeground(QColor(status_col))
            self._results_table.setItem(row, 0, item_status)

            # Scenario ID
            item_id = QTableWidgetItem(result.scenario_id)
            item_id.setFlags(item_id.flags() & ~Qt.ItemIsEditable)
            self._results_table.setItem(row, 1, item_id)

            # Duration
            item_dur = QTableWidgetItem(f"{result.duration_s:.1f}s")
            item_dur.setFlags(item_dur.flags() & ~Qt.ItemIsEditable)
            self._results_table.setItem(row, 2, item_dur)

            # Failure count
            fail_count = len(result.failures)
            item_fails = QTableWidgetItem(str(fail_count) if fail_count else "—")
            item_fails.setFlags(item_fails.flags() & ~Qt.ItemIsEditable)
            if fail_count:
                item_fails.setForeground(QColor(tokens.ACCENT_ERROR))
            self._results_table.setItem(row, 3, item_fails)

    @Slot()
    def _on_result_selected(self) -> None:
        row = self._results_table.currentRow()
        if 0 <= row < len(self._results):
            result = self._results[row]
            self._lbl_detail_header.setText(
                f"Scenario: {result.scenario_id}  ·  "
                f"{'PASS' if result.passed else 'FAIL'}  ·  "
                f"{result.duration_s:.1f}s"
            )

            lines = []
            if result.build:
                lines.append(f"Build: {result.build.configuration} (engine {result.build.engine})")
            lines.append(f"Duration: {result.duration_s:.1f}s (start delay: {result.start_delay_s:.1f}s)")
            lines.append("")

            if result.steps:
                lines.append("═══ Steps ═══")
                for step in result.steps:
                    dur = f" ({step.t1 - step.t0:.2f}s)" if step.t1 else ""
                    err = f"  ERROR: {step.error}" if step.error else ""
                    lines.append(f"  [{step.status}] {step.i}: {step.kind}{dur}{err}")
                lines.append("")

            if result.legs:
                lines.append("═══ Legs ═══")
                for leg in result.legs:
                    lines.append(
                        f"  [{leg.result}] → {leg.target}: {leg.distance_cm:.0f}cm in {leg.seconds:.1f}s "
                        f"(max step: {leg.max_step_cm:.0f}cm)"
                    )
                lines.append("")

            if result.expect:
                lines.append("═══ Expectations ═══")
                for exp in result.expect:
                    label = exp.expect if isinstance(exp.expect, str) else json.dumps(exp.expect)
                    lines.append(f"  {'✓' if exp.ok else '✕'} {label}  (observed: {exp.observed})")
                lines.append("")

            if result.failures:
                lines.append("═══ Failures ═══")
                for f in result.failures:
                    lines.append(f"  • {f}")

            self._detail_text.setPlainText("\n".join(lines))

    @Slot()
    def _on_launch(self) -> None:
        import os
        if not self._current_project:
            if "PYTEST_CURRENT_TEST" not in os.environ:
                QMessageBox.information(
                    self,
                    "No Game Selected",
                    "Please select a game first from the Games or Design view before launching.",
                )
            return

        exe = self._get_packaged_exe()
        if not exe and "PYTEST_CURRENT_TEST" not in os.environ:
            reply = QMessageBox.question(
                self,
                "Packaged Build Not Found",
                f"No packaged game executable was found for '{self._current_project}'.\n\n"
                f"Actionable Guidance:\n"
                f"1. A game must be packaged into a Windows executable before playing.\n"
                f"2. Run the Forge build pipeline (including the 'package' step) from the Build View.\n\n"
                f"Would you like to switch to the Build View and start building now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.buildRequested.emit(self._current_project)
            return

        self.launchRequested.emit(self._current_project)
