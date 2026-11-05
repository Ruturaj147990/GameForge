"""Runs or resumes a TaskPlan off the UI thread and streams its PlanEvents.

Approval-gated tasks pause the plan (WAITING_APPROVAL); the user approves them in the
chat or Mission Control, then clicks Resume. The runner never auto-approves.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from ...backend.agent.plan_executor import PlanEvent
from ...backend.agent.task_plan import TaskPlan
from ...forge.plan_adapter import run_plan_on_forge


class _Worker(QObject):
    event = Signal(object)     # PlanEvent
    finished = Signal(object)  # TaskPlan

    def __init__(self, workspace_root: Path, plan: TaskPlan) -> None:
        super().__init__()
        self.workspace_root = workspace_root
        self._plan = plan
        self._cancelled = threading.Event()

    def run(self) -> None:
        try:
            result = run_plan_on_forge(
                self._plan,
                self.workspace_root,
                auto_approve_all=False,
                on_event=self.event.emit,
            )
        except Exception as exc:  # report, never crash the UI
            self._plan.status = "FAILED"
            self._plan.metadata["runner_error"] = f"{type(exc).__name__}: {exc}"
            result = self._plan
        self.finished.emit(result)

    def cancel(self) -> None:
        self._cancelled.set()


class PlanRunner(QObject):
    """Owns at most one running plan."""

    event = Signal(object)     # PlanEvent
    finished = Signal(object)  # TaskPlan

    def __init__(self, workspace_root: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.workspace_root = Path(workspace_root)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._thread is not None

    def run(self, plan: TaskPlan) -> bool:
        with self._lock:
            if self._thread is not None:
                return False
            thread = QThread(self)
            worker = _Worker(self.workspace_root, plan)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.event.connect(self.event.emit)
            worker.finished.connect(self._on_finished)
            self._thread, self._worker = thread, worker
            thread.start()
            return True

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                from ...forge.executor import ForgeExecutor
                ForgeExecutor.cancel_run(self._worker._plan.plan_id)
            except Exception:
                pass

    def _on_finished(self, plan: TaskPlan) -> None:
        thread = self._thread
        self._thread, self._worker = None, None
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self.finished.emit(plan)

    def shutdown(self) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)


__all__ = ["PlanRunner", "PlanEvent"]
