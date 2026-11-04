"""Authoritative DesignStore for GameForge IDE (docs/01_ARCHITECTURE.md).

Provides crash-resilient persistence, revision history, and diffing for GameDesignSpec:
- Atomic two-phase write with fsync persistence
- Windows NTFS file lock contention retry with exponential backoff
- Automatic .bak backup creation before file replacement
- Self-healing corruption recovery from .bak or latest history revision
- Dangling temporary file garbage collection
"""
from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, List, Optional, Union

from ..design.gds import GameDesignSpec
from .atomic import (
    atomic_write_text,
    safe_read_text,
    sweep_dangling_temp_files,
)

logger = logging.getLogger(__name__)

DESIGN_SUBDIR = Path("GameForge") / "design"
_REV_RE = re.compile(r"^r(\d+)\.gds\.json$")


class RevisionConflict(RuntimeError):
    """Raised when saving a revision that does not strictly exceed the stored revision."""
    pass


def _diff_nodes(val_a: Any, val_b: Any, path: str, ops: list[dict]) -> None:
    if val_a == val_b:
        return
    if isinstance(val_a, dict) and isinstance(val_b, dict):
        all_keys = sorted(set(val_a.keys()) | set(val_b.keys()))
        for k in all_keys:
            sub_path = f"{path}/{k}"
            if k in val_a and k not in val_b:
                ops.append({"op": "remove", "path": sub_path, "from": val_a[k]})
            elif k not in val_a and k in val_b:
                ops.append({"op": "add", "path": sub_path, "value": val_b[k]})
            else:
                _diff_nodes(val_a[k], val_b[k], sub_path, ops)
    elif isinstance(val_a, list) and isinstance(val_b, list):
        min_len = min(len(val_a), len(val_b))
        for i in range(min_len):
            _diff_nodes(val_a[i], val_b[i], f"{path}/{i}", ops)
        if len(val_a) > len(val_b):
            for i in range(min_len, len(val_a)):
                ops.append({"op": "remove", "path": f"{path}/{i}", "from": val_a[i]})
        elif len(val_b) > len(val_a):
            for i in range(min_len, len(val_b)):
                ops.append({"op": "add", "path": f"{path}/{i}", "value": val_b[i]})
    else:
        ops.append({"op": "replace", "path": path, "from": val_a, "value": val_b})


def diff(a: GameDesignSpec, b: GameDesignSpec) -> List[dict]:
    """Structural diff as JSON-Patch-like ops [{"op": "replace", "path": "/entities/2/count", "from": 4, "value": 6}]."""
    dict_a = a.model_dump()
    dict_b = b.model_dump()
    ops: List[dict] = []
    _diff_nodes(dict_a, dict_b, "", ops)
    return ops


class DesignStore:
    """Encapsulates GameDesignSpec storage, revision history, and corruption recovery."""

    def __init__(self, project_dir: Union[Path, str]):
        self.project_dir = Path(project_dir).resolve()
        self.design_dir = self.project_dir / DESIGN_SUBDIR
        self.history_dir = self.design_dir / "history"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.design_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        try:
            sweep_dangling_temp_files(self.design_dir, max_age_seconds=600.0, recursive=False)
            sweep_dangling_temp_files(self.history_dir, max_age_seconds=600.0, recursive=False)
        except Exception:
            pass

    @property
    def main_file(self) -> Path:
        return self.design_dir / "game.gds.json"

    def save(self, gds: GameDesignSpec) -> Path:
        """Write game.gds.json and history/r{revision:04d}.gds.json atomically with backup and fsync."""
        self._ensure_dirs()
        rev = gds.meta.revision

        stored = self.load()
        if stored is not None and rev <= stored.meta.revision:
            raise RevisionConflict(
                f"Cannot save revision {rev}; stored revision is {stored.meta.revision} (must strictly exceed it)"
            )

        json_text = gds.to_json()
        rev_file = self.history_dir / f"r{rev:04d}.gds.json"

        # 1. Write historical revision snapshot with lock retries and backup
        atomic_write_text(rev_file, json_text, sync=True, backup=False)

        # 2. Write main specification file with lock retries, fsync, and automatic .bak backup
        atomic_write_text(self.main_file, json_text, sync=True, backup=True)

        return self.main_file

    def load(self) -> Optional[GameDesignSpec]:
        """Load current game.gds.json with automatic self-healing fallback to history and .bak."""
        latest_rev = self.latest_revision_number()

        # If primary file is healthy, check it first
        if self.main_file.is_file():
            text, _ = safe_read_text(self.main_file, fallback_backup=False)
            if text and text.strip():
                try:
                    loaded = GameDesignSpec.model_validate_json(text)
                    if latest_rev is None or loaded.meta.revision >= latest_rev:
                        return loaded
                except Exception as exc:
                    logger.warning("Corrupt main GDS at %s (%s). Attempting history/bak fallback.", self.main_file, exc)

        # Primary missing or corrupt: check latest history revision first (authoritative immutable history)
        if latest_rev is not None:
            rev_gds = self.load_revision(latest_rev)
            if rev_gds is not None:
                logger.info("Successfully recovered corrupted GDS from history revision r%04d", latest_rev)
                try:
                    atomic_write_text(self.main_file, rev_gds.to_json(), sync=True, backup=True)
                except Exception:
                    pass
                return rev_gds

        # Fallback to .bak if history is not available
        text, _ = safe_read_text(self.main_file, fallback_backup=True)
        if text and text.strip():
            try:
                return GameDesignSpec.model_validate_json(text)
            except Exception:
                pass

        return None

    def load_revision(self, rev: int) -> Optional[GameDesignSpec]:
        """Load specific historical revision with lock retry."""
        rev_file = self.history_dir / f"r{rev:04d}.gds.json"
        if not rev_file.is_file():
            return None
        text, _ = safe_read_text(rev_file, fallback_backup=False)
        if text:
            try:
                return GameDesignSpec.model_validate_json(text)
            except Exception:
                return None
        return None

    def history(self) -> List[int]:
        """Return sorted list of revision numbers preserved in history."""
        if not self.history_dir.is_dir():
            return []
        revs: List[int] = []
        try:
            for p in self.history_dir.iterdir():
                if p.is_file():
                    m = _REV_RE.match(p.name)
                    if m:
                        revs.append(int(m.group(1)))
        except OSError:
            pass
        return sorted(revs)

    def latest_revision_number(self) -> Optional[int]:
        h = self.history()
        return h[-1] if h else None

    def diff_current_against(self, target: GameDesignSpec) -> List[dict]:
        current = self.load()
        if current is None:
            return []
        return diff(current, target)


# Backward-compatible functional API
def save(project_dir: Union[Path, str], gds: GameDesignSpec) -> Path:
    return DesignStore(project_dir).save(gds)


def load(project_dir: Union[Path, str]) -> Optional[GameDesignSpec]:
    return DesignStore(project_dir).load()


def load_revision(project_dir: Union[Path, str], rev: int) -> Optional[GameDesignSpec]:
    return DesignStore(project_dir).load_revision(rev)


def history(project_dir: Union[Path, str]) -> List[int]:
    return DesignStore(project_dir).history()
