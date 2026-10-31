"""RunStore: persistence, event logging and runs index for Forge runs (AD-11)."""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .model import RunState

_INDEX_LOCK = threading.Lock()


class RunStore:
    def __init__(self, project_dir: Optional[Union[Path, str]], workspace_dir: Union[Path, str]):
        self.project_dir: Optional[Path] = Path(project_dir).resolve() if project_dir else None
        self.workspace_dir: Path = Path(workspace_dir).resolve()

    def run_dir(self, run_id: str) -> Path:
        if self.project_dir:
            return self.project_dir / "Saved" / "GameForge" / "runs" / run_id
        return self.workspace_dir / ".gameforge" / "runs" / run_id

    def save(self, state: RunState) -> Path:
        """Write state.json atomically with up to 5 retries on PermissionError."""
        rdir = self.run_dir(state.run.run_id)
        rdir.mkdir(parents=True, exist_ok=True)
        target = rdir / "state.json"
        tmp_name = f"state.json.tmp_{secrets.token_hex(4)}"
        tmp_path = rdir / tmp_name

        payload = state.model_dump_json(indent=1)
        tmp_path.write_text(payload, encoding="utf-8")

        # Atomic replace with retry for Windows file locks
        last_err: Optional[Exception] = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, target)
                last_err = None
                break
            except PermissionError as exc:
                last_err = exc
                time.sleep(0.1)

        if last_err is not None:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise last_err

        self._update_index(state)
        return target

    def append_event(self, run_id: str, event: Dict[str, Any]) -> None:
        """Append one JSON line to events.jsonl with a timestamp."""
        rdir = self.run_dir(run_id)
        rdir.mkdir(parents=True, exist_ok=True)
        ev = dict(event)
        if "t" not in ev:
            ev["t"] = time.time()
        line = json.dumps(ev, sort_keys=True, separators=(",", ":"), default=str)
        target = rdir / "events.jsonl"
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")

    def load(self, run_id: str) -> Optional[RunState]:
        """Load RunState by run_id from the store."""
        target = self.run_dir(run_id) / "state.json"
        if not target.exists():
            # Fallback: check workspace runs if project run was not found
            fallback = self.workspace_dir / ".gameforge" / "runs" / run_id / "state.json"
            if fallback.exists():
                target = fallback
            else:
                return None
        try:
            return RunState.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception:
            return None

    def load_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Load all events recorded for a run."""
        target = self.run_dir(run_id) / "events.jsonl"
        if not target.exists():
            fallback = self.workspace_dir / ".gameforge" / "runs" / run_id / "events.jsonl"
            if fallback.exists():
                target = fallback
            else:
                return []
        events = []
        with open(target, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def latest_for_project(self, project_dir: Union[Path, str]) -> Optional[RunState]:
        """Find and load the latest run for a project directory."""
        pdir = Path(project_dir).resolve()
        runs_dir = pdir / "Saved" / "GameForge" / "runs"
        if not runs_dir.is_dir():
            # Check runs index
            entries = [e for e in self.get_runs_index() if e.get("project_dir") == str(pdir)]
            if not entries:
                return None
            entries.sort(key=lambda e: e.get("updated_at", 0), reverse=True)
            return self.load(entries[0]["run_id"])

        best_state: Optional[RunState] = None
        best_time = -1.0
        for entry in runs_dir.iterdir():
            if entry.is_dir():
                state_file = entry / "state.json"
                if state_file.is_file():
                    try:
                        st = RunState.model_validate_json(state_file.read_text(encoding="utf-8"))
                        if st.updated_at > best_time:
                            best_time = st.updated_at
                            best_state = st
                    except Exception:
                        continue
        return best_state

    def get_runs_index(self) -> List[Dict[str, Any]]:
        """Return the list of recorded runs from the index file."""
        idx_file = self.workspace_dir / ".gameforge" / "runs_index.json"
        if not idx_file.is_file():
            return []
        try:
            with open(idx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _update_index(self, state: RunState) -> None:
        """Update <workspace>/.gameforge/runs_index.json keeping newest 200."""
        with _INDEX_LOCK:
            idx_dir = self.workspace_dir / ".gameforge"
            idx_dir.mkdir(parents=True, exist_ok=True)
            idx_file = idx_dir / "runs_index.json"

            runs = self.get_runs_index()
            # Remove existing entry if present
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
            # Sort by updated_at descending and keep newest 200
            runs.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
            runs = runs[:200]

            tmp_idx = idx_dir / f"runs_index.json.tmp_{secrets.token_hex(4)}"
            tmp_idx.write_text(json.dumps(runs, indent=1), encoding="utf-8")
            for _ in range(5):
                try:
                    os.replace(tmp_idx, idx_file)
                    break
                except PermissionError:
                    time.sleep(0.1)
