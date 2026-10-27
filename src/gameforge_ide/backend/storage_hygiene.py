"""Workspace metadata hygiene (Master Blueprint v2 §8.1: per-workspace cap, rotation, retention).

plan() is a pure preview; apply() executes exactly that plan. Never touched: chat sessions,
pending approvals, egress/settings files, the spend ledger (an audit record), and anything
outside <workspace>/.gameforge.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

DEFAULT_CAP_BYTES = 512 * 2**20
LOG_ROTATE_BYTES = 10 * 2**20
LOG_KEEP = 5
RETENTION_DAYS = 30

# category -> (relative dir, glob, prunable)
PRUNABLE = {
    "diffs": ("diffs", "*.json"),
    "snapshots": ("snapshots", "*"),
    "tasks": ("tasks", "*.json"),
    "exports": ("exports", "*"),
    "e2e": ("e2e", "*"),
}
PROTECTED_NAMES = {"egress.json", "settings.json", "spend.jsonl", "ide_settings.ini", "unreal_session.token"}


@dataclass
class HygienePlan:
    total_bytes: int
    cap_bytes: int
    delete: List[str] = field(default_factory=list)
    rotate: List[str] = field(default_factory=list)
    freed_bytes: int = 0

    def summary(self) -> str:
        return (f".gameforge uses {self.total_bytes / 2**20:.1f} MB (cap {self.cap_bytes / 2**20:.0f} MB); "
                f"plan: delete {len(self.delete)} item(s), rotate {len(self.rotate)} log(s), "
                f"free {self.freed_bytes / 2**20:.1f} MB")


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def plan(workspace_root: Path, cap_bytes: int = DEFAULT_CAP_BYTES, now: float = None) -> HygienePlan:
    root = Path(workspace_root) / ".gameforge"
    now = now or time.time()
    if not root.is_dir():
        return HygienePlan(0, cap_bytes)
    total = _size(root)
    pl = HygienePlan(total, cap_bytes)
    for log in root.rglob("*.log"):
        if log.is_file() and log.stat().st_size > LOG_ROTATE_BYTES:
            pl.rotate.append(str(log))
    # approvals that are finished (not PENDING) and old
    candidates = []
    appr = root / "approvals"
    if appr.is_dir():
        import json
        for f in appr.glob("apr_*.json"):
            try:
                status = json.loads(f.read_text(encoding="utf-8")).get("status")
            except (OSError, ValueError):
                continue
            if status != "PENDING":
                candidates.append(f)
    for rel, pattern in PRUNABLE.values():
        d = root / rel
        if d.is_dir():
            candidates.extend(d.glob(pattern))
    candidates = [c for c in candidates if c.name not in PROTECTED_NAMES]
    candidates.sort(key=lambda p: p.stat().st_mtime)  # oldest first
    cutoff = now - RETENTION_DAYS * 86400
    projected = total
    for c in candidates:
        old = c.stat().st_mtime < cutoff
        if old or projected > cap_bytes:
            size = _size(c)
            pl.delete.append(str(c))
            pl.freed_bytes += size
            projected -= size
        if not old and projected <= cap_bytes:
            break
    return pl


def apply(workspace_root: Path, pl: HygienePlan) -> HygienePlan:
    root = (Path(workspace_root) / ".gameforge").resolve()
    for p in pl.rotate:
        path = Path(p)
        if root not in path.resolve().parents:
            continue
        for i in range(LOG_KEEP - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            if src.exists():
                os.replace(src, path.with_name(f"{path.name}.{i + 1}"))
        os.replace(path, path.with_name(f"{path.name}.1"))
        overflow = path.with_name(f"{path.name}.{LOG_KEEP + 1}")
        if overflow.exists():
            overflow.unlink()
    for p in pl.delete:
        path = Path(p)
        if root not in path.resolve().parents or path.name in PROTECTED_NAMES:
            continue
        if path.is_dir():
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    return pl
