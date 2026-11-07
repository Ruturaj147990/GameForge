"""Unit Tests for Chat Message Selection, Copy, Bounded Rendering, and Approval Cards.

Covers:
1. ApprovalCard for Command Execution Requests:
   - Single command & command batch displays
   - Shell, working directory, reason, and monospace command code block
   - Risk category badge rendering and styling
   - [Approve], [Approve Batch], and [Reject] action button signals
2. _MessageBubble Interaction & Clipboard:
   - Selection flags: Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
   - Copy button interaction with QApplication.clipboard()
   - Markdown and monospace code block rendering
3. ChatPanel Bounded Rendering & Lifecycle:
   - Cap enforcement at MAX_CHAT_BUBBLES
   - Oldest bubble removal and deleteLater() scheduling without leaks
4. ToolActivityItem & Genuine Operations:
   - Live activity formatting for read, edit, pytest, shell commands, unreal automation
   - Toggle details expand/collapse mechanics
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTextBrowser

from src.gameforge_ide.desktop.panels.activity_card import (
    ToolActivityItem,
    format_tool_activity,
)
from src.gameforge_ide.desktop.panels.approval_card import ApprovalCard
from src.gameforge_ide.desktop.panels.chat_panel import (
    ChatPanel,
    MAX_CHAT_BUBBLES,
    _MessageBubble,
)
from src.gameforge_ide.desktop.styles import tokens


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ==============================================================================
# 1. ApprovalCard Tests for Command Approvals & Risk Badges
# ==============================================================================

def test_approval_card_single_command_request(qapp: QApplication):
    """Verify ApprovalCard formats and displays a single command approval request."""
    approval_data = {
        "approval_id": "app_cmd_001",
        "tool": "run_command",
        "command": "pytest tests/unit/ -k test_permissions",
        "shell": "powershell",
        "working_directory": "E:/gameforge_step1",
        "reason": "Verify permissions mode unit tests before commit",
        "risk_category": "development_test",
    }

    card = ApprovalCard(approval_data)
    try:
        assert card.objectName() == "approvalCard"
        assert card.is_command_request is True
        assert card.command_payload == "pytest tests/unit/ -k test_permissions"

        # Check risk badge
        risk_badge = card.findChild(QLabel, "approvalRiskBadge")
        assert risk_badge is not None
        assert "DEVELOPMENT TEST" in risk_badge.text()

        # Check shell, cwd, and reason
        text_labels = [lbl.text() for lbl in card.findChildren(QLabel)]
        combined_text = " ".join(text_labels)
        assert "powershell" in combined_text
        assert "E:/gameforge_step1" in combined_text
        assert "Verify permissions mode unit tests before commit" in combined_text
        assert "pytest tests/unit/ -k test_permissions" in combined_text

        # Check action buttons
        btn_approve = card.findChild(QPushButton, "approvalApprove")
        btn_reject = card.findChild(QPushButton, "approvalReject")
        assert btn_approve is not None
        assert btn_reject is not None
        assert btn_approve.text() == "Approve"
        assert btn_reject.text() == "Reject"

        # Check approve signal
        approved_ids: List[str] = []
        card.approve_clicked.connect(approved_ids.append)
        btn_approve.click()
        assert approved_ids == ["app_cmd_001"]
    finally:
        card.deleteLater()

    # Check reject signal on separate card (since approve/reject are mutually exclusive)
    card_reject = ApprovalCard(approval_data)
    try:
        btn_reject = card_reject.findChild(QPushButton, "approvalReject")
        assert btn_reject is not None
        rejected_ids: List[str] = []
        card_reject.reject_clicked.connect(rejected_ids.append)
        btn_reject.click()
        assert rejected_ids == ["app_cmd_001"]
    finally:
        card_reject.deleteLater()


def test_approval_card_command_batch_request(qapp: QApplication):
    """Verify ApprovalCard displays command batch with 'Approve Batch' button."""
    batch_cmds = [
        "git status --porcelain",
        "git diff --stat",
        "pytest graders/protected/ -q",
    ]
    approval_data = {
        "approval_id": "app_batch_002",
        "tool": "terminal_run",
        "commands": batch_cmds,
        "shell": "powershell",
        "working_directory": "E:/gameforge_step1",
        "reason": "Pre-flight workspace check",
        "risk_category": "workspace_edit",
    }

    card = ApprovalCard(approval_data)
    try:
        assert card.is_command_request is True
        # Title should indicate batch
        text_labels = [lbl.text() for lbl in card.findChildren(QLabel)]
        combined_text = " ".join(text_labels)
        assert "batch" in combined_text.lower()
        for cmd in batch_cmds:
            assert cmd in combined_text

        # Button should say 'Approve Batch'
        btn_approve = card.findChild(QPushButton, "approvalApprove")
        assert btn_approve is not None
        assert btn_approve.text() == "Approve Batch"

        # Risk badge
        risk_badge = card.findChild(QLabel, "approvalRiskBadge")
        assert risk_badge is not None
        assert "WORKSPACE EDIT" in risk_badge.text()
    finally:
        card.deleteLater()


def test_approval_card_destructive_risk_badge(qapp: QApplication):
    """Verify destructive risk categories display high-contrast warning badges."""
    approval_data = {
        "approval_id": "app_danger_003",
        "tool": "run_command",
        "command": "rm -rf scratch/old_builds",
        "shell": "powershell",
        "working_directory": "E:/gameforge_step1",
        "reason": "Purge temporary build cache",
        "risk_category": "destructive_delete",
    }

    card = ApprovalCard(approval_data)
    try:
        risk_badge = card.findChild(QLabel, "approvalRiskBadge")
        assert risk_badge is not None
        assert "DESTRUCTIVE DELETE" in risk_badge.text()
        assert tokens.ACCENT_ERROR in risk_badge.text()
    finally:
        card.deleteLater()


# ==============================================================================
# 2. _MessageBubble Selection, Formatting, and Clipboard Tests
# ==============================================================================

def test_message_bubble_selection_flags_and_formatting(qapp: QApplication):
    """Verify _MessageBubble allows keyboard/mouse text selection and rich markdown."""
    raw_markdown = "Here is the plan:\n\n1. Run tests\n2. Update context.md\n\n```python\nprint('GameForge IDE')\n```"
    bubble = _MessageBubble(role="assistant", text=raw_markdown)
    try:
        assert bubble.role == "assistant"
        assert bubble._raw_text == raw_markdown

        content = bubble.findChild(QTextBrowser)
        assert content is not None

        # Verify text interaction flags
        flags = content.textInteractionFlags()
        assert bool(flags & Qt.TextSelectableByMouse) is True
        assert bool(flags & Qt.TextSelectableByKeyboard) is True
        assert bool(flags & Qt.LinksAccessibleByMouse) is True
        assert content.contextMenuPolicy() == Qt.DefaultContextMenu

        # Verify content was rendered
        html_text = content.toHtml()
        assert "GameForge IDE" in html_text
        assert "Run tests" in html_text
    finally:
        bubble.deleteLater()


def test_message_bubble_clipboard_copy(qapp: QApplication):
    """Verify copy button copies exact message content to system clipboard."""
    msg_text = "def calculate_score(points: int) -> int:\n    return points * 10\n"
    bubble = _MessageBubble(role="assistant", text=msg_text)
    try:
        btn_copy = bubble.findChild(QPushButton, "btn_copy_bubble")
        assert btn_copy is not None

        # Clear clipboard first
        QApplication.clipboard().clear()
        assert QApplication.clipboard().text() == ""

        # Trigger copy
        btn_copy.click()

        # Check clipboard content
        assert QApplication.clipboard().text() == msg_text
        assert btn_copy.text() == "Copied! ✓"
    finally:
        bubble.deleteLater()


# ==============================================================================
# 3. ChatPanel Bounded Rendering & Widget Lifecycle Tests
# ==============================================================================

def test_chat_panel_bounded_rendering_and_trimming(qapp: QApplication, temp_workspace: Path):
    """Verify ChatPanel caps bubbles at MAX_CHAT_BUBBLES without memory/widget leaks."""
    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        # Add 205 bubbles (exceeding MAX_CHAT_BUBBLES = 200)
        total_to_add = MAX_CHAT_BUBBLES + 5
        for i in range(total_to_add):
            chat._add_bubble("user" if i % 2 == 0 else "assistant", f"Message payload sequence index {i}")

        # Count active _MessageBubble widgets in layout
        active_bubbles = []
        for idx in range(chat._msg_layout.count()):
            w = chat._msg_layout.itemAt(idx).widget()
            if isinstance(w, _MessageBubble):
                active_bubbles.append(w)

        # Bubble count must never exceed MAX_CHAT_BUBBLES
        assert len(active_bubbles) == MAX_CHAT_BUBBLES

        # The oldest bubbles (0 to 4) should have been pruned; youngest must remain
        first_bubble_text = active_bubbles[0]._raw_text
        last_bubble_text = active_bubbles[-1]._raw_text

        assert "index 5" in first_bubble_text
        assert f"index {total_to_add - 1}" in last_bubble_text
    finally:
        chat.deleteLater()


# ==============================================================================
# 4. ToolActivityItem & Format Activity Tests
# ==============================================================================

def test_format_tool_activity_genuine_operations():
    """Verify genuine tool operations format with exact icons and badges."""
    # 1. File reading
    icon, action, target, badge = format_tool_activity(
        "read_file",
        {"file_path": "src/gameforge_ide/desktop/tokens.py"},
        {"lines": 142},
        is_running=False,
    )
    assert icon == "📖"
    assert action == "Read"
    assert "tokens.py" in target
    assert badge == "142 lines"

    # 2. PyTest command execution
    icon, action, target, badge = format_tool_activity(
        "run_command",
        {"command": "pytest tests/unit/ -q"},
        {"exit_code": 0},
        is_running=False,
    )
    assert icon == "⚡"
    assert action == "Ran"
    assert "pytest" in target
    assert badge == "exit 0"

    # 3. Failed command execution
    icon, action, target, badge = format_tool_activity(
        "run_command",
        {"command": "pytest tests/failing_test.py"},
        {"exit_code": 1},
        is_running=False,
    )
    assert icon == "⚡"
    assert action == "Ran"
    assert badge == "exit 1"

    # 4. Standard command execution
    icon, action, target, badge = format_tool_activity(
        "run_command",
        {"command": "git status --porcelain"},
        {"exit_code": 0},
        is_running=False,
    )
    assert icon == "⚡"
    assert action == "Ran"
    assert badge == "exit 0"

    # 5. Propose edit with diff lines
    diff_patch = "--- a.py\n+++ a.py\n@@ -1,2 +1,3 @@\n+line1\n+line2\n-oldline\n"
    icon, action, target, badge = format_tool_activity(
        "propose_edit",
        {"file_path": "Source/Player.cpp"},
        {"diff_patch": diff_patch},
        is_running=False,
    )
    assert icon == "✏️"
    assert action == "Edited"
    assert "Player.cpp" in target
    assert badge == "+2 / -1 lines"

    # 6. Unreal automation tests
    icon, action, target, badge = format_tool_activity(
        "unreal_run_tests",
        {},
        {"status": "OK"},
        is_running=False,
    )
    assert icon == "🧪"
    assert "Unreal automation tests" in target
    assert badge == "passed"


def test_tool_activity_item_widget_and_toggle(qapp: QApplication):
    """Verify ToolActivityItem expands and collapses details on button toggle."""
    item = ToolActivityItem(
        tool_name="run_command",
        args={"command": "pytest tests/unit/desktop/ -q"},
        result={"exit_code": 0, "output": "7 passed in 0.44s"},
    )
    try:
        assert item.objectName() == "toolActivityItem"
        assert item._btn_toggle is not None
        assert item._details_frame is not None
        assert item._details_frame.isHidden() is True
        assert item._details_expanded is False

        # Click toggle button to expand details
        item._btn_toggle.click()
        assert item._details_expanded is True
        assert item._details_frame.isHidden() is False
        assert item._btn_toggle.text() == "▾ Details"

        # Click again to collapse
        item._btn_toggle.click()
        assert item._details_expanded is False
        assert item._details_frame.isHidden() is True
        assert item._btn_toggle.text() == "▸ Details"
    finally:
        item.deleteLater()
