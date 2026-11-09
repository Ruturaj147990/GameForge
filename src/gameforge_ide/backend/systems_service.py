"""Re-export SystemsService from desktop.services.systems_service."""
from __future__ import annotations

try:
    from ..desktop.services.systems_service import SystemsService
except ImportError:
    SystemsService = None  # type: ignore[assignment,misc]

__all__ = ["SystemsService"]
