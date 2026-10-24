"""GameForge IDE — Direct ToolGateway wrapper for native desktop use."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _ToolRunnable(QRunnable):
    """QRunnable that executes a single tool and emits the result."""

    class _Signals(QObject):
        finished = Signal(str, dict)  # (tool_name, result)

    def __init__(self, gateway, name: str, arguments: Dict[str, Any], parent: QObject | None = None) -> None:
        super().__init__()
        self.signals = _ToolRunnable._Signals(parent)
        self._gateway = gateway
        self._name = name
        self._arguments = arguments

    @Slot()
    def run(self) -> None:
        result = self._gateway.execute_tool(self._name, self._arguments)
        self.signals.finished.emit(self._name, result)


class ToolService(QObject):
    """Thin wrapper around ToolGateway for direct in-process tool execution.

    Tools are dispatched to QThreadPool workers so the UI thread is never
    blocked by filesystem or subprocess operations.
    """

    tool_result = Signal(str, dict)  # (tool_name, result)

    def __init__(self, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.workspace_root = workspace_root
        self._pool = QThreadPool.globalInstance()
        self._gateway = None

    def set_workspace(self, new_workspace: Path) -> None:
        """Switch active workspace directory and recreate ToolGateway."""
        self.workspace_root = Path(new_workspace).resolve()
        self._gateway = None


    def _ensure_gateway(self):
        if self._gateway is not None:
            return
        from ...backend.tools.gateway import ToolGateway
        self._gateway = ToolGateway(self.workspace_root)

    def execute(self, name: str, arguments: Dict[str, Any] | None = None) -> None:
        """Execute a tool asynchronously; result emitted via tool_result signal."""
        self._ensure_gateway()
        runnable = _ToolRunnable(self._gateway, name, arguments or {}, parent=self)
        runnable.signals.finished.connect(self.tool_result)
        self._pool.start(runnable)

    def execute_sync(
        self,
        name: str,
        arguments: Dict[str, Any] | None = None,
        *,
        approval_granted: bool = False,
    ) -> Dict[str, Any]:
        """Execute a tool synchronously (call from non-UI threads only)."""
        self._ensure_gateway()
        return self._gateway.execute_tool(
            name, arguments or {}, approval_granted=approval_granted
        )

    def execute_approved_sync(
        self, name: str, arguments: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Execute after a UI action that explicitly approves this operation."""
        return self.execute_sync(name, arguments, approval_granted=True)

    @property
    def gateway(self):
        self._ensure_gateway()
        return self._gateway
