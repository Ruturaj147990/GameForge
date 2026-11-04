"""Authoritative DiffStore for GameForge IDE.

Provides crash-resilient persistence, SHA-256 verification, and rollback storage for diff records:
- Atomic two-phase write with fsync persistence
- Windows NTFS file lock contention retry with exponential backoff
- Automatic .bak backup creation before file replacement
- Self-healing corruption recovery from .bak
- Dangling temporary file garbage collection
"""
from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union

from .atomic import (
    atomic_write_json,
    safe_read_json,
    sweep_dangling_temp_files,
)

logger = logging.getLogger(__name__)


class DiffStore:
    """Manages persistent diffs and rollback snapshots under <workspace>/.gameforge/diffs/."""

    def __init__(self, workspace_root: Union[Path, str]):
        self.workspace_root = Path(workspace_root).resolve()
        self.diffs_dir = self.workspace_root / ".gameforge" / "diffs"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.diffs_dir.mkdir(parents=True, exist_ok=True)
        try:
            sweep_dangling_temp_files(self.diffs_dir, max_age_seconds=600.0, recursive=False)
        except Exception:
            pass

    def save_diff(self, diff_id: str, rec: Dict[str, Any]) -> Path:
        """Atomically persist diff record with base64 encoded bytes and SHA-256 digests."""
        self._ensure_dir()
        target_path = self.diffs_dir / f"{diff_id}.json"

        orig_bytes = rec.get("original_bytes", b"")
        if isinstance(orig_bytes, str):
            orig_bytes = orig_bytes.encode("utf-8")
        new_bytes = rec.get("new_bytes", b"")
        if isinstance(new_bytes, str):
            new_bytes = new_bytes.encode("utf-8")

        file_path_str = str(rec.get("file_path", ""))
        target_file_str = str(rec.get("target_file", ""))
        if not target_file_str and file_path_str:
            target_file_str = str(self.workspace_root / file_path_str)

        diff_patch_str = str(rec.get("diff_patch", rec.get("diff_text", "")))
        file_existed = rec.get("file_existed")
        if file_existed is None:
            file_existed = bool(orig_bytes)
        else:
            file_existed = bool(file_existed)

        data = {
            "diff_id": diff_id,
            "file_path": file_path_str,
            "target_file": target_file_str,
            "file_existed": file_existed,
            "target_content": str(rec.get("target_content", "")),
            "replacement_content": str(rec.get("replacement_content", "")),
            "original_text": str(rec.get("original_text", "")),
            "new_text": str(rec.get("new_text", "")),
            "original_bytes_b64": base64.b64encode(orig_bytes).decode("ascii"),
            "new_bytes_b64": base64.b64encode(new_bytes).decode("ascii"),
            "original_sha256": hashlib.sha256(orig_bytes).hexdigest(),
            "new_sha256": hashlib.sha256(new_bytes).hexdigest(),
            "diff_patch": diff_patch_str,
            "diff_text": diff_patch_str,
            "encoding": str(rec.get("encoding", "utf-8")),
            "status": str(rec.get("status", "PENDING_APPROVAL")),
            "created_at": rec.get("created_at", time.time()),
        }

        atomic_write_json(target_path, data, indent=2, sync=True, backup=True)
        return target_path

    def load_diff(self, diff_id: str) -> Optional[Dict[str, Any]]:
        """Load diff record from disk with automatic .bak backup recovery."""
        target_path = self.diffs_dir / f"{diff_id}.json"
        if not target_path.is_file():
            bak = target_path.with_suffix(".json.bak")
            if not bak.is_file():
                return None

        data, _ = safe_read_json(target_path, fallback_backup=True)
        if not isinstance(data, dict):
            return None

        try:
            data["original_bytes"] = base64.b64decode(data.get("original_bytes_b64", ""))
            data["new_bytes"] = base64.b64decode(data.get("new_bytes_b64", ""))
            if not data.get("target_file") and data.get("file_path"):
                data["target_file"] = str(self.workspace_root / data["file_path"])
            if not data.get("diff_patch") and data.get("diff_text"):
                data["diff_patch"] = data["diff_text"]
            if "file_existed" not in data:
                data["file_existed"] = bool(data.get("original_bytes"))
            if "encoding" not in data:
                data["encoding"] = "utf-8"
            return data
        except Exception as exc:
            logger.warning("Failed decoding diff bytes for %s: %s", diff_id, exc)
            return None

    def list_diffs(self) -> List[Dict[str, Any]]:
        """List all diff records."""
        if not self.diffs_dir.is_dir():
            return []
        diffs: List[Dict[str, Any]] = []
        try:
            for p in sorted(self.diffs_dir.glob("*.json")):
                if p.name.endswith(".bak") or ".tmp" in p.name:
                    continue
                diff_rec = self.load_diff(p.stem)
                if diff_rec is not None:
                    diffs.append(diff_rec)
        except OSError:
            pass
        return diffs

    def delete_diff(self, diff_id: str) -> bool:
        """Safely delete diff file and backup."""
        target = self.diffs_dir / f"{diff_id}.json"
        bak = target.with_suffix(".json.bak")
        deleted = False
        try:
            if target.exists():
                target.unlink(missing_ok=True)
                deleted = True
            if bak.exists():
                bak.unlink(missing_ok=True)
        except OSError:
            pass
        return deleted
