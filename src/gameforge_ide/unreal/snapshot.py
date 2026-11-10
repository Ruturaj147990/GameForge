"""Unreal Snapshot and Rollback Recovery Manager for GameForge IDE.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Pre-mutation snapshot recording SHA-256 hashes of all affected asset/source paths.
- Post-mutation hash verification.
- Safe rollback: only restores if current hash matches recorded post-mutation hash,
  preventing overwrites of independent user modifications.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

_UNREAL_VIRTUAL_ROOTS = ("/Game/", "/Engine/", "/Script/")
_SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class SnapshotItem(BaseModel):
    rel_path: str
    existed: bool
    pre_sha256: str
    post_sha256: Optional[str] = None
    pre_bytes_b64: str = ""  # Base64 encoded for binary or text assets


class SnapshotManifest(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    operation_name: str
    items: Dict[str, SnapshotItem] = Field(default_factory=dict)
    status: str = "RECORDED"  # "RECORDED", "COMMITTED", "ROLLED_BACK", "CONFLICT"


class SnapshotManager:
    """Manages pre-mutation asset snapshots and hash-verified rollback."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.storage_dir = (self.workspace_root / ".gameforge" / "snapshots").resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _resolve_workspace_path(self, p_str: str) -> Path:
        """Resolve a relative or Unreal virtual asset path safely within workspace_root."""
        if not isinstance(p_str, str) or not p_str.strip():
            raise ValueError(f"Invalid snapshot path: {p_str!r}")
        rel = p_str.strip().replace("\\", "/")
        if rel.startswith(_UNREAL_VIRTUAL_ROOTS):
            rel = rel.lstrip("/")
        candidate = (self.workspace_root / rel).resolve()
        if not candidate.is_relative_to(self.workspace_root):
            raise ValueError(f"Snapshot path escapes workspace boundary: {p_str!r}")
        return candidate

    def _snapshot_file(self, snapshot_id: str) -> Path:
        if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.match(snapshot_id):
            raise ValueError(f"Invalid snapshot_id: {snapshot_id!r}")
        path = (self.storage_dir / f"{snapshot_id}.json").resolve()
        if not path.is_relative_to(self.storage_dir):
            raise ValueError(f"Snapshot path escapes storage directory: {snapshot_id!r}")
        return path

    def create_pre_snapshot(self, operation_name: str, affected_paths: List[str]) -> str:
        """Records pre-mutation state of all specified file and asset paths."""
        snapshot = SnapshotManifest(operation_name=operation_name)

        for p_str in affected_paths:
            p = self._resolve_workspace_path(p_str)
            if p.exists() and p.is_file():
                raw = p.read_bytes()
                item = SnapshotItem(
                    rel_path=p_str,
                    existed=True,
                    pre_sha256=self._sha256(raw),
                    pre_bytes_b64=base64.b64encode(raw).decode("ascii"),
                )
            else:
                item = SnapshotItem(
                    rel_path=p_str,
                    existed=False,
                    pre_sha256="",
                    pre_bytes_b64="",
                )
            snapshot.items[p_str] = item

        self.save_snapshot(snapshot)
        return snapshot.snapshot_id

    def commit_post_state(self, snapshot_id: str) -> SnapshotManifest:
        """Records post-mutation state hashes for rollback integrity checks."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found.")

        for p_str, item in snapshot.items.items():
            p = self._resolve_workspace_path(p_str)
            if p.exists() and p.is_file():
                raw = p.read_bytes()
                item.post_sha256 = self._sha256(raw)
            else:
                item.post_sha256 = ""

        snapshot.status = "COMMITTED"
        self.save_snapshot(snapshot)
        return snapshot

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """Restores pre-mutation state if and only if no subsequent independent modifications occurred."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"status": "ERROR", "error": f"Snapshot {snapshot_id} not found."}

        restored: List[str] = []
        conflicts: List[str] = []

        # 1. Preflight check: verify all current hashes match post_sha256 and resolve bounds
        resolved_items: List[tuple[str, SnapshotItem, Path]] = []
        try:
            for p_str, item in snapshot.items.items():
                p = self._resolve_workspace_path(p_str)
                resolved_items.append((p_str, item, p))
        except ValueError as exc:
            return {"status": "ERROR", "snapshot_id": snapshot_id, "error": str(exc)}

        for p_str, item, p in resolved_items:
            current_bytes = p.read_bytes() if p.exists() and p.is_file() else b""
            current_hash = self._sha256(current_bytes) if p.exists() and p.is_file() else ""

            expected_post_hash = item.post_sha256 if item.post_sha256 is not None else item.pre_sha256
            if current_hash != expected_post_hash:
                conflicts.append(
                    f"{p_str}: Current hash ({current_hash[:8]}...) != expected post hash ({expected_post_hash[:8]}...). Modified independently."
                )

        if conflicts:
            snapshot.status = "CONFLICT"
            self.save_snapshot(snapshot)
            return {
                "status": "CONFLICT",
                "snapshot_id": snapshot_id,
                "conflicts": conflicts,
                "error": "Rollback refused to prevent overwriting independent user modifications.",
            }

        # 2. Execute restoration
        for p_str, item, p in resolved_items:
            if item.existed:
                try:
                    raw = base64.b64decode(item.pre_bytes_b64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    return {
                        "status": "ERROR",
                        "snapshot_id": snapshot_id,
                        "error": f"Corrupted snapshot payload for '{p_str}': {exc}",
                    }
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
                restored.append(p_str)
            else:
                # File was newly created by operation — delete it on rollback
                if p.exists():
                    p.unlink()
                    restored.append(f"{p_str} (deleted)")

        snapshot.status = "ROLLED_BACK"
        self.save_snapshot(snapshot)
        return {
            "status": "RESTORED",
            "snapshot_id": snapshot_id,
            "restored_paths": restored,
        }

    def save_snapshot(self, snapshot: SnapshotManifest) -> None:
        path = self._snapshot_file(snapshot.snapshot_id)
        path.write_text(json.dumps(snapshot.model_dump(), indent=2), encoding="utf-8", newline="\n")

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotManifest]:
        try:
            path = self._snapshot_file(snapshot_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            return SnapshotManifest.model_validate_json(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None
