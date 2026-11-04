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

    RESERVED_DEVICE_NAMES = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        if not self.workspace_root.exists() or not self.workspace_root.is_dir():
            raise ValueError(f"Workspace root does not exist or is not a directory: {self.workspace_root}")

    def validate_path(self, target_path: Path | str, allow_write: bool = False) -> Path:
        """Validates that target_path is inside workspace_root and not in protected paths.
        
        Returns the resolved Path if valid, otherwise raises SecurityViolationError.
        """
        raw_str = str(target_path).strip()
        if not raw_str:
            if allow_write:
                raise SecurityViolationError("Write violation: Empty path cannot be written to.")
            return self.workspace_root

        # Reject Alternate Data Streams (NTFS ADS) on Windows
        # Strip leading Windows drive specification (e.g. C:) if present before checking for colons
        path_without_drive = raw_str
        if len(path_without_drive) >= 2 and path_without_drive[1] == ":" and path_without_drive[0].isalpha():
            path_without_drive = path_without_drive[2:]
        if ":" in path_without_drive:
            raise SecurityViolationError(
                f"Alternate data stream violation: '{target_path}' contains invalid colon specifier."
            )

        raw_path = Path(raw_str)

        # Check for Windows reserved device names in any path component
        for part in raw_path.parts:
            # Strip extensions to detect CON.txt, NUL.dat, etc.
            stem = part.split(".")[0].lower()
            if stem in self.RESERVED_DEVICE_NAMES:
                raise SecurityViolationError(
                    f"Reserved device violation: '{target_path}' contains Windows reserved device name '{part}'."
                )

        try:
            if not raw_path.is_absolute():
                resolved = (self.workspace_root / raw_path).resolve()
            else:
                resolved = raw_path.resolve()
        except (RuntimeError, OSError) as e:
            raise SecurityViolationError(f"Path resolution failure for '{target_path}': {e}")

        # Workspace containment check (prevent path traversal)
        try:
            rel = resolved.relative_to(self.workspace_root)
        except ValueError:
            raise SecurityViolationError(
                f"Path traversal violation: '{target_path}' resolves to '{resolved}' which is outside workspace '{self.workspace_root}'"
            )

        # Check protected paths for writes
        if allow_write:
            if resolved == self.workspace_root:
                raise SecurityViolationError(
                    "Write violation: Cannot modify or overwrite the workspace root directory itself."
                )

            rel_str = rel.as_posix().lower()
            parts_lower = [p.lower() for p in rel.parts]
            for pattern in self.PROTECTED_PATTERNS:
                pat_lower = pattern.lower().replace("\\", "/")
                # For git repository metadata: protect .git folder or file components,
                # but allow non-repository files like .gitignore or .gitattributes.
                if pat_lower == ".git":
                    if ".git" in parts_lower:
                        raise SecurityViolationError(
                            f"Write violation: Cannot modify protected system path '{rel_str}' (matches protected pattern '{pattern}')"
                        )
                else:
                    if pat_lower in rel_str or rel_str.startswith(pat_lower):
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
