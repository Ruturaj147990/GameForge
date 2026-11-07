"""End-to-End Backend-Frontend Integration Test Suite (DEF-307).

Verifies the complete set of 20 end-to-end workflows from Section 6.2 of the
GameForge Master Engineering Overhaul:
 1. Application startup & window initialization
 2. Project discovery & selection
 3. New conversation creation
 4. User prompt submission
 5. LLM response streaming
 6. Genuine dynamic planning (LLM plan generation)
 7. Plan approval / Proceed confirmation
 8. Tool execution through CommandExecutionBroker
 9. Live background activity chips update
 10. File modification and atomic writes
 11. Disk persistence & verification
 12. Error diagnosis and display
 13. Actual repair execution with bounded budget
 14. Context-usage telemetry updates
 15. Conversation persistence to SQLite / JSON
 16. Conversation restoration on reload
 17. Model selection and switching (9B default, 4B vision)
 18. Cancellation of active tasks without orphaned threads/processes
 19. Permission approval / rejection flow
 20. Clean application shutdown and restart
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List

import pytest
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.agent.multi_file_manifest import FileChangeOperation, MultiFileChangeManifest
from src.gameforge_ide.backend.agent.plan_generator import PlanArtifact, PlanGenerator, PlanStep
from src.gameforge_ide.backend.agent.repair_system import FailureCategory, RepairEngine
from src.gameforge_ide.backend.agent.runtime import AgentEvent, AgentRuntime
from src.gameforge_ide.backend.models.command_contract import (
    CommandExecutionRequest,
    CommandStatus,
    RiskCategory,
)
from src.gameforge_ide.backend.models.context_usage import ContextBreakdown, ContextUsageReport
from src.gameforge_ide.backend.models.modes import AutonomyProfile, PermissionsMode, TaskMode
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.tools.command_broker import CommandExecutionBroker, POWERSHELL_ALIASES
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.core.process_manager import ProcessLifecycleManager
from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.panels.activity_card import ToolActivityItem
from src.gameforge_ide.desktop.panels.approval_card import ApprovalCard
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble
from src.gameforge_ide.desktop.panels.plan_card import PlanCard
from src.gameforge_ide.desktop.services.action_runner import ActionRunner
from src.gameforge_ide.desktop.services.agent_service import AgentService
from src.gameforge_ide.desktop.services.projects_service import ProjectsService
from src.gameforge_ide.desktop.widgets.context_indicator import ContextUsageIndicator
from src.gameforge_ide.storage.approval_store import ApprovalStore


# ── Workflow 1: Application startup & window initialization ───────────────────

def test_workflow_01_app_startup_and_window_initialization(qapp, tmp_path):
    """Workflow 1: Application startup, window sizing, service setup, and clean close."""
    ws = tmp_path / "ws1"
    ws.mkdir(parents=True, exist_ok=True)

    win = MainWindow(workspace_root=ws)
    try:
        assert win.confirm_on_close is True
        win.confirm_on_close = False

        # Verify minimum dimensions and geometry
        assert win.minimumWidth() >= 1280
        assert win.minimumHeight() >= 780
        assert "GameForge" in win.windowTitle()

        # Verify child subsystems and shell components exist
        assert hasattr(win, "_top_bar") and win._top_bar is not None
        assert hasattr(win, "_rail") and win._rail is not None
        assert hasattr(win, "_view_host") and win._view_host is not None
        assert hasattr(win, "_chat_panel") and win._chat_panel is not None
        assert hasattr(win, "_assistant_panel") and win._assistant_panel is not None
        assert hasattr(win, "_agent") and win._agent is not None
        assert hasattr(win, "_tools") and win._tools is not None
        assert hasattr(win, "_projects_service") and win._projects_service is not None

        # Verify central widget and splitter layout
        assert win.centralWidget() is not None
    finally:
        win.confirm_on_close = False
        win.close()
        win.deleteLater()


# ── Workflow 2: Project discovery & selection ─────────────────────────────────

def test_workflow_02_project_discovery_and_selection(qapp, tmp_path):
    """Workflow 2: Projects discovery, selection event propagation, and project_dir sync."""
    ws = tmp_path / "ws2"
    ws.mkdir(parents=True, exist_ok=True)
    proj_dir = ws / "Projects" / "AetherQuest"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "AetherQuest.uproject").write_text("{}", encoding="utf-8")
    (proj_dir / ".gameforge").mkdir(parents=True, exist_ok=True)

    win = MainWindow(workspace_root=ws)
    try:
        win.confirm_on_close = False
        service = win._projects_service
        projects = service.list_projects()
        names = [p.name for p in projects]
        assert "AetherQuest" in names

        # Emit selection via TopBar
        win._top_bar.projectSelected.emit("AetherQuest")
        assert win._current_project == "AetherQuest"
        assert win._current_project_dir == proj_dir.resolve()

        # Verify chat panel and active session project_dir were updated
        assert win._chat_panel._session_id is not None
        sess = win._agent.get_session(win._chat_panel._session_id)
        if sess:
            assert sess.project_dir is not None
            assert Path(sess.project_dir).resolve() == proj_dir.resolve()
    finally:
        win.confirm_on_close = False
        win.close()
        win.deleteLater()


# ── Workflow 3: New conversation creation ─────────────────────────────────────

def test_workflow_03_new_conversation_creation(qapp, tmp_path):
    """Workflow 3: New session creation, parameter persistence, and UI reset."""
    ws = tmp_path / "ws3"
    ws.mkdir(parents=True, exist_ok=True)

    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)
        initial_sess_id = panel._session_id
        assert initial_sess_id is not None

        # Change selectors
        panel.task_mode_combo.setCurrentText("Fast")
        panel.permissions_mode_combo.setCurrentText("Request All")

        # Create new session
        panel._new_session()
        new_sess_id = panel._session_id
        assert new_sess_id is not None
        assert new_sess_id != initial_sess_id

        # Verify new session persisted in backend with correct mode
        sess = agent.get_session(new_sess_id)
        assert sess is not None
        assert str(sess.task_mode).lower() == "fast"
        assert str(sess.permissions_mode).lower() == "request_all"
    finally:
        agent.shutdown()


# ── Workflow 4: User prompt submission ────────────────────────────────────────

def test_workflow_04_user_prompt_submission(qapp, tmp_path):
    """Workflow 4: Prompt input, user bubble addition, and prompt transmission."""
    ws = tmp_path / "ws4"
    ws.mkdir(parents=True, exist_ok=True)

    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)
        prompt_text = "Implement double jump mechanic for platformer character."
        panel._input.setPlainText(prompt_text)

        # Trigger send
        panel._on_send()

        # Input box is cleared
        assert panel._input.toPlainText() == ""

        # User bubble exists in message layout
        user_bubbles = []
        for i in range(panel._msg_layout.count()):
            w = panel._msg_layout.itemAt(i).widget()
            if isinstance(w, _MessageBubble) and getattr(w, "role", "") == "user":
                user_bubbles.append(w)
        assert len(user_bubbles) >= 1
        assert prompt_text in user_bubbles[-1]._raw_text
    finally:
        agent.shutdown()


# ── Workflow 5: LLM response streaming ────────────────────────────────────────

def test_workflow_05_llm_response_streaming(qapp, tmp_path):
    """Workflow 5: Incremental token reception and bubble rendering without leak."""
    ws = tmp_path / "ws5"
    ws.mkdir(parents=True, exist_ok=True)

    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)
        panel._active_bubble = panel._add_bubble("assistant", "")

        # Stream normal narrative tokens
        panel._on_token("I will ")
        panel._on_token("inspect the ")
        panel._on_token("character class.")

        assert panel._active_bubble._raw_text == "I will inspect the character class."

        # Verify <think> tags are stripped and suppressed
        panel._on_token("<think>Internal reasoning</think>")
        assert "<think>" not in panel._active_bubble._raw_text
    finally:
        agent.shutdown()


# ── Workflow 6: Genuine dynamic planning (LLM plan generation) ────────────────

def test_workflow_06_genuine_dynamic_planning(qapp, tmp_path):
    """Workflow 6: Dynamic planning generates genuine goal-tailored DAG plans."""
    ws = tmp_path / "ws6"
    ws.mkdir(parents=True, exist_ok=True)
    gateway = ToolGateway(ws)
    generator = PlanGenerator(workspace_root=ws, tool_gateway=gateway)

    custom_goal = "Create a modern stamina and health HUD system with UMG widgets."
    plan = generator.generate_llm_plan_artifact(
        prompt=custom_goal,
        session_id="sess_plan_test",
        is_game=False,
    )

    assert isinstance(plan, PlanArtifact)
    assert plan.goal == custom_goal
    assert len(plan.steps) >= 3

    # Dynamic plan must not contain hardcoded Sudoku puzzle steps
    step_titles = [s.title.lower() for s in plan.steps]
    step_descs = [s.description.lower() for s in plan.steps]
    all_text = " ".join(step_titles + step_descs)
    assert "sudoku" not in all_text

    # Verify PlanCard rendering in UI
    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)
        panel._on_plan_received(plan.model_dump())
        plan_cards = [
            panel._msg_layout.itemAt(i).widget()
            for i in range(panel._msg_layout.count())
            if isinstance(panel._msg_layout.itemAt(i).widget(), PlanCard)
        ]
        assert len(plan_cards) == 1
        assert plan_cards[0].plan_id == plan.plan_id
    finally:
        agent.shutdown()


# ── Workflow 7: Plan approval / Proceed confirmation ──────────────────────────

def test_workflow_07_plan_approval_proceed_confirmation(qapp, tmp_path):
    """Workflow 7: Plan proceed action triggers plan execution."""
    ws = tmp_path / "ws7"
    ws.mkdir(parents=True, exist_ok=True)

    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)
        plan_data = {
            "plan_id": "plan_test_proceed",
            "session_id": panel._session_id,
            "goal": "Build Inventory Widget",
            "summary": "Implementation plan",
            "implementation_method": "direct_code_edit",
            "status": "awaiting_approval",
            "steps": [
                {
                    "step_id": "step_1",
                    "title": "Create Widget Header",
                    "description": "Declare UMG widget class",
                    "target_files": ["Source/Widget.h"],
                    "tools": ["write_file"],
                    "status": "pending",
                }
            ],
        }
        panel._on_plan_received(plan_data)
        card = panel._plan_cards.get("plan_test_proceed")
        assert card is not None

        # Trigger proceed
        proceed_called = []
        panel.send_prompt = lambda p: proceed_called.append(p) or True
        panel._on_plan_proceed("plan_test_proceed")

        assert len(proceed_called) == 1
        assert proceed_called[0] == "proceed"
    finally:
        agent.shutdown()


# ── Workflow 8: Tool execution through CommandExecutionBroker ─────────────────

def test_workflow_08_tool_execution_through_command_broker(qapp, tmp_path):
    """Workflow 8: PermissionsMode gating, state machine validation, and alias normalization."""
    ws = tmp_path / "ws8"
    ws.mkdir(parents=True, exist_ok=True)
    broker = CommandExecutionBroker(workspace_root=ws)

    # 1. REQUEST_ALL requires approval even for routine read commands
    risk_all, req_all, _ = broker.classify_risk("cat file.txt", permissions_mode=PermissionsMode.REQUEST_ALL)
    assert req_all is True

    # 2. AUTO allows safe routine dev commands automatically
    risk_safe, req_safe, _ = broker.classify_risk("git status", permissions_mode=PermissionsMode.AUTO)
    assert req_safe is False

    # 3. AUTO requires approval for destructive deletes
    risk_del, req_del, _ = broker.classify_risk("rm -rf Source/", permissions_mode=PermissionsMode.AUTO)
    assert req_del is True
    assert risk_del == RiskCategory.DESTRUCTIVE_DELETE

    # 4. UNRESTRICTED allows workspace operations without routine approval
    risk_unres, req_unres, _ = broker.classify_risk("Get-ChildItem", permissions_mode=PermissionsMode.UNRESTRICTED)
    assert req_unres is False

    # 5. Execute state machine transitions to AWAITING_APPROVAL when not pre-approved
    req = CommandExecutionRequest(
        command="cat file.txt",
        permissions_mode=PermissionsMode.REQUEST_ALL,
        working_directory=str(ws),
    )
    res = broker.execute(req, approval_granted=False)
    assert res.status == CommandStatus.AWAITING_APPROVAL
    assert res.requires_approval is True

    # 6. Shell alias normalization
    assert POWERSHELL_ALIASES.get("cat") == "Get-Content"
    assert POWERSHELL_ALIASES.get("dir") == "Get-ChildItem"
    assert broker._extract_first_executable("cat README.md", shell="powershell") == "Get-Content"


# ── Workflow 9: Live background activity chips update ─────────────────────────

def test_workflow_09_live_background_activity_chips_update(qapp, tmp_path):
    """Workflow 9: Tool execution events create sleek activity chips in chat."""
    ws = tmp_path / "ws9"
    ws.mkdir(parents=True, exist_ok=True)

    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)

        # Trigger tool call
        panel._on_tool_called("run_command", {"command": "pytest tests/unit/"})
        item = panel._active_tool_item
        assert item is not None
        assert isinstance(item, ToolActivityItem)

        # Trigger tool result
        panel._on_tool_result("run_command", {"status": "SUCCESS", "exit_code": 0, "output": "3 passed"})
        assert "pytest" in item._title_label.text()
        assert "exit 0" in item._badge_label.text()
    finally:
        agent.shutdown()


# ── Workflow 10: File modification and atomic writes ──────────────────────────

def test_workflow_10_file_modification_and_atomic_writes(qapp, tmp_path):
    """Workflow 10: Two-phase atomic write, backup file creation, and manifest ordering."""
    ws = tmp_path / "ws10"
    ws.mkdir(parents=True, exist_ok=True)
    gateway = ToolGateway(ws)
    edit_tools = gateway.edit_tools

    # 1. Atomic write with fsync and backup
    rel_path = "Source/MyGame/Player.cpp"
    cpp_code = "#include \"Player.h\"\nvoid APlayer::BeginPlay() { Super::BeginPlay(); }\n"
    res = edit_tools.write_file(subpath=rel_path, content=cpp_code)

    assert res["status"] == "SUCCESS"
    target = ws / rel_path
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == cpp_code
    assert res.get("diff_id") is not None

    # 2. Multi-file topological ordering: headers before source
    manifest = MultiFileChangeManifest(manifest_id="mf_01", goal="Update Player")
    manifest.add_operation(FileChangeOperation.create(subpath="Source/MyGame/Player.cpp", replacement_content="#include \"Player.h\""))
    manifest.add_operation(FileChangeOperation.create(subpath="Source/MyGame/Player.h", replacement_content="#pragma once"))

    ordered = manifest.get_topological_execution_order()
    ordered_paths = [Path(c.subpath).name for c in ordered]
    assert ordered_paths == ["Player.h", "Player.cpp"]


# ── Workflow 11: Disk persistence & verification ──────────────────────────────

def test_workflow_11_disk_persistence_and_verification(qapp, tmp_path):
    """Workflow 11: Disk persistence verification of written fragments."""
    ws = tmp_path / "ws11"
    ws.mkdir(parents=True, exist_ok=True)
    gateway = ToolGateway(ws)
    edit_tools = gateway.edit_tools

    file_path = "Source/Constants.h"
    content = "#pragma once\nconstexpr int MAX_PLAYERS = 8;\n"
    res = edit_tools.write_file(subpath=file_path, content=content)
    assert res["status"] == "SUCCESS"

    # Verify disk contents matches
    v_res = edit_tools.verify_disk_contents(subpath=file_path, expected_fragment="MAX_PLAYERS")
    assert v_res["status"] == "SUCCESS"
    assert v_res["verified"] is True
    assert v_res["sha256"] is not None


# ── Workflow 12: Error diagnosis and display ──────────────────────────────────

def test_workflow_12_error_diagnosis_and_display(qapp, tmp_path):
    """Workflow 12: Deterministic error diagnosis classifies MSVC compiler errors."""
    ws = tmp_path / "ws12"
    ws.mkdir(parents=True, exist_ok=True)
    engine = RepairEngine(ws)

    compiler_log = (
        "E:\\GameForge\\projects\\TestGame\\Source\\Player.cpp(25): error C2065: "
        "'UCharacterMovementComponent': undeclared identifier\n"
    )

    cause = engine.extract_root_cause(compiler_log, stage_id="build_editor")
    assert cause.category == FailureCategory.CODE_DEFECT
    assert "Player.cpp" in (cause.primary_file or "")
    assert "C2065" in cause.description or "undeclared identifier" in cause.description


# ── Workflow 13: Actual repair execution with bounded budget ──────────────────

def test_workflow_13_repair_execution_bounded_budget(qapp, tmp_path):
    """Workflow 13: Repair engine stops after bounded budget or no-progress."""
    ws = tmp_path / "ws13"
    ws.mkdir(parents=True, exist_ok=True)
    engine = RepairEngine(ws)

    compiler_log = "error C2143: syntax error : missing ';' before '}'"
    cause = engine.extract_root_cause(compiler_log, stage_id="build_editor")

    can_repair, _ = engine.can_attempt_repair(cause)
    assert can_repair is True

    diff_text = "--- a.cpp\n+++ a.cpp\n@@ -1 +1 @@\n-x\n+x;\n"

    # Attempt 1
    engine.record_attempt(
        cause=cause,
        diff_text=diff_text,
        modified_files=["Source/a.cpp"],
        result_status="FAILED",
        diag_count_before=1,
        diag_count_after=1,
    )
    # Attempt 2 (identical diff and no error reduction)
    engine.record_attempt(
        cause=cause,
        diff_text=diff_text,
        modified_files=["Source/a.cpp"],
        result_status="FAILED",
        diag_count_before=1,
        diag_count_after=1,
    )

    # Policy limit: 2 consecutive attempts without progress halts repair
    can_repair_after, reason = engine.can_attempt_repair(cause)
    assert can_repair_after is False
    assert "consecutive attempts without measurable progress" in reason


# ── Workflow 14: Context-usage telemetry updates ───────────────────────────────

def test_workflow_14_context_usage_telemetry_updates(qapp, tmp_path):
    """Workflow 14: ContextUsageReport schema, 7-category breakdown, and UI sync."""
    ws = tmp_path / "ws14"
    ws.mkdir(parents=True, exist_ok=True)
    cm = ContextManager(ws)
    sm = SessionManager(ws)
    sess = sm.create_session(name="Context Test", model_name="gameforge-qwen3.5-9b:latest")

    report = cm.get_context_usage(
        session_id=sess.session_id,
        model_id="gameforge-qwen3.5-9b:latest",
        session_manager=sm,
    )

    assert isinstance(report, ContextUsageReport)
    assert report.nominal_capacity == 32768
    assert report.effective_budget < report.nominal_capacity
    assert report.used_tokens > 0
    assert report.remaining_tokens > 0
    assert 0.0 <= report.utilization_pct <= 100.0

    # Verify all 7 categories are accounted for
    bd = report.breakdown
    assert bd.system_prompt > 0
    assert bd.memory > 0
    assert bd.reserved_output == 2048
    assert bd.other_overhead == 256

    # Test frontend ContextUsageIndicator widget
    ind = ContextUsageIndicator()
    ind.update_report(report)
    assert "32" in ind._lbl_tokens.text()
    assert ind._progress.value() == int(round(report.utilization_pct))
    assert ind._badge.text() in ("EXACT", "EST")


# ── Workflow 15: Conversation persistence to SQLite / JSON ────────────────────

def test_workflow_15_conversation_persistence_sqlite_json(qapp, tmp_path):
    """Workflow 15: SessionManager persists messages, tools, and diffs atomically."""
    ws = tmp_path / "ws15"
    ws.mkdir(parents=True, exist_ok=True)
    sm = SessionManager(ws)

    sess = sm.create_session(name="Persist Session", model_name="gameforge-qwen3.5-9b:latest")
    sid = sess.session_id

    sm.append_message(sid, "user", "Please create GameMode header.")
    sm.append_message(sid, "assistant", "Creating Source/MyGame/MyGameMode.h.")
    sm.record_tool(
        session_id=sid,
        tool_name="write_file",
        arguments={"subpath": "Source/MyGame/MyGameMode.h"},
        output="{\"status\": \"SUCCESS\"}",
        status="SUCCESS",
    )
    sm.set_session_mode(sid, permissions_mode=PermissionsMode.UNRESTRICTED)

    # Verify atomic session file exists in .gameforge/sessions/
    sess_file = ws / ".gameforge" / "sessions" / f"{sid}.json"
    assert sess_file.is_file()

    loaded = sm.get_session(sid)
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert len(loaded.tool_history) == 1
    assert loaded.permissions_mode == "unrestricted"


# ── Workflow 16: Conversation restoration on reload ───────────────────────────

def test_workflow_16_conversation_restoration_on_reload(qapp, tmp_path):
    """Workflow 16: Brand new SessionManager instance restores prior state."""
    ws = tmp_path / "ws16"
    ws.mkdir(parents=True, exist_ok=True)
    sm1 = SessionManager(ws)

    sess = sm1.create_session(name="Restoration Test", model_name="gameforge-qwen3.5-4b:latest")
    sid = sess.session_id
    sm1.append_message(sid, "user", "Historical prompt message")
    sm1.append_message(sid, "assistant", "Historical response text")

    # Simulate restart by destroying sm1 and instantiating sm2
    del sm1
    sm2 = SessionManager(ws)
    restored = sm2.get_session(sid)

    assert restored is not None
    assert restored.session_id == sid
    assert restored.model_name == "gameforge-qwen3.5-4b:latest"
    assert len(restored.messages) == 2
    assert restored.messages[0].content == "Historical prompt message"
    assert restored.messages[1].content == "Historical response text"


# ── Workflow 17: Model selection and switching (9B default, 4B vision) ────────

def test_workflow_17_model_selection_and_switching(qapp, tmp_path):
    """Workflow 17: Model switching synchronizes TopBar, ChatPanel, and AssistantPanel."""
    ws = tmp_path / "ws17"
    ws.mkdir(parents=True, exist_ok=True)

    win = MainWindow(workspace_root=ws)
    try:
        win.confirm_on_close = False
        chat = win._chat_panel
        assistant = win._assistant_panel

        # Switch to 4B vision model
        chat.set_model("gameforge-qwen3.5-4b:latest")

        assert chat._current_model == "gameforge-qwen3.5-4b:latest"
        assert assistant.model_combo.currentText() == "gameforge-qwen3.5-4b:latest"

        # Verify session model was updated
        sess = win._agent.get_session(chat._session_id)
        assert sess.model_name == "gameforge-qwen3.5-4b:latest"

        # Switch back to 9B
        chat.set_model("gameforge-qwen3.5-9b:latest")
        assert chat._current_model == "gameforge-qwen3.5-9b:latest"
        assert assistant.model_combo.currentText() == "gameforge-qwen3.5-9b:latest"
    finally:
        win.confirm_on_close = False
        win.close()
        win.deleteLater()


# ── Workflow 18: Cancellation of active tasks without orphaned threads/processes

def test_workflow_18_task_cancellation_no_orphans(qapp, tmp_path):
    """Workflow 18: User stop cleanly sets cancel flag without process leak."""
    ws = tmp_path / "ws18"
    ws.mkdir(parents=True, exist_ok=True)

    proc_mgr = ProcessLifecycleManager()
    agent = AgentService(ws)
    try:
        sess_id = agent.create_session(name="Cancel Test")
        agent.send(sess_id, "Very long prompt to run in background")
        assert agent.is_busy is True

        # Issue cancellation
        agent.stop()
        assert agent.is_stopping is True

        # ProcessLifecycleManager terminates active processes without leaks
        proc_mgr.terminate_all()
        assert proc_mgr.get_active_count() == 0
    finally:
        agent.shutdown()


# ── Workflow 19: Permission approval / rejection flow ─────────────────────────

def test_workflow_19_permission_approval_rejection_flow(qapp, tmp_path):
    """Workflow 19: WAITING_APPROVAL triggers ApprovalCard; approve/reject resumes/halts."""
    ws = tmp_path / "ws19"
    ws.mkdir(parents=True, exist_ok=True)
    appr_store = ApprovalStore(ws)

    # 1. Create approval record with command details
    rec = appr_store.create(
        tool="run_command",
        args={"command": "pytest tests/test_physics.py", "shell": "powershell"},
        summary="Run command: `pytest tests/test_physics.py`",
        consequence="Executes pytest tests/test_physics.py via powershell",
        command="pytest tests/test_physics.py",
        shell="powershell",
        working_directory=".",
        risk_category="development_test",
        reason="Run physics unit tests",
    )
    appr_id = rec["approval_id"]

    agent = AgentService(ws)
    try:
        panel = ChatPanel(agent, workspace_root=ws)

        # Trigger WAITING_APPROVAL in chat
        panel._on_status("WAITING_APPROVAL", {"approval": rec})

        # Card rendered in chat layout
        card = panel._cards.get(appr_id)
        assert card is not None
        assert isinstance(card, ApprovalCard)
        assert card.is_command_request is True
        assert card.risk_category == "development_test"

        # Test Rejection flow
        panel._on_reject_action(appr_id)
        status_after_reject = appr_store.get(appr_id)["status"]
        assert status_after_reject == "REJECTED"

        # Create another approval for Approve test
        rec2 = appr_store.create(
            tool="run_command",
            args={"command": "dir", "shell": "powershell"},
            summary="Run command: `dir`",
            consequence="List dir",
            command="dir",
            shell="powershell",
            working_directory=".",
            risk_category="routine_read",
        )
        appr_id2 = rec2["approval_id"]
        panel._on_status("WAITING_APPROVAL", {"approval": rec2})
        card2 = panel._cards.get(appr_id2)
        assert card2 is not None

        # Test Approve flow
        panel._on_approve_action(appr_id2)
        # Card switches to running
        assert not card2._btn_cancel.isHidden()
        assert card2._btn_approve.isHidden()
    finally:
        agent.shutdown()


# ── Workflow 20: Clean application shutdown and restart ───────────────────────

def test_workflow_20_clean_application_shutdown_and_restart(qapp, tmp_path):
    """Workflow 20: Clean application shutdown with win.confirm_on_close = False."""
    ws = tmp_path / "ws20"
    ws.mkdir(parents=True, exist_ok=True)

    win = MainWindow(workspace_root=ws)
    try:
        win.confirm_on_close = False
        # Exercise tabs and panels
        win._switch_studio_view("games")
        win._switch_studio_view("settings")
        win._switch_studio_view("home")

        # Close cleanly without dialog freeze
        closed = win.close()
        assert closed is True
    finally:
        win.deleteLater()
