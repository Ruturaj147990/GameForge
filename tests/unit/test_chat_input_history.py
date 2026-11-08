"""Chat input: Up/Down recall previous prompts; Esc stops a running task; render throttle flushes."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble
from src.gameforge_ide.desktop.services.agent_service import AgentService


def _key(panel, key):
    ev = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    return panel.eventFilter(panel._input, ev)


def test_prompt_history_up_down(tmp_path):
    QApplication.instance() or QApplication([])
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        panel._remember_prompt("first")
        panel._remember_prompt("second")
        assert _key(panel, Qt.Key_Up) and panel._input.toPlainText() == "second"
        assert _key(panel, Qt.Key_Up) and panel._input.toPlainText() == "first"
        assert _key(panel, Qt.Key_Down) and panel._input.toPlainText() == "second"
        assert _key(panel, Qt.Key_Down) and panel._input.toPlainText() == ""
        panel._input.setPlainText("my own draft")
        assert _key(panel, Qt.Key_Up) is False  # editing: arrows move the cursor
    finally:
        agent.shutdown()
        panel.deleteLater()


def test_bubble_throttled_render_flushes_on_finalise():
    QApplication.instance() or QApplication([])
    b = _MessageBubble("assistant", "")
    for i in range(200):
        b.append_token(f"tok{i} ")
    b.finalise()
    assert "tok199" in b._content.toPlainText()
    assert b._raw_text.endswith("tok199 ")


def test_markdown_only_safe_links_are_clickable():
    QApplication.instance() or QApplication([])
    b = _MessageBubble("assistant", "")
    out = b._markdown_to_html("[ok](https://example.com) and [bad](javascript:alert(1)) *it*")
    assert 'href="https://example.com"' in out
    assert "javascript:" not in out.split("href=")[-1] or 'href="javascript' not in out
    assert "<i>it</i>" in out
