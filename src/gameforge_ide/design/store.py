"""Disk storage and revision history for GameDesignSpec (P1 WI-1.8)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, List, Optional

from .gds import GameDesignSpec

DESIGN_DIR = Path("GameForge") / "design"
_REV_RE = re.compile(r"^r(\d+)\.gds\.json$")


class RevisionConflict(RuntimeError):
    """Raised when saving a revision that does not strictly exceed the stored revision."""
    pass


def save(project_dir: Path, gds: GameDesignSpec) -> Path:
    """Write game.gds.json and history/r{revision:04d}.gds.json atomically. The revision must exceed the stored one."""
    target_dir = Path(project_dir) / DESIGN_DIR
    history_dir = target_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    main_file = target_dir / "game.gds.json"
    rev = gds.meta.revision

    if main_file.is_file():
        stored = load(project_dir)
        if stored is not None and rev <= stored.meta.revision:
            raise RevisionConflict(
                f"Cannot save revision {rev}; stored revision is {stored.meta.revision} (must strictly exceed it)"
            )

    json_text = gds.to_json()
    rev_file = history_dir / f"r{rev:04d}.gds.json"

    # Write history revision file atomically
    tmp_rev = history_dir / f".tmp_{secrets.token_hex(4)}.json"
    tmp_rev.write_text(json_text, encoding="utf-8")
    os.replace(tmp_rev, rev_file)

    # Write main game.gds.json atomically
    tmp_main = target_dir / f".tmp_{secrets.token_hex(4)}.json"
    tmp_main.write_text(json_text, encoding="utf-8")
    os.replace(tmp_main, main_file)

    return main_file


def load(project_dir: Path) -> Optional[GameDesignSpec]:
    """Load the current game.gds.json for a project, or None if it doesn't exist."""
    main_file = Path(project_dir) / DESIGN_DIR / "game.gds.json"
    if not main_file.is_file():
        return None
    try:
        text = main_file.read_text(encoding="utf-8")
        return GameDesignSpec.model_validate_json(text)
    except Exception:
        return None


def history(project_dir: Path) -> List[int]:
    """Return sorted list of revision numbers preserved in the history directory."""
    history_dir = Path(project_dir) / DESIGN_DIR / "history"
    if not history_dir.is_dir():
        return []
    revs: List[int] = []
    for p in history_dir.iterdir():
        if p.is_file():
            m = _REV_RE.match(p.name)
            if m:
                revs.append(int(m.group(1)))
    return sorted(revs)


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
