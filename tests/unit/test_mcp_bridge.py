"""Unit tests for Unreal MCP bridge client (WI-10.6)."""
from pathlib import Path
import pytest

from src.gameforge_ide.unreal.mcp_bridge import UnrealMcpClient, verify_port_coexistence


def test_port_coexistence():
    res = verify_port_coexistence(editor_port=47815, mcp_port=8000)
    assert res["coexistence_valid"] is True
    assert res["status"] == "PASS"

    res_collision = verify_port_coexistence(editor_port=8000, mcp_port=8000)
    assert res_collision["coexistence_valid"] is False
    assert res_collision["status"] == "FAIL"


def test_read_only_tool_rejection():
    client = UnrealMcpClient()
    # Mutating tool call must be rejected immediately without network call
    res = client.call_read_only_tool("delete_actor", {"actor_id": "guard_1"})
    assert "error" in res
    assert "strictly read-only" in res["error"]
