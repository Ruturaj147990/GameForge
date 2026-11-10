"""GameForge IDE — QThread-based Agent Service.

Bridges the synchronous/async AgentRuntime to PySide6's Qt signal system,
running inference in a background worker thread so the UI never blocks.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication


class _AgentWorker(QObject):
    """Runs the agent loop in a dedicated QThread.

    Emits Qt signals for every event yielded by AgentRuntime so the main
    thread can update widgets safely.
    """

    token_received = Signal(str)           # incremental token text
    status_changed = Signal(str, dict)     # (status_label, metadata)
    plan_received = Signal(dict)           # structured PlanArtifact payload
    tool_called = Signal(str, dict)        # (tool_name, args)
    tool_result = Signal(str, dict)        # (tool_name, result)
    file_changed = Signal(str, dict)       # (content_or_path, metadata)
    diff_pending = Signal(str, dict)       # (diff_id, metadata)
    context_usage_updated = Signal(object) # ContextUsageReport payload
    error_occurred = Signal(str)           # error message
    task_done = Signal(str)                # final full text

    def __init__(
        self,
        workspace_root: Path,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.workspace_root = workspace_root
        self._session_id: Optional[str] = None
        self._prompt: str = ""
        self._resume_diff_id: Optional[str] = None
        self._resume_approval_id: Optional[str] = None
        self._resume_tool_result: Dict[str, Any] = {}
        self._resume_tool_name: Optional[str] = None
        self._resume_approved: bool = True
        self._stop_flag = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        # Lazy imports to avoid loading heavy deps until first use
        self._lock = threading.RLock()
        self._runtime = None
        self._session_manager = None
        self._router = None
        self._projects_service = None

    def attach_projects_service(self, projects_service: Any) -> None:
        """Connect to shared ProjectsService to ground active project context."""
        self._projects_service = projects_service
        if self._runtime is not None:
            self._runtime.projects_service = projects_service

    def _ensure_runtime(self) -> None:
        with self._lock:
            if self._runtime is not None:
                return
            from ...backend.agent.runtime import AgentRuntime
            from ...backend.providers.router import ModelRouter
            from ...backend.session_manager import SessionManager

            self._session_manager = SessionManager(self.workspace_root)
            self._router = ModelRouter()
            self._runtime = AgentRuntime(
                workspace_root=self.workspace_root,
                session_manager=self._session_manager,
                model_router=self._router,
                studio_mode=False,
                projects_service=self._projects_service,
            )

    def set_task(self, session_id: str, prompt: str) -> None:
        self._session_id = session_id
        self._prompt = prompt
        self._resume_diff_id = None
        self._resume_approval_id = None
        self._resume_tool_result = {}
        self._resume_tool_name = None
        self._resume_approved = True
        self._stop_flag.clear()

    def set_resume_task(self, session_id: str, diff_id: str, approved: bool = True) -> None:
        self._session_id = session_id
        self._resume_diff_id = diff_id
        self._resume_approval_id = None
        self._resume_tool_result = {}
        self._resume_tool_name = None
        self._resume_approved = approved
        self._stop_flag.clear()

    def set_resume_approval_task(
        self,
        session_id: str,
        approval_id: str,
        tool_result: Dict[str, Any],
        approved: bool = True,
        tool_name: Optional[str] = None,
    ) -> None:
        self._session_id = session_id
        self._resume_diff_id = None
        self._resume_approval_id = approval_id
        self._resume_tool_result = tool_result or {}
        self._resume_tool_name = tool_name
        self._resume_approved = approved
        self._stop_flag.clear()

    @Slot()
    def run(self) -> None:  # noqa: D102
        if self._stop_flag.is_set():
            return
        try:
            self._ensure_runtime()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                self._task = loop.create_task(self._stream())
                loop.run_until_complete(self._task)
            except asyncio.CancelledError:
                pass
            finally:
                self._loop = None
                self._task = None
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                try:
                    loop.run_until_complete(loop.shutdown_default_executor())
                except Exception:
                    pass
                loop.close()
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    async def _stream(self) -> None:
        def _emit_safe(sig: Any, *args: Any) -> None:
            try:
                sig.emit(*args)
            except (RuntimeError, Exception):
                pass

        full_text = ""
        if self._stop_flag.is_set():
            print("[GameForge Agent] Task cancelled before stream start.", flush=True)
            _emit_safe(self.task_done, "[Cancelled by user]")
            return
        if self._resume_diff_id is not None:
            stream_gen = self._runtime.resume_task_after_diff(
                self._session_id, self._resume_diff_id, approved=self._resume_approved
            )
            self._resume_diff_id = None
        elif self._resume_approval_id is not None:
            stream_gen = self._runtime.resume_task_after_approval(
                self._session_id,
                self._resume_approval_id,
                self._resume_tool_result,
                approved=self._resume_approved,
                tool_name=self._resume_tool_name,
            )
            self._resume_approval_id = None
            self._resume_tool_result = {}
            self._resume_tool_name = None
        else:
            stream_gen = self._runtime.execute_task_stream(
                self._session_id, self._prompt
            )
        try:
            print(f"\n[GameForge Agent] Stream started for session {self._session_id}...", flush=True)
            async for event in stream_gen:
                if self._stop_flag.is_set():
                    print("[GameForge Agent] Task cancelled by user.", flush=True)
                    _emit_safe(self.task_done, full_text or "[Cancelled by user]")
                    return
                etype = event.event_type
                if etype == "token":
                    full_text += event.content
                    _emit_safe(self.token_received, event.content)
                elif etype == "status":
                    print(f"[GameForge Agent Status] {event.content}", flush=True)
                    _emit_safe(self.status_changed, event.content, event.metadata)
                elif etype == "plan":
                    print(f"[GameForge Agent Plan] Plan event received", flush=True)
                    plan_data = event.metadata.get("plan") or event.metadata
                    _emit_safe(self.plan_received, plan_data if isinstance(plan_data, dict) else {"content": event.content})
                elif etype == "context_usage":
                    report = event.metadata.get("report") if isinstance(event.metadata, dict) else None
                    if report is not None:
                        _emit_safe(self.context_usage_updated, report)
                elif etype == "tool_call":
                    tool = event.metadata.get("tool", "")
                    args = event.metadata.get("args", {})
                    print(f"[GameForge Agent Tool] >>> Calling `{tool}` with args: {args}", flush=True)
                    _emit_safe(self.tool_called, tool, args)
                elif etype == "tool_result":
                    tool = event.metadata.get("tool", "")
                    res = event.metadata.get("result", {})
                    status = res.get("status", "SUCCESS") if isinstance(res, dict) else "OK"
                    print(f"[GameForge Agent Tool] <<< `{tool}` returned status: {status}", flush=True)
                    _emit_safe(self.tool_result, tool, res)
                elif etype == "file_changed":
                    print(f"[GameForge Agent FileChanged] {event.content}", flush=True)
                    _emit_safe(self.file_changed, event.content, event.metadata)
                elif etype == "diff_pending":
                    print(f"[GameForge Agent Diff] Diff pending: {event.metadata.get('diff_id', '')}", flush=True)
                    _emit_safe(
                        self.diff_pending,
                        event.metadata.get("diff_id", ""), event.metadata
                    )
                elif etype == "error":
                    print(f"[GameForge Agent Error] {event.content}", flush=True)
                    _emit_safe(self.error_occurred, event.content)
                    return
                elif etype == "done":
                    print(f"[GameForge Agent Done] Task turn complete. ({len(full_text)} chars generated)", flush=True)
                    _emit_safe(self.task_done, full_text or event.content)
                    if self._session_id:
                        try:
                            usage = self.get_context_usage(self._session_id)
                            if usage:
                                _emit_safe(self.context_usage_updated, usage)
                        except Exception:
                            pass
                    return
            if not self._stop_flag.is_set():
                print(f"[GameForge Agent Done] Stream finished. ({len(full_text)} chars)", flush=True)
                _emit_safe(self.task_done, full_text)
                if self._session_id:
                    try:
                        usage = self.get_context_usage(self._session_id)
                        if usage:
                            _emit_safe(self.context_usage_updated, usage)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            print("[GameForge Agent] Task cancelled.", flush=True)
            _emit_safe(self.task_done, full_text or "[Cancelled by user]")
            return
        except Exception as exc:
            print(f"[GameForge Agent Error] Stream exception: {exc}", flush=True)
            _emit_safe(self.error_occurred, str(exc))
            return
        finally:
            if hasattr(stream_gen, "aclose"):
                try:
                    await stream_gen.aclose()
                except Exception:
                    pass


    def stop(self) -> None:
        self._stop_flag.set()
        # Propagate to the runtime so the in-flight model request is aborted (the provider's
        # streaming reader closes the HTTP connection) instead of only being ignored when the
        # next event arrives. cancel_task() is thread-safe.
        runtime = getattr(self, "_runtime", None)
        session_id = getattr(self, "_session_id", None)
        if runtime is not None and session_id and hasattr(runtime, "cancel_task"):
            try:
                runtime.cancel_task(session_id)
            except Exception:
                pass
        loop = getattr(self, "_loop", None)
        task = getattr(self, "_task", None)
        if loop and not loop.is_closed() and task and not task.done():
            loop.call_soon_threadsafe(task.cancel)

    # Public session helpers ---------------------------------------------------

    def create_session(
        self,
        name: str = "Chat Session",
        model_name: Optional[str] = None,
        provider_type: str = "ollama",
        project_dir: Optional[Union[str, Path]] = None,
        **kwargs,
    ) -> str:
        """Creates a new session and returns its ID."""
        with self._lock:
            self._ensure_runtime()
            if not project_dir and hasattr(self, "_projects_service") and self._projects_service:
                project_dir = getattr(self._projects_service, "active_project_dir", None)
            try:
                session = self._session_manager.create_session(
                    name=name, model_name=model_name, provider_type=provider_type, project_dir=project_dir, **kwargs
                )
            except TypeError:
                kwargs.pop("permissions_mode", None)
                session = self._session_manager.create_session(
                    name=name, model_name=model_name, provider_type=provider_type, project_dir=project_dir, **kwargs
                )
            return session.session_id

    def set_session_mode(
        self,
        session_id: str,
        task_mode: Optional[Any] = None,
        autonomy_profile: Optional[Any] = None,
        permissions_mode: Optional[Any] = None,
        **kwargs,
    ) -> bool:
        """Update task_mode, autonomy_profile, and/or permissions_mode on an existing session."""
        with self._lock:
            self._ensure_runtime()
            call_kwargs = {}
            if task_mode is not None:
                call_kwargs["task_mode"] = task_mode
            if autonomy_profile is not None:
                call_kwargs["autonomy_profile"] = autonomy_profile
            if permissions_mode is not None:
                call_kwargs["permissions_mode"] = permissions_mode
            try:
                return self._session_manager.set_session_mode(session_id, **call_kwargs)
            except TypeError:
                call_kwargs.pop("permissions_mode", None)
                return self._session_manager.set_session_mode(session_id, **call_kwargs)

    def get_context_usage(self, session_id: str) -> Optional[Any]:
        """Query runtime or context manager for active context usage report."""
        with self._lock:
            self._ensure_runtime()
            if hasattr(self._runtime, "get_context_usage"):
                try:
                    model_name = None
                    if self._session_manager:
                        sess = self._session_manager.get_session(session_id)
                        if sess:
                            model_name = sess.model_name
                    return self._runtime.get_context_usage(session_id, model_id=model_name)
                except Exception:
                    pass
            if hasattr(self._runtime, "context_manager") and hasattr(self._runtime.context_manager, "get_context_usage"):
                try:
                    return self._runtime.context_manager.get_context_usage(session_id)
                except TypeError:
                    try:
                        return self._runtime.context_manager.get_context_usage()
                    except Exception:
                        pass
                except Exception:
                    pass
            return None

    def get_session(self, session_id: str):
        """Retrieve a session by its ID."""
        with self._lock:
            self._ensure_runtime()
            return self._session_manager.get_session(session_id)

    def set_session_model(self, session_id: str, model_name: str, provider_type: Optional[str] = None) -> bool:
        """Update model for an existing session."""
        with self._lock:
            self._ensure_runtime()
            return self._session_manager.set_session_model(session_id, model_name, provider_type=provider_type)

    def set_session_project_dir(self, session_id: str, project_dir: Optional[Union[str, Path]]) -> bool:
        """Update active project directory on an existing session."""
        with self._lock:
            self._ensure_runtime()
            return self._session_manager.set_session_project_dir(session_id, project_dir)

    def list_models(self) -> list:
        """Returns list of available model dicts."""
        with self._lock:
            self._ensure_runtime()
            return [m.model_dump() for m in self._router.list_all_models()]

    @property
    def session_manager(self):
        with self._lock:
            self._ensure_runtime()
            return self._session_manager


class AgentService(QObject):
    """Public-facing service that manages the worker QThread lifecycle.

    Usage::
        service = AgentService(workspace_root)
        service.token_received.connect(my_slot)
        service.send(session_id, "Write a UE5 GameMode subclass")
    """

    # Mirror worker signals at service level for ergonomic connection
    token_received = Signal(str)
    status_changed = Signal(str, dict)
    plan_received = Signal(dict)
    tool_called = Signal(str, dict)
    tool_result = Signal(str, dict)
    file_changed = Signal(str, dict)
    diff_pending = Signal(str, dict)
    context_usage_updated = Signal(object)
    error_occurred = Signal(str)
    task_done = Signal(str)
    _trigger_run = Signal()

    def __init__(self, workspace_root: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.workspace_root = workspace_root

        self._thread = QThread()
        self._worker = _AgentWorker(workspace_root)
        self._worker.moveToThread(self._thread)

        # Wire worker → service signals
        self._worker.token_received.connect(self.token_received)
        self._worker.status_changed.connect(self.status_changed)
        self._worker.plan_received.connect(self.plan_received)
        self._worker.tool_called.connect(self.tool_called)
        self._worker.tool_result.connect(self.tool_result)
        self._worker.file_changed.connect(self.file_changed)
        self._worker.diff_pending.connect(self.diff_pending)
        self._worker.context_usage_updated.connect(self.context_usage_updated)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.task_done.connect(self.task_done)
        self._trigger_run.connect(self._worker.run)

        # Start the thread (the worker runs tasks on demand, not on start)
        self._thread.start()

        self._busy = False
        self._stopping = False
        self.task_done.connect(self._on_done)
        self.error_occurred.connect(self._on_done_err)

    def _on_done(self, _: str) -> None:
        self._busy = False
        self._stopping = False

    def _on_done_err(self, _: str) -> None:
        self._busy = False
        self._stopping = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    @is_busy.setter
    def is_busy(self, value: bool) -> None:
        self._busy = bool(value)

    @property
    def is_stopping(self) -> bool:
        return self._stopping

    def send(self, session_id: str, prompt: str) -> bool:
        """Dispatch a prompt to the agent.  Returns False if busy."""
        if self._busy:
            return False
        self._busy = True
        self._worker.set_task(session_id, prompt)
        self._trigger_run.emit()
        return True

    def resume_after_diff(self, session_id: str, diff_id: str, approved: bool = True) -> bool:
        """Resume a suspended agent task following a diff approval or rejection."""
        if self._busy:
            return False
        self._busy = True
        self._worker.set_resume_task(session_id, diff_id, approved=approved)
        self._trigger_run.emit()
        return True

    def resume_after_approval(
        self,
        session_id: str,
        approval_id: str,
        tool_result: Dict[str, Any],
        approved: bool = True,
        tool_name: Optional[str] = None,
    ) -> bool:
        """Resume a suspended agent task following user approval or rejection of a command/tool."""
        if self._busy:
            return False
        self._busy = True
        self._worker.set_resume_approval_task(
            session_id, approval_id, tool_result, approved=approved, tool_name=tool_name
        )
        self._trigger_run.emit()
        return True

    def attach_projects_service(self, projects_service: Any) -> None:
        """Connect to shared ProjectsService to ground active project context."""
        self._projects_service = projects_service
        if hasattr(self, "_worker") and self._worker:
            self._worker.attach_projects_service(projects_service)

    def stop(self) -> None:
        """Request cancellation; remain busy until the worker actually exits."""
        if not self._busy:
            return
        self._stopping = True
        self._worker.stop()

    def set_workspace(self, new_workspace: Path) -> None:
        """Switch active workspace directory and reset runtime state safely."""
        self.stop()
        if self._thread.isRunning() and self._busy:
            app = QApplication.instance()
            for _ in range(10):
                if not self._busy:
                    break
                if app:
                    app.processEvents()
                time.sleep(0.05)
        self.workspace_root = Path(new_workspace).resolve()
        with self._worker._lock:
            self._worker.workspace_root = self.workspace_root
            self._worker._runtime = None
            self._worker._session_manager = None
            self._worker._router = None

    def create_session(self, **kwargs) -> str:
        return self._worker.create_session(**kwargs)

    def set_session_mode(
        self,
        session_id: str,
        task_mode: Optional[Any] = None,
        autonomy_profile: Optional[Any] = None,
        permissions_mode: Optional[Any] = None,
        **kwargs,
    ) -> bool:
        return self._worker.set_session_mode(
            session_id,
            task_mode=task_mode,
            autonomy_profile=autonomy_profile,
            permissions_mode=permissions_mode,
            **kwargs,
        )

    def get_context_usage(self, session_id: str) -> Optional[Any]:
        return self._worker.get_context_usage(session_id)

    def get_session(self, session_id: str):
        return self._worker.get_session(session_id)

    def set_session_model(self, session_id: str, model_name: str, provider_type: Optional[str] = None) -> bool:
        return self._worker.set_session_model(session_id, model_name, provider_type=provider_type)

    def set_session_project_dir(self, session_id: str, project_dir: Optional[Union[str, Path]]) -> bool:
        return self._worker.set_session_project_dir(session_id, project_dir=project_dir)

    def list_models(self) -> list:
        return self._worker.list_models()

    @property
    def session_manager(self):
        return self._worker.session_manager

    def shutdown(self) -> None:
        """Gracefully shut down background thread with cooperative drainage."""
        self._busy = False
        self._stopping = True
        if hasattr(self, "_worker") and self._worker:
            self._worker.stop()
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(3000):
                # Cooperative drainage with UI event processing instead of dangerous terminate()
                app = QApplication.instance()
                for _ in range(20):
                    if self._thread.wait(100):
                        break
                    if app:
                        app.processEvents()
        self._busy = False
        self._stopping = False

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
