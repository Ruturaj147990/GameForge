"""Safe File Editing, Diff Generation, and Rollback for GameForge IDE."""

from __future__ import annotations

import base64
import difflib
import hashlib
import itertools
import json
import os
import stat
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..security.boundary import BoundaryManager, SecurityViolationError
from ...storage.atomic import atomic_write, atomic_write_json
from ...storage.diff_store import DiffStore


class EditTools:
    """Manages diff generation, patch approval, atomic edits, and rollback snapshots."""

    def __init__(self, boundary: BoundaryManager):
        self.boundary = boundary
        self.pending_diffs: Dict[str, Dict[str, Any]] = {}
        self.applied_diffs: Dict[str, Dict[str, Any]] = {}
        self.diff_store = DiffStore(self.boundary.workspace_root)
        self.diffs_dir = self.diff_store.diffs_dir

    def _save_diff_to_disk(self, rec: Dict[str, Any]) -> None:
        try:
            self.diff_store.save_diff(rec["diff_id"], rec)
        except Exception:
            pass

    def _load_diff_from_disk(self, diff_id: str) -> Optional[Dict[str, Any]]:
        data = self.diff_store.load_diff(diff_id)
        if data:
            if not data.get("target_file") and data.get("file_path"):
                data["target_file"] = str(self.boundary.workspace_root / data["file_path"])
            if not data.get("diff_patch") and data.get("diff_text"):
                data["diff_patch"] = data["diff_text"]
            if "file_existed" not in data:
                data["file_existed"] = bool(data.get("original_bytes"))
            if "encoding" not in data:
                data["encoding"] = "utf-8"
        return data

    @staticmethod
    def _digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _detect_encoding(data: bytes) -> str:
        """Detect encoding from byte BOM or content: UTF-8-BOM, UTF-16-LE, UTF-16-BE, UTF-8."""
        if not data:
            return "utf-8"
        if data.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if data.startswith(b"\xff\xfe"):
            return "utf-16-le"
        if data.startswith(b"\xfe\xff"):
            return "utf-16-be"
        try:
            data.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            try:
                data.decode("utf-16")
                return "utf-16"
            except UnicodeDecodeError:
                return "utf-8"

    @staticmethod
    def _atomic_write(target_file: Path, content: bytes) -> None:
        """Write content atomically so an interrupted apply cannot truncate a file."""
        atomic_write(target_path=target_file, content=content)

    def propose_edit(
        self,
        subpath: str = "",
        target_content: str = "",
        replacement_content: str = "",
        file_path: str = "",
        path: str = "",
    ) -> Dict[str, Any]:
        """Proposes a code change, verifies path, and generates a unified diff for review."""
        effective_path = subpath or file_path or path

        # Strip accidental markdown code block fences if replacement_content is wrapped in ```
        if replacement_content:
            stripped_rc = replacement_content.strip()
            if stripped_rc.startswith("```") and stripped_rc.endswith("```"):
                rc_lines = stripped_rc.splitlines()
                if len(rc_lines) >= 2 and rc_lines[0].startswith("```") and rc_lines[-1].strip() == "```":
                    replacement_content = "\n".join(rc_lines[1:-1])
                    if replacement_content and not replacement_content.endswith("\n"):
                        replacement_content += "\n"
        try:
            target_file = self.boundary.validate_path(effective_path, allow_write=True)
        except (SecurityViolationError, ValueError) as exc:
            return {
                "status": "BLOCKED",
                "error": f"Security boundary violation: {exc}",
            }

        if not target_file.exists():
            clean_sub = effective_path.replace("\\", "/").strip("/")
            parts = clean_sub.split("/")
            if parts and parts[0].lower() == self.boundary.workspace_root.name.lower():
                remapped = "/".join(parts[1:])
                try:
                    remapped_file = self.boundary.validate_path(remapped, allow_write=True)
                    if remapped_file.exists():
                        target_file = remapped_file
                except Exception:
                    pass

        if target_file.exists() and target_file.is_dir():
            return {
                "status": "ERROR",
                "error": f"Target path is a directory, not a file: {effective_path}",
            }

        file_existed = target_file.is_file()
        original_bytes = target_file.read_bytes() if target_file.exists() else b""
        encoding = self._detect_encoding(original_bytes) if original_bytes else "utf-8"
        original_text = original_bytes.decode(encoding, errors="replace") if original_bytes else ""

        if original_text and target_content and target_content == replacement_content:
            return {
                "status": "NOOP",
                "message": f"No changes proposed: replacement_content is identical to target_content for {effective_path}.",
            }

        # Check if target_content is present in file (if not creating fresh file)
        if original_text and not target_content:
            # If target_content is empty but replacement_content is provided, this represents
            # a full-file rewrite intention. Allow full-file replacement if replacement_content is non-empty.
            if replacement_content:
                target_content = original_text
            else:
                return {
                    "status": "ERROR",
                    "error": f"target_content cannot be empty when editing existing file: {subpath}. Provide the exact code block to replace.",
                }

        new_text = original_text
        if original_text:
            if target_content in original_text:
                new_text = original_text.replace(target_content, replacement_content, 1)
            else:
                # 1. Robust normalized matching across CRLF and LF line endings
                norm_orig = original_text.replace("\r\n", "\n")
                norm_target = target_content.replace("\r\n", "\n")
                norm_repl = replacement_content.replace("\r\n", "\n")

                if norm_target in norm_orig:
                    pos = norm_orig.find(norm_target)
                    end_pos = pos + len(norm_target)

                    orig_lines = original_text.splitlines(keepends=True)
                    cum_lengths = [0] + list(itertools.accumulate([len(l) for l in orig_lines]))

                    line_idx = norm_orig[:pos].count("\n")
                    last_nl = norm_orig[:pos].rfind("\n")
                    col_idx = pos - (last_nl + 1) if last_nl != -1 else pos
                    o_start = cum_lengths[line_idx] + col_idx if line_idx < len(cum_lengths) else len(original_text)

                    end_line_idx = norm_orig[:end_pos].count("\n")
                    end_last_nl = norm_orig[:end_pos].rfind("\n")
                    end_col_idx = end_pos - (end_last_nl + 1) if end_last_nl != -1 else end_pos
                    o_end = cum_lengths[end_line_idx] + end_col_idx if end_line_idx < len(cum_lengths) else len(original_text)

                    matched_block = original_text[o_start:o_end]
                    line_ending = "\r\n" if "\r\n" in matched_block else ("\r\n" if "\r\n" in original_text else "\n")
                    adjusted_repl = norm_repl.replace("\n", line_ending)
                    new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                else:
                    # 2. Resilient Whitespace-Tolerant Matching (handles indent and minor formatting drift)
                    orig_lines_raw = norm_orig.splitlines(keepends=True)
                    orig_stripped = [l.strip() for l in orig_lines_raw]
                    target_lines_raw = norm_target.splitlines(keepends=True)
                    target_stripped = [l.strip() for l in target_lines_raw if l.strip()]

                    found_match = False
                    if target_stripped and len(target_stripped) <= len(orig_stripped):
                        first_t = target_stripped[0]
                        for i in range(len(orig_stripped) - len(target_stripped) + 1):
                            if orig_stripped[i] == first_t:
                                # Check if subsequent stripped lines match
                                match_len = len(target_stripped)
                                if [l for l in orig_stripped[i : i + match_len] if l] == target_stripped:
                                    # Calculate start and end character positions in original_text
                                    orig_lines_with_nl = original_text.splitlines(keepends=True)
                                    cum_lens = [0] + list(itertools.accumulate([len(l) for l in orig_lines_with_nl]))
                                    o_start = cum_lens[i]
                                    end_idx = min(i + match_len, len(orig_lines_with_nl))
                                    o_end = cum_lens[end_idx] if end_idx < len(cum_lens) else len(original_text)

                                    line_ending = "\r\n" if "\r\n" in original_text else "\n"
                                    adjusted_repl = norm_repl.replace("\n", line_ending)
                                    new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                                    found_match = True
                                    break

                    if not found_match:
                        # 3. Fuzzy ratio fallback for near-identical single-block replacements
                        # Only attempted if target_content is multi-line to avoid false positive short matches
                        if len(target_content.splitlines()) >= 3:
                            matcher = difflib.SequenceMatcher(None, norm_orig, norm_target)
                            match = matcher.find_longest_match(0, len(norm_orig), 0, len(norm_target))
                            if match.size >= int(len(norm_target) * 0.88):
                                o_start_norm = match.a
                                o_end_norm = match.a + match.size
                                orig_lines = original_text.splitlines(keepends=True)
                                cum_lengths = [0] + list(itertools.accumulate([len(l) for l in orig_lines]))

                                line_idx = norm_orig[:o_start_norm].count("\n")
                                last_nl = norm_orig[:o_start_norm].rfind("\n")
                                col_idx = o_start_norm - (last_nl + 1) if last_nl != -1 else o_start_norm
                                o_start = cum_lengths[line_idx] + col_idx if line_idx < len(cum_lengths) else len(original_text)

                                end_line_idx = norm_orig[:o_end_norm].count("\n")
                                end_last_nl = norm_orig[:o_end_norm].rfind("\n")
                                end_col_idx = o_end_norm - (end_last_nl + 1) if end_last_nl != -1 else o_end_norm
                                o_end = cum_lengths[end_line_idx] + end_col_idx if end_line_idx < len(cum_lengths) else len(original_text)

                                line_ending = "\r\n" if "\r\n" in original_text else "\n"
                                adjusted_repl = norm_repl.replace("\n", line_ending)
                                new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                                found_match = True

                    if not found_match:
                        return {
                            "status": "ERROR",
                            "error": f"Target content block not found in file: {subpath}",
                        }

            if new_text == original_text:
                return {
                    "status": "ERROR",
                    "error": f"Failed to apply replacement in file: {effective_path}. Replacement did not produce any changes.",
                }
        else:
            new_text = replacement_content

        new_bytes = new_text.encode(encoding)

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
            "file_existed": file_existed,
            "target_content": target_content,
            "replacement_content": replacement_content,
            "original_text": original_text,
            "new_text": new_text,
            "original_bytes": original_bytes,
            "new_bytes": new_bytes,
            "original_sha256": self._digest(original_bytes),
            "new_sha256": self._digest(new_bytes),
            "diff_patch": diff_patch,
            "diff_text": diff_patch,
            "encoding": encoding,
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
        try:
            self.boundary.validate_path(target_file, allow_write=True)
        except (SecurityViolationError, ValueError) as exc:
            return {
                "status": "BLOCKED",
                "error": f"Security boundary violation for {rec.get('file_path', '')}: {exc}",
            }

        # Check for external file creation or deletion
        if rec.get("file_existed") is not None and rec["file_existed"] != target_file.is_file():
            return {
                "status": "STALE",
                "diff_id": diff_id,
                "file_path": rec["file_path"],
                "error": "File existence state changed after this diff was proposed; review a newly generated diff before applying.",
            }

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
        try:
            self.boundary.validate_path(target_file, allow_write=True)
        except (SecurityViolationError, ValueError) as exc:
            return {
                "status": "BLOCKED",
                "error": f"Security boundary violation for {rec.get('file_path', '')}: {exc}",
            }

        current_bytes = target_file.read_bytes() if target_file.exists() else b""
        if self._digest(current_bytes) != rec["new_sha256"]:
            return {
                "status": "STALE",
                "diff_id": diff_id,
                "file_path": rec["file_path"],
                "error": "File changed after this diff was applied; rollback would overwrite newer work.",
            }

        try:
            file_existed = rec.get("file_existed")
            if file_existed is None:
                file_existed = True if rec.get("original_bytes") else False

            if not file_existed:
                # File was newly created by this edit, delete it with read-only clearance & retry
                if target_file.exists():
                    try:
                        os.chmod(target_file, stat.S_IWRITE | stat.S_IREAD)
                    except Exception:
                        pass
                    deleted = False
                    for attempt in range(5):
                        try:
                            target_file.unlink()
                            deleted = True
                            break
                        except (PermissionError, OSError):
                            time.sleep(0.05 * (2 ** attempt))
                            try:
                                os.chmod(target_file, stat.S_IWRITE | stat.S_IREAD)
                            except Exception:
                                pass
                    if not deleted and target_file.exists():
                        target_file.unlink()

                    # Clean up empty parent directories up to workspace root
                    try:
                        parent = target_file.parent
                        while parent != self.boundary.workspace_root and parent.is_relative_to(self.boundary.workspace_root):
                            if not any(parent.iterdir()):
                                parent.rmdir()
                                parent = parent.parent
                            else:
                                break
                    except Exception:
                        pass
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

    def apply_batch(self, diff_ids: List[str]) -> Dict[str, Any]:
        """Atomically applies a batch of approved diffs across multiple files.
        
        Performs pre-validation on all diffs and hashes first; if any diff is stale
        or invalid, the transaction aborts with zero filesystem modifications.
        If a write failure occurs mid-batch, previously applied diffs in the batch
        are rolled back automatically and restored to PENDING_APPROVAL.
        """
        if not diff_ids:
            return {"status": "NOOP", "applied_diff_ids": [], "files": []}

        # Phase 1: Pre-validation (dry run)
        validated_records: List[Dict[str, Any]] = []
        seen_targets: set[str] = set()
        for diff_id in diff_ids:
            if diff_id not in self.pending_diffs:
                loaded = self._load_diff_from_disk(diff_id)
                if loaded and loaded.get("status") == "PENDING_APPROVAL":
                    self.pending_diffs[diff_id] = loaded
                else:
                    return {
                        "status": "ERROR",
                        "error": f"Pending diff {diff_id} not found for batch application.",
                        "failed_diff_id": diff_id,
                    }

            rec = self.pending_diffs[diff_id]
            target_file = Path(rec["target_file"])
            try:
                self.boundary.validate_path(target_file, allow_write=True)
            except (SecurityViolationError, ValueError) as e:
                return {
                    "status": "BLOCKED",
                    "error": f"Security boundary violation for {rec['file_path']}: {e}",
                    "failed_diff_id": diff_id,
                }

            norm_target = str(target_file.resolve()).lower()
            if norm_target in seen_targets:
                return {
                    "status": "ERROR",
                    "error": f"Duplicate target file in batch: '{rec['file_path']}' is targeted by multiple diffs. Consolidate changes into a single diff per file.",
                    "failed_diff_id": diff_id,
                }
            seen_targets.add(norm_target)

            if rec.get("file_existed") is not None and rec["file_existed"] != target_file.is_file():
                return {
                    "status": "STALE",
                    "failed_diff_id": diff_id,
                    "file_path": rec["file_path"],
                    "error": f"File {rec['file_path']} existence changed after diff was proposed; batch aborted.",
                }

            current_bytes = target_file.read_bytes() if target_file.exists() else b""
            if self._digest(current_bytes) != rec["original_sha256"]:
                return {
                    "status": "STALE",
                    "failed_diff_id": diff_id,
                    "file_path": rec["file_path"],
                    "error": f"File {rec['file_path']} changed after diff {diff_id} was proposed; batch aborted.",
                }
            validated_records.append(rec)

        # Phase 2: Staged execution with automatic rollback on error
        applied_now: List[str] = []
        applied_files: List[str] = []
        try:
            for rec in validated_records:
                diff_id = rec["diff_id"]
                target_file = Path(rec["target_file"])
                self._atomic_write(target_file, rec["new_bytes"])

                rec["status"] = "APPLIED"
                self.applied_diffs[diff_id] = rec
                self.pending_diffs.pop(diff_id, None)
                self._save_diff_to_disk(rec)

                applied_now.append(diff_id)
                applied_files.append(rec["file_path"])

            return {
                "status": "SUCCESS",
                "applied_diff_ids": applied_now,
                "files": applied_files,
                "message": f"Successfully applied batch of {len(applied_now)} diffs.",
            }
        except Exception as exc:
            # Transaction rollback: revert all diffs applied in this batch so far
            rollback_errors = []
            for rb_id in reversed(applied_now):
                rb_res = self.rollback_diff(rb_id)
                if rb_res.get("status") != "SUCCESS":
                    rollback_errors.append(f"{rb_id}: {rb_res.get('error')}")
                else:
                    # Restore diff record back to PENDING_APPROVAL so transaction state is atomic
                    rec_rb = self.applied_diffs.pop(rb_id, None)
                    if rec_rb:
                        rec_rb["status"] = "PENDING_APPROVAL"
                        self.pending_diffs[rb_id] = rec_rb
                        self._save_diff_to_disk(rec_rb)

            err_msg = f"Batch application failed during write: {exc}."
            if rollback_errors:
                err_msg += f" Note: transaction rollback encountered issues: {'; '.join(rollback_errors)}"
            else:
                err_msg += " All previously applied files in batch were successfully rolled back and restored to pending state."

            return {
                "status": "ERROR",
                "error": err_msg,
                "applied_diff_ids": [],
            }

    def rollback_batch(self, diff_ids: List[str]) -> Dict[str, Any]:
        """Rolls back a batch of applied diffs in reverse order.
        
        Validates freshness for all files first. If any file has been modified
        after the diff was applied, aborts without modifying files.
        """
        if not diff_ids:
            return {"status": "NOOP", "rolled_back_diff_ids": [], "files": []}

        # Pre-validate all diffs
        validated_records: List[Dict[str, Any]] = []
        for diff_id in diff_ids:
            if diff_id not in self.applied_diffs:
                loaded = self._load_diff_from_disk(diff_id)
                if loaded and loaded.get("status") == "APPLIED":
                    self.applied_diffs[diff_id] = loaded
                else:
                    return {
                        "status": "ERROR",
                        "error": f"Applied diff {diff_id} not found for batch rollback.",
                        "failed_diff_id": diff_id,
                    }

            rec = self.applied_diffs[diff_id]
            target_file = Path(rec["target_file"])
            try:
                self.boundary.validate_path(target_file, allow_write=True)
            except (SecurityViolationError, ValueError) as e:
                return {
                    "status": "BLOCKED",
                    "error": f"Security boundary violation for {rec['file_path']}: {e}",
                    "failed_diff_id": diff_id,
                }

            current_bytes = target_file.read_bytes() if target_file.exists() else b""
            if self._digest(current_bytes) != rec["new_sha256"]:
                return {
                    "status": "STALE",
                    "failed_diff_id": diff_id,
                    "file_path": rec["file_path"],
                    "error": f"File {rec['file_path']} changed after diff was applied; batch rollback aborted.",
                }
            validated_records.append(rec)

        # Roll back in reverse order
        rolled_back_ids: List[str] = []
        rolled_back_files: List[str] = []
        for rec in reversed(validated_records):
            diff_id = rec["diff_id"]
            rb_res = self.rollback_diff(diff_id)
            if rb_res.get("status") == "SUCCESS":
                rolled_back_ids.append(diff_id)
                rolled_back_files.append(rec["file_path"])
            else:
                return {
                    "status": "ERROR",
                    "error": f"Batch rollback failed on {diff_id}: {rb_res.get('error')}",
                    "rolled_back_diff_ids": rolled_back_ids,
                }

        return {
            "status": "SUCCESS",
            "rolled_back_diff_ids": rolled_back_ids,
            "files": rolled_back_files,
            "message": f"Successfully rolled back batch of {len(rolled_back_ids)} diffs.",
        }
