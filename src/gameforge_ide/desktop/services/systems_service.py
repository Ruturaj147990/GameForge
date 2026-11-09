"""SystemsService: Qt service polling systems readiness on JobManager (WI-4.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from ...core.jobs import JobHandle, JobManager, default_job_manager
from ...core.systems import SystemsSnapshot, probe_all


class SystemsService(QObject):
    """Qt service that periodically probes systems on a background thread and emits snapshots."""

    snapshotChanged = Signal(object)

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        job_manager: Optional[JobManager] = None,
        parent: Optional[QObject] = None,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self.job_manager = job_manager or default_job_manager()
        self._last_snapshot: Optional[SystemsSnapshot] = None
        self._window_visible: bool = True
        self._window_minimized: bool = False
        self._is_probing: bool = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_now)
        self._update_interval()

        if auto_start:
            self._timer.start()
            self.refresh_now()

    def set_window_state(self, visible: bool, minimized: bool = False) -> None:
        """Adjust polling interval depending on window visibility and state."""
        self._window_visible = visible
        self._window_minimized = minimized
        self._update_interval()

    def _update_interval(self) -> None:
        if not self._window_visible or self._window_minimized:
            # 120s when minimized or hidden
            self._timer.setInterval(120_000)
        else:
            # 30s when active and visible
            self._timer.setInterval(30_000)

    def refresh_now(self) -> None:
        """Trigger an asynchronous systems probe via JobManager."""
        if self._is_probing:
            return
        self._is_probing = True
        ws = self.workspace_root

        def _do_probe() -> SystemsSnapshot:
            return probe_all(workspace_root=ws)

        try:
            handle: JobHandle = self.job_manager.submit(_do_probe, name="systems_probe")
            handle.add_done_callback(self._on_probe_complete)
        except Exception:
            self._is_probing = False
            raise

    def _on_probe_complete(self, handle: JobHandle) -> None:
        try:
            import shiboken6
            if not shiboken6.isValid(self):
                return
        except Exception:
            pass
        self._is_probing = False
        try:
            snapshot = handle.result()
            if snapshot is not None:
                self._last_snapshot = snapshot
                self.snapshotChanged.emit(snapshot)
        except Exception:
            pass

    @property
    def latest_snapshot(self) -> Optional[SystemsSnapshot]:
        return self._last_snapshot

    def stop(self) -> None:
        """Stop background polling timer."""
        self._timer.stop()
