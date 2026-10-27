"""Runs one user-approved action off the UI thread and streams its progress.

This is the trusted approval path from the Master Blueprint: only a UI event bound to an
approval ID can move a pending action to APPROVED and execute it. Model text cannot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal

from ...backend.tools.gateway import ToolGateway


class _Worker(QObject):
    progress = Signal(str, dict)   # (event kind, data)
    finished = Signal(dict)        # final result

    def __init__(self, workspace_root: Path, approval_id: str) -> None:
        super().__init__()
        self._workspace_root = workspace_root
        self._approval_id = approval_id
        import threading
        self.cancel_event = threading.Event()

    def run(self) -> None:
        gateway = ToolGateway(self._workspace_root)
        store = gateway.game_tools.approvals
        rec = store.transition(self._approval_id, "APPROVED")
        if rec is None:
            self.finished.emit({"status": "BLOCKED", "error": "approval is no longer pending (already used or rejected)"})
            return
        try:
            if rec["tool"] == "create_game":
                result = gateway.game_tools.create_game(
                    rec["args"]["params"], package=rec["args"].get("package", True),
                    on_event=lambda kind, data: self.progress.emit(kind, data), cancel_event=self.cancel_event)
            elif rec["tool"] == "create_game_freeform":
                result = gateway.game_tools.create_game_freeform(
                    rec["args"]["prompt"], rec["args"].get("title"),
                    on_event=lambda kind, data: self.progress.emit(kind, data), cancel_event=self.cancel_event)
            else:
                result = gateway.execute_tool(rec["tool"], rec["args"], approval_granted=True)
        except Exception as exc:  # report, never crash the UI
            result = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        ok = result.get("status") == "SUCCESS"
        store.transition(self._approval_id, "DONE" if ok else "FAILED",
                         {k: result.get(k) for k in ("status", "report_path", "failed_stage", "exe", "error")})
        result["approval_id"] = self._approval_id
        self.finished.emit(result)


class ActionRunner(QObject):
    """Owns one worker thread per approved action."""

    progress = Signal(str, str, dict)  # (approval_id, kind, data)
    finished = Signal(str, dict)       # (approval_id, result)

    def __init__(self, workspace_root: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root)
        self._threads: Dict[str, QThread] = {}
        self._workers: Dict[str, _Worker] = {}

    def is_running(self, approval_id: str) -> bool:
        return approval_id in self._threads

    def approve(self, approval_id: str) -> bool:
        if approval_id in self._threads:
            return False
        thread = QThread(self)
        worker = _Worker(self._workspace_root, approval_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda kind, data, aid=approval_id: self.progress.emit(aid, kind, data))
        worker.finished.connect(lambda res, aid=approval_id: self._on_finished(aid, res))
        self._threads[approval_id] = thread
        self._workers[approval_id] = worker
        thread.start()
        return True

    def cancel(self, approval_id: str) -> bool:
        worker = self._workers.get(approval_id)
        if worker is None:
            return False
        worker.cancel_event.set()  # the toolchain kills the running process tree
        return True

    def reject(self, approval_id: str) -> Optional[Dict[str, Any]]:
        return ToolGateway(self._workspace_root).game_tools.approvals.transition(approval_id, "REJECTED")

    def _on_finished(self, approval_id: str, result: Dict[str, Any]) -> None:
        thread = self._threads.pop(approval_id, None)
        self._workers.pop(approval_id, None)
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self.finished.emit(approval_id, result)

    def shutdown(self) -> None:
        for worker in list(self._workers.values()):
            worker.cancel_event.set()
        for thread in list(self._threads.values()):
            thread.quit()
            thread.wait(2000)
