"""Filesystem Inspection Tools for GameForge IDE."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..security.boundary import BoundaryManager, SecurityViolationError

BINARY_EXTENSIONS = (
    ".pyc", ".pyd", ".dll", ".exe", ".pdb", ".bin", ".gguf",
    ".uasset", ".umap", ".ubulk", ".uptnl",
    ".png", ".jpg", ".jpeg", ".tga", ".exr", ".dds", ".hdr", ".ico",
    ".wav", ".mp3", ".ogg", ".flac",
    ".fbx", ".obj", ".blend", ".gltf", ".glb",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".pak", ".iso",
)


def _detect_file_encoding(file_path: Path) -> str:
    """Detect file encoding from BOM or byte inspection: UTF-8-BOM, UTF-16-LE, UTF-16-BE, UTF-8."""
    try:
        with open(file_path, "rb") as handle:
            header = handle.read(4)
        if header.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if header.startswith(b"\xff\xfe"):
            return "utf-16-le"
        if header.startswith(b"\xfe\xff"):
            return "utf-16-be"

        with open(file_path, "rb") as handle:
            chunk = handle.read(8192)
        try:
            chunk.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            try:
                chunk.decode("utf-16")
                return "utf-16"
            except UnicodeDecodeError:
                return "utf-8"
    except Exception:
        return "utf-8"


def tool_list_dir(
    boundary: BoundaryManager,
    subpath: str = ".",
    max_depth: int = 2,
    include_hidden: bool = False,
    path: str = "",
    dir_path: str = "",
    directory: str = "",
    folder: str = "",
    depth: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Lists files and directories under subpath with safety checks."""
    effective_path = path or dir_path or directory or folder or subpath or "."
    effective_depth = depth if depth is not None else max_depth
    try:
        target_dir = boundary.validate_path(effective_path, allow_write=False)
    except (SecurityViolationError, ValueError) as exc:
        return {"error": f"Security violation: {exc}"}

    if not target_dir.exists():
        clean_sub = effective_path.replace("\\", "/").strip("/")
        parts = clean_sub.split("/")
        if parts and parts[0].lower() == boundary.workspace_root.name.lower():
            remapped = "/".join(parts[1:]) or "."
            try:
                remapped_dir = boundary.validate_path(remapped, allow_write=False)
                if remapped_dir.exists():
                    target_dir = remapped_dir
            except Exception:
                pass
    if not target_dir.exists():
        return {"error": f"Directory not found: {effective_path}"}
    if not target_dir.is_dir():
        return {"error": f"Path is not a directory: {effective_path}"}

    results = []

    for root, dirs, files in os.walk(target_dir):
        rel_root = Path(root).relative_to(target_dir)
        curr_depth = len(rel_root.parts) if str(rel_root) != "." else 0
        if curr_depth >= effective_depth:
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
    subpath: str = "",
    start_line: int = 1,
    end_line: Optional[int] = None,
    file_path: str = "",
    path: str = "",
    file: str = "",
    filepath: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Reads line-numbered content from a file inside the workspace."""
    effective_path = subpath or file_path or path or file or filepath or ""
    try:
        target_file = boundary.validate_path(effective_path, allow_write=False)
    except (SecurityViolationError, ValueError) as exc:
        return {"error": f"Security violation: {exc}"}

    if not target_file.exists():
        clean_sub = effective_path.replace("\\", "/").strip("/")
        parts = clean_sub.split("/")
        if parts and parts[0].lower() == boundary.workspace_root.name.lower():
            remapped = "/".join(parts[1:])
            try:
                remapped_file = boundary.validate_path(remapped, allow_write=False)
                if remapped_file.exists():
                    target_file = remapped_file
            except Exception:
                pass
    if not target_file.exists():
        return {"error": f"File does not exist: {effective_path}"}
    if not target_file.is_file():
        return {"error": f"Path is not a file: {effective_path}"}

    encoding = _detect_file_encoding(target_file)
    lines = None
    last_err = None
    for attempt in range(3):
        try:
            with open(target_file, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()
            last_err = None
            break
        except (PermissionError, OSError) as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))

    if lines is None:
        return {"error": f"Failed to read file: {last_err}"}

    try:
        start_line_int = int(start_line) if start_line is not None else 1
    except (ValueError, TypeError):
        start_line_int = 1

    total_lines = len(lines)
    s_idx = max(0, start_line_int - 1)
    truncated = False

    if end_line is not None:
        try:
            end_line_int = int(end_line)
        except (ValueError, TypeError):
            end_line_int = total_lines
        e_idx = max(s_idx, min(total_lines, end_line_int))
    else:
        # Default safety ceiling for large files (> 2,000 lines) to prevent runaway memory
        if total_lines - s_idx > 2000:
            e_idx = min(total_lines, s_idx + 2000)
            truncated = True
        else:
            e_idx = total_lines

    selected = lines[s_idx:e_idx]
    numbered = [f"{i + s_idx + 1:4d} | {line}" for i, line in enumerate(selected)]

    response: Dict[str, Any] = {
        "status": "SUCCESS",
        "file_path": str(target_file.relative_to(boundary.workspace_root).as_posix()),
        "total_lines": total_lines,
        "start_line": start_line_int,
        "end_line": e_idx,
        "content": "".join(selected),
        "formatted": "".join(numbered),
        "encoding": encoding,
    }
    if truncated:
        response["truncated"] = True
        response["message"] = (
            f"Displaying lines {start_line} through {e_idx} of {total_lines}. "
            "Specify start_line and end_line for subsequent ranges."
        )

    return response


def tool_search_code(
    boundary: BoundaryManager,
    query: str = "",
    subpath: str = ".",
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 50,
    pattern: str = "",
    search_term: str = "",
    text: str = "",
    path: str = "",
    dir_path: str = "",
    directory: str = "",
    limit: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Searches workspace files for code patterns."""
    effective_query = query or pattern or search_term or text or ""
    effective_path = path or dir_path or directory or subpath or "."
    try:
        effective_limit = int(limit) if limit is not None else int(max_results)
    except (ValueError, TypeError):
        effective_limit = 50

    if not is_regex and (not effective_query or not effective_query.strip()):
        return {"status": "SUCCESS", "matches": [], "truncated": False}

    try:
        target_dir = boundary.validate_path(effective_path, allow_write=False)
    except (SecurityViolationError, ValueError) as exc:
        return {"error": f"Security violation: {exc}"}

    if not target_dir.exists():
        clean_sub = effective_path.replace("\\", "/").strip("/")
        parts = clean_sub.split("/")
        if parts and parts[0].lower() == boundary.workspace_root.name.lower():
            remapped = "/".join(parts[1:]) or "."
            try:
                remapped_dir = boundary.validate_path(remapped, allow_write=False)
                if remapped_dir.exists():
                    target_dir = remapped_dir
            except Exception:
                pass

    if not target_dir.exists():
        return {"error": f"Directory not found: {effective_path}"}

    matches = []
    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        re_pattern = re.compile(effective_query if is_regex else re.escape(effective_query), flags)
    except re.error as e:
        return {"error": f"Invalid regular expression '{effective_query}': {e}"}

    for root, dirs, files in os.walk(target_dir):
        # Ignore git, cache, build dirs
        dirs[:] = [
            d for d in dirs
            if d not in [
                ".git", "__pycache__", "Intermediate", "Binaries", "Saved",
                ".pytest_cache", ".gameforge", "DerivedDataCache", "Build", "node_modules", "scratch",
            ]
        ]

        for f in files:
            if f.endswith(BINARY_EXTENSIONS):
                continue
            file_path = Path(root) / f
            encoding = _detect_file_encoding(file_path)
            try:
                with open(file_path, "r", encoding=encoding, errors="ignore") as handle:
                    for line_idx, line in enumerate(handle, 1):
                        if re_pattern.search(line):
                            matches.append({
                                "file": str(file_path.relative_to(boundary.workspace_root).as_posix()),
                                "line": line_idx,
                                "content": line.strip()[:500],
                            })
                            if len(matches) >= effective_limit:
                                return {"status": "SUCCESS", "matches": matches, "truncated": True}
            except Exception:
                continue

    return {"status": "SUCCESS", "matches": matches, "truncated": False}
