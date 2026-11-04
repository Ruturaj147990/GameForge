"""Authoritative Forge Run & Execution State Persistence (AD-11).

Provides crash-resilient RunState persistence, event logging, and index management:
- Atomic two-phase write with fsync persistence
- Windows NTFS file lock contention retry with exponential backoff
- Automatic .bak backup creation for state and run index
- Self-healing corruption recovery from .bak
- fsync persistence for JSONL event logging
- Dangling temporary file garbage collection
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..forge.model import RunState
from .atomic import (
    atomic_write_json,
    atomic_write_text,
    safe_read_json,
    safe_read_text,
    sweep_dangling_temp_files,
)

logger = logging.getLogger(__name__)
_INDEX_LOCK = threading.Lock()


class RunStore:
    """Manages execution state, event streams, and runs index for Forge runs."""

    def __init__(self, project_dir: Optional[Union[Path, str]], workspace_dir: Union[Path, str]):
        self.project_dir: Optional[Path] = Path(project_dir).resolve() if project_dir else None
        self.workspace_dir: Path = Path(workspace_dir).resolve()
        self._sweep_abandoned_temps()

    def _sweep_abandoned_temps(self) -> None:
        try:
            runs_root = self.workspace_dir / ".gameforge" / "runs"
            if runs_root.is_dir():
                sweep_dangling_temp_files(runs_root, max_age_seconds=600.0, recursive=True)
            if self.project_dir:
                p_runs = self.project_dir / "Saved" / "GameForge" / "runs"
                if p_runs.is_dir():
                    sweep_dangling_temp_files(p_runs, max_age_seconds=600.0, recursive=True)
        except Exception:
            pass

    def run_dir(self, run_id: str) -> Path:
        if self.project_dir:
            return self.project_dir / "Saved" / "GameForge" / "runs" / run_id
        return self.workspace_dir / ".gameforge" / "runs" / run_id

    def save(self, state: RunState) -> Path:
        """Write state.json atomically with automatic .bak backup and fsync."""
        rdir = self.run_dir(state.run.run_id)
        rdir.mkdir(parents=True, exist_ok=True)
        target = rdir / "state.json"
        payload = state.model_dump_json(indent=1)

        atomic_write_text(target, payload, sync=True, backup=True)
        self._update_index(state)
        return target

    def append_event(self, run_id: str, event: Dict[str, Any]) -> None:
        """Append one JSON line to events.jsonl with a timestamp, lock retry, and fsync."""
        rdir = self.run_dir(run_id)
        rdir.mkdir(parents=True, exist_ok=True)
        ev = dict(event)
        if "t" not in ev:
            ev["t"] = time.time()
        line = json.dumps(ev, sort_keys=True, separators=(",", ":"), default=str)
        target = rdir / "events.jsonl"

        # Retry loop for Windows NTFS concurrent lock contention
        for attempt in range(5):
            try:
                with open(target, "a", encoding="utf-8", newline="\n") as f:
                    f.write(line + "\n")
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                break
            except (PermissionError, OSError) as exc:
                if attempt == 4:
                    logger.error("Failed appending event to %s: %s", target, exc)
                    raise
                time.sleep(0.05 * (attempt + 1))

    def load(self, run_id: str) -> Optional[RunState]:
        """Load RunState by run_id with self-healing fallback to .bak."""
        target = self.run_dir(run_id) / "state.json"
        if not target.exists():
            fallback = self.workspace_dir / ".gameforge" / "runs" / run_id / "state.json"
            if fallback.exists():
                target = fallback
            else:
                return None

        text, recovered = safe_read_text(target, fallback_backup=True)
        if text:
            try:
                from ..forge.model import RunState
                return RunState.model_validate_json(text)
            except Exception as exc:
                logger.warning("Corrupt RunState in %s: %s", target, exc)
                return None
        return None

    def load_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Load all events recorded for a run with lock retry."""
        target = self.run_dir(run_id) / "events.jsonl"
        if not target.exists():
            fallback = self.workspace_dir / ".gameforge" / "runs" / run_id / "events.jsonl"
            if fallback.exists():
                target = fallback
            else:
                return []

        events: List[Dict[str, Any]] = []
        for attempt in range(3):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                return events
            except (PermissionError, OSError):
                if attempt == 2:
                    return events
                time.sleep(0.05 * (attempt + 1))
        return events

    def latest_for_project(self, project_dir: Union[Path, str]) -> Optional[RunState]:
        """Find and load the latest run for a project directory."""
        pdir = Path(project_dir).resolve()
        runs_dir = pdir / "Saved" / "GameForge" / "runs"
        if not runs_dir.is_dir():
            entries = [e for e in self.get_runs_index() if e.get("project_dir") == str(pdir)]
            if not entries:
                return None
            entries.sort(key=lambda e: e.get("updated_at", 0), reverse=True)
            return self.load(entries[0]["run_id"])

        best_state: Optional[RunState] = None
        best_time = -1.0
        try:
            for entry in runs_dir.iterdir():
                if entry.is_dir():
                    state_file = entry / "state.json"
                    if state_file.is_file():
                        try:
                            st = self.load(entry.name)
                            if st and st.updated_at > best_time:
                                best_time = st.updated_at
                                best_state = st
                        except Exception:
                            continue
        except OSError:
            pass
        return best_state

    def get_runs_index(self) -> List[Dict[str, Any]]:
        """Return the list of recorded runs from the index file with .bak fallback."""
        idx_file = self.workspace_dir / ".gameforge" / "runs_index.json"
        if not idx_file.is_file():
            bak_file = idx_file.with_suffix(".json.bak")
            if not bak_file.is_file():
                return []
        data, _ = safe_read_json(idx_file, fallback_backup=True)
        return data if isinstance(data, list) else []

    def _update_index(self, state: RunState) -> None:
        """Update <workspace>/.gameforge/runs_index.json keeping newest 200 with atomic backup."""
        with _INDEX_LOCK:
            idx_dir = self.workspace_dir / ".gameforge"
            idx_dir.mkdir(parents=True, exist_ok=True)
            idx_file = idx_dir / "runs_index.json"

            runs = self.get_runs_index()
            runs = [r for r in runs if r.get("run_id") != state.run.run_id]

            new_entry = {
                "run_id": state.run.run_id,
                "title": state.run.title,
                "project_dir": str(state.run.project_dir) if state.run.project_dir else None,
                "status": state.status,
                "created_at": state.run.created_at,
                "updated_at": state.updated_at,
            }
            runs.insert(0, new_entry)
            runs.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
            runs = runs[:200]

            atomic_write_json(idx_file, runs, indent=1, sync=True, backup=True)


ForgeStore = RunStore
