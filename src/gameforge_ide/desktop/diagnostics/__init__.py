"""GameForge IDE — Desktop UI Diagnostics and Thread Stall Monitoring Package."""

from __future__ import annotations

from .stall_monitor import StallMonitor, setup_stall_monitor

__all__ = ["StallMonitor", "setup_stall_monitor"]

