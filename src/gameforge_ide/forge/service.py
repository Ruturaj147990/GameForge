"""Forge Service bridge and run management (AD-11).

Exposes ForgeService and run orchestration helpers within the forge subsystem.
"""
from __future__ import annotations

from ..desktop.services.forge_service import ForgeService

__all__ = ["ForgeService"]
