"""Regression tests for approval flow and game clone requests."""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.pipeline.spec_from_prompt import is_game_creation_request
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.providers.base import ModelProvider, ProviderCapabilities, StreamChunk
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel
from src.gameforge_ide.desktop.panels.approval_card import ApprovalCard
from src.gameforge_ide.desktop.services.agent_service import AgentService


class MockApprovalToolProvider(ModelProvider):
    """Mock provider that calls unreal_editor mutating op."""
    def __init__(self):
        pass

    def get_provider_id(self) -> str:
        return "mock_tool"

    def is_available(self) -> bool:
        return True

    def list_models(self):
        from src.gameforge_ide.backend.providers.base import ModelInfo
        return [ModelInfo(id="test_model", name="Test Model", provider="mock_tool")]

    def get_capabilities(self, model_name: str) -> ProviderCapabilities:
        return ProviderCapabilities(max_context=8192, supports_tools=True)

    async def complete(self, *args, **kwargs):
        from src.gameforge_ide.backend.providers.base import ChatResponse
        return ChatResponse(content="", model="test_model")

    async def stream_chat(self, *args, **kwargs):
        call_json = '{"tool": "unreal_editor", "args": {"uproject": "TeamArena.uproject", "op": "new_level", "args": {"name": "DM_CTF"}}}'
        yield StreamChunk(token=f"```json\n{call_json}\n```")


@pytest.fixture(scope="session")
def qapp():
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_clone_prompts_recognized_as_game_creation():
    """Verify clone and fps prompts are recognized as game creation requests."""
    assert is_game_creation_request("make a counter strike clone.")
    assert is_game_creation_request("Counter-Strike clone: FPS shooter with two teams")
    assert is_game_creation_request("create a doom clone with 3 levels")
    assert is_game_creation_request("build a tactical fps shooter")


def test_unreal_editor_creates_approval_card(tmp_path):
    """Verify AgentRuntime yields approval dict in WAITING_APPROVAL for unreal_editor op."""
    sm = SessionManager(tmp_path)
    router = ModelRouter()
    provider = MockApprovalToolProvider()
    router.register_provider("mock_tool", provider)

    rt = AgentRuntime(tmp_path, sm, router, studio_mode=False)
    sid = sm.create_session("t", "test_model", "mock_tool").session_id

    async def collect():
        return [e async for e in rt.execute_task_stream(sid, "Add level DM_CTF using unreal_editor")]

    events = asyncio.run(collect())
    wait_events = [e for e in events if e.event_type == "status" and e.content == "WAITING_APPROVAL"]
    assert len(wait_events) >= 1, "Expected WAITING_APPROVAL status event"
    approval = wait_events[0].metadata.get("approval")
    assert approval is not None, "Expected approval dict in metadata"
    assert approval["tool"] == "unreal_editor"
    assert approval["status"] == "PENDING"
    assert "apr_" in approval["approval_id"]


def test_chat_panel_renders_approval_card(qapp, tmp_path):
    """Verify ChatPanel renders ApprovalCard with approve and reject buttons."""
    agent = AgentService(tmp_path)
    panel = ChatPanel(agent, workspace_root=tmp_path)
    try:
        approval_rec = {
            "approval_id": "apr_test123",
            "tool": "unreal_editor",
            "args": {"op": "new_level", "uproject": "TeamArena.uproject"},
            "summary": "Run unreal_editor: new_level on TeamArena.uproject",
            "consequence": "Creates new level in Unreal Editor",
            "status": "PENDING",
        }
        panel._on_status("WAITING_APPROVAL", {"tool": "unreal_editor", "approval": approval_rec})

        cards = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), ApprovalCard)
        ]
        assert len(cards) == 1, f"Expected 1 ApprovalCard, got {len(cards)}"
        assert cards[0].approval_id == "apr_test123"
    finally:
        agent.shutdown()
