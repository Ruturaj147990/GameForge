"""Typed Tool Gateway and Dispatcher for GameForge IDE."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from ..security.boundary import BoundaryManager, SecurityViolationError
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
                        "subpath": {"type": "string", "default": "."},
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
                        "subpath": {"type": "string"},
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
                        "query": {"type": "string"},
                        "kind": {"type": "string"},
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
                        "query": {"type": "string"},
                        "subpath": {"type": "string", "default": "."},
                        "is_regex": {"type": "boolean", "default": False},
                    },
                    "required": ["query"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="propose_edit",
                description="Propose a file edit, generating a unified diff for developer review.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string"},
                        "target_content": {"type": "string"},
                        "replacement_content": {"type": "string"},
                    },
                    "required": ["subpath", "replacement_content"],
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

    def tool_requires_approval(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """True when dispatching ``name`` with ``arguments`` needs explicit user approval."""
        canonical_name = TOOL_ALIASES.get(name, name)
        args = dict(arguments) if isinstance(arguments, dict) else {}
        if canonical_name == "propose_edit":
            return False
        if canonical_name == "unreal_editor" and args.get("op") in READ_ONLY_EDITOR_OPS:
            return False  # T0 read-back operations
        definition = next((item for item in self.get_definitions() if item.name == canonical_name), None)
        if definition is None:
            # Fail closed: unrecognized tool actions require explicit approval or are rejected
            return True
        return definition.requires_approval

    def execute_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        approval_granted: bool = False,
    ) -> Dict[str, Any]:
        """Dispatch a tool, requiring explicit approval for marked actions.

        ``propose_edit`` only records a preview and remains available to the
        agent; the subsequent apply action is separately approval-gated.
        """
        t0 = time.time()
        args = dict(arguments) if isinstance(arguments, dict) else {}
        canonical_name = TOOL_ALIASES.get(name, name)

        definition = next((item for item in self.get_definitions() if item.name == canonical_name), None)
        if definition is None:
            return {"status": "ERROR", "error": f"Unknown tool: '{name}'"}

        if self.tool_requires_approval(canonical_name, args) and not approval_granted:
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

