"""Unreal Engine 5.8 MCP Bridge (WI-10.6).

Read-only client connecting to Unreal 5.8 Model Context Protocol (MCP) service.
Allows listing Toolset Registry tools and invoking read-only inspection operations.
Verifies port coexistence:
- Port 47815: GameForge Native Live Editor SyncContext (P0 WI-0.9)
- Port 8000: Unreal Engine 5.8 MCP Toolset Service
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
READ_ONLY_PREFIXES = (
    "inspect_",
    "get_",
    "list_",
    "query_",
    "read_",
    "describe_",
    "find_",
    "search_",
    "status_",
)
_MUTATING_WORD_RE = re.compile(r"(?:^|_)(delete|remove|modify|set|create|spawn|write|update|exec|destroy|drop|clear|kill)(?:_|$)", re.IGNORECASE)


def _validate_read_only(tool_name: str) -> Optional[str]:
    """Return error message if tool violates read-only safety, or None if valid."""
    lower = tool_name.lower().strip()
    if not lower.startswith(READ_ONLY_PREFIXES):
        return f"Tool '{tool_name}' rejected: GameForge MCP Bridge is strictly read-only"
    # Reject mutating compound operations like inspect_and_modify or get_and_delete
    for pfx in READ_ONLY_PREFIXES:
        if lower.startswith(pfx):
            remainder = lower[len(pfx):]
            m = _MUTATING_WORD_RE.search(remainder)
            if m:
                return f"Tool '{tool_name}' rejected: contains mutating action '{m.group(1)}'"
            break
    return None


class UnrealMcpClient:
    """Read-only client for the Unreal Engine 5.8 MCP Toolset Registry."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        if host.lower() not in ALLOWED_LOOPBACK_HOSTS:
            raise ValueError(
                f"Invalid host '{host}': GameForge MCP Bridge is strictly loopback only ({', '.join(sorted(ALLOWED_LOOPBACK_HOSTS))})"
            )
        self.host = host
        self.port = port
        self.endpoint = f"http://{host}:{port}/mcp"

    def list_tools(self, timeout_s: float = 3.0) -> List[Dict[str, Any]]:
        """Query Toolset Registry for registered MCP tools."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1,
        }
        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "GameForge-MCP-Bridge"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("result", {}).get("tools", [])
        except Exception:
            return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout_s: float = 5.0) -> Dict[str, Any]:
        """Invoke a tool in Unreal MCP registry, strictly enforcing read-only boundary."""
        err = _validate_read_only(tool_name)
        if err:
            raise PermissionError(err)
        return self.call_read_only_tool(tool_name, arguments, timeout_s)

    def call_read_only_tool(self, tool_name: str, arguments: Dict[str, Any], timeout_s: float = 5.0) -> Dict[str, Any]:
        """Invoke a tool in the Unreal MCP registry if it is read-only."""
        err = _validate_read_only(tool_name)
        if err:
            return {"error": err}

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
            "id": 2,
        }
        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "GameForge-MCP-Bridge"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e)}


def verify_port_coexistence(editor_port: int = 47815, mcp_port: int = 8000) -> Dict[str, Any]:
    """Verify that Live Editor loopback port and Unreal MCP port do not collide."""
    collides = (editor_port == mcp_port)
    return {
        "editor_port": editor_port,
        "mcp_port": mcp_port,
        "coexistence_valid": not collides,
        "status": "PASS" if not collides else "FAIL",
    }
