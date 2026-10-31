"""UI stall detector for Studio UX v2 (WI-4.12).

Measures event loop lateness using a 16 ms QTimer.
Records stalls > 50 ms with Python stack trace samples from the main thread.
Writes reports/P4/stalls.json upon stop() or process exit when GAMEFORGE_STALL_MONITOR=1.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Slot

logger = logging.getLogger(__name__)

STALL_THRESHOLD_MS = 50.0
INTERVAL_MS = 16


class StallMonitor(QObject):
    """Monitors Qt UI thread responsiveness and logs stalls."""

    def __init__(self, parent: Optional[QObject] = None, output_dir: Optional[Path] = None) -> None:
        super().__init__(parent)
        self._output_dir = Path(output_dir or Path("reports/P4")).resolve()
        self._timer: Optional[QTimer] = None
        self._last_tick: float = 0.0
        self._startup_time: float = time.time()
        self._startup_grace_s: float = 2.0  # Exclude startup from stall records
        self._stalls: List[Dict[str, Any]] = []
        self._main_thread_id = threading.main_thread().ident

    def start(self) -> None:
        if self._timer is not None:
            return
        self._last_tick = time.time()
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        atexit.register(self.save_report)

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.save_report()

    @Slot()
    def _on_tick(self) -> None:
        now = time.time()
        dt_ms = (now - self._last_tick) * 1000.0
        self._last_tick = now

        # Skip ticks within startup grace period
        if now - self._startup_time < self._startup_grace_s:
            return

        lateness_ms = dt_ms - INTERVAL_MS
        if lateness_ms > STALL_THRESHOLD_MS:
            # Capture stack frame of main thread
            stack_lines: List[str] = []
            frames = sys._current_frames()
            if self._main_thread_id in frames:
                frame = frames[self._main_thread_id]
                stack_lines = traceback.format_stack(frame)

            stall_info = {
                "timestamp": now,
                "duration_ms": round(dt_ms, 2),
                "lateness_ms": round(lateness_ms, 2),
                "stack": "".join(stack_lines),
            }
            self._stalls.append(stall_info)
            logger.warning("UI STALL detected: %.1f ms lateness", lateness_ms)

    def save_report(self) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_file = self._output_dir / "stalls.json"
        report = {
            "stalls_detected": len(self._stalls),
            "threshold_ms": STALL_THRESHOLD_MS,
            "stalls": self._stalls,
        }
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return out_file


_MONITOR: Optional[StallMonitor] = None


def setup_stall_monitor() -> Optional[StallMonitor]:
    global _MONITOR
    if os.environ.get("GAMEFORGE_STALL_MONITOR") == "1" and _MONITOR is None:
        _MONITOR = StallMonitor()
        _MONITOR.start()
    return _MONITOR
