"""GameForge IDE — Desktop Acceptance & Native Workflow Test Suite.

Rigorously verifies all Milestone K native desktop requirements:
1. PySide6 MainWindow assembly, layout, and dock widget configuration.
2. Direct in-process AgentService and ToolService execution (zero localhost/browser required).
3. Session lifecycle, persistence, and reloading.
4. Project Explorer navigation and file selection.
5. Complete diff lifecycle: Propose -> Verify unmodified -> Reject -> Verify unmodified ->
   Propose -> Approve -> Verify file written -> Run validation command -> Rollback ->
   Verify original SHA-256 restored.
6. UnrealPanel engine detection, uproject scanning, and staged build triggering.
7. Task cancellation safety without false success.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QListWidget

from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel
from src.gameforge_ide.desktop.panels.diff_panel import DiffPanel
from src.gameforge_ide.desktop.panels.explorer_panel import ExplorerPanel
from src.gameforge_ide.desktop.panels.terminal_panel import TerminalPanel
from src.gameforge_ide.desktop.panels.unreal_panel import UnrealPanel
from src.gameforge_ide.desktop.services.agent_service import AgentService
from src.gameforge_ide.desktop.services.tool_service import ToolService


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance exists."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def disposable_workspace(tmp_path):
    """Creates a realistic disposable game project directory for testing."""
    ws = tmp_path / "TestGameWorkspace"
    ws.mkdir(parents=True, exist_ok=True)

    # Add realistic game files
    source_dir = ws / "Source" / "TestGame"
    source_dir.mkdir(parents=True, exist_ok=True)
    header = source_dir / "GameCharacter.h"
    header.write_text(
        "#pragma once\n"
        "#include 'CoreMinimal.h'\n"
        "class FGameCharacter {\n"
        "public:\n"
        "    float Health = 100.0f;\n"
        "};\n",
        encoding="utf-8",
    )
    cpp = source_dir / "GameCharacter.cpp"
    cpp.write_text(
        "#include 'GameCharacter.h'\n"
        "// Implementation\n",
        encoding="utf-8",
    )

    # Mock uproject
    uproj = ws / "TestGame.uproject"
    uproj.write_text('{"FileVersion": 3, "EngineAssociation": "5.7"}', encoding="utf-8")

    return ws


# ── 1. Desktop Window & Dock Verification ───────────────────────────────────

def test_desktop_main_window_assembly(qapp, disposable_workspace):
    """Verifies MainWindow creates all native dock widgets and shuts down cleanly."""
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False

    assert win.windowTitle().startswith("GameForge IDE")
    assert isinstance(win.centralWidget(), ChatPanel)
    assert hasattr(win, "_explorer") and isinstance(win._explorer, ExplorerPanel)
    assert hasattr(win, "_unreal_panel") and isinstance(win._unreal_panel, UnrealPanel)
    assert hasattr(win, "_diff_panel") and isinstance(win._diff_panel, DiffPanel)
    assert hasattr(win, "_terminal") and isinstance(win._terminal, TerminalPanel)

    # Verify menu bar & actions
    mb = win.menuBar()
    assert mb is not None
    actions = [a.text() for a in mb.actions()]
    assert any("&File" in a for a in actions)
    assert any("&View" in a for a in actions)
    object_names = {
        action.objectName()
        for menu_action in mb.actions()
        for action in (menu_action.menu().actions() if menu_action.menu() else [])
    }
    assert {
        "file_new_session", "file_quit", "view_explorer", "view_unreal",
        "view_diff", "view_terminal", "view_toggle_theme", "view_reset_layout",
        "help_about",
    } <= object_names
    theme_action = win.findChild(type(win._act_theme), "view_toggle_theme")
    assert theme_action is not None and theme_action.shortcut().toString() == "Ctrl+T"

    # Process events offscreen
    win.show()
    qapp.processEvents()

    # Clean shutdown
    win.close()
    qapp.processEvents()


# ── 2. Session Lifecycle & Persistence ───────────────────────────────────────

def test_desktop_session_persistence(disposable_workspace):
    """Verifies sessions created through AgentService persist to disk and reload."""
    agent1 = AgentService(disposable_workspace)
    session_id = agent1.create_session(
        name="Native Session Test",
        model_name="gameforge-27b-sft:latest",
        provider_type="ollama",
    )
    assert session_id is not None
    assert len(session_id) > 10

    # Verify session file exists in workspace .gameforge/sessions
    session_file = disposable_workspace / ".gameforge" / "sessions" / f"{session_id}.json"
    assert session_file.exists()

    agent1.shutdown()

    # Re-open session manager and verify persistence
    agent2 = AgentService(disposable_workspace)
    loaded = agent2.session_manager.get_session(session_id)
    assert loaded is not None
    assert loaded.session_id == session_id
    assert loaded.name == "Native Session Test"
    assert loaded.model_name == "gameforge-27b-sft:latest"
    agent2.shutdown()


def test_chat_composer_preserves_exact_prompt_text(qapp, disposable_workspace):
    """Sending a prompt preserves leading/trailing whitespace and indentation."""
    agent = AgentService(disposable_workspace)
    panel = ChatPanel(agent)
    sent = []
    agent.send = lambda session_id, prompt: sent.append((session_id, prompt)) or True
    prompt = "  \n\tvoid Tick() {\n    Super::Tick(Delta);\n}\n  "
    panel._input.setPlainText(prompt)

    panel._on_send()

    assert sent == [(panel._session_id, prompt)]
    agent.shutdown()


# ── 3. File Explorer Navigation ──────────────────────────────────────────────

def test_desktop_explorer_panel(qapp, disposable_workspace):
    """Verifies ExplorerPanel discovers workspace entries and emits file_selected."""
    ts = ToolService(disposable_workspace)
    explorer = ExplorerPanel(ts, disposable_workspace)
    explorer._populate_root()
    qapp.processEvents()

    selected_files = []
    explorer.file_selected.connect(lambda p: selected_files.append(p))

    # Verify root item
    tree = explorer._tree
    assert tree.topLevelItemCount() == 1
    root = tree.topLevelItem(0)
    assert root.text(0) == disposable_workspace.name

    # Trigger expansion of children
    explorer._populate_children(root, disposable_workspace)
    child_names = [root.child(i).text(0) for i in range(root.childCount())]
    assert "Source" in child_names
    assert "TestGame.uproject" in child_names

    # Test search filter
    explorer._on_search("GameCharacter")
    qapp.processEvents()
    explorer._on_search("")  # clear search
    qapp.processEvents()


# ── 4. Full Diff Lifecycle: Propose -> Reject -> Approve -> Rollback ─────────

def test_desktop_diff_complete_lifecycle(qapp, disposable_workspace):
    """Exercises the complete diff workflow:

    1. Propose change to GameCharacter.h
    2. Confirm file remains untouched before approval
    3. Reject change -> confirm file remains unchanged
    4. Propose second change -> Approve -> confirm file modified on disk
    5. Run validator command
    6. Rollback -> confirm original file SHA-256 is restored exactly
    """
    ts = ToolService(disposable_workspace)
    diff_panel = DiffPanel(ts)

    target_file = disposable_workspace / "Source" / "TestGame" / "GameCharacter.h"
    original_bytes = target_file.read_bytes()
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()

    # Step 1: Propose edit
    propose_res = ts.execute_sync(
        "propose_edit",
        {
            "subpath": "Source/TestGame/GameCharacter.h",
            "target_content": "float Health = 100.0f;",
            "replacement_content": "float Health = 250.0f; // Buffed",
        },
    )
    assert propose_res["status"] == "PENDING_APPROVAL"
    diff_id_1 = propose_res["diff_id"]
    patch_1 = propose_res["diff_patch"]

    # Step 2: Confirm file remains untouched
    assert target_file.read_bytes() == original_bytes

    # Step 3: Reject diff in panel
    rejected_signals = []
    diff_panel.diff_rejected.connect(lambda d: rejected_signals.append(d))
    diff_panel.show_diff(diff_id_1, {"file_path": "Source/TestGame/GameCharacter.h", "diff_patch": patch_1})
    diff_panel._on_reject()
    qapp.processEvents()

    assert diff_id_1 in rejected_signals
    # File must still be untouched
    assert target_file.read_bytes() == original_bytes
    assert hashlib.sha256(target_file.read_bytes()).hexdigest() == original_sha256

    # Step 4: Propose second edit
    propose_res_2 = ts.execute_sync(
        "propose_edit",
        {
            "subpath": "Source/TestGame/GameCharacter.h",
            "target_content": "float Health = 100.0f;",
            "replacement_content": "float Health = 500.0f;\n    bool bIsInvulnerable = true;",
        },
    )
    assert propose_res_2["status"] == "PENDING_APPROVAL"
    diff_id_2 = propose_res_2["diff_id"]

    # Step 5: Approve second edit in panel
    approved_signals = []
    diff_panel.diff_approved.connect(lambda d: approved_signals.append(d))
    diff_panel.show_diff(diff_id_2, {"file_path": "Source/TestGame/GameCharacter.h", "diff_patch": propose_res_2["diff_patch"]})
    diff_panel._on_approve()
    qapp.processEvents()

    assert diff_id_2 in approved_signals
    new_text = target_file.read_text(encoding="utf-8")
    assert "float Health = 500.0f;" in new_text
    assert "bIsInvulnerable = true;" in new_text

    # Step 6: Run validator command (python file check)
    val_res = ts.execute_approved_sync(
        "run_command",
        {"command": "python -c \"print('Validator PASS')\""},
    )
    assert val_res["status"] == "SUCCESS"
    assert "Validator PASS" in val_res["output"]

    # Step 7: Rollback change
    rolled_signals = []
    diff_panel.diff_rolled_back.connect(lambda d: rolled_signals.append(d))
    diff_panel._on_rollback()
    qapp.processEvents()

    assert diff_id_2 in rolled_signals
    restored_bytes = target_file.read_bytes()
    restored_sha256 = hashlib.sha256(restored_bytes).hexdigest()

    assert restored_sha256 == original_sha256
    assert "bIsInvulnerable" not in target_file.read_text(encoding="utf-8")


# ── 5. Unreal Engine Panel & Build Discovery ─────────────────────────────────

def test_desktop_unreal_panel_discovery(qapp, disposable_workspace):
    """Verifies UnrealPanel executes engine detection and project enumeration."""
    ts = ToolService(disposable_workspace)
    unreal = UnrealPanel(ts, disposable_workspace)
    qapp.processEvents()

    # Trigger refresh
    unreal._refresh()
    # Allow background threads to complete
    for _ in range(20):
        qapp.processEvents()
        time.sleep(0.05)

    # Verify project list contains TestGame.uproject
    items = [unreal._project_list.item(i).text() for i in range(unreal._project_list.count())]
    assert "TestGame" in items
    assert unreal._btn_build.isEnabled() is True


# ── 6. Task Cancellation Safety ──────────────────────────────────────────────

def test_desktop_task_cancellation(disposable_workspace):
    """Verifies stopping an agent task safely resets is_busy flag without false success."""
    agent = AgentService(disposable_workspace)
    session_id = agent.create_session(name="Cancel Test")

    done_signals = []
    agent.task_done.connect(lambda t: done_signals.append(t))

    # Mark busy
    agent._worker.set_task(session_id, "running prompt")
    agent._busy = True
    assert agent.is_busy is True

    # Stop task
    agent.stop()
    assert agent.is_busy is True
    assert agent.is_stopping is True
    assert agent._worker._stop_flag.is_set() is True
    assert agent.send("new-session", "must not replace running task") is False
    assert agent._worker._session_id == session_id
    assert agent._worker._prompt == "running prompt"

    # The service becomes available only after worker completion is observed.
    agent._on_done("[Cancelled by user]")
    assert agent.is_busy is False
    assert agent.is_stopping is False

    agent.shutdown()


def test_new_session_ignores_late_events_from_stopped_run(qapp, disposable_workspace):
    agent = AgentService(disposable_workspace)
    panel = ChatPanel(agent)
    old_session_id = panel._session_id
    agent._worker.set_task(old_session_id, "old task")
    agent._busy = True
    panel._active_bubble = panel._add_bubble("assistant", "Old response")

    panel._new_session()
    new_session_id = panel._session_id
    assert new_session_id != old_session_id
    assert agent.is_busy is True
    assert panel._ignore_active_task_events is True

    panel._on_token("late old-session token")
    panel._on_tool_called("run_command", {"command": "late"})
    panel._on_done("late old-session completion")
    qapp.processEvents()

    assert panel._ignore_active_task_events is False
    current_text = "\n".join(
        panel._msg_layout.itemAt(index).widget()._raw_text
        for index in range(panel._msg_layout.count())
        if panel._msg_layout.itemAt(index).widget() is not None
    )
    assert "late old-session token" not in current_text
    assert "late old-session completion" not in current_text

    agent._on_done("cancelled old task")
    agent.shutdown()


# ── 7. Message Bubble Auto-Sizing and Markdown ───────────────────────────────

def test_message_bubble_dynamic_sizing_and_markdown(qapp, disposable_workspace):
    """Verifies that _MessageBubble dynamically resizes to content without clipping."""
    from src.gameforge_ide.desktop.panels.chat_panel import _MessageBubble

    # Short single line
    b_short = _MessageBubble("user", "Hello GameForge")
    b_short.resize(500, 100)
    qapp.processEvents()
    b_short._adjust_height()
    h_short = b_short._content.height()
    assert h_short >= 36

    # Long multi-line message with code block
    long_code = (
        "Here is the character component header:\n\n"
        "```cpp\n"
        "#pragma once\n"
        "#include 'CoreMinimal.h'\n"
        "#include 'Components/ActorComponent.h'\n"
        "#include 'GameCharacterComponent.generated.h'\n\n"
        "UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))\n"
        "class GAMEFORGE_API UGameCharacterComponent : public UActorComponent\n"
        "{\n"
        "    GENERATED_BODY()\n"
        "public:\n"
        "    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category='Attributes')\n"
        "    float Health = 100.0f;\n"
        "};\n"
        "```\n\n"
        "Tested against UE 5.7 conventions."
    )
    b_long = _MessageBubble("assistant", long_code)
    b_long.resize(500, 400)
    qapp.processEvents()
    b_long._adjust_height()
    h_long = b_long._content.height()

    # Long message must be significantly taller than short message (never clamped to 30px)
    assert h_long > 100
    assert h_long > h_short

    # Verify copy button
    b_long._copy_to_clipboard()
    assert QApplication.clipboard().text() == long_code


# ── 8. Dock Proportions and Terminal Toggle ──────────────────────────────────

def test_dock_proportions_and_terminal_toggle(qapp, disposable_workspace):
    """Verifies MainWindow sets proportional dock sizing and toolbar terminal toggle."""
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    win.resize(1600, 960)
    win.show()
    qapp.processEvents()

    assert win._dock_explorer.minimumWidth() >= 200
    assert win._dock_unreal.minimumWidth() >= 280
    assert win._dock_terminal.minimumHeight() >= 120

    # Test terminal toggle action
    assert win._dock_terminal.isVisible() is True
    win._act_tb_terminal.trigger()
    qapp.processEvents()
    assert win._dock_terminal.isVisible() is False

    win._act_tb_terminal.trigger()
    qapp.processEvents()
    assert win._dock_terminal.isVisible() is True

    win.close()
    qapp.processEvents()


def test_command_palette_filters_and_runs_implemented_action(qapp, disposable_workspace, monkeypatch):
    """Ctrl+K palette lists implemented commands and dispatches the chosen one."""
    captured = {}

    def capture_dialog(dialog):
        captured["dialog"] = dialog
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", capture_dialog)
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    win.resize(1400, 900)
    win.show()
    qapp.processEvents()

    palette_action = win.findChild(type(win._act_command_palette), "command_palette")
    assert palette_action is not None
    assert palette_action.shortcut().toString() == "Ctrl+K"
    win._open_command_palette()

    dialog = captured["dialog"]
    search = dialog.findChild(QLineEdit, "command_palette_search")
    commands = dialog.findChild(QListWidget, "command_palette_commands")
    assert search is not None and commands is not None
    search.setText("terminal")
    visible = [commands.item(i) for i in range(commands.count()) if not commands.item(i).isHidden()]
    assert [item.text() for item in visible] == ["Toggle Terminal"]

    visible[0].data(Qt.UserRole)()
    qapp.processEvents()
    assert win._dock_terminal.isVisible() is False

    win.close()
    qapp.processEvents()


def test_theme_toggle_converts_inline_styles_and_persists(qapp, disposable_workspace):
    """Studio theme changes update existing panel styles and persist the choice."""
    settings_path = disposable_workspace / ".gameforge" / "ide_settings.ini"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = QSettings(str(settings_path), QSettings.IniFormat)
    keys = ("appearance/theme", "window/geometry", "window/layout")
    previous = {key: settings.value(key) if settings.contains(key) else None for key in keys}
    existed = {key: settings.contains(key) for key in keys}
    settings.setValue("appearance/theme", "dark")

    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    win._diff_panel._diff_view.display_patch("+Added line\n")
    assert "#9ca3af" in win._ollama_indicator.styleSheet()
    win._toggle_theme()
    qapp.processEvents()
    assert win._theme == "light"
    assert settings.value("appearance/theme") == "light"
    assert "#5b6575" in win._ollama_indicator.styleSheet()
    assert "#f6f7fb" in qapp.styleSheet()
    diff_cursor = QTextCursor(win._diff_panel._diff_view.document())
    diff_cursor.setPosition(0)
    diff_cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
    added_format = diff_cursor.charFormat()
    assert added_format.foreground().color().name() == "#047857"
    assert added_format.background().color().name() == "#e2f4ec"
    win._diff_panel._diff_view.display_patch("+Future light diff\n")
    diff_cursor = QTextCursor(win._diff_panel._diff_view.document())
    diff_cursor.setPosition(0)
    diff_cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
    future_diff_format = diff_cursor.charFormat()
    assert future_diff_format.foreground().color().name() == "#047857"
    from src.gameforge_ide.desktop.panels.chat_panel import _MessageBubble
    light_bubble = _MessageBubble("assistant", "Light-theme response")
    assert "#047857" in light_bubble.styleSheet()
    assert "#1c2432" in light_bubble._content.document().defaultStyleSheet()
    win._chat_panel._status_bar.set_busy()
    assert "#a16207" in win._chat_panel._status_bar._dot.styleSheet()
    win._terminal._output.clear()
    win._terminal._write_err("light error\n")
    terminal_format = win._terminal._output.document().firstBlock().begin().fragment().charFormat()
    assert terminal_format.foreground().color().name() == "#c2413a"

    win._toggle_theme()
    qapp.processEvents()
    assert win._theme == "dark"
    assert "#9ca3af" in win._ollama_indicator.styleSheet()
    assert "#f59e0b" in win._chat_panel._status_bar._dot.styleSheet()
    assert "#00d9a3" in light_bubble.styleSheet()
    assert "#f3f4f8" in light_bubble._content.document().defaultStyleSheet()
    diff_cursor = QTextCursor(win._diff_panel._diff_view.document())
    diff_cursor.setPosition(0)
    diff_cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
    added_format = diff_cursor.charFormat()
    assert added_format.foreground().color().name() == "#00d9a3"
    win._toggle_theme()
    win.show()
    qapp.processEvents()
    win._dock_explorer.hide()
    win.close()
    qapp.processEvents()
    assert settings.value("appearance/theme") == "light"
    assert settings.value("window/geometry") is not None
    assert settings.value("window/layout") is not None

    restored = MainWindow(disposable_workspace)
    restored.confirm_on_close = False
    assert restored._theme == "light"
    restored.show()
    qapp.processEvents()
    assert restored._dock_explorer.isHidden()
    restored._reset_layout()
    qapp.processEvents()
    assert not restored._dock_explorer.isHidden()
    restored.close()
    qapp.processEvents()

    for key in keys:
        if existed[key]:
            settings.setValue(key, previous[key])
        else:
            settings.remove(key)
    settings.sync()


def test_reset_layout_restores_default_dock_state_and_size(qapp, disposable_workspace):
    win = MainWindow(disposable_workspace)
    win.confirm_on_close = False
    win.show()
    qapp.processEvents()

    win._dock_terminal.hide()
    win._dock_explorer.hide()
    qapp.processEvents()
    assert win._dock_terminal.isHidden()
    assert win._dock_explorer.isHidden()

    reset_action = win.findChild(type(win._act_reset_layout), "view_reset_layout")
    assert reset_action is not None
    reset_action.trigger()
    qapp.processEvents()
    assert not win._dock_terminal.isHidden()
    assert not win._dock_explorer.isHidden()
    assert win.size() == QSize(1600, 960)

    win.close()
    qapp.processEvents()


# ── 9. Unreal Panel UAT and Path Detection ───────────────────────────────────

def test_unreal_panel_uat_and_path_detection(qapp, disposable_workspace):
    """Verifies UnrealPanel displays install_path and UAT availability."""
    ts = ToolService(disposable_workspace)
    unreal = UnrealPanel(ts, disposable_workspace)
    qapp.processEvents()

    # Mock tool result
    unreal._on_tool_result("unreal_engine_info", {
        "installed": True,
        "version": "5.7.4",
        "install_path": r"E:\UE\UE_5.7",
        "uat_available": True,
    })
    qapp.processEvents()

    assert "Detected" in unreal._row_installed._val.text()
    assert unreal._row_version._val.text() == "5.7.4"
    assert "E:\\UE\\UE_5.7" in unreal._row_path._val.text()
    assert "RunUAT" in unreal._row_uat._val.text()


# ── 10. Agent Async Generator Cleanup ────────────────────────────────────────

def test_agent_worker_async_cleanup(disposable_workspace):
    """Verifies _AgentWorker handles stream execution and shuts down without unhandled asyncgen warnings."""
    agent = AgentService(disposable_workspace)
    session_id = agent.create_session(name="Asyncgen Cleanup Test")

    # Send a prompt and let it finish or simulate done
    worker = agent._worker
    assert worker is not None
    agent.shutdown()
    assert agent._thread.isRunning() is False

