"""Runs one user-approved action off the UI thread and streams its progress.

This is the trusted approval path from the Master Blueprint: only a UI event bound to an
approval ID can move a pending action to APPROVED and execute it. Model text cannot.
Moved onto JobManager + Forge in P2 WI-2.8.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from ...backend.tools.gateway import ToolGateway
from ...core.jobs import JobHandle, JobManager, default_job_manager


class ActionRunner(QObject):
    """Owns execution of approved actions using JobManager and Forge."""

    progress = Signal(str, str, dict)  # (approval_id, kind, data)
    finished = Signal(str, dict)       # (approval_id, result)

    def __init__(
        self,
        workspace_root: Path,
        job_manager: Optional[JobManager] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root).resolve()
        self.job_manager = job_manager or default_job_manager()
        self._handles: Dict[str, JobHandle] = {}
        self._cancel_events: Dict[str, threading.Event] = {}

    def is_running(self, approval_id: str) -> bool:
        handle = self._handles.get(approval_id)
        return handle is not None and not handle.done()

    def approve(self, approval_id: str) -> bool:
        if self.is_running(approval_id):
            return False

        cancel_ev = threading.Event()
        self._cancel_events[approval_id] = cancel_ev

        def _worker_fn() -> None:
            gateway = ToolGateway(self._workspace_root)
            store = gateway.game_tools.approvals
            rec = store.transition(approval_id, "APPROVED")
            if rec is None:
                self.finished.emit(
                    approval_id,
                    {"status": "BLOCKED", "error": "approval is no longer pending (already used or rejected)"},
                )
                return

            if rec.get("plan_id"):
                self.finished.emit(
                    approval_id,
                    {
                        "status": "SUCCESS",
                        "approval_id": approval_id,
                        "plan_id": rec["plan_id"],
                        "message": "Approved — resume the plan in Mission Control → Execution Plan.",
                    },
                )
                return

            try:
                tool = rec.get("tool")
                args = rec.get("args", {})
                if tool == "forge_run":
                    from ...forge.store import RunStore
                    from ...forge.executor import ForgeExecutor
                    from ...forge.handlers import HANDLERS
                    from ...core.events import default_bus

                    pdir = Path(args["project_dir"]) if args.get("project_dir") else None
                    rstore = RunStore(project_dir=pdir, workspace_dir=self._workspace_root)
                    state = rstore.load(args["run_id"])
                    if state is None:
                        result = {"status": "ERROR", "error": f"run {args['run_id']} not found"}
                    else:
                        state.approvals["run"] = approval_id
                        bus = default_bus()

                        def _on_forge(topic: str, ev: Dict[str, Any]) -> None:
                            self.progress.emit(approval_id, ev.get("kind", "forge"), ev)

                        unsub = bus.subscribe("forge", _on_forge)
                        try:
                            executor = ForgeExecutor(HANDLERS, bus=bus)
                            state = executor.run(state, rstore)
                        finally:
                            unsub()
                        ok = state.status == "DONE"
                        result = {"status": "SUCCESS" if ok else state.status, "run_id": state.run.run_id}

                elif tool == "create_game":
                    gds_or_params = args.get("gds") or args.get("params") or args
                    result = gateway.game_tools.create_game(
                        gds_or_params,
                        package=args.get("package", True),
                        on_event=lambda kind, data: self.progress.emit(approval_id, kind, data),
                        cancel_event=cancel_ev,
                    )
                elif tool == "create_game_freeform":
                    result = gateway.game_tools.create_game_freeform(
                        args["prompt"],
                        args.get("title"),
                        on_event=lambda kind, data: self.progress.emit(approval_id, kind, data),
                        cancel_event=cancel_ev,
                    )
                else:
                    result = gateway.execute_tool(tool, args, approval_granted=True)
            except Exception as exc:
                result = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

            ok = result.get("status") == "SUCCESS"
            store.transition(
                approval_id,
                "DONE" if ok else "FAILED",
                {k: result.get(k) for k in ("status", "report_path", "failed_stage", "exe", "error")},
            )
            result["approval_id"] = approval_id
            self.finished.emit(approval_id, result)

        handle = self.job_manager.submit(
            _worker_fn,
            name=f"action_{approval_id}",
            cancel_event=cancel_ev,
        )
        self._handles[approval_id] = handle
        return True

    def cancel(self, approval_id: str) -> bool:
        ev = self._cancel_events.get(approval_id)
        if ev is not None:
            ev.set()
        handle = self._handles.get(approval_id)
        if handle is not None:
            handle.cancel()
            return True
        return False

    def reject(self, approval_id: str) -> Optional[Dict[str, Any]]:
        return ToolGateway(self._workspace_root).game_tools.approvals.transition(approval_id, "REJECTED")

    def shutdown(self) -> None:
        for ev in self._cancel_events.values():
            ev.set()
        for h in self._handles.values():
            h.cancel()
