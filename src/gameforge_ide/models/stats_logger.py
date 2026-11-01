"""Model structured-output repair statistics logger (WI-9.6)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def log_model_stat(
    role: str,
    model_name: str,
    action: str,
    first_try_valid: bool,
    repaired: bool,
    duration_s: float,
    workspace_dir: Optional[Path] = None,
) -> None:
    """Log a structured-output outcome to <workspace>/.gameforge/model_stats.jsonl."""
    if workspace_dir is None:
        try:
            from ..core.settings import get_settings
            workspace_dir = get_settings().default_workspace
        except Exception:
            workspace_dir = Path(".")

    stats_dir = Path(workspace_dir).resolve() / ".gameforge"
    stats_dir.mkdir(parents=True, exist_ok=True)
    stats_file = stats_dir / "model_stats.jsonl"

    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": role,
        "model": model_name,
        "action": action,
        "first_try_valid": first_try_valid,
        "repaired": repaired,
        "duration_s": round(duration_s, 3),
    }

    try:
        with open(stats_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def read_model_stats(workspace_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read all logged model repair stats."""
    if workspace_dir is None:
        try:
            from ..core.settings import get_settings
            workspace_dir = get_settings().default_workspace
        except Exception:
            workspace_dir = Path(".")

    stats_file = Path(workspace_dir).resolve() / ".gameforge" / "model_stats.jsonl"
    if not stats_file.is_file():
        return []

    entries = []
    try:
        with open(stats_file, "r", encoding="utf-8") as f:
            for line in f:
                sline = line.strip()
                if sline:
                    entries.append(json.loads(sline))
    except Exception:
        pass
    return entries


def compute_aggregate_model_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute per-model and per-role JSON success and repair rates."""
    total = len(entries)
    if total == 0:
        return {"total_calls": 0, "first_try_rate": 0.0, "repaired_rate": 0.0, "models": {}}

    first_try_count = sum(1 for e in entries if e.get("first_try_valid", False))
    repaired_count = sum(1 for e in entries if e.get("repaired", False))

    by_model: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        m = e.get("model", "unknown")
        if m not in by_model:
            by_model[m] = {"calls": 0, "first_try": 0, "repaired": 0}
        by_model[m]["calls"] += 1
        if e.get("first_try_valid", False):
            by_model[m]["first_try"] += 1
        if e.get("repaired", False):
            by_model[m]["repaired"] += 1

    model_summaries = {}
    for m, d in by_model.items():
        c = d["calls"]
        model_summaries[m] = {
            "total_calls": c,
            "first_try_rate": round((d["first_try"] / c) * 100.0, 1),
            "repaired_rate": round((d["repaired"] / c) * 100.0, 1),
        }

    return {
        "total_calls": total,
        "first_try_rate": round((first_try_count / total) * 100.0, 1),
        "repaired_rate": round((repaired_count / total) * 100.0, 1),
        "models": model_summaries,
    }
