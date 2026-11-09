"""Authoritative Task & Plan Persistence Store for GameForge IDE.

Provides crash-resilient storage for multi-step TaskPlans and execution state:
- Atomic two-phase write with fsync persistence
- Windows NTFS file lock contention retry with exponential backoff
- Automatic .bak backup creation before file replacement
- Self-healing corruption recovery from .bak
- Dangling temporary file garbage collection
"""
from __future__ import annotations

import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Union

from ..backend.agent.task_plan import TaskPlan
from .atomic import (
    atomic_write_json,
    safe_read_json,
    sweep_dangling_temp_files,
)

logger = logging.getLogger(__name__)

_SAFE_PLAN_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


def _validate_identifier(val: str, label: str = "plan_id") -> str:
    clean = str(val or "").strip()
    if (
        not clean
        or ".." in clean
        or "/" in clean
        or "\\" in clean
        or not _SAFE_PLAN_ID_RE.fullmatch(clean)
    ):
        raise ValueError(f"Invalid {label}: {val!r}")
    return clean


class TaskStore:
    """Manages TaskPlan and task execution state persistence under <workspace>/.gameforge/."""

    def __init__(self, workspace_root: Union[Path, str]):
        self.workspace_root = Path(workspace_root).resolve()
        self.plans_dir = self.workspace_root / ".gameforge" / "plans"
        self.tasks_dir = self.workspace_root / ".gameforge" / "tasks"
        self._lock = threading.RLock()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        try:
            sweep_dangling_temp_files(self.plans_dir, max_age_seconds=600.0, recursive=False)
            sweep_dangling_temp_files(self.tasks_dir, max_age_seconds=600.0, recursive=False)
        except Exception:
            pass

    def _plan_path(self, plan_id: str) -> Path:
        safe_id = _validate_identifier(plan_id, "plan_id")
        candidate = (self.plans_dir / f"{safe_id}.json").resolve()
        if candidate.parent != self.plans_dir.resolve():
            raise ValueError(f"Plan path escapes plans directory: {plan_id!r}")
        return candidate

    def _task_state_path(self, session_id: str) -> Path:
        safe_id = _validate_identifier(session_id, "session_id")
        candidate = (self.tasks_dir / f"{safe_id}_state.json").resolve()
        if candidate.parent != self.tasks_dir.resolve():
            raise ValueError(f"Task state path escapes tasks directory: {session_id!r}")
        return candidate

    def save_plan(self, plan: TaskPlan) -> Path:
        """Persists the plan atomically with automatic .bak backup and fsync."""
        with self._lock:
            self._ensure_dirs()
            target_path = self._plan_path(plan.plan_id)
            plan.updated_at = time.time()
            atomic_write_json(target_path, plan.model_dump(), indent=2, sync=True, backup=True)
            return target_path

    def load_plan(self, plan_id: str) -> Optional[TaskPlan]:
        """Loads a persisted TaskPlan with self-healing fallback to .bak."""
        with self._lock:
            target = self._plan_path(plan_id)
            if not target.is_file():
                bak = target.with_suffix(".json.bak")
                if not bak.is_file():
                    return None

            data, _ = safe_read_json(target, fallback_backup=True)
            if isinstance(data, dict):
                try:
                    return TaskPlan(**data)
                except Exception as exc:
                    logger.warning("Corrupt TaskPlan data in %s: %s", target, exc)
                    return None
            return None

    def list_plans(self, limit: Optional[int] = None) -> List[TaskPlan]:
        """Returns all persisted plans in descending order of update time."""
        with self._lock:
            if not self.plans_dir.is_dir():
                return []
            plans: List[TaskPlan] = []
            try:
                for p in self.plans_dir.glob("plan_*.json"):
                    if p.name.endswith(".bak") or ".tmp" in p.name:
                        continue
                    try:
                        loaded = self.load_plan(p.stem)
                    except ValueError:
                        continue
                    if loaded is not None:
                        plans.append(loaded)
            except OSError:
                pass
            plans.sort(key=lambda x: x.updated_at, reverse=True)
            return plans[:limit] if limit is not None else plans

    def delete_plan(self, plan_id: str) -> bool:
        """Safely delete a plan and its backup."""
        with self._lock:
            target = self._plan_path(plan_id)
            bak = target.with_suffix(".json.bak")
            deleted = False
            try:
                if target.exists():
                    target.unlink(missing_ok=True)
                    deleted = True
                if bak.exists():
                    bak.unlink(missing_ok=True)
            except OSError:
                pass
            return deleted

    def save_task_state(self, session_id: str, state_dict: Dict[str, Any]) -> Path:
        """Persists task state dictionary atomically with backup."""
        with self._lock:
            self._ensure_dirs()
            target = self._task_state_path(session_id)
            atomic_write_json(target, state_dict, indent=2, sync=True, backup=True)
            return target

    def load_task_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Loads task state with automatic backup recovery."""
        with self._lock:
            target = self._task_state_path(session_id)
            if not target.is_file():
                bak = target.with_suffix(".json.bak")
                if not bak.is_file():
                    return None
            data, _ = safe_read_json(target, fallback_backup=True)
            return data if isinstance(data, dict) else None
