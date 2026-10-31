"""Diagnostics package."""
from .stall_monitor import StallMonitor, setup_stall_monitor

__all__ = ["StallMonitor", "setup_stall_monitor"]
