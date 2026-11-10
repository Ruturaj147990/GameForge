"""Provenance and Environment Recording for GameForge Benchmark."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


def _creationflags() -> int:
    """Returns CREATE_NO_WINDOW flag on Windows to prevent console flashing."""
    return 0x08000000 if sys.platform == "win32" else 0


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
    hardware_notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert environment record to serializable dictionary."""
        return asdict(self)


def capture_environment(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Captures deterministic environment, hardware, and git provenance metadata."""
    root = workspace_root or Path.cwd()
    git_commit: Optional[str] = os.environ.get("GAMEFORGE_GIT_COMMIT")
    git_branch: Optional[str] = os.environ.get("GAMEFORGE_GIT_BRANCH")
    git_dirty = False

    flags = _creationflags()

    try:
        # Check git commit
        if not git_commit:
            res_hash = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=flags,
            )
            if res_hash.returncode == 0:
                git_commit = res_hash.stdout.strip()

        # Check git branch
        if not git_branch:
            res_branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=flags,
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
            creationflags=flags,
        )
        if res_status.returncode == 0:
            git_dirty = bool(res_status.stdout.strip())
    except Exception:
        pass

    # Read git commit fallback directly from .git/HEAD if subprocess failed
    if not git_commit:
        head_path = root / ".git" / "HEAD"
        if head_path.is_file():
            try:
                head_ref = head_path.read_text(encoding="utf-8").strip()
                if head_ref.startswith("ref: "):
                    ref_rel = head_ref[5:].strip()
                    if not git_branch:
                        git_branch = ref_rel.split("/")[-1]
                    ref_file = root / ".git" / ref_rel
                    if ref_file.is_file():
                        git_commit = ref_file.read_text(encoding="utf-8").strip()
                else:
                    git_commit = head_ref
            except Exception:
                pass

    hardware_notes: Dict[str, Any] = {
        "cpu_count": os.cpu_count() or 6,
    }

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
        hardware_notes=hardware_notes,
    )

    return rec.to_dict()
