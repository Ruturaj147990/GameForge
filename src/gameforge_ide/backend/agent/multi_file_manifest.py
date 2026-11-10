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
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field

from ..tools.gateway import ToolGateway
from .code_verify import _strip_cpp_comments_and_strings

logger = logging.getLogger(__name__)

OperationKind = Literal["create", "modify", "delete"]
FileType = Literal["header", "source", "config", "asset", "other"]
ManifestStatus = Literal["staged", "applied", "verified", "failed", "rolled_back"]

_CPP_SKIP_NAMES = {
    "if", "for", "while", "switch", "return", "catch", "sizeof", "alignof",
    "decltype", "static_assert", "UCLASS", "USTRUCT", "UENUM", "UPROPERTY",
    "UFUNCTION", "GENERATED_BODY", "GENERATED_UCLASS_BODY", "TEXT",
    "DECLARE_DYNAMIC_MULTICAST_DELEGATE", "DECLARE_DELEGATE",
}


def _extract_declared_methods(header_content: str, class_name: Optional[str] = None) -> List[str]:
    """Extract C++ method names declared in a header that require a `.cpp` definition.

    Ignores:
    - `UFUNCTION(BlueprintImplementableEvent)` and `UFUNCTION(BlueprintNativeEvent)`
    - Pure virtual methods (`= 0;`), `= default;`, and `= delete;`
    - Inline header method definitions (`{ ... }`)
    - Constructors (`ClassName(...)`) and destructors (`~ClassName(...)`)
    - Macros and member variable value-initializers
    """
    if not header_content:
        return []

    stripped = _strip_cpp_comments_and_strings(header_content)
    detected_classes: Set[str] = set()
    if class_name:
        detected_classes.add(class_name)
    for cm in re.finditer(r"\b(?:class|struct)\s+(?:[A-Z0-9_]+_API\s+)?([A-Za-z_]\w*)\b\s*(?::|[^{;]*\{)", stripped):
        detected_classes.add(cm.group(1))

    # Strip inline function bodies `{ ... }` inside the class body while keeping class-level braces intact:
    # We inspect line-by-line / statement-by-statement while tracking UFUNCTION specifiers.
    lines = stripped.splitlines()
    methods: List[str] = []
    seen: Set[str] = set()
    skip_next_ufunction = False

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check for UFUNCTION macro
        if re.match(r"^UFUNCTION\s*\(", line):
            ufunc_text = line
            while ")" not in ufunc_text and i + 1 < n:
                i += 1
                ufunc_text += " " + lines[i].strip()
            if re.search(r"\b(?:BlueprintImplementableEvent|BlueprintNativeEvent)\b", ufunc_text):
                skip_next_ufunction = True
            else:
                skip_next_ufunction = False
            i += 1
            continue

        # Skip other Unreal macros or preprocessor directives
        if line.startswith("#") or re.match(r"^(?:UPROPERTY|UCLASS|USTRUCT|UENUM|GENERATED_BODY|GENERATED_UCLASS_BODY)\b", line):
            i += 1
            continue

        # Ignore destructor declarations (`~ClassName(...)`)
        if "~" in line:
            skip_next_ufunction = False
            i += 1
            continue

        # Join multi-line declaration up to `;` or `{`
        stmt = line
        j = i
        while ";" not in stmt and "{" not in stmt and j + 1 < n and (j - i) < 6:
            j += 1
            nxt = lines[j].strip()
            if nxt.startswith(("#", "UFUNCTION", "UPROPERTY", "public:", "protected:", "private:")):
                break
            stmt += " " + nxt

        # If this statement opens an inline body `{`, skip past its closing `}`
        if "{" in stmt and (";" not in stmt or stmt.find("{") < stmt.find(";")):
            skip_next_ufunction = False
            i = j + 1
            continue

        # Check for pure virtual `= 0`, `= default`, `= delete`
        if re.search(r"=\s*(?:0|default|delete)\s*;", stmt):
            skip_next_ufunction = False
            i = j + 1
            continue

        m = re.match(
            r"^(?:virtual\s+|static\s+|inline\s+|FORCEINLINE\s+|explicit\s+|constexpr\s+)*"
            r"(?:const\s+)?"
            r"(?P<ret>[A-Za-z_][\w:<>*&\s]*?)\s+"
            r"(?P<name>[A-Za-z_]\w*)\s*"
            r"\((?P<params>[^;{}]*)\)\s*"
            r"(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?(?:final\s*)?;\s*$",
            stmt,
        )
        if m:
            ret_type = m.group("ret").strip()
            fn_name = m.group("name").strip()
            params_str = m.group("params").strip()

            if skip_next_ufunction:
                skip_next_ufunction = False
                i = j + 1
                continue

            # Ignore constructors, keywords, macros, or invalid return types
            if (
                fn_name not in _CPP_SKIP_NAMES
                and fn_name not in detected_classes
                and ret_type not in ("class", "struct", "enum", "namespace", "return", "typedef", "using")
                and not fn_name.startswith("DECLARE_")
            ):
                # Filter out member variable constructor calls like `FVector Offset(0.f, 0.f, 100.f);`
                # Valid parameter lists are either empty, `void`, or start with a type identifier (not a number/quote)
                is_value_init = bool(params_str) and bool(re.match(r"^[\d\-\+\"']", params_str))
                if not is_value_init and fn_name not in seen:
                    seen.add(fn_name)
                    methods.append(fn_name)
            i = j + 1
            continue

        if ";" in stmt:
            skip_next_ufunction = False
        i += 1

    return methods


