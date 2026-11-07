"""Git Version Control Inspection Tools for GameForge IDE."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def _win32_extra_kw() -> Dict[str, Any]:
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": si}


class GitTools:
    """Provides non-destructive git inspection utilities for the IDE."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def get_status(self) -> Dict[str, Any]:
        """Returns structured git status (branch, modified, untracked)."""
        try:
            extra_kw = _win32_extra_kw()
            # Branch name
            branch_proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=10,
                **extra_kw,
            )
            branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "unknown"

            # Porcelain status
            stat_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=10,
                **extra_kw,
            )
            lines = stat_proc.stdout.splitlines()
            modified = []
            untracked = []
            for line in lines:
                code = line[:2].strip()
                path = line[3:].strip()
                if code == "??":
                    untracked.append(path)
                else:
                    modified.append({"status_code": code, "path": path})

            return {
                "status": "SUCCESS",
                "branch": branch,
                "clean": len(lines) == 0,
                "modified_count": len(modified),
                "untracked_count": len(untracked),
                "modified": modified,
                "untracked": untracked,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def get_diff(self, path: str = "", subpath: str = "", file_path: str = "", **kwargs: Any) -> Dict[str, Any]:
        """Returns unstaged git diff with boundary path containment validation."""
        effective_path = path or subpath or file_path or ""
        try:
            cmd = ["git", "diff"]
            if effective_path:
                from ..security.boundary import BoundaryManager, SecurityViolationError
                bm = BoundaryManager(self.workspace_root)
                valid_path = bm.validate_path(effective_path, allow_write=False)
                rel_path = str(valid_path.relative_to(self.workspace_root).as_posix())
                cmd.append(rel_path)
            extra_kw = _win32_extra_kw()
            diff_proc = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=15,
                **extra_kw,
            )
            return {
                "status": "SUCCESS",
                "diff": diff_proc.stdout,
                "has_changes": len(diff_proc.stdout.strip()) > 0,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
