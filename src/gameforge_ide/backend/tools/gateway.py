"""Typed Tool Gateway and Dispatcher for GameForge IDE."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from ..security.boundary import BoundaryManager, SecurityViolationError
from ..models.modes import AutonomyProfile
from .asset_tools import ProceduralMeshGenerator
from .edit_tools import EditTools
from .fs_tools import tool_list_dir, tool_read_file, tool_search_code
from ...unreal import op_catalog
from .game_tools import READ_ONLY_EDITOR_OPS, GameTools
from .git_tools import GitTools
from .terminal_tools import TerminalTools
from .unreal_tools import UnrealEngineTools


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_approval: bool = False


TOOL_ALIASES: Dict[str, str] = {
    "apply_diff": "apply_edit",
    "apply_diffs_batch": "apply_batch",
    "reject_diff": "reject_edit",
    "rollback_diff": "rollback_edit",
    "rollback_diffs_batch": "rollback_batch",
}


class ToolGateway:
    """Central typed dispatcher for all tools in GameForge IDE."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.boundary = BoundaryManager(self.workspace_root)
        self.edit_tools = EditTools(self.boundary)
        self.terminal_tools = TerminalTools(self.workspace_root)
        self.git_tools = GitTools(self.workspace_root)
        self.unreal_tools = UnrealEngineTools(self.workspace_root)
        self.asset_tools = ProceduralMeshGenerator()
        self.game_tools = GameTools(self.workspace_root)

    def get_definitions(self, for_hosted: bool = False) -> List[ToolDefinition]:
        """Returns schemas for all registered tools."""
        from ...unreal import op_schemas

        if for_hosted:
            one_of = []
            for op_name in sorted(op_catalog.agent_ops()):
                model = op_schemas.SCHEMAS.get(op_name)
                args_schema = model.model_json_schema() if model else {"type": "object"}
                one_of.append({
                    "type": "object",
                    "properties": {
                        "uproject": {"type": "string"},
                        "op": {"const": op_name},
                        "args": args_schema,
                    },
                    "required": ["uproject", "op"],
                })
            unreal_editor_params: Dict[str, Any] = {"oneOf": one_of}
        else:
            unreal_editor_params = {
                "type": "object",
                "properties": {
                    "uproject": {"type": "string"},
                    "op": {"type": "string", "enum": op_catalog.agent_ops()},
                    "args": {"type": "object"},
                },
                "required": ["uproject", "op"],
            }

        return [
            ToolDefinition(
                name="list_dir",
                description="List files and directories in a given path relative to workspace root.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string", "default": ".", "description": "Path relative to workspace root (aliases: path, directory)."},
                        "path": {"type": "string"},
                        "max_depth": {"type": "integer", "default": 2},
                    },
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="read_file",
                description="Read line-numbered contents of a file in the workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string", "description": "Path relative to workspace root (aliases: file_path, path)."},
                        "file_path": {"type": "string"},
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "default": 1},
                        "end_line": {"type": "integer", "optional": True},
                    },
                    "required": ["subpath"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="search_index",
                description="Search indexed C++ symbols, config settings, and assets across the project.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for symbol name or asset (aliases: q, symbol)."},
                        "q": {"type": "string"},
                        "kind": {"type": "string", "description": "Filter by kind: class, struct, enum, function, property."},
                        "limit": {"type": "integer", "default": 50},
                        "offset": {"type": "integer", "default": 0},
                    },
                    "required": ["query"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="search_code",
                description="Search workspace for text or regex patterns.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Text or regex pattern (aliases: pattern)."},
                        "pattern": {"type": "string"},
                        "subpath": {"type": "string", "default": ".", "description": "Directory relative to workspace root (aliases: path)."},
                        "path": {"type": "string"},
                        "is_regex": {"type": "boolean", "default": False},
                    },
                    "required": ["query"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="propose_edit",
                description="Propose a file edit or new file creation, generating a unified diff for developer review. Accepts subpath, file_path, or path.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string", "description": "Path relative to workspace root (aliases: file_path, path)."},
                        "file_path": {"type": "string"},
                        "path": {"type": "string"},
                        "target_content": {"type": "string", "description": "Target block to replace (aliases: target, old_content)."},
                        "replacement_content": {"type": "string", "description": "New content to insert (aliases: replacement, new_content)."},
                    },
                    "required": ["replacement_content"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="apply_edit",
                description="Apply an approved diff to the filesystem.",
                parameters={
                    "type": "object",
                    "properties": {
                        "diff_id": {"type": "string"},
                    },
                    "required": ["diff_id"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="apply_batch",
                description="Atomically apply a list of approved diff IDs across multiple files.",
                parameters={
                    "type": "object",
                    "properties": {
                        "diff_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["diff_ids"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="rollback_edit",
                description="Revert an applied diff back to pre-edit state.",
                parameters={
                    "type": "object",
                    "properties": {
                        "diff_id": {"type": "string"},
                    },
                    "required": ["diff_id"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="rollback_batch",
                description="Atomically roll back a list of applied diff IDs in reverse order.",
                parameters={
                    "type": "object",
                    "properties": {
                        "diff_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["diff_ids"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="reject_edit",
                description="Reject a proposed diff without modifying the filesystem.",
                parameters={
                    "type": "object",
                    "properties": {
                        "diff_id": {"type": "string"},
                        "reason": {"type": "string", "default": "User rejected"},
                    },
                    "required": ["diff_id"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="write_file",
                description="Atomically write or overwrite a file in the workspace with rollback tracking.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string", "description": "Target file path relative to workspace."},
                        "content": {"type": "string", "description": "Full file content to write."},
                        "file_path": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["subpath", "content"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="verify_disk",
                description="Verify that a file exists on disk and optionally contains an expected content fragment.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string", "description": "Target file path relative to workspace."},
                        "expected_fragment": {"type": "string", "default": ""},
                    },
                    "required": ["subpath"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="run_command",
                description="Execute an approved non-shell command inside the workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "subpath": {"type": "string", "default": "."},
                        "timeout_seconds": {"type": "integer", "default": 60},
                    },
                    "required": ["command"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="git_status",
                description="Inspect git branch, modified files, and untracked files.",
                parameters={"type": "object", "properties": {}},
                requires_approval=False,
            ),
            ToolDefinition(
                name="git_diff",
                description="Inspect current unstaged git diffs in the workspace.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "default": ""}},
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="unreal_engine_info",
                description="Query host Unreal Engine 5.7 installation and toolchain.",
                parameters={"type": "object", "properties": {}},
                requires_approval=False,
            ),
            ToolDefinition(
                name="unreal_find_projects",
                description="Find all .uproject Unreal projects in the workspace.",
                parameters={"type": "object", "properties": {}},
                requires_approval=False,
            ),
            ToolDefinition(
                name="unreal_build",
                description="Run memory-safe staged Unreal project compilation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "uproject_rel_path": {"type": "string"},
                        "target_name": {"type": "string", "optional": True},
                    },
                    "required": ["uproject_rel_path"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="plan_game",
                description="Turn a game request into a Game Spec (recipe, parameters, acceptance tests) without side effects.",
                parameters={"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]},
            ),
            ToolDefinition(
                name="create_game",
                description="Create a complete playable Unreal game from a Game Spec: scaffold, build, level, tests, package, self-test.",
                parameters={"type": "object", "properties": {"params": {"type": "object"},
                                                             "package": {"type": "boolean", "default": True}},
                            "required": ["params"]},
                requires_approval=True,
            ),
            ToolDefinition(
                name="create_game_freeform",
                description="Create a game with no matching recipe: a model writes gameplay C++ on the verified host framework; compile, repair, package and self-test gates apply.",
                parameters={"type": "object", "properties": {"prompt": {"type": "string"}, "title": {"type": "string"}},
                            "required": ["prompt"]},
                requires_approval=True,
            ),
            ToolDefinition(
                name="unreal_editor",
                description=("Run one named operation in the live Unreal Editor for a project. Read-only ops run "
                             "without approval. Ops by domain: " + op_catalog.describe_for_agent()),
                parameters=unreal_editor_params,
                requires_approval=True,
            ),
            ToolDefinition(
                name="unreal_run_tests",
                description="Run Unreal automation tests for a project and return parsed results.",
                parameters={"type": "object", "properties": {"uproject": {"type": "string"},
                                                             "test_filter": {"type": "string", "default": "GameForge"}},
                            "required": ["uproject"]},
                requires_approval=True,
            ),
            ToolDefinition(
                name="unreal_package",
                description="Cook and package an Unreal project for Windows.",
                parameters={"type": "object", "properties": {"uproject": {"type": "string"}}, "required": ["uproject"]},
                requires_approval=True,
            ),
            ToolDefinition(
                name="play_game",
                description="Launch a packaged game produced by GameForge.",
                parameters={"type": "object", "properties": {"exe": {"type": "string"}}, "required": ["exe"]},
                requires_approval=True,
            ),
            ToolDefinition(
                name="generate_3d_mesh",
                description="Generate a procedural 3D mesh (.obj, .mtl) with Unreal import metadata.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "default": "SM_BlockoutCube"},
                        "size": {"type": "number", "default": 100.0},
                    },
                },
                requires_approval=False,
            ),
        ]

    def tool_requires_approval(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        autonomy_profile: Optional[AutonomyProfile | str] = None,
    ) -> bool:
        """True when dispatching ``name`` with ``arguments`` needs explicit user approval under active autonomy profile."""
        canonical_name = TOOL_ALIASES.get(name, name)
        args = dict(arguments) if isinstance(arguments, dict) else {}
        profile = AutonomyProfile(autonomy_profile) if autonomy_profile else AutonomyProfile.MANUAL

        # Read-only operations never require approval in any profile
        read_only_tools = {
            "list_dir", "read_file", "search_code", "search_index", "verify_disk",
            "git_status", "git_diff", "unreal_engine_info", "unreal_find_projects",
            "generate_3d_mesh", "reject_edit", "plan_game",
        }
        if canonical_name in read_only_tools:
            return False

        if canonical_name == "unreal_editor" and args.get("op") in READ_ONLY_EDITOR_OPS:
            return False  # T0 read-back operations

        if canonical_name == "propose_edit":
            # propose_edit produces diff preview without mutating disk
            return False

        # In MANUAL profile: all mutations, commands, builds require approval
        if profile == AutonomyProfile.MANUAL:
            return True

        # In AUTO_EDIT profile: safe file modifications inside workspace proceed automatically
        if profile == AutonomyProfile.AUTO_EDIT:
            if canonical_name in ("apply_edit", "apply_batch", "write_file", "rollback_edit", "rollback_batch"):
                return False
            # Commands, builds, packages, unreal editor mutations still require approval
            return True

        # In AGENTIC profile: safe file edits, allowlisted project commands, safe builds & tests proceed automatically
        if profile == AutonomyProfile.AGENTIC:
            if canonical_name in ("apply_edit", "apply_batch", "write_file", "rollback_edit", "rollback_batch"):
                return False
            if canonical_name in ("unreal_run_tests", "unreal_build"):
                return False
            if canonical_name == "run_command":
                cmd = str(args.get("command", "")).strip().lower()
                # Allowlisted non-destructive dev commands
                allowlist_starts = ("pytest", "python -m pytest", "git ", "git.exe ", "cargo test", "ctest")
                if any(cmd.startswith(p) for p in allowlist_starts):
                    return False
                return True

        definition = next((item for item in self.get_definitions() if item.name == canonical_name), None)
        if definition is None:
            # Fail closed: unrecognized tool actions require explicit approval or are rejected
            return True
        return definition.requires_approval

    def _normalize_arguments(self, canonical_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(args)

        # Path parameter normalization across tools
        path_val = (
            normalized.get("subpath")
            or normalized.get("file_path")
            or normalized.get("path")
            or normalized.get("filepath")
            or normalized.get("file")
            or normalized.get("dir_path")
            or normalized.get("directory")
            or normalized.get("folder")
        )
        if path_val and "subpath" not in normalized:
            normalized["subpath"] = path_val

        if canonical_name == "propose_edit":
            target = (
                normalized.get("target_content")
                or normalized.get("target")
                or normalized.get("old_content")
                or normalized.get("old_str")
                or normalized.get("search")
                or normalized.get("find")
                or normalized.get("original_content")
                or normalized.get("original_text")
                or normalized.get("old")
            )
            if target is not None and "target_content" not in normalized:
                normalized["target_content"] = target
            elif "target_content" not in normalized:
                normalized["target_content"] = ""

            repl = (
                normalized.get("replacement_content")
                or normalized.get("replacement")
                or normalized.get("new_content")
                or normalized.get("new_str")
                or normalized.get("replace")
                or normalized.get("new")
                or normalized.get("content")
                or normalized.get("text")
            )
            if repl is not None and "replacement_content" not in normalized:
                normalized["replacement_content"] = repl

        elif canonical_name in ("apply_edit", "rollback_edit", "reject_edit"):
            diff_id = normalized.get("diff_id") or normalized.get("id") or normalized.get("diff")
            if diff_id and "diff_id" not in normalized:
                normalized["diff_id"] = diff_id

        elif canonical_name in ("apply_batch", "rollback_batch"):
            diff_ids = (
                normalized.get("diff_ids")
                or normalized.get("diffs")
                or normalized.get("ids")
                or normalized.get("diff_id")
            )
            if diff_ids is not None:
                if isinstance(diff_ids, str):
                    if "," in diff_ids:
                        normalized["diff_ids"] = [d.strip() for d in diff_ids.split(",") if d.strip()]
                    elif diff_ids.strip():
                        normalized["diff_ids"] = [diff_ids.strip()]
                    else:
                        normalized["diff_ids"] = []
                else:
                    normalized["diff_ids"] = list(diff_ids)

        elif canonical_name == "read_file":
            start = (
                normalized.get("start_line")
                or normalized.get("startLine")
                or normalized.get("line_start")
                or normalized.get("from_line")
            )
            if start is not None:
                try:
                    normalized["start_line"] = int(start)
                except (ValueError, TypeError):
                    pass
            end = (
                normalized.get("end_line")
                or normalized.get("endLine")
                or normalized.get("line_end")
                or normalized.get("to_line")
            )
            if end is not None:
                try:
                    normalized["end_line"] = int(end)
                except (ValueError, TypeError):
                    pass

        elif canonical_name == "search_code":
            q = (
                normalized.get("query")
                or normalized.get("pattern")
                or normalized.get("search_term")
                or normalized.get("text")
            )
            if q is not None and "query" not in normalized:
                normalized["query"] = q

        elif canonical_name == "search_index":
            q = (
                normalized.get("query")
                or normalized.get("q")
                or normalized.get("search")
                or normalized.get("symbol")
            )
            if q is not None and "query" not in normalized:
                normalized["query"] = q
            kind = normalized.get("kind") or normalized.get("type") or normalized.get("symbol_type")
            if kind is not None and "kind" not in normalized:
                normalized["kind"] = kind
            proj = normalized.get("project") or normalized.get("project_name") or normalized.get("proj")
            if proj is not None and "project" not in normalized:
                normalized["project"] = proj

        elif canonical_name == "run_command":
            cmd = normalized.get("command") or normalized.get("cmd")
            if cmd is not None and "command" not in normalized:
                normalized["command"] = cmd
            cwd = (
                normalized.get("subpath")
                or normalized.get("path")
                or normalized.get("cwd")
                or normalized.get("working_dir")
            )
            if cwd is not None and "subpath" not in normalized:
                normalized["subpath"] = cwd
            to = normalized.get("timeout_seconds") or normalized.get("timeout")
            if to is not None and "timeout_seconds" not in normalized:
                try:
                    normalized["timeout_seconds"] = int(to)
                except (ValueError, TypeError):
                    pass

        return normalized

    def execute_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        approval_granted: bool = False,
        autonomy_profile: Optional[AutonomyProfile | str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a tool, requiring explicit approval for marked actions.

        ``propose_edit`` only records a preview and remains available to the
        agent; the subsequent apply action is separately approval-gated.
        """
        t0 = time.time()
        args = dict(arguments) if isinstance(arguments, dict) else {}
        canonical_name = TOOL_ALIASES.get(name, name)
        args = self._normalize_arguments(canonical_name, args)

        definition = next((item for item in self.get_definitions() if item.name == canonical_name), None)
        if definition is None:
            return {"status": "ERROR", "error": f"Unknown tool: '{name}'"}

        if self.tool_requires_approval(canonical_name, args, autonomy_profile=autonomy_profile) and not approval_granted:
            return {
                "status": "PENDING_APPROVAL",
                "tool": name,
                "error": "This tool requires explicit user approval before execution.",
                "execution_time_seconds": round(time.time() - t0, 3),
            }

        # Validate required parameters from tool schema
        params_schema = definition.parameters or {}
        required_params = params_schema.get("required", [])
        missing = [p for p in required_params if p not in args or args[p] is None]
        # Allow propose_edit to use any of ('subpath', 'file_path', 'path')
        if canonical_name == "propose_edit":
            if not any(k in args and args[k] for k in ("subpath", "file_path", "path")):
                missing.append("subpath")
        if missing:
            return {
                "status": "ERROR",
                "error": f"Missing required parameter(s) for tool '{name}': {', '.join(missing)}",
                "execution_time_seconds": round(time.time() - t0, 3),
            }

        try:
            if canonical_name == "search_index":
                from ...index.indexer import ProjectIndex
                from ...core.projects import resolve_project_dir
                proj_name = args.get("project") or args.get("project_name")
                if proj_name:
                    # Enforce workspace boundary check on target project path
                    try:
                        self.boundary.validate_path(proj_name, allow_write=False)
                    except (SecurityViolationError, ValueError) as exc:
                        raise SecurityViolationError(f"Target project path is outside workspace: {exc}")
                    resolved_dir = resolve_project_dir(proj_name, self.workspace_root)
                    if not resolved_dir:
                        return {"status": "ERROR", "error": f"Project not found: '{proj_name}'"}
                    proj_dir = self.boundary.validate_path(resolved_dir, allow_write=False)
                else:
                    proj_dir = self.workspace_root
                try:
                    limit = max(1, min(1000, int(args.get("limit", 50))))
                except (ValueError, TypeError):
                    limit = 50
                try:
                    offset = max(0, int(args.get("offset", 0)))
                except (ValueError, TypeError):
                    offset = 0
                idx = ProjectIndex(proj_dir)
                res = idx.search_symbols(
                    query=str(args.get("query", "")),
                    kind=args.get("kind"),
                    limit=limit,
                    offset=offset,
                )
            elif canonical_name == "list_dir":
                res = tool_list_dir(self.boundary, **args)
            elif canonical_name == "read_file":
                res = tool_read_file(self.boundary, **args)
            elif canonical_name == "search_code":
                res = tool_search_code(self.boundary, **args)
            elif canonical_name == "propose_edit":
                res = self.edit_tools.propose_edit(**args)
            elif canonical_name == "apply_edit":
                res = self.edit_tools.apply_diff(**args)
            elif canonical_name == "apply_batch":
                res = self.edit_tools.apply_batch(**args)
            elif canonical_name == "reject_edit":
                res = self.edit_tools.reject_diff(**args)
            elif canonical_name == "write_file":
                res = self.edit_tools.write_file(**args)
            elif canonical_name == "verify_disk":
                res = self.edit_tools.verify_disk_contents(**args)
            elif canonical_name == "rollback_edit":
                res = self.edit_tools.rollback_diff(**args)
            elif canonical_name == "rollback_batch":
                res = self.edit_tools.rollback_batch(**args)
            elif canonical_name == "run_command":
                res = self.terminal_tools.run_command(**args)
            elif canonical_name == "git_status":
                res = self.git_tools.get_status()
            elif canonical_name == "git_diff":
                res = self.git_tools.get_diff(**args)
            elif canonical_name == "unreal_engine_info":
                res = self.unreal_tools.get_engine_info()
            elif canonical_name == "unreal_find_projects":
                res = {"status": "SUCCESS", "projects": self.unreal_tools.find_uprojects()}
            elif canonical_name == "unreal_build":
                res = self.unreal_tools.run_staged_build(**args)
            elif canonical_name == "plan_game":
                res = self.game_tools.plan_game(**args)
            elif canonical_name == "create_game":
                res = self.game_tools.create_game(**args)
            elif canonical_name == "create_game_freeform":
                res = self.game_tools.create_game_freeform(**args)
            elif canonical_name == "unreal_editor":
                res = self.game_tools.unreal_editor(**args)
            elif canonical_name == "unreal_run_tests":
                res = self.game_tools.unreal_run_tests(**args)
            elif canonical_name == "unreal_package":
                res = self.game_tools.unreal_package(**args)
            elif canonical_name == "play_game":
                res = self.game_tools.play_game(**args)
            elif canonical_name == "generate_3d_mesh":
                res = self.asset_tools.generate_cube(**args)
            else:
                return {"status": "ERROR", "error": f"Unknown tool: '{name}'"}

            res["execution_time_seconds"] = round(time.time() - t0, 3)
            return res
        except SecurityViolationError as e:
            return {
                "status": "BLOCKED",
                "error": f"Security violation: {str(e)}",
                "execution_time_seconds": round(time.time() - t0, 3),
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": f"Tool execution failed: {str(e)}",
                "execution_time_seconds": round(time.time() - t0, 3),
            }

