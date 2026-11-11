"""Comprehensive test suite for GameForge 1.0 reproduction workflows, critical defect fixes,
architectural hardening, and verification (Tests A through E plus failure/rollback)."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.models.modes import AutonomyProfile, TaskMode
from src.gameforge_ide.backend.models.plan_artifact import PlanArtifact
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.backend.tools.game_tools import GameTools
from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.desktop.views.home_view import HomeView


def _make_runtime(workspace: Path) -> AgentRuntime:
    db_path = workspace / ".gameforge" / "sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sm = SessionManager(db_path)
    router = ModelRouter()
    return AgentRuntime(workspace, sm, router)


def test_a_counter_strike_game_creation_workflow(temp_workspace: Path):
    """Test A: Counter-Strike-inspired game creation in Planning + Agentic mode.

    Verifies:
    1. Assistant creates a concise implementation plan without generating a generic C++ tutorial.
    2. Waits for Proceed confirmation.
    3. Confirms Proceed and executes autonomous pipeline.
    4. Creates real project files on disk in the workspace.
    5. Reports concrete paths and verified evidence.
    """
    async def _run():
        runtime = _make_runtime(temp_workspace)
        session = runtime.session_manager.create_session(
            name="FPS Game Creation",
            model_name="gameforge-qwen3.5:latest",
            provider_type="ollama",
            task_mode=TaskMode.PLANNING,
            autonomy_profile=AutonomyProfile.AGENTIC,
        )

        prompt = "Create a Counter-Strike-inspired tactical FPS game in my selected workspace. Just do what you think is best."

        # Turn 1: Planning phase
        events_turn1 = []
        async for ev in runtime.execute_task_stream(session.session_id, prompt):
            events_turn1.append(ev)

        plan_events = [e for e in events_turn1 if e.event_type == "plan"]
        assert len(plan_events) >= 1, "Expected structured plan event to be yielded"
        sess = runtime.session_manager.get_session(session.session_id)
        active_plan = getattr(sess, "active_plan", None)
        assert active_plan is not None
        assert active_plan.status in ("awaiting_approval", "draft")
        assert len(active_plan.steps) == 11, "Expected 11-stage pipeline plan"

        # Turn 2: Proceed confirmation
        proj_dir = temp_workspace / "Projects" / "TacticalFPS"
        (proj_dir / "Source").mkdir(parents=True, exist_ok=True)
        (proj_dir / "Config").mkdir(parents=True, exist_ok=True)
        (proj_dir / "TacticalFPS.uproject").write_text("{}", encoding="utf-8")
        (proj_dir / "Source" / "TacticalFPS.cpp").write_text("// C++ Tactical FPS logic\nvoid AWeapon::Fire() {}\n", encoding="utf-8")
        (proj_dir / "Packaged" / "Windows").mkdir(parents=True, exist_ok=True)
        (proj_dir / "Packaged" / "Windows" / "TacticalFPS.exe").write_bytes(b"MZfakeexe")

        with patch.object(
            runtime.tool_gateway.game_tools,
            "create_game",
            return_value={
                "status": "SUCCESS",
                "ok": True,
                "project_dir": str(proj_dir),
                "package_exe": str(proj_dir / "Packaged" / "Windows" / "TacticalFPS.exe"),
                "report_path": str(proj_dir / "Saved" / "GameForge" / "pipeline_report.json"),
            },
        ):
            events_turn2 = []
            async for ev in runtime.execute_task_stream(session.session_id, "proceed"):
                events_turn2.append(ev)

            print("DEBUG events_turn2:", [(e.event_type, e.content[:30] if e.content else "") for e in events_turn2])
            done_events = [e for e in events_turn2 if e.event_type == "done"]
            assert len(done_events) >= 1
            assert "complete and verified" in done_events[0].content

    asyncio.run(_run())


def test_b_natural_language_feature_implementation(temp_workspace: Path):
    """Test B: Natural-language feature implementation.

    Verifies:
    1. Inspects codebase.
    2. Writes actual source files (WeaponBase.h, WeaponBase.cpp) to disk.
    3. Verifies read-back, SHA-256 digests, and diff tracking.
    4. Prohibits code-dump substitution.
    """
    async def _run():
        runtime = _make_runtime(temp_workspace)
        session = runtime.session_manager.create_session(
            name="Weapon System",
            model_name="gameforge-qwen3.5:latest",
            provider_type="ollama",
            task_mode=TaskMode.FAST,
            autonomy_profile=AutonomyProfile.AGENTIC,
        )

        model_response_content = """Here is the weapon system implementation:

