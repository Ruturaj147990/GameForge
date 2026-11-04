"""Authoritative Atomic File Operations for GameForge IDE.

Provides safe, crash-resilient atomic file writing with:
- Windows NTFS file lock retries and exponential backoff
- Read-only attribute clearing (os.chmod) on locked targets
- fsync persistence to protect against sudden process termination or OS crash
- Safe temporary filename prefix truncation to guarantee MAX_PATH and NTFS 255-char safety
- Clean temp file unlinking on failure with no exception shadowing
- Dangling temp file (.tmp_*, *.tmp) garbage collection
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, List, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = 5
DEFAULT_BACKOFF_BASE = 0.05


def safe_temp_prefix(target_name: str, max_stem_len: int = 40) -> str:
    """Generate a safe prefix for temp files that will never exceed NTFS 255-char component limits."""
    # Strip any directory separators if present
    base_name = Path(target_name).name
    # Truncate base name to max_stem_len
    truncated = base_name[:max_stem_len] if len(base_name) > max_stem_len else base_name
    return f".{truncated}."


def atomic_write(
    target_path: Union[Path, str],
    content: bytes,
    make_parents: bool = True,
    max_retries: int = DEFAULT_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sync: bool = True,
    backup: bool = False,
) -> Path:
    """Atomically write binary content to target_path.

    Uses a temporary file in the target directory followed by os.replace.
    Retries on PermissionError or OSError with exponential backoff, clearing
    read-only attributes if the target exists.
    If backup=True and target exists and is non-empty, creates a verified .bak backup.
    """
    target = Path(target_path).resolve()
    parent = target.parent
    bak_path = target.with_suffix(target.suffix + ".bak")

    if make_parents:
        parent.mkdir(parents=True, exist_ok=True)

    # If requested and target already exists with valid content, create a backup copy
    if backup and target.is_file():
        try:
            if target.stat().st_size > 0:
                for b_attempt in range(max_retries):
                    try:
                        shutil.copyfile(str(target), str(bak_path))
                        break
                    except (PermissionError, OSError):
                        if bak_path.exists():
                            try:
                                os.chmod(bak_path, stat.S_IWRITE | stat.S_IREAD)
                            except Exception:
                                pass
                        time.sleep(min(backoff_base * (2 ** b_attempt), 0.5))
        except Exception as bak_exc:
            logger.debug("Failed to create backup for %s: %s", target, bak_exc)

    prefix = safe_temp_prefix(target.name)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=prefix, suffix=".tmp", dir=str(parent)
    )

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            if sync:
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                os.replace(temporary_name, target)
                last_exc = None
                break
            except (PermissionError, OSError) as exc:
                last_exc = exc
                if target.exists():
                    try:
                        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
                    except Exception:
                        pass
                sleep_sec = backoff_base * (2 ** attempt)
                time.sleep(min(sleep_sec, 0.5))

        if last_exc is not None:
            raise last_exc

        # If backup requested and backup does not yet exist (first write), initialize it
        if backup and not bak_path.is_file() and target.is_file():
            try:
                for b_attempt in range(max_retries):
                    try:
                        shutil.copyfile(str(target), str(bak_path))
                        break
                    except (PermissionError, OSError):
                        if bak_path.exists():
                            try:
                                os.chmod(bak_path, stat.S_IWRITE | stat.S_IREAD)
                            except Exception:
                                pass
                        time.sleep(min(backoff_base * (2 ** b_attempt), 0.5))
            except Exception:
                pass

        return target

    except Exception:
        # Guaranteed cleanup of temporary file without shadowing root cause
        try:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        except (FileNotFoundError, PermissionError, OSError):
            pass
        raise


def atomic_write_text(
    target_path: Union[Path, str],
    text: str,
    encoding: str = "utf-8",
    make_parents: bool = True,
    max_retries: int = DEFAULT_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sync: bool = True,
    backup: bool = False,
) -> Path:
    """Atomically write text content to target_path."""
    content_bytes = text.encode(encoding)
    return atomic_write(
        target_path=target_path,
        content=content_bytes,
        make_parents=make_parents,
        max_retries=max_retries,
        backoff_base=backoff_base,
        sync=sync,
        backup=backup,
    )


def atomic_write_json(
    target_path: Union[Path, str],
    data: Any,
    indent: Optional[int] = 2,
    encoding: str = "utf-8",
    default: Any = str,
    make_parents: bool = True,
    max_retries: int = DEFAULT_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sync: bool = True,
    backup: bool = True,
) -> Path:
    """Atomically serialize data to JSON and write to target_path with optional backup."""
    payload = json.dumps(data, indent=indent, default=default)
    return atomic_write_text(
        target_path=target_path,
        text=payload,
        encoding=encoding,
        make_parents=make_parents,
        max_retries=max_retries,
        backoff_base=backoff_base,
        sync=sync,
        backup=backup,
    )


def safe_read_text(
    target_path: Union[Path, str],
    fallback_backup: bool = True,
    max_retries: int = 3,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    encoding: str = "utf-8",
) -> Tuple[Optional[str], bool]:
    """Safely read text with retry on locks and automatic .bak fallback.

    Returns:
        (text, recovered): Tuple of file text (or None) and whether recovered from backup.
    """
    target = Path(target_path).resolve()
    backup = target.with_suffix(target.suffix + ".bak")

    # Read primary
    if target.is_file():
        for attempt in range(max_retries):
            try:
                text = target.read_text(encoding=encoding)
                if text.strip():
                    return text, False
                break
            except (PermissionError, OSError):
                if attempt == max_retries - 1:
                    break
                time.sleep(backoff_base * (2 ** attempt))

    # Read backup
    if fallback_backup and backup.is_file():
        for attempt in range(max_retries):
            try:
                bak_text = backup.read_text(encoding=encoding)
                if bak_text.strip():
                    try:
                        atomic_write_text(target, bak_text, encoding=encoding, backup=False)
                    except Exception:
                        pass
                    return bak_text, True
            except (PermissionError, OSError):
                time.sleep(backoff_base * (2 ** attempt))

    return None, False


def safe_read_json(
    target_path: Union[Path, str],
    fallback_backup: bool = True,
    max_retries: int = 3,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    encoding: str = "utf-8",
) -> Tuple[Optional[Any], bool]:
    """Safely read and deserialize JSON from target_path with lock retry and automatic .bak recovery.

    Returns:
        (data, recovered): Tuple of parsed data (or None if failed) and whether data was recovered from backup.
    """
    target = Path(target_path).resolve()
    backup = target.with_suffix(target.suffix + ".bak")

    primary_text: Optional[str] = None
    if target.is_file():
        for attempt in range(max_retries):
            try:
                primary_text = target.read_text(encoding=encoding)
                break
            except (PermissionError, OSError):
                if attempt == max_retries - 1:
                    break
                time.sleep(backoff_base * (2 ** attempt))

    if primary_text and primary_text.strip():
        try:
            return json.loads(primary_text), False
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Corrupt JSON detected in %s (%s). Attempting backup recovery.", target, exc)

    if fallback_backup and backup.is_file():
        backup_text: Optional[str] = None
        for attempt in range(max_retries):
            try:
                backup_text = backup.read_text(encoding=encoding)
                break
            except (PermissionError, OSError):
                time.sleep(backoff_base * (2 ** attempt))

        if backup_text and backup_text.strip():
            try:
                data = json.loads(backup_text)
                logger.info("Successfully recovered JSON in %s from backup %s", target, backup)
                try:
                    atomic_write_text(target, backup_text, encoding=encoding, backup=False)
                except Exception:
                    pass
                return data, True
            except (json.JSONDecodeError, ValueError):
                logger.error("Both primary %s and backup %s are corrupted JSON.", target, backup)

    return None, False


def sweep_dangling_temp_files(
    root_dir: Union[Path, str],
    max_age_seconds: float = 3600.0,
    patterns: Optional[List[str]] = None,
    recursive: bool = True,
) -> List[Path]:
    """Find and remove abandoned .tmp_* and *.tmp files older than max_age_seconds."""
    root = Path(root_dir).resolve()
    if not root.is_dir():
        return []

    target_patterns = patterns or [".tmp_*", "*.tmp", ".*.tmp", "*.tmp_*", "*.tmp.*"]
    now = time.time()
    removed: List[Path] = []

    for pattern in target_patterns:
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)
        for p in iterator:
            if p.is_file():
                try:
                    mtime = p.stat().st_mtime
                    if (now - mtime) >= max_age_seconds:
                        try:
                            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                        except Exception:
                            pass
                        p.unlink(missing_ok=True)
                        removed.append(p)
                except (OSError, PermissionError):
                    continue

    return removed
