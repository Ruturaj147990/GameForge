"""Safe File Editing, Diff Generation, and Rollback for GameForge IDE."""

from __future__ import annotations

import base64
import difflib
import hashlib
import itertools
import json
import os
import re
import stat
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..security.boundary import BoundaryManager, SecurityViolationError
from ...storage.atomic import atomic_write, atomic_write_json
from ...storage.diff_store import DiffStore


def _apply_unified_diff_text(
    original_text: str,
    diff_text: str,
    fuzzy_window: int = 25,
) -> Tuple[bool, str, Optional[str]]:
    """Applies a multi-hunk unified diff to original_text with context verification and fuzzy offset matching.

    Returns (success, result_text, error_message).
    """
    if not diff_text or not diff_text.strip():
        return True, original_text, None

    orig_lines = original_text.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    dom_nl = "\r\n" if original_text.count("\r\n") > (original_text.count("\n") - original_text.count("\r\n")) else "\n"

    hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    out_lines: List[str] = []
    orig_idx = 0
    i = 0
    n = len(diff_lines)

    # Skip file headers (--- / +++)
    while i < n and (diff_lines[i].startswith("---") or diff_lines[i].startswith("+++")):
        i += 1

    def _matches_at(start_idx: int, expected: List[str], strip_ws: bool = False) -> bool:
        if start_idx < orig_idx or start_idx + len(expected) > len(orig_lines):
            return False
        for k, exp_line in enumerate(expected):
            actual_line = orig_lines[start_idx + k].rstrip("\r\n")
            if strip_ws:
                if actual_line.strip() != exp_line.strip():
                    return False
            else:
                if actual_line != exp_line:
                    return False
        return True

    while i < n:
        line = diff_lines[i]
        match = hunk_header_re.match(line)
        if not match:
            i += 1
            continue

        hunk_orig_start = max(0, int(match.group(1)) - 1)  # 0-indexed line number in original file
        i += 1

        # Collect all lines belonging to this hunk
        hunk_body: List[str] = []
        while i < n and not diff_lines[i].startswith("@@"):
            hunk_body.append(diff_lines[i])
            i += 1

        expected_orig = [
            hl[1:].rstrip("\r\n")
            for hl in hunk_body
            if len(hl) > 0 and hl[0] in (" ", "-")
        ]

        # Find matching start index (exact at nominal start, then fuzzy offset search within +/- fuzzy_window)
        matched_start: Optional[int] = None
        if not expected_orig:
            matched_start = min(max(orig_idx, hunk_orig_start), len(orig_lines))
        else:
            offsets = [0]
            for d in range(1, fuzzy_window + 1):
                offsets.append(-d)
                offsets.append(d)
            for off in offsets:
                cand = hunk_orig_start + off
                if _matches_at(cand, expected_orig, strip_ws=False):
                    matched_start = cand
                    break
            if matched_start is None:
                for off in offsets:
                    cand = hunk_orig_start + off
                    if _matches_at(cand, expected_orig, strip_ws=True):
                        matched_start = cand
                        break

        if matched_start is None:
            probe_idx = min(max(orig_idx, hunk_orig_start), max(0, len(orig_lines) - 1))
            got_line = orig_lines[probe_idx].strip() if orig_lines else "<EOF>"
            exp_first = expected_orig[0].strip() if expected_orig else ""
            return (
                False,
                original_text,
                f"Diff context mismatch near line {hunk_orig_start + 1}: expected {exp_first!r}, got {got_line!r}",
            )

        # Advance untouched original lines up to matched_start
        while orig_idx < matched_start and orig_idx < len(orig_lines):
            out_lines.append(orig_lines[orig_idx])
            orig_idx += 1

        # Apply hunk operations at matched_start
        for hline in hunk_body:
            prefix = hline[0] if len(hline) > 0 else ""
            content = hline[1:] if len(hline) > 0 else ""
            if prefix == " ":
                out_lines.append(orig_lines[orig_idx])
                orig_idx += 1
            elif prefix == "-":
                orig_idx += 1
            elif prefix == "+":
                if not content.endswith(("\n", "\r\n")):
                    content = content + dom_nl
                out_lines.append(content)
            elif prefix == "\\":
                pass

    # Append any remaining untouched original lines
    while orig_idx < len(orig_lines):
        out_lines.append(orig_lines[orig_idx])
        orig_idx += 1

    return True, "".join(out_lines), None


