"""Filesystem Inspection Tools for GameForge IDE."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..security.boundary import BoundaryManager, SecurityViolationError


def tool_list_dir(
    boundary: BoundaryManager,
    subpath: str = ".",
    max_depth: int = 2,
    include_hidden: bool = False,
) -> Dict[str, Any]:
    """Lists files and directories under subpath with safety checks."""
    target_dir = boundary.validate_path(subpath, allow_write=False)
    if not target_dir.exists():
        return {"error": f"Directory not found: {subpath}"}
    if not target_dir.is_dir():
        return {"error": f"Path is not a directory: {subpath}"}

    results = []
    base_parts = len(target_dir.parts)

    for root, dirs, files in os.walk(target_dir):
        rel_root = Path(root).relative_to(target_dir)
        depth = len(rel_root.parts) if str(rel_root) != "." else 0
        if depth >= max_depth:
            dirs.clear()
            continue

        if not include_hidden:
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            files = [f for f in files if not f.startswith(".")]

        for d in dirs:
            dir_path = Path(root) / d
            results.append({
                "path": str(dir_path.relative_to(boundary.workspace_root).as_posix()),
                "is_dir": True,
            })

        for f in files:
            file_path = Path(root) / f
            try:
                size = file_path.stat().st_size
            except Exception:
                size = 0
            results.append({
                "path": str(file_path.relative_to(boundary.workspace_root).as_posix()),
                "is_dir": False,
                "size_bytes": size,
            })

    return {"status": "SUCCESS", "count": len(results), "items": results}


def tool_read_file(
    boundary: BoundaryManager,
    subpath: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
) -> Dict[str, Any]:
    """Reads line-numbered content from a file inside the workspace."""
    target_file = boundary.validate_path(subpath, allow_write=False)
    if not target_file.exists():
        return {"error": f"File does not exist: {subpath}"}
    if not target_file.is_file():
        return {"error": f"Path is not a file: {subpath}"}

    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

    total_lines = len(lines)
    s_idx = max(0, start_line - 1)
    e_idx = min(total_lines, end_line) if end_line is not None else total_lines

    selected = lines[s_idx:e_idx]
    numbered = [f"{i + s_idx + 1:4d} | {line}" for i, line in enumerate(selected)]

    return {
        "status": "SUCCESS",
        "file_path": str(target_file.relative_to(boundary.workspace_root).as_posix()),
        "total_lines": total_lines,
        "start_line": start_line,
        "end_line": e_idx,
        "content": "".join(selected),
        "formatted": "".join(numbered),
    }


def tool_search_code(
    boundary: BoundaryManager,
    query: str,
    subpath: str = ".",
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> Dict[str, Any]:
    """Searches workspace files for code patterns."""
    target_dir = boundary.validate_path(subpath, allow_write=False)
    if not target_dir.exists():
        return {"error": f"Directory not found: {subpath}"}

    matches = []
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(query if is_regex else re.escape(query), flags)

    for root, dirs, files in os.walk(target_dir):
        # Ignore git, cache, build dirs
        dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "Intermediate", "Binaries", "Saved", ".pytest_cache"]]

        for f in files:
            if f.endswith((".pyc", ".pyd", ".dll", ".exe", ".pdb", ".bin", ".gguf")):
                continue
            file_path = Path(root) / f
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    for line_idx, line in enumerate(handle, 1):
                        if pattern.search(line):
                            matches.append({
                                "file": str(file_path.relative_to(boundary.workspace_root).as_posix()),
                                "line": line_idx,
                                "content": line.strip(),
                            })
                            if len(matches) >= max_results:
                                return {"status": "SUCCESS", "matches": matches, "truncated": True}
            except Exception:
                continue

    return {"status": "SUCCESS", "matches": matches, "truncated": False}
