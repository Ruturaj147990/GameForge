"""Provenance and Environment Recording for GameForge Benchmark."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class EnvironmentRecord:
    os: str
    os_release: str
    architecture: str
    processor: str
    python_version: str
    python_executable: str
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    git_dirty: bool = False
    hostname: str = ""
    timestamp_utc: str = ""


def capture_environment(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Captures deterministic environment, hardware, and git provenance metadata."""
    root = workspace_root or Path.cwd()
    git_commit = None
    git_branch = None
    git_dirty = False

    try:
        # Check git commit
        res_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res_hash.returncode == 0:
            git_commit = res_hash.stdout.strip()

        # Check git branch
        res_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res_branch.returncode == 0:
            git_branch = res_branch.stdout.strip()

        # Check status dirty
        res_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res_status.returncode == 0:
            git_dirty = bool(res_status.stdout.strip())
    except Exception:
        pass

    rec = EnvironmentRecord(
        os=platform.system(),
        os_release=platform.release(),
        architecture=platform.machine(),
        processor=platform.processor() or "AMD/Intel x64",
        python_version=sys.version.split()[0],
        python_executable=sys.executable,
        git_commit=git_commit,
        git_branch=git_branch,
        git_dirty=git_dirty,
        hostname=platform.node(),
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    return asdict(rec)
