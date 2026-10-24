"""Security and Path Boundary Protection for GameForge IDE."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


class SecurityViolationError(Exception):
    """Raised when an operation attempts to breach security bounds."""
    pass


class BoundaryManager:
    """Enforces workspace boundaries, path traversal rejection, and protected file immunity."""

    PROTECTED_PATTERNS: List[str] = [
        "graders/protected",
        ".git",
        "models/ollama/models/blobs",
    ]

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        if not self.workspace_root.exists() or not self.workspace_root.is_dir():
            raise ValueError(f"Workspace root does not exist or is not a directory: {self.workspace_root}")

    def validate_path(self, target_path: Path | str, allow_write: bool = False) -> Path:
        """Validates that target_path is inside workspace_root and not in protected paths.
        
        Returns the resolved Path if valid, otherwise raises SecurityViolationError.
        """
        raw_path = Path(target_path)
        if not raw_path.is_absolute():
            resolved = (self.workspace_root / raw_path).resolve()
        else:
            resolved = raw_path.resolve()

        # Workspace containment check (prevent path traversal)
        try:
            rel = resolved.relative_to(self.workspace_root)
        except ValueError:
            raise SecurityViolationError(
                f"Path traversal violation: '{target_path}' resolves to '{resolved}' which is outside workspace '{self.workspace_root}'"
            )

        # Check protected paths for writes
        if allow_write:
            rel_str = rel.as_posix().lower()
            for pattern in self.PROTECTED_PATTERNS:
                if pattern.lower() in rel_str or rel_str.startswith(pattern.lower()):
                    raise SecurityViolationError(
                        f"Write violation: Cannot modify protected system path '{rel_str}' (matches protected pattern '{pattern}')"
                    )

        return resolved

    def is_safe(self, target_path: Path | str, allow_write: bool = False) -> bool:
        """Returns True if path is safe, False otherwise."""
        try:
            self.validate_path(target_path, allow_write=allow_write)
            return True
        except (SecurityViolationError, ValueError):
            return False
