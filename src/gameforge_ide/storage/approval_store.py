"""Authoritative ApprovalStore for GameForge IDE (Blueprint §8.1).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading

_APPROVAL_ID_RE = re.compile(r"^apr_[0-9a-f]{12}$")
"""Authoritative ApprovalStore for GameForge IDE (Blueprint §8.1).

Provides crash-resilient persistence and state machine transitions for tool execution approvals:
- Atomic two-phase write with fsync persistence
- Windows NTFS file lock contention retry with exponential backoff
- Automatic .bak backup creation before replacement
- Self-healing corruption recovery from .bak
- Dangling temporary file garbage collection
"""

import logging
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional, Union

from .atomic import (
    atomic_write_json,
    safe_read_json,
    sweep_dangling_temp_files,
)

logger = logging.getLogger(__name__)


class ApprovalStore:
    """Persisted pending actions. Only the UI's approve path may execute them."""

    def __init__(self, workspace_root: Union[Path, str]):
        self.workspace_root = Path(workspace_root).resolve()
        self.root = self.workspace_root / ".gameforge" / "approvals"
        self._lock = threading.Lock()
        self._ensure_dir()

    def _approval_path(self, approval_id: str) -> Path:
        """Validates syntax and resolves path within protected approvals root."""
        if not isinstance(approval_id, str) or not _APPROVAL_ID_RE.fullmatch(approval_id):
            raise ValueError(f"Invalid approval identifier: {approval_id!r}")
        candidate = (self.root / f"{approval_id}.json").resolve()
        try:
            if candidate.parent.resolve() != self.root:
                raise ValueError("Approval path escaped its protected directory")
        except OSError:
            pass
        return candidate

    @staticmethod
    def compute_digest(tool: str, args: Dict[str, Any], session_id: Optional[str] = None) -> str:
        """Deterministic SHA-256 digest of canonical tool operation."""
        payload = {"tool": str(tool), "args": args, "session_id": str(session_id or "")}
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def record_execution_receipt(
        self,
        approval_id: str,
        status: str,
        exit_code: Optional[int] = None,
        output_summary: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stores a machine-verifiable execution receipt bound to an approved action."""
        with self._lock:
            rec = self.get(approval_id)
            if rec is None:
                raise ValueError(f"Cannot record receipt for non-existent approval {approval_id}")
            receipt = {
                "receipt_id": f"rcp_{approval_id[4:]}",
                "approval_id": approval_id,
                "operation_digest": rec.get("operation_digest", ""),
                "tool": rec.get("tool"),
                "status": status,
                "exit_code": exit_code,
                "output_summary": output_summary,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "details": details or {},
            }
            receipt_path = self.root / f"{approval_id}_receipt.json"
            atomic_write_json(receipt_path, receipt, indent=1, sync=True)
            return receipt

    def get_execution_receipt(self, approval_id: str) -> Optional[Dict[str, Any]]:
        """Reads stored execution receipt for an approval ID."""
        if not isinstance(approval_id, str) or not _APPROVAL_ID_RE.fullmatch(approval_id):
            return None
        receipt_path = self.root / f"{approval_id}_receipt.json"
        if not receipt_path.is_file():
            return None
        data, _ = safe_read_json(receipt_path, fallback_backup=False)
        return data if isinstance(data, dict) else None

    def _ensure_dir(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            sweep_dangling_temp_files(self.root, max_age_seconds=600.0, recursive=False)
        except Exception:
            pass

    def create(
        self,
        tool: str,
        args: Dict[str, Any],
        summary: str,
        consequence: str,
        session_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """plan_id marks a plan-task approval: approving it unblocks the plan, which runs the tool."""
        self._ensure_dir()
        digest = self.compute_digest(tool, args, session_id=session_id)
        rec = {
            "operation_digest": digest,
            "approval_id": "apr_" + secrets.token_hex(6),
            "tool": tool,
            "args": args,
            "summary": summary,
            "consequence": consequence,
            "session_id": session_id,
            "status": "PENDING",
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **extra,
        }
        if plan_id:
            rec["plan_id"] = plan_id

        self._write(rec)
        return rec

    def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        try:
            path = self._approval_path(approval_id)
        except (ValueError, TypeError):
            return None
        if not path.is_file():
            bak = path.with_suffix(".json.bak")
            if not bak.is_file():
                return None
        data, _ = safe_read_json(path, fallback_backup=True)
        return data if isinstance(data, dict) else None

    def list_pending(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out: List[Dict[str, Any]] = []
        try:
            for p in sorted(self.root.glob("apr_*.json")):
                if p.name.endswith(".bak") or ".tmp" in p.name:
                    continue
                data, _ = safe_read_json(p, fallback_backup=True)
                if isinstance(data, dict) and data.get("status") == "PENDING":
                    out.append(data)
        except OSError:
            pass
        return out

    def list_all(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out: List[Dict[str, Any]] = []
        try:
            for p in sorted(self.root.glob("apr_*.json")):
                if p.name.endswith(".bak") or ".tmp" in p.name:
                    continue
                data, _ = safe_read_json(p, fallback_backup=True)
                if isinstance(data, dict):
                    out.append(data)
        except OSError:
            pass
        out.sort(key=lambda r: r.get("created", ""), reverse=True)
        return out

    def transition(self, approval_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """PENDING -> APPROVED/REJECTED -> DONE/FAILED. Returns None if transition is not allowed."""
        with self._lock:
            rec = self.get(approval_id)
            allowed = {
                "PENDING": {"APPROVED", "REJECTED"},
                "APPROVED": {"DONE", "FAILED"},
            }
            if rec is None or status not in allowed.get(rec.get("status", ""), set()):
                return None
            rec["status"] = status
            rec[f"{status.lower()}_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            if result is not None:
                rec["result"] = result
            self._write(rec)
            return rec

    def delete(self, approval_id: str) -> bool:
        try:
            path = self._approval_path(approval_id)
        except (ValueError, TypeError):
            return False
        bak = path.with_suffix(".json.bak")
        deleted = False
        try:
            if path.exists():
                path.unlink(missing_ok=True)
                deleted = True
            if bak.exists():
                bak.unlink(missing_ok=True)
        except OSError:
            pass
        return deleted

    def _write(self, rec: Dict[str, Any]) -> None:
        path = self.root / f"{rec['approval_id']}.json"
        atomic_write_json(path, rec, indent=1, sync=True, backup=True)
