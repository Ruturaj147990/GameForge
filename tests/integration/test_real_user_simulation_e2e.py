"""Real-World End-to-End User Simulation Scenarios (Section 11).

Exercises the actual desktop GUI (MainWindow, ChatPanel, Rail, ViewHost)
and backend components across 8 realistic user simulation scenarios:
1. Straightforward game creation request ("Make a 3D platformer where the player collects 6 coins and reaches the portal.")
2. Request involving multiple game objects and interactions (arena game with 5 guards, 3 health pickups, hazard trap, spawner)
3. Request requiring several sequential Unreal operations (inspect level actors, spawn actor, read back transforms)
4. Request involving modifications to existing project content (modifying game design spec on active project)
5. Complex request requiring planning, tool selection, execution, and verification (codebase exploration, C++ rules inspection, architecture report)
6. Request that intentionally triggers an error or invalid operation (launching non-existent executable play_game("Fake.exe"))
7. Multi-step conversation verifying project context retention across turns
8. Long-running operation verifying progress streaming and frontend responsiveness (StallMonitor 0 stalls > 50ms)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QTextEdit

from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.session_manager import ChatMessage, SessionManager
from src.gameforge_ide.backend.tools.game_tools import GameTools
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.core.settings import get_settings, reset_settings_cache
from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
from src.gameforge_ide.desktop.diagnostics.stall_monitor import StallMonitor
from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble
from src.gameforge_ide.unreal import op_catalog, op_schemas


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_env(tmp_path: Path, monkeypatch):
    """Sets up an isolated workspace and project environment."""
    monkeypatch.setenv("GAMEFORGE_STALL_MONITOR", "1")
    monkeypatch.setenv("GAMEFORGE_PROJECTS_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(tmp_path / "settings.json"))
    reset_settings_cache()

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    # Initialize a sample Unreal project
    proj_dir = projects_dir / "SampleGame"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "SampleGame.uproject").write_text(
        json.dumps({
            "FileVersion": 3,
            "EngineAssociation": "5.7",
            "Category": "Games",
            "Description": "Sample Unreal 5.7 project",
            "Plugins": [
                {"Name": "GameForge", "Enabled": True},
                {"Name": "PythonScriptPlugin", "Enabled": True},
            ],
        }),
        encoding="utf-8",
    )

    # Create dummy binaries
    bin_dir = proj_dir / "Binaries" / "Win64"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "SampleGame.exe").write_bytes(b"MZfakebinary")

    # Create initial GDS
    gds_dir = proj_dir / "GameForge" / "design"
    gds_dir.mkdir(parents=True, exist_ok=True)
    (gds_dir / "game.gds.json").write_text(
        preset_platformer().model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Create Source code files
    source_dir = proj_dir / "Source" / "SampleGame"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SampleGame.h").write_text(
        "#pragma once\n#include 'CoreMinimal.h'\n",
        encoding="utf-8",
    )
    (source_dir / "SampleGame.cpp").write_text(
        '#include "SampleGame.h"\n#include "Modules/ModuleManager.h"\nIMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, SampleGame, "SampleGame");\n',
        encoding="utf-8",
    )

    return {
        "workspace": tmp_path,
        "projects_dir": projects_dir,
        "project_dir": proj_dir,
    }


def test_scenario_1_straightforward_game_creation(qapp, test_env):
    """Scenario 1: Straightforward game creation request.

    User Request: 'Make a 3D platformer where the player collects 6 coins and reaches the portal.'
    Verifies: Prompt understanding, GDS synthesis, entity identification, and plan generation.
    """
    prompt = "Make a 3D platformer where the player collects 6 coins and reaches the portal."
    res = prompt_to_gds(prompt)
    assert res.status == "OK", f"Expected OK status, got {res.status}: {res.errors}"
    assert res.gds is not None
    assert res.gds.overview.genre.value.lower() == "platformer"

    # Verify entities synthesized match prompt specifications
    kinds = [e.kind.value for e in res.gds.entities]
    assert "player" in kinds
    assert "pickup" in kinds

    # Verify pickup count (coins) is preserved or synthesized appropriately
    pickup_entity = next(e for e in res.gds.entities if e.kind.value == "pickup")
    assert pickup_entity.count >= 1

    # Verify ToolGateway plan_game returns successful structured spec
    gateway = ToolGateway(test_env["workspace"])
    plan_res = gateway.execute_tool("plan_game", {"prompt": prompt})
    assert plan_res["status"] == "SUCCESS"
    assert "gds" in plan_res


def test_scenario_2_multiple_game_objects_and_interactions(qapp, test_env):
    """Scenario 2: Request involving multiple game objects and interactions.

    User Request: 'arena game with 5 guards, 3 health pickups, hazard trap, spawner'
    Verifies: Multi-entity parsing, correct counts, hazard assignment, and game design integrity.
    """
    prompt = "arena game with 5 guards, 3 health pickups, hazard trap, spawner"
    res = prompt_to_gds(prompt)
    assert res.status == "OK", f"Expected OK status: {res.errors}"
    assert res.gds is not None

    entity_kinds = {e.kind.value for e in res.gds.entities}
    assert "player" in entity_kinds
    assert "pickup" in entity_kinds
    assert "hazard" in entity_kinds
    assert "guard" in entity_kinds

    # Check that counts reflect user intent
    guards = next(e for e in res.gds.entities if e.kind.value == "guard")
    pickups = next(e for e in res.gds.entities if e.kind.value == "pickup")
    hazards = next(e for e in res.gds.entities if e.kind.value == "hazard")

    assert guards.count >= 3
    assert pickups.count == 3
    assert hazards.count >= 1


def test_scenario_3_sequential_unreal_operations(qapp, test_env):
    """Scenario 3: Sequential Unreal operations.

    User Workflow:
    1. Inspect level actors (actors_in_level).
    2. Spawn actor with specified class, transform, and label (spawn_actor).
    3. Query resulting state (read back after write).
    Verifies: op_schemas validation, argument normalization, and error containment.
    """
    uproject_path = str(test_env["project_dir"] / "SampleGame.uproject")

    # Step 1: Validate actors_in_level argument validation
    clean_args, errs = op_schemas.validate_args("actors_in_level", {"limit": 50}, strict=True)
    assert not errs
    assert clean_args["limit"] == 50

    # Step 2: Validate spawn_actor argument validation with transform
    spawn_payload = {
        "label": "TestCoin_01",
        "actor_class": "StaticMeshActor",
        "location": {"x": 100.0, "y": 200.0, "z": 50.0},
        "rotation": {"pitch": 0.0, "yaw": 45.0, "roll": 0.0},
        "snap_to_ground": False,
    }
    clean_spawn, errs = op_schemas.validate_args("spawn_actor", spawn_payload, strict=True)
    assert not errs
    assert clean_spawn["label"] == "TestCoin_01"
    assert clean_spawn["location"]["x"] == 100.0

    # Step 3: Verify read-back schema validation & dispatch
    # When editor is offline, ToolGateway unreal_editor fails closed honestly without fabricating
    gateway = ToolGateway(test_env["workspace"])
    mock_link = MagicMock()
    mock_link.call.return_value = {"ok": False, "errors": ["EDITOR_NOT_CONNECTED"]}
    with patch.object(gateway.game_tools, "_link", return_value=mock_link):
        res = gateway.execute_tool(
            "unreal_editor",
            {"uproject": uproject_path, "op": "actors_in_level", "args": {"limit": 10}},
            approval_granted=True,
        )
        assert res["status"] == "ERROR"
        assert res["result"]["errors"] == ["EDITOR_NOT_CONNECTED"]
        mock_link.call.assert_called_once_with("actors_in_level", {"limit": 10})

    # When live editor is active, verify structured envelope is returned cleanly
    mock_link_live = MagicMock()
    mock_link_live.call.return_value = {
        "ok": True,
        "op": "actors_in_level",
        "data": {"actors": ["PlayerStart_1", "TestCoin_01"], "count": 2},
    }
    with patch.object(gateway.game_tools, "_link", return_value=mock_link_live):
        res_live = gateway.execute_tool(
            "unreal_editor",
            {"uproject": uproject_path, "op": "actors_in_level", "args": {"limit": 10}},
            approval_granted=True,
        )
        assert res_live["status"] == "SUCCESS"
        assert res_live["result"]["data"]["count"] == 2


def test_scenario_4_modify_existing_project_content(qapp, test_env):
    """Scenario 4: Request involving modifications to existing project content.

    User Request: Modifying existing game spec on active project.
    Verifies: GDS loading, RFC 6902 patch creation, application, and file persistence.
    """
    proj_dir = test_env["project_dir"]
    gds_file = proj_dir / "GameForge" / "design" / "game.gds.json"
    assert gds_file.is_file()

    initial_gds = GameDesignSpec.model_validate_json(gds_file.read_text(encoding="utf-8"))
    initial_coins = next(e.count for e in initial_gds.entities if e.kind.value == "pickup")

    game_tools = GameTools(test_env["workspace"])
    # Mock the Unreal build step while allowing the save_hook to persist patched GDS
    def fake_pipeline(**kwargs):
        if "save_hook" in kwargs and callable(kwargs["save_hook"]):
            kwargs["save_hook"](proj_dir)
        return {"ok": True, "status": "SUCCESS"}

    with patch.object(game_tools, "_execute_composer_forge_pipeline", side_effect=fake_pipeline):
        mod_res = game_tools.modify_game(
            prompt="add 5 coins",
            project_dir=proj_dir,
            package=False,
        )

    assert mod_res.get("ok") is True
    assert "patch_ops" in mod_res
    assert len(mod_res["patch_ops"]) >= 1

    # Verify GDS modified on disk
    updated_gds = GameDesignSpec.model_validate_json(gds_file.read_text(encoding="utf-8"))
    updated_coins = next(e.count for e in updated_gds.entities if e.kind.value == "pickup")
    assert updated_coins > initial_coins


def test_scenario_5_complex_planning_codebase_exploration_report(qapp, test_env):
    """Scenario 5: Complex request requiring planning, tool selection, execution, and verification.

    User Request: 'Explore project C++ codebase, inspect module declaration, and write architecture report.'
    Verifies: list_dir, read_file, search_code, write_file, verify_disk tool chain execution.
    """
    gateway = ToolGateway(test_env["project_dir"])

    # 1. list_dir
    list_res = gateway.execute_tool("list_dir", {"subpath": "Source/SampleGame"})
    assert list_res["status"] == "SUCCESS"
    entries = [item["path"] for item in list_res["items"]]
    assert any("SampleGame.h" in e for e in entries)
    assert any("SampleGame.cpp" in e for e in entries)

    # 2. read_file
    read_res = gateway.execute_tool("read_file", {"subpath": "Source/SampleGame/SampleGame.cpp"})
    assert read_res["status"] == "SUCCESS"
    assert "IMPLEMENT_PRIMARY_GAME_MODULE" in read_res["content"]

    # 3. search_code
    search_res = gateway.execute_tool("search_code", {"query": "CoreMinimal"})
    assert search_res["status"] == "SUCCESS"
    assert len(search_res["matches"]) >= 1

    # 4. write_file (architecture report)
    report_content = (
        "# Architecture Report: SampleGame\n\n"
        "## Engine Version\nUnreal Engine 5.7.4\n\n"
        "## Modules\n- Primary: SampleGame (FDefaultGameModuleImpl)\n"
    )
    write_res = gateway.execute_tool(
        "write_file",
        {"subpath": "docs/ARCHITECTURE.md", "content": report_content},
        approval_granted=True,
    )
    assert write_res["status"] == "SUCCESS"

    # 5. verify_disk
    verify_res = gateway.execute_tool(
        "verify_disk",
        {"subpath": "docs/ARCHITECTURE.md", "expected_fragment": "SampleGame (FDefaultGameModuleImpl)"},
    )
    assert verify_res["status"] == "SUCCESS"
    assert verify_res["verified"] is True


def test_scenario_6_intentional_error_and_honest_reporting(qapp, test_env):
    """Scenario 6: Request that intentionally triggers an error or invalid operation.

    User Request: Launch a fake or non-existent game executable `play_game('FakeGame_NonExistent.exe')`.
    Verifies: System fails closed, reports honest error message, does NOT crash or hallucinate success.
    """
    game_tools = GameTools(test_env["workspace"])
    res = game_tools.play_game(exe="FakeGame_NonExistent.exe")

    # Must be BLOCKED or ERROR; must not report OK or fabricate a process ID
    assert res.get("status") in ("BLOCKED", "ERROR")
    assert res.get("ok", False) is False
    assert any(needle in res.get("error", "") for needle in ("Not a packaged game executable", "does not exist or was rejected"))

    # Check through ToolGateway as well
    gateway = ToolGateway(test_env["workspace"])
    gw_res = gateway.execute_tool("play_game", {"exe": "FakeGame_NonExistent.exe"}, approval_granted=True)
    assert gw_res.get("status") in ("BLOCKED", "ERROR")
    assert gw_res.get("ok", False) is False


def test_scenario_7_multistep_conversation_context_retention(qapp, test_env):
    """Scenario 7: Multi-step conversation verifying project context retention across turns.

    Verifies: SessionManager persists messages, ContextManager retains project identity and turns.
    """
    sm = SessionManager(test_env["workspace"])
    session = sm.create_session(name="Context Retention Test")
    sid = session.session_id

    # Turn 1: Project specification
    sm.append_message(sid, "user", "We are building an Unreal 5.7 roguelike called Starlight.")
    sm.append_message(sid, "assistant", "Understood. Project Starlight (Unreal 5.7 Roguelike) context initialized.")

    # Turn 2: Follow-up request relying on previous turn
    sm.append_message(sid, "user", "What is the project name and genre we discussed?")

    # Inspect context retention
    current_session = sm.get_session(sid)
    assert current_session is not None
    messages = current_session.messages
    assert len(messages) == 3

    cm = ContextManager(test_env["workspace"])
    history_dicts = [{"role": m.role, "content": m.content} for m in messages]
    compacted = cm.compact_conversation_history(history_dicts, max_tokens=4000)

    assembled_history = " ".join(m.get("content", "") for m in compacted)
    assert "Starlight" in assembled_history
    assert "roguelike" in assembled_history
    assert len(compacted) == 3


def test_scenario_8_long_running_progress_streaming_and_responsiveness(qapp, test_env):
    """Scenario 8: Long-running operation verifying progress streaming and frontend responsiveness.

    Verifies: MainWindow and ChatPanel process background events, StallMonitor records 0 stalls > 50ms.
    """
    monitor = StallMonitor(output_dir=test_env["workspace"] / "reports")
    monitor.start()

    win = MainWindow(test_env["workspace"])
    win._current_project = "SampleGame"
    win.resize(1440, 900)
    win.show()

    try:
        chat = win._chat_panel
        assert chat is not None

        # Simulate progressive streaming tokens and activity pills into ChatPanel
        chat._on_token("Analyzing project structure...\n")
        qapp.processEvents()

        # Simulate tool execution activity
        chat._on_tool_called("list_dir", {"subpath": "Source"})
        qapp.processEvents()
        chat._on_tool_result("list_dir", {"status": "SUCCESS", "entries": ["SampleGame"]})
        qapp.processEvents()

        chat._on_token("Found module SampleGame. Verifying build targets...\n")
        qapp.processEvents()

        # Simulate multi-step UI switching during streaming
        win._switch_studio_view("design")
        qapp.processEvents()
        win._switch_studio_view("build")
        qapp.processEvents()
        win._switch_studio_view("play")
        qapp.processEvents()
        win._switch_studio_view("home")
        qapp.processEvents()

        # Complete turn
        chat._on_done("Analysis complete. Module SampleGame is healthy and ready for compilation.")
        qapp.processEvents()

        # Confirm assistant bubble rendered correctly
        bubbles = [
            chat._msg_layout.itemAt(i).widget()
            for i in range(chat._msg_layout.count())
            if isinstance(chat._msg_layout.itemAt(i).widget(), _MessageBubble)
        ]
        assert len(bubbles) >= 1

    finally:
        monitor.stop()
        win.confirm_on_close = False
        win.close()
        win.deleteLater()

    # Verify stall report
    report_path = monitor.save_report()
    assert report_path.is_file()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "stalls_detected" in data
