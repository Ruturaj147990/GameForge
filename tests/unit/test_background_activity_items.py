"""Unit tests for Antigravity-style background activity pills and tool execution chips."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QFrame

from src.gameforge_ide.desktop.panels.activity_card import (
    StatusActivityItem,
    ToolActivityItem,
    format_target_path,
    format_tool_activity,
)
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble
from src.gameforge_ide.desktop.services.agent_service import AgentService


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_format_target_path_various_depths():
    """Verify format_target_path returns clean readable relative paths."""
    assert format_target_path("xyz.py") == "xyz.py"
    assert format_target_path("Source/Player.cpp") == "Source/Player.cpp"
    assert format_target_path("./src/backend/runtime.py") == "src/backend/runtime.py"
    assert format_target_path("deep/nested/path/to/file.cpp", max_parts=3) == "deep/.../file.cpp"
    assert format_target_path("E:/gameforge_step1/src/gameforge_ide/desktop/panels/chat_panel.py") == ".../panels/chat_panel.py"
    assert format_target_path("") == ""


def test_format_tool_activity_all_standard_tools():
    """Verify format_tool_activity formats all standard tools with icons and clean actions."""
    # 1. read_file
    icon, act, tgt, bdg = format_tool_activity("read_file", {"subpath": "xyz.py"}, is_running=True)
    assert icon == "📖"
    assert act == "Reading"
    assert tgt == "xyz.py"

    icon, act, tgt, bdg = format_tool_activity("read_file", {"subpath": "xyz.py"}, result={"status": "SUCCESS", "lines": 42})
    assert act == "Read"
    assert bdg == "42 lines"

    # 2. write_file
    icon, act, tgt, bdg = format_tool_activity("write_file", {"subpath": "Source/Player.cpp", "content": "line1\nline2"}, result={"status": "SUCCESS"})
    assert icon == "📝"
    assert act == "Wrote"
    assert bdg == "2 lines"

    # 3. propose_edit
    diff_patch = "--- a/f\n+++ b/f\n@@ -1 +1,2 @@\n-old\n+new1\n+new2"
    icon, act, tgt, bdg = format_tool_activity("propose_edit", {"subpath": "Player.h"}, result={"status": "SUCCESS", "diff_patch": diff_patch})
    assert icon == "✏️"
    assert act == "Edited"
    assert "+2 / -1 lines" in bdg

    # 4. search_code
    icon, act, tgt, bdg = format_tool_activity("search_code", {"query": "JumpZVelocity"}, result={"status": "SUCCESS", "matches": [1, 2, 3]})
    assert icon == "🔍"
    assert act == "Searched code for"
    assert '"JumpZVelocity"' in tgt
    assert bdg == "3 matches"

    # 5. search_index
    icon, act, tgt, bdg = format_tool_activity("search_index", {"query": "AInventory"}, result={"status": "SUCCESS", "results": [1]})
    assert icon == "🔎"
    assert act == "Searched symbols for"
    assert bdg == "1 symbol"

    # 6. list_dir
    icon, act, tgt, bdg = format_tool_activity("list_dir", {"subpath": "Source"}, result={"status": "SUCCESS", "entries": ["a", "b"]})
    assert icon == "📁"
    assert act == "Listed"
    assert bdg == "2 items"

    # 7. run_command
    icon, act, tgt, bdg = format_tool_activity("run_command", {"command": "pytest tests/unit"}, result={"status": "SUCCESS", "exit_code": 0})
    assert icon == "⚡"
    assert act == "Ran"
    assert "pytest" in tgt
    assert bdg == "exit 0"

    # 8. unreal_run_tests
    icon, act, tgt, bdg = format_tool_activity("unreal_run_tests", {}, result={"status": "SUCCESS"})
    assert icon == "🧪"
    assert act == "Ran"
    assert bdg == "passed"

    # 9. error status
    icon, act, tgt, bdg = format_tool_activity("read_file", {"subpath": "missing.py"}, result={"status": "ERROR", "error": "File not found"})
    assert act == "Read failed"
    assert bdg == "failed"


def test_tool_activity_item_lifecycle_and_details_toggle(qapp):
    """Verify ToolActivityItem initializes in running state and updates in-place on result."""
    item = ToolActivityItem("read_file", {"subpath": "Source/Player.cpp"})
    try:
        assert item.role == "tool"
        assert item.is_running is True
        assert "Source/Player.cpp" in item._raw_text
        assert item._pulse_timer.isActive()
        assert item._details_expanded is False
        assert item._details_frame.isHidden()

        # Toggle details
        item.toggle_details()
        assert item._details_expanded is True
        assert not item._details_frame.isHidden()
        assert item._btn_toggle.text() == "▾ Details"

        item.toggle_details()
        assert item._details_expanded is False
        assert item._details_frame.isHidden()
        assert item._btn_toggle.text() == "▸ Details"

        # Update result in-place
        item.set_result({"status": "SUCCESS", "content": "line1\nline2\nline3", "lines": 3})
        assert item.is_running is False
        assert not item._pulse_timer.isActive()
        assert "3 lines" in item._raw_text
    finally:
        item.deleteLater()


def test_status_activity_item_thinking_planning_repairing(qapp):
    """Verify StatusActivityItem cleanly renders thinking, planning, and self-repairing phases."""
    # 1. Thinking
    s_think = StatusActivityItem("thinking", {"iteration": 2})
    try:
        assert s_think.role == "status"
        assert s_think.is_running is True
        assert "Thinking (step 2)..." in s_think._raw_text
        assert s_think._pulse_timer.isActive()

        s_think.finalise()
        assert s_think.is_running is False
        assert not s_think._pulse_timer.isActive()
        assert "Thought for" in s_think._raw_text
    finally:
        s_think.deleteLater()

    # 2. Planning
    s_plan = StatusActivityItem("planning", {})
    try:
        assert "Planning implementation steps..." in s_plan._raw_text
        s_plan.finalise()
        assert "Plan formulated" in s_plan._raw_text
    finally:
        s_plan.deleteLater()

    # 3. Repairing
    s_repair = StatusActivityItem("repairing", {"attempt": 1})
    try:
        assert "Self-correcting build/test errors (attempt 1)..." in s_repair._raw_text
        s_repair.finalise()
        assert "Error diagnosis complete" in s_repair._raw_text
    finally:
        s_repair.deleteLater()


def test_chat_panel_in_place_tool_activity_and_no_raw_json_dump(qapp, tmp_path):
    """Verify ChatPanel updates ToolActivityItem in-place instead of creating duplicate raw JSON dumps."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        # Start thinking
        panel._on_status("THINKING", {"iteration": 1})
        status_items = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), StatusActivityItem)
        ]
        assert len(status_items) == 1
        assert status_items[0].is_running is True

        # Dispatch read_file tool call
        panel._on_tool_called("read_file", {"subpath": "Source/Player.cpp"})

        # Thinking item is finalized
        assert status_items[0].is_running is False

        # Exactly 1 ToolActivityItem exists in running state
        tool_items = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), ToolActivityItem)
        ]
        assert len(tool_items) == 1
        assert tool_items[0].tool_name == "read_file"
        assert tool_items[0].is_running is True
        assert "Source/Player.cpp" in tool_items[0]._raw_text

        # Tool result completes
        panel._on_tool_result("read_file", {"status": "SUCCESS", "lines": 48})

        # Still exactly 1 ToolActivityItem (updated in-place!), NOT 2 separate bubbles!
        tool_items = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), ToolActivityItem)
        ]
        assert len(tool_items) == 1
        assert tool_items[0].is_running is False
        assert "48 lines" in tool_items[0]._raw_text

        # Stream assistant response
        panel._on_token("I have read Player.cpp.")
        panel._on_done("I have read Player.cpp.")

        # Assistant bubble exists with clean text
        assistant_bubbles = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), _MessageBubble)
            and panel._msg_layout.itemAt(i).widget().role == "assistant"
        ]
        assert len(assistant_bubbles) == 1
        assert "I have read Player.cpp." in assistant_bubbles[0]._raw_text
    finally:
        agent.shutdown()
        panel.deleteLater()