apply_unified_diff = _apply_unified_diff_text


class EditTools:
    """Manages diff generation, patch approval, atomic edits, and rollback snapshots."""

    def __init__(self, boundary: BoundaryManager):
        self.boundary = boundary
        self._lock = threading.RLock()
        self.pending_diffs: Dict[str, Dict[str, Any]] = {}
        self.applied_diffs: Dict[str, Dict[str, Any]] = {}
        self.diff_store = DiffStore(self.boundary.workspace_root)
        self.diffs_dir = self.diff_store.diffs_dir

    @staticmethod
    def _apply_unified_diff_text(original_text: str, diff_text: str, fuzzy_window: int = 25) -> Tuple[bool, str, Optional[str]]:
        return _apply_unified_diff_text(original_text, diff_text, fuzzy_window=fuzzy_window)

    def apply_patch_unified(self, subpath: str, diff_text: str) -> Dict[str, Any]:
        """Apply a unified diff directly to subpath with context verification and atomic write."""
        with self._lock:
            prop = self.propose_edit(subpath=subpath, patch=diff_text)
            if prop.get("status") != "PENDING_APPROVAL":
                return prop
            return self.apply_diff(prop["diff_id"])

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
    def _unwrap_markdown_fences(content: str) -> str:
        """Strip enclosing markdown code block fences (```lang ... ```) safely while preserving line ending semantics."""
        if not content:
            return content
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
                inner = "\n".join(lines[1:-1])
                # Preserve trailing newline if multi-line or original snippet had a trailing newline
                if content.endswith(("\n", "\r\n")) or len(lines) > 2:
                    if inner and not inner.endswith("\n"):
                        inner += "\n"
                return inner
        return content

    @staticmethod
    def _detect_dominant_line_ending(text: str) -> str:
        """Detect whether CRLF or LF is dominant in text."""
        crlf = text.count("\r\n")
        lf = text.count("\n") - crlf
        return "\r\n" if crlf > lf else "\n"

    @staticmethod
    def _atomic_write(target_file: Path, content: bytes) -> None:
        """Write content atomically so an interrupted apply cannot truncate a file."""
        atomic_write(target_path=target_file, content=content)

    @staticmethod
    def _validate_file_syntax(target_file: Path, new_bytes: bytes) -> Optional[str]:
        """Validate syntax for common formats like .py and .json. Returns error message if syntax is invalid, else None."""
        suffix = target_file.suffix.lower()
        if suffix == ".py":
            try:
                compile(new_bytes, str(target_file), "exec")
            except SyntaxError as exc:
                return f"Python syntax error at line {exc.lineno}: {exc.msg}"
        elif suffix == ".json":
            try:
                json.loads(new_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                return f"JSON syntax error: {exc}"
        return None

    def propose_edit(
        self,
        subpath: str = "",
        target_content: str = "",
        replacement_content: str = "",
        file_path: str = "",
        path: str = "",
        content: str = "",
        target: str = "",
        old_content: str = "",
        old_str: str = "",
        search: str = "",
        find: str = "",
        replacement: str = "",
        new_content: str = "",
        new_str: str = "",
        replace: str = "",
        text: str = "",
        file: str = "",
        filepath: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Proposes a code change, verifies path, and generates a unified diff for review."""
        effective_path = (
            subpath
            or file_path
            or path
            or file
            or filepath
            or kwargs.get("rel_path", "")
            or kwargs.get("file_path", "")
            or kwargs.get("subpath", "")
            or kwargs.get("path", "")
            or kwargs.get("file", "")
            or kwargs.get("filepath", "")
            or ""
        )
        if not target_content:
            target_content = (
                target
                or old_content
                or old_str
                or search
                or find
                or kwargs.get("target", "")
                or kwargs.get("target_content", "")
                or kwargs.get("old_content", "")
                or kwargs.get("old_str", "")
                or kwargs.get("search", "")
                or kwargs.get("find", "")
                or kwargs.get("original_content", "")
                or kwargs.get("original_text", "")
                or ""
            )
        if not replacement_content:
            replacement_content = (
                replacement
                or new_content
                or new_str
                or replace
                or content
                or text
                or kwargs.get("replacement", "")
                or kwargs.get("replacement_content", "")
                or kwargs.get("new_content", "")
                or kwargs.get("new_str", "")
                or kwargs.get("replace", "")
                or kwargs.get("content", "")
                or kwargs.get("text", "")
                or ""
            )

        # Strip accidental markdown code block fences if replacement_content or target_content is wrapped in ```
        replacement_content = self._unwrap_markdown_fences(replacement_content)
        target_content = self._unwrap_markdown_fences(target_content)

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
        dom_ending = self._detect_dominant_line_ending(original_text) if original_text else "\n"

        if original_text and target_content and target_content == replacement_content:
            return {
                "status": "NOOP",
                "message": f"No changes proposed: replacement_content is identical to target_content for {effective_path}.",
            }

        raw_chunks = kwargs.get("chunks") or kwargs.get("edits")
        raw_patch = kwargs.get("patch") or kwargs.get("diff") or kwargs.get("unified_diff")
        is_unified_diff = bool(
            raw_patch
            or (replacement_content and (replacement_content.startswith("--- ") or replacement_content.startswith("@@ ")))
        )

        # Check if target_content is present in file (if not creating fresh file)
        is_full_file_rewrite = False
        if original_text and not target_content and not raw_chunks and not is_unified_diff:
            if replacement_content:
                is_full_file_rewrite = True
                target_content = original_text
            else:
                return {
                    "status": "ERROR",
                    "error": f"target_content cannot be empty when editing existing file: {effective_path}. Provide the exact code block to replace.",
                }

        new_text = original_text

        if original_text and is_unified_diff:
            diff_text = raw_patch or replacement_content
            ok, applied_text, err = apply_unified_diff(original_text, diff_text)
            if not ok:
                return {
                    "status": "ERROR",
                    "error": f"Failed to apply unified diff patch to {effective_path}: {err}",
                }
            new_text = applied_text

        elif original_text and raw_chunks and isinstance(raw_chunks, (list, tuple)):
            # Multi-chunk diff application with cumulative line and character offset tracking
            matched_chunks = []
            for c_idx, c in enumerate(raw_chunks):
                if not isinstance(c, dict):
                    continue
                c_target = str(c.get("target_content") or c.get("target") or c.get("old_content") or c.get("search") or "")
                c_repl = str(c.get("replacement_content") or c.get("replacement") or c.get("new_content") or c.get("replace") or "")
                c_target = self._unwrap_markdown_fences(c_target)
                c_repl = self._unwrap_markdown_fences(c_repl)
                if not c_target:
                    return {"status": "ERROR", "error": f"Chunk #{c_idx + 1} is missing target_content."}

                c_norm_orig = original_text.replace("\r\n", "\n")
                c_norm_target = c_target.replace("\r\n", "\n")

                if c_target in original_text:
                    pos = original_text.find(c_target)
                    end_pos = pos + len(c_target)
                elif c_norm_target in c_norm_orig:
                    pos_norm = c_norm_orig.find(c_norm_target)
                    end_pos_norm = pos_norm + len(c_norm_target)
                    orig_lines = original_text.splitlines(keepends=True)
                    cum_lengths = [0] + list(itertools.accumulate([len(l) for l in orig_lines]))

                    line_idx = c_norm_orig[:pos_norm].count("\n")
                    last_nl = c_norm_orig[:pos_norm].rfind("\n")
                    col_idx = pos_norm - (last_nl + 1) if last_nl != -1 else pos_norm
                    pos = cum_lengths[line_idx] + col_idx if line_idx < len(cum_lengths) else len(original_text)

                    end_line_idx = c_norm_orig[:end_pos_norm].count("\n")
                    end_last_nl = c_norm_orig[:end_pos_norm].rfind("\n")
                    end_col_idx = end_pos_norm - (end_last_nl + 1) if end_last_nl != -1 else end_pos_norm
                    end_pos = cum_lengths[end_line_idx] + end_col_idx if end_line_idx < len(cum_lengths) else len(original_text)
                else:
                    return {"status": "ERROR", "error": f"Chunk #{c_idx + 1} target block not found in file: {effective_path}"}

                matched_chunks.append({
                    "start": pos,
                    "end": end_pos,
                    "target": original_text[pos:end_pos],
                    "replacement": c_repl,
                })

            # Sort chunks by start position in original text
            matched_chunks.sort(key=lambda m: m["start"])

            # Verify no overlapping chunks
            for i in range(len(matched_chunks) - 1):
                if matched_chunks[i]["end"] > matched_chunks[i + 1]["start"]:
                    return {"status": "ERROR", "error": f"Overlapping chunks in multi-chunk edit for {effective_path}."}

            # Sequentially apply chunks with cumulative offset adjustments
            new_text = original_text
            cumulative_char_offset = 0
            cumulative_line_offset = 0

            for m in matched_chunks:
                adj_start = m["start"] + cumulative_char_offset
                adj_end = m["end"] + cumulative_char_offset

                repl = m["replacement"]
                if dom_ending == "\r\n":
                    repl = repl.replace("\r\n", "\n").replace("\n", "\r\n")
                else:
                    repl = repl.replace("\r\n", "\n")

                orig_chunk_text = original_text[m["start"]:m["end"]]
                if orig_chunk_text.endswith(("\n", "\r\n")) and not repl.endswith(("\n", "\r\n")):
                    repl += dom_ending

                new_text = new_text[:adj_start] + repl + new_text[adj_end:]

                delta_chars = len(repl) - (m["end"] - m["start"])
                delta_lines = repl.count("\n") - orig_chunk_text.count("\n")
                cumulative_char_offset += delta_chars
                cumulative_line_offset += delta_lines

        elif original_text:
            if is_full_file_rewrite:
                # Full-file rewrite: strictly preserve file's dominant line ending
                if dom_ending == "\r\n":
                    new_text = replacement_content.replace("\r\n", "\n").replace("\n", "\r\n")
                else:
                    new_text = replacement_content.replace("\r\n", "\n")
            elif target_content in original_text:
                # Tier 1: Exact substring match with line ending & boundary formatting preservation
                line_ending = dom_ending
                repl_to_use = replacement_content
                if dom_ending == "\r\n":
                    repl_to_use = repl_to_use.replace("\r\n", "\n").replace("\n", "\r\n")
                else:
                    repl_to_use = repl_to_use.replace("\r\n", "\n")

                if (
                    not target_content.endswith(("\n", "\r\n"))
                    and repl_to_use.endswith(("\n", "\r\n"))
                    and (target_content + line_ending) in original_text
                ):
                    new_text = original_text.replace(target_content + line_ending, repl_to_use, 1)
                else:
                    new_text = original_text.replace(target_content, repl_to_use, 1)
            else:
                # Tier 2: Robust normalized matching across CRLF and LF line endings
                norm_orig = original_text.replace("\r\n", "\n")
                norm_target = target_content.replace("\r\n", "\n")
                norm_repl = replacement_content.replace("\r\n", "\n")

                target_to_find = norm_target
                if (
                    target_to_find not in norm_orig
                    and not target_to_find.endswith("\n")
                    and (target_to_find + "\n") in norm_orig
                    and norm_repl.endswith("\n")
                ):
                    target_to_find = target_to_find + "\n"

                if target_to_find in norm_orig:
                    pos = norm_orig.find(target_to_find)
                    end_pos = pos + len(target_to_find)

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
                    line_ending = "\r\n" if "\r\n" in matched_block else dom_ending
                    adjusted_repl = norm_repl.replace("\n", line_ending)
                    new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                else:
                    # Tier 3: Resilient Whitespace & Indentation Tolerant Sequence Matching
                    orig_lines_raw = norm_orig.splitlines(keepends=True)
                    orig_stripped = [l.strip() for l in orig_lines_raw]
                    target_lines_raw = norm_target.splitlines(keepends=True)
                    target_stripped = [l.strip() for l in target_lines_raw]

                    orig_non_empty = [(i, l) for i, l in enumerate(orig_stripped) if l]
                    target_non_empty = [(i, l) for i, l in enumerate(target_stripped) if l]

                    found_match = False
                    if target_non_empty and len(target_non_empty) <= len(orig_non_empty):
                        t_seq = [t[1] for t in target_non_empty]
                        o_seq = [o[1] for o in orig_non_empty]
                        t_len = len(t_seq)

                        for k in range(len(o_seq) - t_len + 1):
                            if o_seq[k : k + t_len] == t_seq:
                                start_line_idx = orig_non_empty[k][0]
                                end_line_idx = orig_non_empty[k + t_len - 1][0]

                                orig_lines_with_nl = original_text.splitlines(keepends=True)
                                cum_lens = [0] + list(itertools.accumulate([len(l) for l in orig_lines_with_nl]))
                                o_start = cum_lens[start_line_idx]
                                end_bound = end_line_idx + 1
                                o_end = cum_lens[end_bound] if end_bound < len(cum_lens) else len(original_text)

                                line_ending = dom_ending
                                adjusted_repl = norm_repl.replace("\n", line_ending)

                                # Preserve full-line boundary formatting
                                if (
                                    adjusted_repl
                                    and original_text[o_start:o_end].endswith(("\n", "\r\n"))
                                    and not adjusted_repl.endswith(("\n", "\r\n"))
                                ):
                                    adjusted_repl += line_ending

                                new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                                found_match = True
                                break

                    if not found_match:
                        # Tier 4: Fuzzy ratio fallback with line-candidate acceleration for large files
                        target_lines = norm_target.splitlines()
                        if len(target_lines) >= 3:
                            t_len = len(target_lines)
                            probe_line = next((l.strip() for l in target_lines if l.strip()), "")
                            candidates = []
                            if probe_line:
                                for idx, ol in enumerate(orig_stripped):
                                    if ol == probe_line or (len(probe_line) > 10 and (probe_line in ol or ol in probe_line)):
                                        candidates.append(idx)

                            best_ratio = 0.0
                            best_slice = None
                            for c_idx in candidates[:20]:
                                start_w = max(0, c_idx - 2)
                                end_w = min(len(orig_lines_raw), c_idx + t_len + 3)
                                window_lines = [l.strip() for l in orig_lines_raw[start_w:end_w]]
                                ratio = difflib.SequenceMatcher(None, window_lines, [l.strip() for l in target_lines]).ratio()
                                if ratio > best_ratio and ratio >= 0.82:
                                    best_ratio = ratio
                                    best_slice = (start_w, end_w)

                            if best_slice:
                                orig_lines = original_text.splitlines(keepends=True)
                                cum_lengths = [0] + list(itertools.accumulate([len(l) for l in orig_lines]))
                                o_start = cum_lengths[best_slice[0]]
                                o_end = cum_lengths[best_slice[1]] if best_slice[1] < len(cum_lengths) else len(original_text)
                                line_ending = dom_ending
                                adjusted_repl = norm_repl.replace("\n", line_ending)
                                if adjusted_repl and not adjusted_repl.endswith(("\n", "\r\n")):
                                    adjusted_repl += line_ending
                                new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                                found_match = True
                            elif len(norm_orig) <= 300_000:
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

                                    line_ending = dom_ending
                                    adjusted_repl = norm_repl.replace("\n", line_ending)
                                    new_text = original_text[:o_start] + adjusted_repl + original_text[o_end:]
                                    found_match = True

                    if not found_match:
                        return {
                            "status": "ERROR",
                            "error": f"Target content block not found in file: {effective_path}",
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
            "diff": diff_patch,
            "message": "Diff generated successfully. Requires developer approval to apply.",
        }

    def apply_diff(
        self,
        diff_id: str = "",
        id: str = "",
        diff: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Applies an approved diff to the filesystem and saves rollback state."""
        effective_id = diff_id or id or diff or ""
        if not effective_id:
            return {"status": "ERROR", "error": "Missing diff_id for apply_diff."}

        if effective_id not in self.pending_diffs:
            loaded = self._load_diff_from_disk(effective_id)
            if loaded and loaded.get("status") == "PENDING_APPROVAL":
                self.pending_diffs[effective_id] = loaded
            else:
                return {"status": "ERROR", "error": f"Pending diff {effective_id} not found."}

        rec = self.pending_diffs[effective_id]
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
                "diff_id": effective_id,
                "file_path": rec["file_path"],
                "error": "File existence state changed after this diff was proposed; review a newly generated diff before applying.",
            }

        current_bytes = target_file.read_bytes() if target_file.exists() else b""
        if self._digest(current_bytes) != rec["original_sha256"]:
            return {
                "status": "STALE",
                "diff_id": effective_id,
                "file_path": rec["file_path"],
                "error": "File changed after this diff was proposed; review a newly generated diff before applying.",
            }

        try:
            self._atomic_write(target_file, rec["new_bytes"])

            rec["status"] = "APPLIED"
            self.applied_diffs[effective_id] = rec
            self.pending_diffs.pop(effective_id, None)
            self._save_diff_to_disk(rec)

            return {
                "status": "SUCCESS",
                "diff_id": effective_id,
                "file_path": rec["file_path"],
                "message": f"Successfully applied changes to {rec['file_path']}.",
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Failed to write file: {e}"}

    def reject_diff(
        self,
        diff_id: str = "",
        reason: str = "User rejected",
        id: str = "",
        diff: str = "",
        message: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Rejects a proposed diff and discards it without touching the filesystem."""
        effective_id = diff_id or id or diff or ""
        effective_reason = reason if reason != "User rejected" else (message or "User rejected")
        if not effective_id:
            return {"status": "ERROR", "error": "Missing diff_id for reject_diff."}

        if effective_id not in self.pending_diffs:
            loaded = self._load_diff_from_disk(effective_id)
            if loaded and loaded.get("status") == "PENDING_APPROVAL":
                self.pending_diffs[effective_id] = loaded
            else:
                return {"status": "ERROR", "error": f"Pending diff {effective_id} not found."}

        rec = self.pending_diffs.pop(effective_id)
        rec["status"] = "REJECTED"
        self._save_diff_to_disk(rec)
        return {
            "status": "REJECTED",
            "diff_id": effective_id,
            "file_path": rec["file_path"],
            "reason": effective_reason,
        }

    def rollback_diff(
        self,
        diff_id: str = "",
        id: str = "",
        diff: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Rolls back an applied diff to its original pre-edit state."""
        effective_id = diff_id or id or diff or ""
        if not effective_id:
            return {"status": "ERROR", "error": "Missing diff_id for rollback_diff."}

        if effective_id not in self.applied_diffs:
            loaded = self._load_diff_from_disk(effective_id)
            if loaded and loaded.get("status") == "APPLIED":
                self.applied_diffs[effective_id] = loaded
            elif loaded:
                return {
                    "status": "ERROR",
                    "diff_id": effective_id,
                    "error": f"Diff {effective_id} is not in APPLIED state (current: {loaded.get('status')}).",
                }
            else:
                return {"status": "ERROR", "diff_id": effective_id, "error": f"Applied diff {effective_id} not found for rollback."}

        rec = self.applied_diffs[effective_id]
        if rec.get("status") != "APPLIED":
            return {
                "status": "ERROR",
                "diff_id": effective_id,
                "file_path": rec.get("file_path", ""),
                "error": f"Diff {effective_id} is not in APPLIED state (current: {rec.get('status')}).",
            }

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
                "diff_id": effective_id,
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
            self.applied_diffs.pop(effective_id, None)
            return {
                "status": "SUCCESS",
                "diff_id": effective_id,
                "file_path": rec["file_path"],
                "message": f"Successfully rolled back {rec['file_path']} to pre-edit state.",
            }

        except Exception as e:
            return {"status": "ERROR", "error": f"Rollback failed: {e}"}

    def apply_batch(
        self,
        diff_ids: Any = None,
        diffs: Any = None,
        ids: Any = None,
        diff_id: str = "",
        validate_syntax: bool = False,
        validator: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Atomically applies a batch of approved diffs across multiple files.
        
        Performs pre-validation on all diffs, hashes, and syntax first; if any diff is stale,
        invalid, or fails syntax check, the transaction aborts with zero filesystem modifications.
        If a write failure or validation error occurs mid-batch, all previously applied files
        in the batch are rolled back automatically in exact reverse order and restored to PENDING_APPROVAL.
        """
        raw_ids = diff_ids if diff_ids is not None else (diffs if diffs is not None else (ids if ids is not None else diff_id))
        if isinstance(raw_ids, str):
            if "," in raw_ids:
                effective_ids = [d.strip() for d in raw_ids.split(",") if d.strip()]
            elif raw_ids.strip():
                effective_ids = [raw_ids.strip()]
            else:
                effective_ids = []
        elif raw_ids and isinstance(raw_ids, (list, tuple, set)):
            effective_ids = []
            for item in raw_ids:
                if isinstance(item, dict):
                    d_id = item.get("diff_id") or item.get("id") or item.get("diff")
                    if d_id:
                        effective_ids.append(str(d_id).strip())
                elif item:
                    effective_ids.append(str(item).strip())
        else:
            effective_ids = []

        if not effective_ids:
            return {"status": "NOOP", "applied_diff_ids": [], "files": []}

        # Phase 1: Pre-validation (dry run)
        validated_records: List[Dict[str, Any]] = []
        seen_targets: set[str] = set()
        for diff_id in effective_ids:
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

            # Optional syntax pre-validation
            if validate_syntax or kwargs.get("validate_syntax") or kwargs.get("syntax_check"):
                syntax_err = self._validate_file_syntax(target_file, rec["new_bytes"])
                if syntax_err:
                    return {
                        "status": "ERROR",
                        "error": f"Pre-validation syntax check failed for {rec['file_path']}: {syntax_err}",
                        "failed_diff_id": diff_id,
                        "file_path": rec["file_path"],
                        "applied_diff_ids": [],
                    }

            validated_records.append(rec)

        # Phase 2: Staged execution with automatic reverse rollback on error
        applied_now: List[str] = []
        applied_files: List[str] = []
        try:
            for rec in validated_records:
                diff_id = rec["diff_id"]
                target_file = Path(rec["target_file"])
                self._atomic_write(target_file, rec["new_bytes"])

                rec["status"] = "APPLIED"
                self.applied_diffs[diff_id] = rec
                applied_now.append(diff_id)

                # Post-write validation check
                if validator is not None and callable(validator):
                    val_res = validator(target_file, rec)
                    if isinstance(val_res, tuple):
                        val_ok, val_err = val_res
                    else:
                        val_ok, val_err = bool(val_res), "Custom validator callback failed"
                    if not val_ok:
                        raise ValueError(f"Validation failed for {rec['file_path']}: {val_err}")

                self.pending_diffs.pop(diff_id, None)
                self._save_diff_to_disk(rec)
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
                    rec_rb = self._load_diff_from_disk(rb_id)
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

    def rollback_batch(
        self,
        diff_ids: Any = None,
        diffs: Any = None,
        ids: Any = None,
        diff_id: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Rolls back a batch of applied diffs in reverse order.
        
        Validates freshness for all files first. If any file has been modified
        after the diff was applied, aborts without modifying files.
        """
        raw_ids = diff_ids if diff_ids is not None else (diffs if diffs is not None else (ids if ids is not None else diff_id))
        if isinstance(raw_ids, str):
            if "," in raw_ids:
                effective_ids = [d.strip() for d in raw_ids.split(",") if d.strip()]
            elif raw_ids.strip():
                effective_ids = [raw_ids.strip()]
            else:
                effective_ids = []
        elif raw_ids:
            effective_ids = list(raw_ids)
        else:
            effective_ids = []

        if not effective_ids:
            return {"status": "NOOP", "rolled_back_diff_ids": [], "files": []}

        # Pre-validate all diffs
        validated_records: List[Dict[str, Any]] = []
        seen_targets: set[str] = set()
        for diff_id in effective_ids:
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

            norm_target = str(target_file.resolve()).lower()
            if norm_target in seen_targets:
                return {
                    "status": "ERROR",
                    "error": f"Duplicate target file in batch rollback: '{rec['file_path']}' is targeted by multiple diffs.",
                    "failed_diff_id": diff_id,
                }
            seen_targets.add(norm_target)

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

    def write_file(
        self,
        subpath: str = "",
        content: str = "",
        overwrite: bool = True,
        session_id: Optional[str] = None,
        file_path: str = "",
        path: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Atomically writes or overwrites a file with full rollback journal and hash tracking."""
        effective_path = subpath or file_path or path or kwargs.get("filepath", "") or kwargs.get("file", "")
        if not effective_path:
            return {"status": "ERROR", "error": "No file path specified for write_file."}

        effective_content = content if content is not None else kwargs.get("text", "")
        effective_content = self._unwrap_markdown_fences(effective_content)

        # Use propose_edit to construct the diff record, then apply immediately
        prop_res = self.propose_edit(
            subpath=effective_path,
            target_content="",
            replacement_content=effective_content,
            session_id=session_id,
        )
        if prop_res.get("status") != "PENDING_APPROVAL":
            return prop_res

        diff_id = prop_res.get("diff_id")
        apply_res = self.apply_diff(diff_id)
        if apply_res.get("status") == "SUCCESS":
            apply_res["diff_id"] = diff_id
            apply_res["diff"] = prop_res.get("diff") or prop_res.get("diff_patch", "")
            apply_res["diff_patch"] = prop_res.get("diff_patch") or prop_res.get("diff", "")
        return apply_res

    def delete_file(
        self,
        subpath: str = "",
        file_path: str = "",
        path: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Safely deletes a file from the workspace with boundary validation."""
        effective_path = subpath or file_path or path or kwargs.get("filepath", "") or kwargs.get("file", "")
        if not effective_path:
            return {"status": "ERROR", "error": "No file path specified for delete_file."}

        try:
            target_path = Path(effective_path)
            if not target_path.is_absolute():
                target_path = self.boundary.workspace_root / target_path
            resolved = self.boundary.validate_path(target_path, allow_write=True)

            if not resolved.exists():
                return {"status": "ERROR", "error": f"File not found: {effective_path}"}
            if resolved.is_dir():
                return {"status": "ERROR", "error": f"Path is a directory, not a file: {effective_path}. Only individual files can be deleted."}

            resolved.unlink()
            rel_str = str(resolved.relative_to(self.boundary.workspace_root)).replace("\\", "/")
            return {
                "status": "SUCCESS",
                "file_path": rel_str,
                "message": f"Successfully deleted {rel_str}.",
            }
        except SecurityViolationError as sve:
            return {"status": "BLOCKED", "error": f"Security boundary violation: {sve}"}
        except Exception as exc:
            return {"status": "ERROR", "error": f"Failed to delete {effective_path}: {exc}"}

    def verify_disk_contents(self, subpath: str, expected_fragment: str = "") -> Dict[str, Any]:
        """Verifies that the target file exists on disk and contains expected_fragment."""
        try:
            target_path = Path(subpath)
            if not target_path.is_absolute():
                target_path = self.boundary.workspace_root / target_path
            resolved = self.boundary.validate_path(target_path, allow_write=False)
            if not resolved.is_file():
                return {"status": "ERROR", "verified": False, "error": f"File does not exist: {subpath}"}
            data = resolved.read_text(encoding="utf-8", errors="replace")
            verified = (expected_fragment in data) if expected_fragment else True
            return {
                "status": "SUCCESS",
                "verified": verified,
                "file_path": str(resolved.relative_to(self.boundary.workspace_root)).replace("\\", "/"),
                "bytes": resolved.stat().st_size,
                "sha256": self._digest(resolved.read_bytes()),
            }
        except Exception as exc:
            return {"status": "ERROR", "verified": False, "error": str(exc)}

    def begin_transaction(self, files: List[str]) -> Dict[str, Any]:
        """Captures baseline SHA-256 hashes for all target files before a multi-file edit."""
        tx_id = f"tx_{uuid.uuid4().hex[:10]}"
        baselines: Dict[str, str] = {}
        for f in files:
            p = Path(f)
            if not p.is_absolute():
                p = self.boundary.workspace_root / p
            try:
                resolved = self.boundary.validate_path(p, allow_write=True)
                baselines[f] = self._digest(resolved.read_bytes()) if resolved.is_file() else "EMPTY"
            except Exception as e:
                return {"status": "ERROR", "error": f"Invalid path {f}: {e}", "tx_id": tx_id}
        return {"status": "SUCCESS", "tx_id": tx_id, "baselines": baselines}

    # Backward-compatible method aliases
    apply_edit = apply_diff
    rollback_edit = rollback_diff