def check_missing_cpp_definitions(
    header_content: str,
    cpp_content: str,
    class_name: Optional[str] = None,
) -> List[str]:
    """Return list of method names declared in `header_content` that lack a definition in `cpp_content`."""
    declared = _extract_declared_methods(header_content, class_name=class_name)
    if not declared:
        return []
    stripped_cpp = _strip_cpp_comments_and_strings(cpp_content or "")
    missing: List[str] = []
    for fn_name in declared:
        if class_name:
            pat = rf"\b{re.escape(class_name)}\s*::\s*{re.escape(fn_name)}\s*\("
        else:
            pat = rf"::\s*{re.escape(fn_name)}\s*\("
        if not re.search(pat, stripped_cpp):
            missing.append(fn_name)
    return missing


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

        # Scan declared class / struct / enum names (excluding forward declarations ending in ;)
        for m in re.finditer(r"\b(?:class|struct)\s+(?:[A-Z0-9_]+_API\s+)?([A-Za-z0-9_]+)\s*([^;{]*?)(?=\{|;)", content):
            tail = content[m.end() : m.end() + 1]
            if tail == "{":
                declared.append(m.group(1))

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

    @staticmethod
    def _extract_declared_methods(header_content: str, class_name: Optional[str] = None) -> List[str]:
        return _extract_declared_methods(header_content, class_name=class_name)

    def validate_header_source_definitions(self) -> Tuple[bool, List[str]]:
        """Check that header method declarations have matching definitions in paired `.cpp` operations."""
        errors: List[str] = []
        headers_by_stem: Dict[str, FileChangeOperation] = {}
        sources_by_stem: Dict[str, FileChangeOperation] = {}
        for op in self.operations:
            stem = Path(op.subpath).stem
            if op.file_type == "header":
                headers_by_stem[stem] = op
            elif op.file_type == "source":
                sources_by_stem[stem] = op

        for stem, h_op in headers_by_stem.items():
            s_op = sources_by_stem.get(stem)
            if s_op is None or not h_op.replacement_content or not s_op.replacement_content:
                continue
            missing = check_missing_cpp_definitions(h_op.replacement_content, s_op.replacement_content)
            for fn in missing:
                errors.append(f"{s_op.subpath}: Missing definition for method `{fn}` declared in `{h_op.subpath}`.")
        return len(errors) == 0, errors

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

    def validate_and_sanitize_cpp_invariants(self) -> List[str]:
        """Automatically sanitizes known invalid C++ syntax before writing/compilation."""
        sanitized_notes = []
        try:
            from ...pipeline.autofix import _convert_key_switch_to_if
        except Exception:
            _convert_key_switch_to_if = None

        for op in self.operations:
            if op.file_type not in ("source", "header"):
                continue

            content = op.replacement_content
            modified = False

            # 1. Switch on FKey
            if _convert_key_switch_to_if and (re.search(r"\bswitch\s*\(\s*Key\s*\)", content) or "case EKeys::" in content):
                new_content, fixed = _convert_key_switch_to_if(content)
                if fixed:
                    content = new_content
                    modified = True
                    sanitized_notes.append(f"{op.subpath}: converted switch(Key) to if/else chain")

            # 2. .ToFloat() on FVector
            if ".ToFloat()" in content:
                content = re.sub(
                    r'FQuat\s*\(\s*(?:FVector(?:\([^)]*\)|::\w+))\s*,\s*(\w+)\.ToFloat\(\)\s*\)',
                    r'\1.Rotation().Quaternion()',
                    content,
                )
                content = re.sub(r'(\b\w+)\.ToFloat\(\)', r'\1.Size()', content)
                modified = True
                sanitized_notes.append(f"{op.subpath}: fixed invalid FVector::ToFloat() call")

            # 3. AddActorWorldRotation FVector
            if re.search(r'AddActorWorldRotation\s*\(\s*FVector\(', content):
                content = re.sub(r'AddActorWorldRotation\s*\(\s*FVector\(', 'AddActorWorldRotation(FRotator(', content)
                modified = True
                sanitized_notes.append(f"{op.subpath}: replaced FVector with FRotator in AddActorWorldRotation")

            if modified:
                op.replacement_content = content

        return sanitized_notes

    def get_topological_execution_order(self) -> List[FileChangeOperation]:
        """Calculates safe edit ordering:
        1. Headers before sources (.h before .cpp).
        2. Declarations before consumers (files declaring symbols before files referencing them).
        3. Base headers before derived headers.
        """
        ops = list(self.operations)
        if len(ops) <= 1:
            return ops

        symbol_to_op: Dict[str, int] = {}
        for idx, op in enumerate(ops):
            for sym in op.symbols_declared:
                symbol_to_op[sym] = idx

        adj: Dict[int, Set[int]] = {i: set() for i in range(len(ops))}
        in_degree: Dict[int, int] = {i: 0 for i in range(len(ops))}

        for idx, op in enumerate(ops):
            if op.file_type == "source":
                header_name = Path(op.subpath).with_suffix(".h").name
                for o_idx, other in enumerate(ops):
                    if o_idx != idx and other.file_type == "header" and Path(other.subpath).name == header_name:
                        adj[o_idx].add(idx)

            for ref_sym in op.symbols_referenced:
                if ref_sym in symbol_to_op:
                    decl_idx = symbol_to_op[ref_sym]
                    if decl_idx != idx:
                        adj[decl_idx].add(idx)

            for dep_path in op.dependencies:
                dep_clean = dep_path.replace("\\", "/")
                for o_idx, other in enumerate(ops):
                    if o_idx != idx and (other.subpath == dep_clean or Path(other.subpath).name == dep_clean):
                        adj[o_idx].add(idx)

        for u in adj:
            for v in adj[u]:
                in_degree[v] += 1

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

        if len(ordered_indices) < len(ops):
            remaining = [ops[i].subpath for i in range(len(ops)) if i not in ordered_indices]
            raise ValueError(
                "Multi-file dependency cycle detected; unresolved operations: "
                + ", ".join(remaining)
            )

        return [ops[i] for i in ordered_indices]

    def apply(
        self,
        gateway: ToolGateway,
        verify_compilation: bool = True,
        rollback_on_failure: bool = True,
        *,
        approval_granted: bool = False,
        permissions_mode: Any = None,
    ) -> MultiFileApplyResult:
        """Apply a validated multi-file change set."""
        result = MultiFileApplyResult(
            manifest_id=self.manifest_id,
            status="staged",
            total_operations=len(self.operations),
        )

        if not self.operations:
            result.status = "failed"
            result.error_message = "Manifest contains no operations."
            return result

        valid_refl, refl_errs = self.validate_reflection_consistency()
        if not valid_refl:
            result.status = "failed"
            result.error_message = "Reflection consistency check failed."
            result.diagnostics = refl_errs
            return result

        self.validate_and_sanitize_cpp_invariants()

        try:
            ordered_ops = self.get_topological_execution_order()
        except ValueError as exc:
            result.status = "failed"
            result.error_message = str(exc)
            result.diagnostics.append(str(exc))
            return result

        ws_root = Path(gateway.workspace_root).resolve()
        validated_paths: Dict[str, Path] = {}
        snapshots: Dict[str, Optional[str]] = {}

        for op in ordered_ops:
            raw = Path(op.subpath)
            if raw.is_absolute() or any(part == ".." for part in raw.parts):
                result.status = "failed"
                result.error_message = f"Unsafe manifest path: {op.subpath!r}"
                return result
            try:
                candidate = gateway.boundary.validate_path(str(ws_root / raw), allow_write=True)
                candidate = Path(candidate)
                resolved_parent = candidate.parent.resolve()
                if resolved_parent != ws_root and ws_root not in resolved_parent.parents:
                    raise ValueError("Target parent escapes the workspace.")
                if candidate.is_symlink():
                    raise ValueError("Symbolic-link targets are not accepted in a multi-file manifest.")
                validated_paths[op.subpath] = candidate
            except Exception as exc:
                result.status = "failed"
                result.error_message = f"Unsafe manifest path {op.subpath!r}: {exc}"
                return result

        for op in ordered_ops:
            file_path = validated_paths[op.subpath]
            if file_path.exists():
                if not file_path.is_file():
                    result.status = "failed"
                    result.error_message = f"Target is not a regular file: {op.subpath}"
                    return result
                try:
                    snapshots[op.subpath] = file_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    result.status = "failed"
                    result.error_message = f"Could not snapshot {op.subpath}: {exc}"
                    return result
            else:
                snapshots[op.subpath] = None

        for op in ordered_ops:
            exists = snapshots[op.subpath] is not None
            if op.operation_kind == "create" and exists:
                result.status = "failed"
                result.error_message = f"Create operation target already exists: {op.subpath}"
                return result
            if op.operation_kind in ("modify", "delete") and not exists:
                result.status = "failed"
                result.error_message = f"{op.operation_kind.title()} operation target does not exist: {op.subpath}"
                return result

        applied_paths: List[str] = []

        def _tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
            kwargs: Dict[str, Any] = {"approval_granted": approval_granted}
            if permissions_mode is not None:
                kwargs["permissions_mode"] = permissions_mode
            return gateway.execute_tool(name, args, **kwargs)

        for op in ordered_ops:
            try:
                if op.operation_kind == "delete":
                    res = _tool("delete_file", {"subpath": op.subpath})
                elif op.operation_kind == "create":
                    res = _tool("write_file", {"subpath": op.subpath, "content": op.replacement_content})
                else:
                    if not op.target_content:
                        res = _tool(
                            "write_file",
                            {"subpath": op.subpath, "content": op.replacement_content},
                        )
                    else:
                        res = _tool(
                            "propose_edit",
                            {
                                "subpath": op.subpath,
                                "target_content": op.target_content,
                                "replacement_content": op.replacement_content,
                            },
                        )
                        if res.get("diff_id"):
                            res = _tool("apply_edit", {"diff_id": res["diff_id"]})

                if res.get("status") == "PENDING_APPROVAL":
                    raise PermissionError(
                        f"Approval required for {op.operation_kind} operation on {op.subpath}."
                    )
                if res.get("status") != "SUCCESS":
                    raise RuntimeError(
                        f"Operation on {op.subpath} failed: {res.get('error', 'unknown error')}"
                    )
                applied_paths.append(op.subpath)
            except Exception as exc:
                result.status = "failed"
                result.error_message = str(exc)
                result.operations_applied = len(applied_paths)
                result.modified_paths = list(applied_paths)
                if rollback_on_failure and applied_paths:
                    rollback_ok, rollback_errors = self._rollback_snapshots(
                        ws_root, snapshots, applied_paths, validated_paths
                    )
                    result.diagnostics.extend(rollback_errors)
                    result.status = "rolled_back" if rollback_ok else "failed"
                else:
                    result.status = "failed"
                return result

        result.operations_applied = len(applied_paths)
        result.modified_paths = list(applied_paths)
        result.status = "applied"

        if verify_compilation and self.verification_command:
            try:
                shell_name = "powershell" if os.name == "nt" else "bash"
                cmd_res = _tool(
                    "run_command",
                    {"command": self.verification_command, "shell": shell_name},
                )
                if cmd_res.get("status") == "PENDING_APPROVAL":
                    raise PermissionError("Compilation verification command requires approval.")
                stdout_str = cmd_res.get("stdout", "")
                stderr_str = cmd_res.get("stderr", "")
                result.verification_output = stdout_str + ("\n" + stderr_str if stderr_str else "")
                if cmd_res.get("exit_code", -1) == 0 and cmd_res.get("status") == "SUCCESS":
                    result.verification_passed = True
                    result.status = "verified"
                else:
                    result.error_message = (
                        f"Compilation verification failed with exit code "
                        f"{cmd_res.get('exit_code', -1)}."
                    )
                    result.diagnostics.append(result.verification_output[:2000])
                    if rollback_on_failure:
                        rollback_ok, rollback_errors = self._rollback_snapshots(
                            ws_root, snapshots, applied_paths, validated_paths
                        )
                        result.diagnostics.extend(rollback_errors)
                        result.status = "rolled_back" if rollback_ok else "failed"
                    else:
                        result.status = "failed"
            except Exception as exc:
                result.verification_passed = False
                result.error_message = f"Compilation verification execution error: {exc}"
                if rollback_on_failure:
                    rollback_ok, rollback_errors = self._rollback_snapshots(
                        ws_root, snapshots, applied_paths, validated_paths
                    )
                    result.diagnostics.extend(rollback_errors)
                    result.status = "rolled_back" if rollback_ok else "failed"
                else:
                    result.status = "failed"
        else:
            result.verification_passed = not bool(self.verification_command)
            result.status = "applied"

        return result

    @staticmethod
    def _rollback_snapshots(
        workspace_root: Path,
        snapshots: Dict[str, Optional[str]],
        modified_paths: List[str],
        validated_paths: Dict[str, Path],
    ) -> Tuple[bool, List[str]]:
        """Restore only modified files using atomic replacement and report failures."""
        errors: List[str] = []
        root_resolved = workspace_root.resolve()
        for subpath in reversed(modified_paths):
            original_text = snapshots.get(subpath)
            fp = validated_paths.get(subpath)
            if fp is None:
                errors.append(f"Rollback skipped {subpath}: no validated path was recorded.")
                continue
            try:
                parent = fp.parent.resolve()
                if parent != root_resolved and root_resolved not in parent.parents:
                    raise ValueError("Rollback target escaped workspace.")
                if fp.is_symlink():
                    raise ValueError("Rollback refuses to follow symbolic links.")
                if original_text is None:
                    if fp.exists():
                        try:
                            fp.unlink(missing_ok=True)
                        except OSError as exc:
                            errors.append(f"Failed to unlink created file {subpath}: {exc}")
                else:
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fd, temp_name = tempfile.mkstemp(
                        prefix=f".{fp.name}.rollback-", dir=str(fp.parent)
                    )
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                            handle.write(original_text)
                            handle.flush()
                            os.fsync(handle.fileno())
                        os.replace(temp_name, fp)
                    finally:
                        if os.path.exists(temp_name):
                            try:
                                os.unlink(temp_name)
                            except OSError:
                                pass
            except Exception as exc:
                errors.append(f"Failed to rollback {subpath}: {exc}")
                logger.exception("Failed to rollback snapshot for %s", subpath)
        return not errors, errors


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
