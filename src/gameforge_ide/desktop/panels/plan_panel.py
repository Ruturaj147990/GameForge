"""Execution Plan Panel for GameForge IDE.

Visualizes structured DAG plans, task dependencies, live state transitions,
acceptance criteria verification, tool activity, diagnostics, and approvals.
Complies with GameForge Master Blueprint and Milestone 1 specification.
"""

from __future__ import annotations

import html as html_lib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...backend.agent.plan_executor import PlanEvent
from ...backend.agent.task_plan import TaskNode, TaskPlan
from ..styles import tokens

STATUS_COLORS = {
    "PLANNED": tokens.TEXT_MUTED,
    "READY": tokens.ACCENT_HOVER,
    "RUNNING": tokens.ACCENT_PRIMARY,
    "WAITING_APPROVAL": tokens.ACCENT_WARNING,
    "VERIFYING": tokens.ACCENT_HOVER,
    "REPAIRING": tokens.ACCENT_WARNING,
    "COMPLETED": tokens.ACCENT_SUCCESS,
    "BLOCKED": tokens.ACCENT_ERROR,
    "FAILED": tokens.ACCENT_ERROR,
    "CANCELLED": tokens.TEXT_MUTED,
}


class PlanPanel(QWidget):
    """Panel displaying active execution plan, DAG tasks, acceptance criteria, and live state."""

    run_requested = Signal(object)
    cancel_requested = Signal()
    approval_review_requested = Signal(object)

    def __init__(self, workspace_root: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("planPanel")
        self.setAccessibleName("Execution Plan Panel")
        self._workspace = Path(workspace_root).resolve()
        self._active_plan: Optional[TaskPlan] = None
        self._runner = None  # PlanRunner, created on first Run/Resume

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header: Goal & Status
        header_card = QFrame()
        header_card.setObjectName("planHeaderCard")
        header_card.setStyleSheet(
            f"QFrame#planHeaderCard {{ background-color: {tokens.BG_SURFACE}; border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 6px; }}"
        )
        hl = QVBoxLayout(header_card)
        hl.setContentsMargins(8, 8, 8, 8)
        hl.setSpacing(6)

        top_row = QHBoxLayout()
        self._lbl_plan_id = QLabel("No active plan")
        self._lbl_plan_id.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: bold; font-size: {tokens.FONT_BODY}px;")
        self._lbl_status = QLabel("IDLE")
        self._lbl_status.setStyleSheet(
            f"background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_MUTED}; border: 1px solid {tokens.BORDER}; padding: 2px 8px; border-radius: {tokens.RADIUS}px; font-weight: bold;"
        )

        top_row.addWidget(self._lbl_plan_id)
        top_row.addStretch(1)
        top_row.addWidget(self._lbl_status)
        hl.addLayout(top_row)

        self._lbl_goal = QLabel("Enter a task or slash command (/plan) to generate an execution plan.")
        self._lbl_goal.setWordWrap(True)
        self._lbl_goal.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        hl.addWidget(self._lbl_goal)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(16)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background-color: {tokens.BG_PANEL}; border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; text-align: center; color: {tokens.TEXT_PRIMARY}; font-size: 10px; font-weight: bold; }}"
            f"QProgressBar::chunk {{ background-color: {tokens.ACCENT_PRIMARY}; border-radius: 4px; }}"
        )
        hl.addWidget(self._progress)

        # Controls row
        btn_row = QHBoxLayout()
        self._btn_resume = QPushButton("▶ Run / Resume")
        self._btn_resume.setAccessibleName("Run or resume plan")
        self._btn_resume.setCursor(Qt.PointingHandCursor)
        self._btn_resume.setStyleSheet(
            f"QPushButton {{ background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY}; border: none; border-radius: {tokens.RADIUS}px; padding: 4px {tokens.SPACE_MD}px; font-weight: 600; font-size: {tokens.FONT_BODY_SM}px; }}"
            f"QPushButton:hover {{ background-color: {tokens.ACCENT_HOVER}; }}"
            f"QPushButton:disabled {{ background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_MUTED}; }}"
        )
        self._btn_resume.clicked.connect(self._on_run_clicked)

        self._btn_cancel = QPushButton("⏹ Cancel")
        self._btn_cancel.setAccessibleName("Cancel plan")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_ERROR}; border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px; }}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)

        self._btn_refresh = QPushButton("⟳ Refresh")
        self._btn_refresh.setAccessibleName("Refresh plan from disk")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton {{ background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY}; border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px; }}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        self._btn_refresh.clicked.connect(self.refresh_from_disk)

        btn_row.addWidget(self._btn_resume)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch(1)
        hl.addLayout(btn_row)

        layout.addWidget(header_card)

        # Splitter: Task Tree (top) and Task Detail Inspector (bottom)
        splitter = QSplitter(Qt.Vertical)

        # Task Tree
        self._tree = QTreeWidget()
        self._tree.setObjectName("planTaskTree")
        self._tree.setAccessibleName("Plan tasks hierarchy")
        self._tree.setHeaderLabels(["Status", "ID", "Task Title", "Type", "Prerequisites", "Tools"])
        self._tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self._tree.header().resizeSection(0, 120)
        self._tree.header().resizeSection(1, 90)
        self._tree.header().resizeSection(2, 220)
        self._tree.header().resizeSection(3, 80)
        self._tree.header().resizeSection(4, 110)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background-color: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY}; border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; }}"
            f"QTreeWidget::item:selected {{ background-color: {tokens.BG_ACTIVE}; color: {tokens.TEXT_PRIMARY}; }}"
            f"QTreeWidget:focus {{ border: 1px solid {tokens.BORDER_FOCUS}; }}"
            f"QHeaderView::section {{ background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_SECONDARY}; border: 1px solid {tokens.BORDER}; padding: 4px; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600; }}"
        )
        self._tree.itemSelectionChanged.connect(self._on_task_selected)
        splitter.addWidget(self._tree)

        # Task Inspector
        detail_widget = QWidget()
        dl = QVBoxLayout(detail_widget)
        dl.setContentsMargins(0, 4, 0, 0)
        dl.setSpacing(4)

        lbl_insp = QLabel("Task Details & Acceptance Evidence:")
        lbl_insp.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-weight: 600; font-size: {tokens.FONT_BODY_SM}px;")
        dl.addWidget(lbl_insp)

        self._detail_browser = QTextBrowser()
        self._detail_browser.setObjectName("planDetailBrowser")
        self._detail_browser.setAccessibleName("Task details inspector")
        self._detail_browser.setOpenExternalLinks(False)
        self._detail_browser.setStyleSheet(
            f"QTextBrowser {{ background-color: {tokens.BG_PANEL}; color: {tokens.TEXT_PRIMARY}; border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; padding: 6px; font-family: Consolas, monospace; font-size: 12px; }}"
            f"QTextBrowser:focus {{ border: 1px solid {tokens.BORDER_FOCUS}; }}"
        )
        dl.addWidget(self._detail_browser)
        splitter.addWidget(detail_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    def set_plan(self, plan: TaskPlan) -> None:
        """Sets the active TaskPlan and populates the view."""
        self._active_plan = plan
        self._lbl_plan_id.setText(f"Plan: {plan.plan_id}")
        self._lbl_goal.setText(plan.goal)
        self._update_status_badge(plan.status)
        self._populate_task_tree()

    def handle_plan_event(self, event: PlanEvent) -> None:
        """Handles a live PlanEvent from TaskPlanExecutor."""
        if not self._active_plan or self._active_plan.plan_id != event.plan_id:
            # Reload plan if mismatched
            loaded = TaskPlan.load_by_id(self._workspace, event.plan_id)
            if loaded:
                self.set_plan(loaded)
            return

        if event.status:
            if event.task_id and event.task_id in self._active_plan.tasks:
                task = self._active_plan.tasks[event.task_id]
                task.status = event.status
                self._update_tree_item(task)
            else:
                self._active_plan.status = event.status
                self._update_status_badge(event.status)

        self._update_progress()
        self._on_task_selected()

    def _update_status_badge(self, status: str) -> None:
        color = STATUS_COLORS.get(status, tokens.TEXT_MUTED)
        self._lbl_status.setText(status)
        self._lbl_status.setStyleSheet(
            f"background-color: {tokens.BG_PANEL}; color: {color}; border: 1px solid {color}; padding: 2px 8px; border-radius: {tokens.RADIUS}px; font-weight: bold;"
        )

    def _populate_task_tree(self) -> None:
        self._tree.clear()
        if not self._active_plan:
            return

        for task in self._active_plan.tasks.values():
            item = QTreeWidgetItem(self._tree)
            item.setData(0, Qt.UserRole, task.task_id)
            self._apply_item_data(item, task)

        self._update_progress()
        if self._tree.topLevelItemCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _update_tree_item(self, task: TaskNode) -> None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == task.task_id:
                self._apply_item_data(item, task)
                break

    def _apply_item_data(self, item: QTreeWidgetItem, task: TaskNode) -> None:
        color = STATUS_COLORS.get(task.status, tokens.TEXT_MUTED)
        item.setText(0, f"● {task.status}")
        item.setForeground(0, QColor(color))
        item.setText(1, task.task_id)
        item.setText(2, task.title)
        item.setText(3, task.task_type)
        item.setText(4, ", ".join(task.dependency_ids) or "–")
        item.setText(5, ", ".join(task.permitted_tools) or "–")

    def _update_progress(self) -> None:
        if not self._active_plan or not self._active_plan.tasks:
            self._progress.setValue(0)
            self._progress.setFormat("No tasks")
            return

        total = len(self._active_plan.tasks)
        completed = sum(1 for t in self._active_plan.tasks.values() if t.status == "COMPLETED")
        pct = int((completed / total) * 100)
        self._progress.setValue(pct)
        self._progress.setFormat(f"{completed} / {total} tasks ({pct}%)")

    @Slot()
    def _on_task_selected(self) -> None:
        items = self._tree.selectedItems()
        if not items or not self._active_plan:
            self._detail_browser.setHtml(f"<span style='color: {tokens.TEXT_MUTED};'>Select a task above to view details.</span>")
            return

        task_id = items[0].data(0, Qt.UserRole)
        task = self._active_plan.tasks.get(task_id)
        if not task:
            return

        color = STATUS_COLORS.get(task.status, tokens.TEXT_MUTED)
        esc = html_lib.escape
        html = [
            f"<h3 style='margin: 0; color: {tokens.TEXT_PRIMARY};'>{esc(str(task.title))} <span style='color: {color}; font-size: 12px;'>[{esc(str(task.status))}]</span></h3>",
            f"<p style='color: {tokens.TEXT_SECONDARY}; margin: 4px 0;'><b>Objective:</b> {esc(str(task.objective))}</p>",
            f"<p style='color: {tokens.TEXT_SECONDARY}; margin: 4px 0;'><b>Expected Result:</b> {esc(str(task.expected_result))}</p>",
            f"<p style='color: {tokens.TEXT_SECONDARY}; margin: 4px 0;'>Type: <code>{esc(str(task.task_type))}</code> | Reversibility: <code>{esc(str(task.reversibility))}</code> | Approval Required: <code>{esc(str(task.requires_approval))}</code></p>",
            f"<p style='color: {tokens.TEXT_SECONDARY}; margin: 4px 0;'>Permitted Tools: <code>{esc(', '.join(task.permitted_tools) or 'None')}</code></p>",
        ]

        if task.error_message:
            html.append(f"<div style='background: {tokens.BG_PANEL}; border: 1px solid {tokens.ACCENT_ERROR}; color: {tokens.ACCENT_ERROR}; padding: 6px; border-radius: {tokens.RADIUS}px; margin: 6px 0;'><b>Error/Blocker:</b> {esc(str(task.error_message))}</div>")

        if task.approval_id:
            html.append(f"<p style='color: {tokens.ACCENT_WARNING}; margin: 4px 0;'><b>Pending Approval ID:</b> <code>{esc(str(task.approval_id))}</code></p>")

        # Acceptance Criteria
        html.append(f"<h4 style='color: {tokens.TEXT_PRIMARY}; margin: 8px 0 4px 0;'>Acceptance Criteria & Evidence:</h4>")
        if task.acceptance:
            html.append("<ul style='margin: 0; padding-left: 20px;'>")
            for pred in task.acceptance:
                mark = f"<span style='color: {tokens.ACCENT_SUCCESS};'>✔ SATISFIED</span>" if pred.satisfied else f"<span style='color: {tokens.ACCENT_ERROR};'>✘ UNMET</span>"
                ev = f"<br/><span style='color: {tokens.TEXT_MUTED};'>Evidence: {esc(str(pred.evidence))}</span>" if pred.evidence else ""
                html.append(f"<li style='color: {tokens.TEXT_PRIMARY}; margin-bottom: 4px;'>{mark} <b>{esc(str(pred.predicate_type))}</b>(<code>{esc(str(pred.target))}</code>){ev}</li>")
            html.append("</ul>")
        else:
            html.append(f"<p style='color: {tokens.TEXT_MUTED};'>No explicit machine predicates attached.</p>")

        # Tool Call / Output
        if task.tool_call:
            html.append(f"<h4 style='color: {tokens.TEXT_PRIMARY}; margin: 8px 0 4px 0;'>Tool Call:</h4>")
            html.append(f"<pre style='background: {tokens.BG_SURFACE}; padding: 6px; border-radius: {tokens.RADIUS}px; color: {tokens.TEXT_PRIMARY};'>{esc(json.dumps(task.tool_call, indent=2))}</pre>")

        if task.evidence:
            html.append(f"<h4 style='color: {tokens.TEXT_PRIMARY}; margin: 8px 0 4px 0;'>Execution Observations:</h4>")
            for idx, ev in enumerate(task.evidence):
                if not isinstance(ev, dict):  # older task stores persisted plain-string observations
                    ev = {"attempt": idx + 1, "output": ev}
                html.append(f"<div style='background: {tokens.BG_SURFACE}; padding: 6px; border-radius: {tokens.RADIUS}px; margin-bottom: 4px; color: {tokens.TEXT_PRIMARY};'><b>Attempt {esc(str(ev.get('attempt')))}:</b><pre>{esc(json.dumps(ev.get('output', {}), indent=2, default=str)[:600])}</pre></div>")

        self._detail_browser.setHtml("".join(html))

    @Slot()
    def _on_run_clicked(self) -> None:
        if not self._active_plan:
            return
        if self._runner is None or self._runner.workspace_root != self._workspace:
            from ..services.plan_runner import PlanRunner
            self._runner = PlanRunner(self._workspace, self)
            self._runner.event.connect(self.handle_plan_event)
            self._runner.finished.connect(self._on_plan_finished)
        # The worker mutates its own deep copy; the panel's copy follows via PlanEvents.
        if self._runner.run(self._active_plan.model_copy(deep=True)):
            self._btn_resume.setEnabled(False)
        self.run_requested.emit(self._active_plan)

    @Slot(object)
    def _on_plan_finished(self, plan: TaskPlan) -> None:
        self._btn_resume.setEnabled(True)
        self.set_plan(plan)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
        self.cancel_requested.emit()

    @Slot()
    def refresh_from_disk(self) -> None:
        plans = TaskPlan.list_plans(self._workspace)
        if plans:
            self.set_plan(plans[0])
