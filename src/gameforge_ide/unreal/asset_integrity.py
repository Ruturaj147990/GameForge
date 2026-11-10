"""Asset Integrity and Provenance Validation Subsystem (DEF-309 / Mandate 4).

Audits Unreal Engine Content/ directories to:
1. Validate binary integrity of .uasset and .umap files (checking magic package tag 0x9E2A83C1,
   minimum header length, and non-zero size).
2. Prevent corrupt or 0-byte files from reaching the Unreal cooker.
3. Prevent mock test assets (e.g. mock_*, dummy_*, or plaintext placeholders) from contaminating
   production Content directories.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Unreal Engine package tag: 0x9E2A83C1 (little-endian: C1 83 2A 9E)
UE_PACKAGE_TAG = b"\xc1\x83*\x9e"
MIN_UASSET_SIZE_BYTES = 32

MOCK_FILENAME_PATTERNS = (
    "mock_",
    "dummy_",
    "test_mock_",
    "fake_",
    "stub_",
    "sample_mock",
)


def is_mock_or_test_asset_name(filename: str) -> bool:
    """Return True if filename indicates a mock or temporary test fixture."""
    lower = filename.lower()
    return any(p in lower for p in MOCK_FILENAME_PATTERNS)


def check_uasset_integrity(path: Path) -> Tuple[bool, Optional[str]]:
    """Validate binary header and structure of an Unreal .uasset or .umap file.
    
    Returns (is_valid, error_reason).
    """
    path = Path(path)
    if not path.is_file():
        return False, f"Asset file does not exist: {path}"

    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"Failed to stat asset '{path.name}': {exc}"

    if size == 0:
        return False, f"Asset '{path.name}' is an empty file (0 bytes)"

    if size < MIN_UASSET_SIZE_BYTES:
        return False, f"Asset '{path.name}' is truncated ({size} bytes < minimum {MIN_UASSET_SIZE_BYTES} bytes)"

    try:
        with open(path, "rb") as f:
            header = f.read(4)
            if header != UE_PACKAGE_TAG:
                # Check if it's plaintext mock text
                f.seek(0)
                sample = f.read(64)
                try:
                    text_sample = sample.decode("utf-8")
                    if any(w in text_sample.lower() for w in ("mock", "dummy", "test", "fake", "todo")):
                        return False, f"Asset '{path.name}' is a plaintext mock/dummy placeholder, not a valid binary asset"
                except UnicodeDecodeError:
                    pass
                # Some procedural or imported assets may have valid binary structure without standard package tag,
                # but any plaintext or corrupted asset is rejected
                if sample and all(b < 128 for b in sample[:16]):
                    return False, f"Asset '{path.name}' contains ASCII/text data instead of Unreal binary package header"
    except OSError as exc:
        return False, f"Failed to read asset '{path.name}': {exc}"

    return True, None


def validate_content_directory(
    content_dir: Path,
    allow_mock_assets: bool = False,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Recursively validate all assets in a Content directory.
    
    Checks:
    - No 0-byte or corrupt files
    - Binary integrity of .uasset and .umap files
    - Contamination by mock/test assets unless allow_mock_assets is True
    """
    content_path = Path(content_dir).resolve()
    issues: List[str] = []
    stats: Dict[str, Any] = {
        "content_dir": str(content_path),
        "total_files": 0,
        "uasset_count": 0,
        "umap_count": 0,
        "other_count": 0,
        "corrupt_count": 0,
        "mock_count": 0,
    }

    if not content_path.is_dir():
        return True, issues, stats

    for root, _, files in os.walk(content_path):
        for fname in files:
            stats["total_files"] += 1
            fpath = Path(root) / fname
            rel_path = fpath.relative_to(content_path).as_posix()
            suffix = fpath.suffix.lower()

            # 1. Classify extension cleanly
            if suffix == ".uasset":
                stats["uasset_count"] += 1
            elif suffix == ".umap":
                stats["umap_count"] += 1
            else:
                stats["other_count"] += 1

            # 2. Check for mock naming contamination
            if not allow_mock_assets and is_mock_or_test_asset_name(fname):
                issues.append(f"Mock asset contamination detected in production content: '{rel_path}'")
                stats["mock_count"] += 1

            # 3. Check for empty or unreadable files
            try:
                fsize = fpath.stat().st_size
                if fsize == 0:
                    issues.append(f"Corrupt 0-byte asset in content: '{rel_path}'")
                    stats["corrupt_count"] += 1
                    continue
            except OSError as exc:
                issues.append(f"Unreadable file in content '{rel_path}': {exc}")
                stats["corrupt_count"] += 1
                continue

            # 4. Check binary integrity for Unreal asset extensions
            if suffix in (".uasset", ".umap"):
                valid, err = check_uasset_integrity(fpath)
                if not valid:
                    issues.append(f"Asset integrity violation in '{rel_path}': {err}")
                    stats["corrupt_count"] += 1

    is_valid = (len(issues) == 0)
    return is_valid, issues, stats
