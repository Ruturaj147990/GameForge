"""Safe File Editing, Diff Generation, and Rollback for GameForge IDE."""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from ..security.boundary import BoundaryManager, SecurityViolationError


class EditTools:
    """Manages diff generation, patch approval, atomic edits, and rollback snapshots."""

    def __init__(self, boundary: BoundaryManager):
        self.boundary = boundary
        self.pending_diffs: Dict[str, Dict[str, Any]] = {}
        self.applied_diffs: Dict[str, Dict[str, Any]] = {}
        self.diffs_dir = self.boundary.workspace_root / ".gameforge" / "diffs"
        try:
            self.diffs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _save_diff_to_disk(self, rec: Dict[str, Any]) -> None:
        try:
            self.diffs_dir.mkdir(parents=True, exist_ok=True)
            diff_id = rec["diff_id"]
            data = {
                "diff_id": diff_id,
                "file_path": rec.get("file_path", ""),
                "target_file": rec.get("target_file", ""),
                "original_text": rec.get("original_text", ""),
                "new_text": rec.get("new_text", ""),
                "original_bytes_b64": base64.b64encode(rec.get("original_bytes", b"")).decode("ascii"),
                "new_bytes_b64": base64.b64encode(rec.get("new_bytes", b"")).decode("ascii"),
                "original_sha256": rec.get("original_sha256", ""),
                "new_sha256": rec.get("new_sha256", ""),
                "diff_patch": rec.get("diff_patch", ""),
                "status": rec.get("status", "PENDING_APPROVAL"),
            }
            target_path = self.diffs_dir / f"{diff_id}.json"
            target_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_diff_from_disk(self, diff_id: str) -> Optional[Dict[str, Any]]:
        target_path = self.diffs_dir / f"{diff_id}.json"
        if not target_path.exists():
            return None
        try:
            data = json.loads(target_path.read_text(encoding="utf-8"))
            data["original_bytes"] = base64.b64decode(data.get("original_bytes_b64", ""))
            data["new_bytes"] = base64.b64decode(data.get("new_bytes_b64", ""))
            return data
        except Exception:
            return None

    @staticmethod
    def _digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _atomic_write(target_file: Path, content: bytes) -> None:
        """Write content atomically so an interrupted apply cannot truncate a file."""
        target_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target_file.name}.", suffix=".tmp", dir=str(target_file.parent)
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target_file)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


    def propose_edit(
        self,
        subpath: str = "",
        target_content: str = "",
        replacement_content: str = "",
        file_path: str = "",
    ) -> Dict[str, Any]:
        """Proposes a code change, verifies path, and generates a unified diff for review."""
        effective_path = subpath or file_path
        target_file = self.boundary.validate_path(effective_path, allow_write=True)

        original_bytes = target_file.read_bytes() if target_file.exists() else b""
        original_text = original_bytes.decode("utf-8", errors="replace")

        # Check if target_content is present in file (if not creating fresh file)
        if original_text and target_content not in original_text:
            norm_orig = original_text.replace("\r\n", "\n")
            norm_target = target_content.replace("\r\n", "\n")
            if norm_target in norm_orig:
                if "\r\n" in original_text:
                    target_content = norm_target.replace("\n", "\r\n")
                    replacement_content = replacement_content.replace("\r\n", "\n").replace("\n", "\r\n")
            else:
                return {
                    "status": "ERROR",
                    "error": f"Target content block not found in file: {subpath}",
                }

        if original_text:
            new_text = original_text.replace(target_content, replacement_content, 1)
        else:
            new_text = replacement_content
        new_bytes = new_text.encode("utf-8")

        # Generate unified diff
        orig_lines = original_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        rel_path = str(target_file.relative_to(self.boundary.workspace_root).as_posix())

        diff_lines = list(difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        ))
        diff_patch = "\n".join(diff_lines)

        diff_id = str(uuid.uuid4())
        diff_record = {
            "diff_id": diff_id,
            "file_path": rel_path,
            "target_file": str(target_file),
            "original_text": original_text,
            "new_text": new_text,
            "original_bytes": original_bytes,
            "new_bytes": new_bytes,
            "original_sha256": self._digest(original_bytes),
            "new_sha256": self._digest(new_bytes),
            "diff_patch": diff_patch,
            "status": "PENDING_APPROVAL",
        }
        self.pending_diffs[diff_id] = diff_record
        self._save_diff_to_disk(diff_record)

        return {
            "status": "PENDING_APPROVAL",
            "diff_id": diff_id,
            "file_path": rel_path,
            "diff_patch": diff_patch,
            "message": "Diff generated successfully. Requires developer approval to apply.",
        }

    def apply_diff(self, diff_id: str) -> Dict[str, Any]:
        """Applies an approved diff to the filesystem and saves rollback state."""
        if diff_id not in self.pending_diffs:
            loaded = self._load_diff_from_disk(diff_id)
            if loaded and loaded.get("status") == "PENDING_APPROVAL":
                self.pending_diffs[diff_id] = loaded
            else:
                return {"status": "ERROR", "error": f"Pending diff {diff_id} not found."}

        rec = self.pending_diffs[diff_id]
        target_file = Path(rec["target_file"])

        # Re-validate security boundary
        self.boundary.validate_path(target_file, allow_write=True)

        current_bytes = target_file.read_bytes() if target_file.exists() else b""
        if self._digest(current_bytes) != rec["original_sha256"]:
            return {
                "status": "STALE",
                "diff_id": diff_id,
                "file_path": rec["file_path"],
                "error": "File changed after this diff was proposed; review a newly generated diff before applying.",
            }

        try:
            self._atomic_write(target_file, rec["new_bytes"])

            rec["status"] = "APPLIED"
            self.applied_diffs[diff_id] = rec
            del self.pending_diffs[diff_id]
            self._save_diff_to_disk(rec)

            return {
                "status": "SUCCESS",
                "diff_id": diff_id,
                "file_path": rec["file_path"],
                "message": f"Successfully applied changes to {rec['file_path']}.",
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Failed to write file: {e}"}

    def reject_diff(self, diff_id: str, reason: str = "User rejected") -> Dict[str, Any]:
        """Rejects a proposed diff and discards it without touching the filesystem."""
        if diff_id not in self.pending_diffs:
            loaded = self._load_diff_from_disk(diff_id)
            if loaded and loaded.get("status") == "PENDING_APPROVAL":
                self.pending_diffs[diff_id] = loaded
            else:
                return {"status": "ERROR", "error": f"Pending diff {diff_id} not found."}

        rec = self.pending_diffs.pop(diff_id)
        rec["status"] = "REJECTED"
        self._save_diff_to_disk(rec)
        return {
            "status": "REJECTED",
            "diff_id": diff_id,
            "file_path": rec["file_path"],
            "reason": reason,
        }

    def rollback_diff(self, diff_id: str) -> Dict[str, Any]:
        """Rolls back an applied diff to its original pre-edit state."""
        if diff_id not in self.applied_diffs:
            loaded = self._load_diff_from_disk(diff_id)
            if loaded and loaded.get("status") == "APPLIED":
                self.applied_diffs[diff_id] = loaded
            else:
                return {"status": "ERROR", "error": f"Applied diff {diff_id} not found for rollback."}

        rec = self.applied_diffs[diff_id]
        target_file = Path(rec["target_file"])
        self.boundary.validate_path(target_file, allow_write=True)

        current_bytes = target_file.read_bytes() if target_file.exists() else b""
        if self._digest(current_bytes) != rec["new_sha256"]:
            return {
                "status": "STALE",
                "diff_id": diff_id,
                "file_path": rec["file_path"],
                "error": "File changed after this diff was applied; rollback would overwrite newer work.",
            }

        try:
            if rec["original_bytes"] == b"":
                # File was newly created, delete it
                if target_file.exists():
                    target_file.unlink()
            else:
                self._atomic_write(target_file, rec["original_bytes"])

            rec["status"] = "ROLLED_BACK"
            self._save_diff_to_disk(rec)
            return {
                "status": "SUCCESS",
                "diff_id": diff_id,
                "file_path": rec["file_path"],
                "message": f"Successfully rolled back {rec['file_path']} to pre-edit state.",
            }

        except Exception as e:
            return {"status": "ERROR", "error": f"Rollback failed: {e}"}
