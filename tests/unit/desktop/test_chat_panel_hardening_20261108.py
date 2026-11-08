"""Tests for ChatPanel visual presentation, tool suppression, and manifest verification."""

import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_is_raw_tool_json_screenshot_flat_dialect(qapp):
    """Verify that ChatPanel._is_raw_tool_json detects and suppresses the flat screenshot command."""
    flat_json = (
        '{\n'
        '  "command": "read_file",\n'
        '  "path": "E:\\\\GameForge\\\\projects\\\\CounterStrike\\\\Source\\\\CounterStrike\\\\GFGameImpl.cpp"\n'
        '}'
    )
    assert ChatPanel._is_raw_tool_json(flat_json) is True


def test_is_raw_tool_json_normal_prose_is_preserved(qapp):
    """Verify that regular user and assistant prose is not flagged as raw tool json."""
    prose = "I have read the implementation file and fixed the color constants."
    assert ChatPanel._is_raw_tool_json(prose) is False


def test_message_bubble_visual_hierarchy(qapp):
    """Verify that assistant messages are borderless and user messages have soft bubble styling."""
    assistant_bubble = _MessageBubble("assistant", "Assistant response text.")
    assert assistant_bubble.property("bubbleRole") == "assistant"
    # Assistant CSS has border: none
    assert "border: none" in assistant_bubble.styleSheet()

    user_bubble = _MessageBubble("user", "User query text.")
    assert user_bubble.property("bubbleRole") == "user"
    # User CSS has border-radius and background
    assert "border-radius" in user_bubble.styleSheet()


def test_btn_copy_bubble_accessible_and_present(qapp):
    """Verify that btn_copy_bubble exists with accessibility name and tooltip."""
    bubble = _MessageBubble("assistant", "Hello copy test.")
    btn_copy = bubble.findChild(type(bubble._btn_copy), "btn_copy_bubble")
    assert btn_copy is not None
    assert btn_copy.accessibleName() == "Copy message content"
    assert "Copy message text" in btn_copy.toolTip()