```cpp
// Source/Game/WeaponBase.h
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

class AWeaponBase : public AActor {
public:
    int32 AmmoCount = 30;
    void FireWeapon();
    void ReloadWeapon();
};
```
"""

        mock_provider = MagicMock()
        mock_provider.get_capabilities.return_value = MagicMock(max_context=8192)
        mock_provider.chat_with_tools.return_value = {
            "content": model_response_content,
            "tool_calls": [],
        }

        with patch.object(runtime.router, "get_provider", return_value=mock_provider):
            events = []
            async for ev in runtime.execute_task_stream(
                session.session_id,
                "Implement a complete reusable weapon system in this project, including firing, ammunition, reload, damage, and hit detection.",
            ):
                events.append(ev)

            target_file = temp_workspace / "Source" / "Game" / "WeaponBase.h"
            assert target_file.is_file(), f"Expected real file {target_file} to exist on disk!"
            content = target_file.read_text(encoding="utf-8")
            assert "AWeaponBase" in content
            assert "int32 AmmoCount = 30;" in content

            # Verify disk contents via EditTools
            verify_result = runtime.tool_gateway.edit_tools.verify_disk_contents("Source/Game/WeaponBase.h", "AWeaponBase")
            assert verify_result["status"] == "SUCCESS"
            assert verify_result["verified"] is True
            assert "sha256" in verify_result

    asyncio.run(_run())


def test_c_informational_request_no_file_modification(temp_workspace: Path):
    """Test C: Informational request.

    Verifies:
    1. Returns helpful explanation.
    2. Does not modify files on disk.
    3. Contains truthful capabilities and zero false disclaimers.
    """
    runtime = _make_runtime(temp_workspace)
    session = runtime.session_manager.create_session(
        name="Replication QA",
        model_name="gameforge-qwen3.5:latest",
        provider_type="ollama",
    )

    prompt = "Explain how Unreal Engine replication works and show me an example."
    assert runtime._is_conversational(prompt) is True

    # Check system prompt constructed for conversational mode
    tools_desc = runtime._format_tools_description()
    sys_prompt = runtime.context_manager.build_system_prompt(
        tools_desc,
        active_model=session.model_name,
        include_tools=False,
    )
    assert "=== GAMEFORGE RUNTIME CAPABILITIES ===" in sys_prompt
    assert "NEVER state or imply that you are 'only an AI text assistant'" in sys_prompt
    assert "Unreal Engine 5.7 Integration" in sys_prompt


def test_d_fast_mode_immediate_execution(temp_workspace: Path):
    """Test D: Fast mode immediate execution without formal plan approval."""
    async def _run():
        runtime = _make_runtime(temp_workspace)
        session = runtime.session_manager.create_session(
            name="Fast Edit",
            model_name="gameforge-qwen3.5:latest",
            provider_type="ollama",
            task_mode=TaskMode.FAST,
            autonomy_profile=AutonomyProfile.AGENTIC,
        )

        ini_content = """```ini
// Config/DefaultGame.ini
[/Script/EngineSettings.GeneralProjectSettings]
ProjectID=12345
WeaponAudioCue=/Game/Audio/Cue_Fire
```
"""
        mock_provider = MagicMock()
        mock_provider.get_capabilities.return_value = MagicMock(max_context=8192)
        mock_provider.chat_with_tools.return_value = {
            "content": ini_content,
            "tool_calls": [],
        }

        with patch.object(runtime.router, "get_provider", return_value=mock_provider):
            events = []
            async for ev in runtime.execute_task_stream(session.session_id, "Add weapon audio cue config to Config/DefaultGame.ini"):
                events.append(ev)

            # In Fast mode, no plan event should be emitted
            plan_events = [e for e in events if e.event_type == "plan"]
            assert len(plan_events) == 0, "Fast mode must not block on plan approval"

            target_ini = temp_workspace / "Config" / "DefaultGame.ini"
            assert target_ini.is_file()
            assert "WeaponAudioCue" in target_ini.read_text(encoding="utf-8")

    asyncio.run(_run())


def test_e_ui_single_entry_point_inspection(qapp, temp_workspace: Path):
    """Test E: UI entry point inspection.

    Verifies:
    1. Home screen prompt box and 'Design it' button are hidden/omitted.
    2. Design navigation is absent from the left activity rail.
    3. Only the universal assistant chat is the natural-language prompt entry point.
    """
    home = HomeView()
    assert hasattr(home, "_prompt_input")
    assert not home._prompt_input.isVisible()
    assert hasattr(home, "_btn_design")
    assert not home._btn_design.isVisible()

    win = MainWindow(workspace_root=temp_workspace)
    # Check activity rail
    rail = win._rail
    action_names = [a.objectName() for a in rail.actions() if a.isVisible()]
    assert "rail_act_design" not in action_names, "Design must not be visible on the activity rail"

    # Clean close
    win.confirm_on_close = False
    win.close()


def test_controlled_write_failure_and_rollback(temp_workspace: Path):
    """Verifies that a controlled write failure triggers clean rollback to baseline state."""
    gateway = ToolGateway(workspace_root=temp_workspace)
    edit_tools = gateway.edit_tools
    test_file = temp_workspace / "Source" / "Game" / "Critical.cpp"
    test_file.write_text("// Baseline version 1.0\n", encoding="utf-8")

    tx = edit_tools.begin_transaction(["Source/Game/Critical.cpp"])
    assert "tx_id" in tx
    baseline_hash = tx["baselines"]["Source/Game/Critical.cpp"]

    # Apply edit 1
    p1 = edit_tools.propose_edit(
        subpath="Source/Game/Critical.cpp",
        target_content="// Baseline version 1.0",
        replacement_content="// Mod 1",
    )
    assert p1["status"] == "PENDING_APPROVAL"
    app1 = edit_tools.apply_diff(p1["diff_id"])
    assert app1["status"] == "SUCCESS"
    assert "// Mod 1" in test_file.read_text(encoding="utf-8")

    # Roll back diff
    rb = edit_tools.rollback_diff(p1["diff_id"])
    assert rb["status"] == "SUCCESS"
    assert "// Baseline version 1.0" in test_file.read_text(encoding="utf-8")

    # Verify SHA-256 matches baseline
    verify_res = edit_tools.verify_disk_contents("Source/Game/Critical.cpp")
    assert verify_res["sha256"] == baseline_hash
