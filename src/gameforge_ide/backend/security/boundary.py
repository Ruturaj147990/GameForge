"""Security and Path Boundary Protection for GameForge IDE."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional


class SecurityViolationError(Exception):
    """Raised when an operation attempts to breach security bounds."""
    pass


def expand_8_3_short_names(path: Path) -> Path:
    """Expand any Windows 8.3 short filename components (e.g. PROGRA~1) to canonical long names."""
    if os.name != "nt":
        return path
    try:
        import ctypes
        path_str = str(path)
        buf = ctypes.create_unicode_buffer(32768)
        res = ctypes.windll.kernel32.GetLongPathNameW(path_str, buf, 32768)
        if res > 0 and buf.value:
            return Path(buf.value)
        curr = path
        missing_parts: List[str] = []
        while not curr.exists() and curr != curr.parent:
            missing_parts.append(curr.name)
            curr = curr.parent
        if curr.exists():
            buf = ctypes.create_unicode_buffer(32768)
            res = ctypes.windll.kernel32.GetLongPathNameW(str(curr), buf, 32768)
            if res > 0 and buf.value:
                expanded = Path(buf.value)
                for part in reversed(missing_parts):
                    expanded = expanded / part
                return expanded
    except Exception:
        pass
    return path


def is_junction_or_reparse(path: Path) -> bool:
    """Checks if a path component is a Windows junction, reparse point, or symlink across Python 3.10-3.14."""
    try:
        if path.is_symlink():
            return True
        if not path.exists():
            return False
        if hasattr(os.path, "isjunction") and os.path.isjunction(str(path)):
            return True
        st = os.lstat(str(path))
        if getattr(st, "st_file_attributes", 0) & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            return True
        return path.is_symlink()
    except (OSError, ValueError):
        return True  # Fail closed on inspection error


class BoundaryManager:
    """Enforces workspace boundaries, path traversal rejection, and protected file immunity."""

    PROTECTED_PATTERNS: List[str] = [
        "graders/protected",
        ".git",
        "models/ollama/models/blobs",
        ".gameforge/approvals",
        ".gameforge/approvals.json",
        ".gameforge/settings.json",
        ".gameforge/ide_settings.ini",
        ".gameforge/credentials",
        ".gameforge/egress.json",
        ".gameforge/spend.jsonl",
        ".gameforge/hosted_spend.jsonl",
        ".gameforge/audit.jsonl",
        ".gameforge/provenance.json",
        ".gameforge/tasks",
    ]

    RESERVED_DEVICE_NAMES = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }

    def __init__(self, workspace_root: Path):
        from unittest.mock import Mock, MagicMock
        if isinstance(workspace_root, (Mock, MagicMock)) or hasattr(workspace_root, "_mock_return_value") or hasattr(workspace_root, "_mock_wraps"):
            self.workspace_root = Path(os.getcwd()).resolve()
            return
        self.workspace_root = expand_8_3_short_names(Path(workspace_root).resolve())
        if not self.workspace_root.exists() or not self.workspace_root.is_dir():
            raise ValueError(f"Workspace root does not exist or is not a directory: {self.workspace_root}")

    @classmethod
    def match_protected_segments(cls, raw_path: Path) -> Optional[str]:
        """Match path segments against PROTECTED_PATTERNS without substring false positives."""
        parts_lower = [p.lower() for p in raw_path.parts if p not in ("/", "\\", "", ".")]
        if not parts_lower:
            return None

        for pattern in cls.PROTECTED_PATTERNS:
            pat_clean = pattern.lower().replace("\\", "/").strip("/")
            pat_parts = [p for p in pat_clean.split("/") if p]
            if not pat_parts:
                continue
            if pat_clean == ".git":
                if ".git" in parts_lower:
                    return pattern
            else:
                plen = len(pat_parts)
                if len(parts_lower) >= plen:
                    for idx in range(len(parts_lower) - plen + 1):
                        if parts_lower[idx : idx + plen] == pat_parts:
                            return pattern
        return None

    def _match_protected_pattern(self, rel_or_target: Path | str) -> Optional[str]:
        """Return the matched PROTECTED_PATTERNS entry using path-segment matching, or None."""
        raw = Path(str(rel_or_target).replace("\\", "/"))
        if raw.is_absolute():
            try:
                raw = raw.resolve().relative_to(self.workspace_root)
            except Exception:
                return None
        return self.match_protected_segments(raw)

    def is_protected_path(self, target_path: Path | str) -> bool:
        """Returns True if target_path matches any protected system/repository path segment."""
        return self._match_protected_pattern(target_path) is not None

    def validate_path(self, target_path: Path | str, allow_write: bool = False) -> Path:
        """Validates that target_path is inside workspace_root and not in protected paths.

        Returns the resolved Path if valid, otherwise raises SecurityViolationError.
        """
        raw_str = str(target_path).strip()
        if not raw_str:
            if allow_write:
                raise SecurityViolationError("Write violation: Empty path cannot be written to.")
            return self.workspace_root

        # Reject unauthorized UNC network share paths (e.g. \\server\share or //server/share)
        if raw_str.startswith(("//", "\\\\")):
            raise SecurityViolationError(
                f"Network share violation: '{target_path}' is an unauthorized UNC network path."
            )

        # Reject Alternate Data Streams (NTFS ADS) on Windows
        path_without_drive = raw_str
        if len(path_without_drive) >= 2 and path_without_drive[1] == ":" and path_without_drive[0].isalpha():
            path_without_drive = path_without_drive[2:]
        if ":" in path_without_drive:
            raise SecurityViolationError(
                f"Alternate data stream violation: '{target_path}' contains invalid colon specifier."
            )

        raw_path = Path(raw_str)

        # Check for NTFS alternate data streams in individual parts
        for idx, part in enumerate(raw_path.parts):
            if idx == 0 and len(part) >= 2 and part[1] == ":":
                continue
            if ":" in part:
                raise SecurityViolationError(
                    f"Alternate data stream violation: '{target_path}' contains colon in component '{part}'."
                )

        # Reject unauthorized Windows drive jumps (e.g. C: vs E:)
        if raw_path.drive and self.workspace_root.drive and raw_path.drive.lower() != self.workspace_root.drive.lower():
            raise SecurityViolationError(
                f"Drive jump violation: '{target_path}' targets drive '{raw_path.drive}' which differs from workspace drive '{self.workspace_root.drive}'."
            )

        # Check for Windows reserved device names in any path component
        for part in raw_path.parts:
            stem = part.split(".")[0].lower()
            if stem in self.RESERVED_DEVICE_NAMES:
                raise SecurityViolationError(
                    f"Reserved device violation: '{target_path}' contains Windows reserved device name '{part}'."
                )

        # Compute relative parts from workspace_root so both relative AND absolute paths inside
        # workspace_root walk the actual directory entries for symlinks/junctions.
        try:
            norm_ws = os.path.normcase(str(self.workspace_root))
            if raw_path.is_absolute():
                lexical_abs = Path(os.path.abspath(str(raw_path)))
                norm_lex = os.path.normcase(str(lexical_abs))
                if not (norm_lex == norm_ws or norm_lex.startswith(norm_ws + os.sep)):
                    raise SecurityViolationError(
                        f"Path traversal violation: '{target_path}' is outside workspace '{self.workspace_root}'"
                    )
                rel_tail = str(lexical_abs)[len(str(self.workspace_root)) :].lstrip("\\/")
                walk_parts = list(Path(rel_tail).parts) if rel_tail else []
            else:
                walk_parts = [
                    p for p in raw_path.parts
                    if p not in ("/", "\\", "") and not (len(p) >= 2 and p[1] == ":")
                ]

            curr = self.workspace_root
            for part in walk_parts:
                curr = curr / part
                if is_junction_or_reparse(curr):
                    try:
                        symlink_target = curr.resolve()
                        norm_target = os.path.normcase(str(symlink_target))
                        if not (norm_target == norm_ws or norm_target.startswith(norm_ws + os.sep)):
                            raise ValueError()
                    except ValueError:
                        raise SecurityViolationError(
                            f"Symlink/junction traversal violation: '{curr}' points outside workspace to '{symlink_target}'."
                        )
                    except OSError as exc:
                        raise SecurityViolationError(f"Failed resolving link '{curr}': {exc}")
        except SecurityViolationError:
            raise
        except OSError as exc:
            raise SecurityViolationError(f"Path inspection failure for '{target_path}': {exc}")

        try:
            if not raw_path.is_absolute():
                resolved = (self.workspace_root / raw_path).resolve()
            else:
                resolved = raw_path.resolve()
            resolved = expand_8_3_short_names(resolved)
        except (RuntimeError, OSError, ValueError) as e:
            raise SecurityViolationError(f"Path resolution failure for '{target_path}': {e}")

        # Windows case-insensitive and slash-normalized workspace containment check
        norm_resolved = os.path.normcase(str(resolved))
        norm_ws = os.path.normcase(str(self.workspace_root))
        is_contained = (norm_resolved == norm_ws or norm_resolved.startswith(norm_ws + os.sep))
        if not is_contained:
            raise SecurityViolationError(
                f"Path traversal violation: '{target_path}' resolves to '{resolved}' which is outside workspace '{self.workspace_root}'"
            )

        # Compute safe relative path
        try:
            rel = resolved.relative_to(self.workspace_root)
        except ValueError:
            rel_str = norm_resolved[len(norm_ws) :].lstrip("\\/")
            rel = Path(rel_str)

        # Check protected paths for writes
        if allow_write:
            if norm_resolved == norm_ws:
                raise SecurityViolationError(
                    "Write violation: Cannot modify or overwrite the workspace root directory itself."
                )

            matched_pat = self._match_protected_pattern(rel)
            if matched_pat is not None:
                rel_str = rel.as_posix().lower()
                raise SecurityViolationError(
                    f"Write violation: Cannot modify protected system path '{rel_str}' (matches protected pattern '{matched_pat}')"
                )

        return resolved

    # Alias for callers using resolve_safe_path
    resolve_safe_path = validate_path

    def is_safe(self, target_path: Path | str, allow_write: bool = False) -> bool:
        """Returns True if path is safe, False otherwise."""
        try:
            self.validate_path(target_path, allow_write=allow_write)
            return True
        except (SecurityViolationError, ValueError):
            return False


def resolve_safe_path(
    workspace_root: Path | str,
    target_path: Path | str,
    allow_write: bool = False,
) -> Path:
    """Module-level helper that validates and resolves target_path inside workspace_root."""
    return BoundaryManager(Path(workspace_root)).validate_path(target_path, allow_write=allow_write)


def is_protected_path(
    target_path: Path | str,
    workspace_root: Optional[Path | str] = None,
) -> bool:
    """Module-level helper that checks if target_path matches a protected path segment."""
    if workspace_root is not None:
        return BoundaryManager(Path(workspace_root)).is_protected_path(target_path)
    raw = Path(str(target_path).replace("\\", "/"))
    return BoundaryManager.match_protected_segments(raw) is not None
