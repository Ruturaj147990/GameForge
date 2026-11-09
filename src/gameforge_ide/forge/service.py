"""Forge Service bridge and run management (AD-11).

Exposes ForgeService and run orchestration helpers within the forge subsystem.
Gracefully degrades in headless environments where PySide6 is not installed.
"""
from __future__ import annotations

try:
    from ..desktop.services.forge_service import ForgeService
except ImportError:
    ForgeService = None  # type: ignore[assignment,misc]

__all__ = ["ForgeService"]
