"""The Execution Plan tab's Run/Resume/Cancel controls drive the real TaskPlanExecutor."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.agent.task_plan import TaskNode, TaskPlan
from src.gameforge_ide.backend.tools.game_tools import ApprovalStore


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _wait(qapp, predicate, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _read_plan(ws: Path, gated: bool) -> TaskPlan:
    (ws / "a.txt").write_text("a", encoding="utf-8")
    plan = TaskPlan(goal="panel run")
    plan.add_task(TaskNode(task_id="read", title="Read", objective="o", expected_result="r",
                           tool_call={"name": "read_file", "arguments": {"subpath": "a.txt"}}))
    if gated:
        plan.add_task(TaskNode(task_id="gate", title="Gate", objective="o", expected_result="r",
                               requires_approval=True, dependency_ids=["read"]))
    plan.save(ws)
    return plan


def test_run_button_executes_plan(qapp, tmp_path: Path):
    from src.gameforge_ide.desktop.panels.plan_panel import PlanPanel
    panel = PlanPanel(tmp_path)
    panel.set_plan(_read_plan(tmp_path, gated=False))
    panel._btn_resume.click()
    assert _wait(qapp, lambda: panel._runner is not None and not panel._runner.is_running()
                 and panel._active_plan.status == "COMPLETED")
    assert panel._active_plan.tasks["read"].status == "COMPLETED"
    assert TaskPlan.load_by_id(tmp_path, panel._active_plan.plan_id).status == "COMPLETED"


def test_plan_approval_releases_task_without_running_tool(qapp, tmp_path: Path):
    from src.gameforge_ide.desktop.panels.plan_panel import PlanPanel
    from src.gameforge_ide.desktop.services.action_runner import ActionRunner
    panel = PlanPanel(tmp_path)
    panel.set_plan(_read_plan(tmp_path, gated=True))
    panel._btn_resume.click()
    assert _wait(qapp, lambda: panel._active_plan.status == "WAITING_APPROVAL" and not panel._runner.is_running())
    approval_id = panel._active_plan.tasks["gate"].approval_id
    rec = ApprovalStore(tmp_path).get(approval_id)
    assert rec["plan_id"] == panel._active_plan.plan_id

    results = []
    runner = ActionRunner(tmp_path)
    runner.finished.connect(lambda aid, res: results.append(res))
    assert runner.approve(approval_id)
    assert _wait(qapp, lambda: bool(results))
    assert results[0]["plan_id"] == panel._active_plan.plan_id
    assert ApprovalStore(tmp_path).get(approval_id)["status"] == "APPROVED"

    panel._btn_resume.click()
    assert _wait(qapp, lambda: not panel._runner.is_running() and panel._active_plan.status == "COMPLETED")
