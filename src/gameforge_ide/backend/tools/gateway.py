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
from .git_tools import GitTools
from .terminal_tools import TerminalTools
from .unreal_tools import UnrealEngineTools


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_approval: bool = False


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

    def get_definitions(self) -> List[ToolDefinition]:
        """Returns schemas for all registered tools."""
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

    def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        *,
        approval_granted: bool = False,
    ) -> Dict[str, Any]:
        """Dispatch a tool, requiring explicit approval for marked actions.

        ``propose_edit`` only records a preview and remains available to the
        agent; the subsequent apply action is separately approval-gated.
        """
        t0 = time.time()
        definition = next((item for item in self.get_definitions() if item.name == name), None)
        if definition is None:
            return {"status": "ERROR", "error": f"Unknown tool: '{name}'"}
        if definition.requires_approval and name != "propose_edit" and not approval_granted:
            return {
                "status": "PENDING_APPROVAL",
                "tool": name,
                "error": "This tool requires explicit user approval before execution.",
                "execution_time_seconds": round(time.time() - t0, 3),
            }
        try:
            if name == "list_dir":
                res = tool_list_dir(self.boundary, **arguments)
            elif name == "read_file":
                res = tool_read_file(self.boundary, **arguments)
            elif name == "search_code":
                res = tool_search_code(self.boundary, **arguments)
            elif name == "propose_edit":
                res = self.edit_tools.propose_edit(**arguments)
            elif name == "apply_edit":
                res = self.edit_tools.apply_diff(**arguments)
            elif name == "reject_edit":
                res = self.edit_tools.reject_diff(**arguments)
            elif name == "rollback_edit":
                res = self.edit_tools.rollback_diff(**arguments)
            elif name == "run_command":
                res = self.terminal_tools.run_command(**arguments)
            elif name == "git_status":
                res = self.git_tools.get_status()
            elif name == "git_diff":
                res = self.git_tools.get_diff(**arguments)
            elif name == "unreal_engine_info":
                res = self.unreal_tools.get_engine_info()
            elif name == "unreal_find_projects":
                res = {"status": "SUCCESS", "projects": self.unreal_tools.find_uprojects()}
            elif name == "unreal_build":
                res = self.unreal_tools.run_staged_build(**arguments)
            elif name == "generate_3d_mesh":
                res = self.asset_tools.generate_cube(**arguments)
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
