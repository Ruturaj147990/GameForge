"""Security and Path Boundary Protection package for GameForge IDE."""
from __future__ import annotations

from .boundary import (
    BoundaryManager,
    SecurityViolationError,
    expand_8_3_short_names,
    is_junction_or_reparse,
    is_protected_path,
    resolve_safe_path,
)

SecurityBoundary = BoundaryManager

__all__ = [
    "BoundaryManager",
    "SecurityBoundary",
    "SecurityViolationError",
    "expand_8_3_short_names",
    "is_junction_or_reparse",
    "is_protected_path",
    "resolve_safe_path",
]
