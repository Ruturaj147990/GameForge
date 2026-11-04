"""Disk storage and revision history for GameDesignSpec (P1 WI-1.8).

Delegates to authoritative crash-resilient storage in src/gameforge_ide/storage/design_store.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from ..storage.design_store import (
    DESIGN_SUBDIR as DESIGN_DIR,
    DesignStore,
    RevisionConflict,
    _diff_nodes,
    diff,
    history,
    load,
    load_revision,
    save,
)
from .gds import GameDesignSpec

__all__ = [
    "DESIGN_DIR",
    "DesignStore",
    "RevisionConflict",
    "diff",
    "history",
    "load",
    "load_revision",
    "save",
]

