"""Validation and persistence for metadata received from the Unreal editor."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field


MAX_CONTEXT_FILE_BYTES = 16 * 1024


class UnrealEditorContext(BaseModel):
    """Small, bounded editor metadata record; never executable instructions."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(default="", max_length=256)
    engine_version: str = Field(default="", max_length=64)
    selected_actor: str = Field(default="", max_length=4096)
    active_asset: str = Field(default="", max_length=1024)
    open_assets: List[str] = Field(default_factory=list, max_length=32)
    last_sync: str = Field(default="", max_length=64)

    @classmethod
    def context_path(cls, workspace_root: Path) -> Path:
        return workspace_root.resolve() / ".gameforge" / "unreal_context.json"


def persist_unreal_context(workspace_root: Path, context: UnrealEditorContext) -> dict:
    """Atomically save validated editor metadata under the selected workspace."""
    root = workspace_root.resolve()
    metadata_dir = root / ".gameforge"
    if metadata_dir.is_symlink() and not metadata_dir.resolve().is_relative_to(root):
        raise ValueError("Workspace metadata path resolves outside the workspace.")
    metadata_dir.mkdir(parents=True, exist_ok=True)
    destination = UnrealEditorContext.context_path(root)
    if not destination.parent.resolve().is_relative_to(root):
        raise ValueError("Unreal context path resolves outside the workspace.")

    payload = context.model_dump()
    payload["last_sync"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_CONTEXT_FILE_BYTES:
        raise ValueError("Unreal context exceeds the configured 16 KiB limit.")

    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        for attempt in range(5):
            try:
                temporary.replace(destination)
                break
            except (PermissionError, OSError):
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except Exception:
                pass
    return payload


def load_unreal_context(workspace_root: Path) -> dict:
    """Read a bounded context record; malformed or missing data is ignored."""
    path = UnrealEditorContext.context_path(workspace_root)
    try:
        if path.stat().st_size > MAX_CONTEXT_FILE_BYTES:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return UnrealEditorContext.model_validate(payload).model_dump() | {
            "last_sync": str(payload.get("last_sync", ""))[:64]
        }
    except (OSError, ValueError, TypeError):
        return {}
