"""Multi-File Change Manifest & Bounded Prose Recovery for GameForge IDE.

Authoritative implementation conforming to DEF-304:
- Coordinates complex repairs spanning 4+ C++ header and source files.
- Enforces safe topological edit ordering:
  - Declarations before consumers
  - Header interfaces (.h/.hpp) before source implementations (.cpp/.c)
  - Reflection declarations (UCLASS, USTRUCT, GENERATED_BODY, .generated.h include) consistent
- Provides atomic batch application with compilation verification and transactional rollback.
- Implements bounded recovery when models emit prose or code blocks instead of structured tools.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field

from ..tools.gateway import ToolGateway

logger = logging.getLogger(__name__)

OperationKind = Literal["create", "modify", "delete"]
FileType = Literal["header", "source", "config", "asset", "other"]
ManifestStatus = Literal["staged", "applied", "verified", "failed", "rolled_back"]


class FileChangeOperation(BaseModel):
    """An individual file modification operation within a multi-file manifest."""
    op_id: str = Field(default_factory=lambda: f"op_{uuid.uuid4().hex[:6]}")
    subpath: str
    target_content: str = ""
    replacement_content: str = ""
    operation_kind: OperationKind = "modify"
    file_type: FileType = "other"
    symbols_declared: List[str] = Field(default_factory=list)
    symbols_referenced: List[str] = Field(default_factory=list)
    reflection_macros: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        subpath: str,
        replacement_content: str,
        target_content: str = "",
        operation_kind: Optional[OperationKind] = None,
        dependencies: Optional[List[str]] = None,
    ) -> "FileChangeOperation":
        clean_path = subpath.replace("\\", "/").strip()
        ftype = cls._infer_file_type(clean_path)
        op_kind = operation_kind or ("create" if not target_content else "modify")

        declared, referenced, macros = cls._scan_symbols_and_reflection(replacement_content, clean_path)

        return cls(
            subpath=clean_path,
            target_content=target_content,
            replacement_content=replacement_content,
            operation_kind=op_kind,
            file_type=ftype,
            symbols_declared=declared,
            symbols_referenced=referenced,
            reflection_macros=macros,
            dependencies=dependencies or [],
        )

    @staticmethod
    def _infer_file_type(path: str) -> FileType:
        ext = Path(path).suffix.lower()
        if ext in (".h", ".hpp", ".hxx", ".inl"):
            return "header"
        if ext in (".cpp", ".c", ".cxx", ".cc"):
            return "source"
        if ext in (".ini", ".json", ".xml", ".yaml", ".yml", ".cs"):
            return "config"
        if ext in (".uasset", ".umap", ".obj", ".fbx"):
            return "asset"
        return "other"

    @staticmethod
    def _scan_symbols_and_reflection(content: str, path: str) -> Tuple[List[str], List[str], List[str]]:
        """Scans C++ content for declared symbols, referenced symbols, and Unreal reflection macros."""
        declared: List[str] = []
        referenced: List[str] = []
        macros: List[str] = []

        if not content:
            return declared, referenced, macros

        # Scan Unreal reflection macros
        reflection_patterns = [
            r"\bUCLASS\b",
            r"\bUSTRUCT\b",
            r"\bUENUM\b",
            r"\bUFUNCTION\b",
            r"\bUPROPERTY\b",
            r"\bGENERATED_BODY\b",
            r"\bGENERATED_UCLASS_BODY\b",
        ]
        for pat in reflection_patterns:
            matches = re.findall(pat, content)
            macros.extend(matches)

        # Scan declared class / struct / enum names
        class_matches = re.findall(r"\b(?:class|struct)\s+(?:[A-Z0-9_]+_API\s+)?([A-Za-z0-9_]+)", content)
        declared.extend(class_matches)

        enum_matches = re.findall(r"\benum\s+(?:class\s+)?([A-Za-z0-9_]+)", content)
        declared.extend(enum_matches)

        # Scan #include statements for referenced headers
        includes = re.findall(r'#include\s+["<]([^">]+)[">]', content)
        for inc in includes:
            inc_base = Path(inc).name
            referenced.append(inc_base)

        return declared, referenced, macros


class MultiFileApplyResult(BaseModel):
    """Detailed result of applying a MultiFileChangeManifest."""
    manifest_id: str
    status: ManifestStatus
    operations_applied: int = 0
    total_operations: int = 0
    verification_passed: bool = False
    verification_output: str = ""
    error_message: Optional[str] = None
    diagnostics: List[str] = Field(default_factory=list)
    modified_paths: List[str] = Field(default_factory=list)


class MultiFileChangeManifest(BaseModel):
    """Coordinates and verifies atomic multi-file repairs across C++ modules."""
    manifest_id: str = Field(default_factory=lambda: f"manifest_{uuid.uuid4().hex[:8]}")
    goal: str
    operations: List[FileChangeOperation] = Field(default_factory=list)
    verification_command: Optional[str] = None
    status: ManifestStatus = "staged"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_operation(self, op: FileChangeOperation) -> None:
        self.operations.append(op)

    def validate_reflection_consistency(self) -> Tuple[bool, List[str]]:
        """Verifies Unreal Engine reflection invariants across all staged operations:
        - Headers with UCLASS() or USTRUCT() must contain GENERATED_BODY().
        - Headers with UCLASS() must include the .generated.h header as the final include.
        """
        errors: List[str] = []

        for op in self.operations:
            if op.file_type != "header":
                continue

            content = op.replacement_content
            has_uclass = bool(re.search(r"\bUCLASS\b", content))
            has_ustruct = bool(re.search(r"\bUSTRUCT\b", content))

            if has_uclass or has_ustruct:
                # 1. Must contain GENERATED_BODY()
                if not re.search(r"\b(?:GENERATED_BODY|GENERATED_UCLASS_BODY)\s*\(\s*\)", content):
                    errors.append(f"{op.subpath}: UCLASS/USTRUCT declared without required GENERATED_BODY() macro.")

                # 2. Must include .generated.h
                header_stem = Path(op.subpath).stem
                expected_gen_inc = f"{header_stem}.generated.h"
                gen_inc_match = re.search(r'#include\s+["<]([^">]*\.generated\.h)[">]', content)
                if not gen_inc_match:
                    errors.append(f"{op.subpath}: Missing reflection header `#include \"{expected_gen_inc}\"`.")
                else:
                    # Verify .generated.h is the last include in the file
                    all_includes = list(re.finditer(r'#include\s+["<]([^">]+)[">]', content))
                    if all_includes:
                        last_inc = all_includes[-1].group(1)
                        if not last_inc.endswith(".generated.h"):
                            errors.append(
                                f"{op.subpath}: Reflection include `{last_inc}` is not the last include. "
                                f"Unreal Engine requires `{expected_gen_inc}` to be the final #include."
                            )

        return len(errors) == 0, errors

    def get_topological_execution_order(self) -> List[FileChangeOperation]:
        """Calculates safe edit ordering:
        1. Headers before sources (.h before .cpp).
        2. Declarations before consumers (files declaring symbols before files referencing them).
        3. Base headers before derived headers.
        """
        ops = list(self.operations)
        if len(ops) <= 1:
            return ops

        # Map symbol name -> op index that declares it
        symbol_to_op: Dict[str, int] = {}
        for idx, op in enumerate(ops):
            for sym in op.symbols_declared:
                symbol_to_op[sym] = idx

        # Build in-degree and adjacency graph
        adj: Dict[int, Set[int]] = {i: set() for i in range(len(ops))}
        in_degree: Dict[int, int] = {i: 0 for i in range(len(ops))}

        for idx, op in enumerate(ops):
            # Header before source preference for same module
            if op.file_type == "source":
                header_name = Path(op.subpath).with_suffix(".h").name
                for o_idx, other in enumerate(ops):
                    if o_idx != idx and other.file_type == "header" and Path(other.subpath).name == header_name:
                        adj[o_idx].add(idx)

            # Declarations before consumers
            for ref_sym in op.symbols_referenced:
                if ref_sym in symbol_to_op:
                    decl_idx = symbol_to_op[ref_sym]
                    if decl_idx != idx:
                        adj[decl_idx].add(idx)

            # Explicit dependencies
            for dep_path in op.dependencies:
                dep_clean = dep_path.replace("\\", "/")
                for o_idx, other in enumerate(ops):
                    if o_idx != idx and (other.subpath == dep_clean or Path(other.subpath).name == dep_clean):
                        adj[o_idx].add(idx)

        # Compute in-degrees
        for u in adj:
            for v in adj[u]:
                in_degree[v] += 1

        # Kahn's algorithm with stable secondary sort (headers first, then path)
        def _node_priority(i: int) -> Tuple[int, str]:
            is_hdr = 0 if ops[i].file_type == "header" else 1
            return (is_hdr, ops[i].subpath)

        ready = [i for i, deg in in_degree.items() if deg == 0]
        ready.sort(key=_node_priority)

        ordered_indices: List[int] = []
        while ready:
            curr = ready.pop(0)
            ordered_indices.append(curr)
            for neighbor in sorted(adj[curr], key=_node_priority):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    ready.append(neighbor)
            ready.sort(key=_node_priority)

        # Handle any circular dependency gracefully by appending remaining
        if len(ordered_indices) < len(ops):
            remaining = [i for i in range(len(ops)) if i not in ordered_indices]
            remaining.sort(key=_node_priority)
            ordered_indices.extend(remaining)

        return [ops[i] for i in ordered_indices]

    def apply(
        self,
        gateway: ToolGateway,
        verify_compilation: bool = True,
        rollback_on_failure: bool = True,
    ) -> MultiFileApplyResult:
        """Applies all operations in safe topological order with compilation verification and rollback."""
        result = MultiFileApplyResult(
            manifest_id=self.manifest_id,
            status="staged",
            total_operations=len(self.operations),
        )

        # 1. Reflection invariant check
        valid_refl, refl_errs = self.validate_reflection_consistency()
        if not valid_refl:
            result.status = "failed"
            result.error_message = "Reflection consistency check failed."
            result.diagnostics = refl_errs
            return result

        ordered_ops = self.get_topological_execution_order()
        ws_root = gateway.workspace_root

        # 2. Capture pre-edit snapshot for transactional rollback
        snapshots: Dict[str, Optional[str]] = {}
        for op in ordered_ops:
            file_p = ws_root / op.subpath
            if file_p.exists() and file_p.is_file():
                try:
                    snapshots[op.subpath] = file_p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    snapshots[op.subpath] = None
            else:
                snapshots[op.subpath] = None

        # 3. Apply edits in topological order
        applied_ops = 0
        modified_paths: List[str] = []

        for op in ordered_ops:
            try:
                if op.operation_kind == "create" or op.target_content == "":
                    # Write new file directly
                    res = gateway.execute_tool(
                        "write_file",
                        {"subpath": op.subpath, "content": op.replacement_content},
                        approval_granted=True,
                    )
                else:
                    # Apply surgical replacement
                    res = gateway.execute_tool(
                        "propose_edit",
                        {
                            "subpath": op.subpath,
                            "target_content": op.target_content,
                            "replacement_content": op.replacement_content,
                        },
                        approval_granted=True,
                    )
                    if res.get("status") == "SUCCESS" and res.get("diff_id"):
                        res = gateway.execute_tool(
                            "apply_edit",
                            {"diff_id": res["diff_id"]},
                            approval_granted=True,
                        )

                if res.get("status") == "SUCCESS":
                    applied_ops += 1
                    modified_paths.append(op.subpath)
                else:
                    raise RuntimeError(f"Operation on {op.subpath} failed: {res.get('error', 'unknown error')}")
            except Exception as exc:
                logger.error("MultiFileChangeManifest operation failed on %s: %s", op.subpath, exc)
                result.status = "failed"
                result.error_message = str(exc)
                result.operations_applied = applied_ops
                result.modified_paths = modified_paths

                if rollback_on_failure:
                    self._rollback_snapshots(ws_root, snapshots)
                    result.status = "rolled_back"
                return result

        result.operations_applied = applied_ops
        result.modified_paths = modified_paths
        result.status = "applied"

        # 4. Compilation Verification
        if verify_compilation and self.verification_command:
            try:
                cmd_res = gateway.execute_tool(
                    "run_command",
                    {"command": self.verification_command, "shell": "powershell"},
                    approval_granted=True,
                )
                stdout_str = cmd_res.get("stdout", "")
                stderr_str = cmd_res.get("stderr", "")
                exit_code = cmd_res.get("exit_code", -1)
                result.verification_output = stdout_str + ("\n" + stderr_str if stderr_str else "")

                if exit_code == 0:
                    result.verification_passed = True
                    result.status = "verified"
                else:
                    result.verification_passed = False
                    result.status = "failed"
                    result.error_message = f"Compilation verification failed with exit code {exit_code}."
                    result.diagnostics.append(result.verification_output[:2000])

                    if rollback_on_failure:
                        self._rollback_snapshots(ws_root, snapshots)
                        result.status = "rolled_back"
            except Exception as v_exc:
                result.verification_passed = False
                result.status = "failed"
                result.error_message = f"Compilation verification execution error: {v_exc}"
                if rollback_on_failure:
                    self._rollback_snapshots(ws_root, snapshots)
                    result.status = "rolled_back"
        else:
            result.verification_passed = True
            result.status = "applied"

        return result

    @staticmethod
    def _rollback_snapshots(workspace_root: Path, snapshots: Dict[str, Optional[str]]) -> None:
        """Rollback applied edits by restoring pre-edit snapshots."""
        for subpath, original_text in snapshots.items():
            fp = workspace_root / subpath
            try:
                if original_text is None:
                    # File was newly created; remove it
                    if fp.exists():
                        fp.unlink(missing_ok=True)
                else:
                    # Restore original content
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(original_text, encoding="utf-8")
            except Exception as r_err:
                logger.error("Failed to rollback snapshot for %s: %s", subpath, r_err)


class BoundedRecoveryHandler:
    """Bounded recovery mechanism when models emit prose or raw code blocks instead of JSON tool calls."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def extract_manifest_from_prose(
        self,
        prose: str,
        workspace_root: Path,
        goal: str = "Recovered changes from prose",
    ) -> Optional[MultiFileChangeManifest]:
        """Extracts code blocks associated with target file paths from markdown prose."""
        if not prose or "```" not in prose:
            return None

        # Look for headers followed by code fences, e.g.:
        # ### `Source/MyGame/Player.h`
        # ```cpp
        # ...
        # ```
        pattern = re.compile(
            r"(?:###?\s*[`\"']?([A-Za-z0-9_\-\./\\]+\.[a-zA-Z0-9]+)[`\"']?|"
            r"//\s*(?:File|Path|Target):\s*([A-Za-z0-9_\-\./\\]+\.[a-zA-Z0-9]+)|"
            r"\*\*(?:File|Create|Edit):\s*[`\"']?([A-Za-z0-9_\-\./\\]+\.[a-zA-Z0-9]+)[`\"']?\*\*)"
            r"[\s\S]*?```(?:[a-zA-Z0-9_\-]+)?\s*([\s\S]*?)```",
            re.IGNORECASE,
        )

        matches = list(pattern.finditer(prose))
        if not matches:
            return None

        manifest = MultiFileChangeManifest(goal=goal)
        for m in matches:
            target_path = m.group(1) or m.group(2) or m.group(3)
            code_block = m.group(4)
            if not target_path or not code_block:
                continue

            clean_path = target_path.replace("\\", "/").strip()
            file_p = workspace_root / clean_path
            is_new = not file_p.exists()

            op = FileChangeOperation.create(
                subpath=clean_path,
                replacement_content=code_block,
                target_content="" if is_new else "",
                operation_kind="create" if is_new else "modify",
            )
            manifest.add_operation(op)

        return manifest if manifest.operations else None

    def evaluate_prose_turn(
        self,
        prose: str,
        turn_attempt: int,
        workspace_root: Path,
    ) -> Tuple[bool, Optional[MultiFileChangeManifest], str]:
        """Evaluates a turn where prose was emitted, returning (can_recover, manifest, diagnostic_msg)."""
        if turn_attempt >= self.max_retries:
            return (
                False,
                None,
                f"Bounded recovery budget exhausted ({turn_attempt}/{self.max_retries} attempts). Halting loop.",
            )

        manifest = self.extract_manifest_from_prose(prose, workspace_root)
        if manifest and manifest.operations:
            return (
                True,
                manifest,
                f"Successfully extracted {len(manifest.operations)} file operations from model prose.",
            )

        return (
            False,
            None,
            (
                f"[Tool Call Required (Attempt {turn_attempt + 1}/{self.max_retries})]: "
                "You emitted conversational narrative or unformatted prose without invoking editing tools. "
                "You MUST call `propose_edit` or `write_file` using structured JSON format."
            ),
        )
