"""Authoritative Storage Subsystem for GameForge IDE.

Exports:
- atomic: atomic_write, atomic_write_text, atomic_write_json, safe_read_text, safe_read_json, sweep_dangling_temp_files
- design_store: DesignStore, save, load, history, diff, RevisionConflict
- forge_store: ForgeStore, RunStore
- run_store: RunStore, ForgeStore
- approval_store: ApprovalStore
- task_store: TaskStore
- diff_store: DiffStore
"""
from __future__ import annotations

from .atomic import (
    atomic_write,
    atomic_write_json,
    atomic_write_text,
    safe_read_json,
    safe_read_text,
    sweep_dangling_temp_files,
)
from .approval_store import ApprovalStore
from .design_store import (
    DesignStore,
    RevisionConflict,
    diff,
    history,
    load,
    load_revision,
    save,
)
from .diff_store import DiffStore
from .forge_store import ForgeStore, RunStore
from .task_store import TaskStore

__all__ = [
    "ApprovalStore",
    "DesignStore",
    "DiffStore",
    "ForgeStore",
    "RevisionConflict",
    "RunStore",
    "TaskStore",
    "atomic_write",
    "atomic_write_json",
    "atomic_write_text",
    "diff",
    "history",
    "load",
    "load_revision",
    "safe_read_json",
    "safe_read_text",
    "save",
    "sweep_dangling_temp_files",
]
