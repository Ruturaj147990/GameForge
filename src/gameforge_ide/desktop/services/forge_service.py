"""ForgeService: Qt service bridging core.events.default_bus to Qt signals (AD-11)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QObject, Signal

from ...core.events import EventBus, default_bus
from ...forge.store import RunStore


class ForgeService(QObject):
    """Qt service that streams Forge events and tracks active/recent runs."""

    runEvent = Signal(dict)
    runListChanged = Signal()

    def __init__(
        self,
        workspace_root: Path,
        bus: Optional[EventBus] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve()
        self.bus = bus or default_bus()
        self.store = RunStore(project_dir=None, workspace_dir=self.workspace_root)
        self._unsub = self.bus.subscribe("forge", self._on_bus_event)

    def _on_bus_event(self, topic: str, event: Dict[str, Any]) -> None:
        # Re-emit on UI thread via Qt signal
        self.runEvent.emit(event)
        kind = event.get("kind")
        if kind in ("run_started", "run_finished"):
            self.runListChanged.emit()

    def active_runs(self) -> List[Dict[str, Any]]:
        index = self.store.get_runs_index()
        return [r for r in index if r.get("status") in ("PENDING", "RUNNING", "WAITING_APPROVAL")]

    def recent_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.store.get_runs_index()[:limit]

    def cancel_run(self, run_id: str) -> bool:
        """Cancel an active Forge run by run_id."""
        from ...forge.executor import ForgeExecutor
        return ForgeExecutor.cancel_run(run_id)

    def close(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
