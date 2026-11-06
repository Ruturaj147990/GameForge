"""Regression test for autonomous game completion from prompt and clean chat interaction."""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from src.gameforge_ide.pipeline.spec_from_prompt import is_game_creation_request
from src.gameforge_ide.design.presets import get_preset_spec
from src.gameforge_ide.design.store import save as save_gds, load as load_gds
from src.gameforge_ide.design.patch import propose_patch, apply_patch
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.tools.fs_tools import tool_list_dir
from src.gameforge_ide.backend.security.boundary import BoundaryManager


def test_is_game_creation_request_expansions():
    """Verify game completion and expand prompts are recognized."""
    assert is_game_creation_request("Complete the counterstrike lite game , only a box is present right now.")
    assert is_game_creation_request("Finish the game and add enemies")
    assert is_game_creation_request("Build out the shooter game with weapons and score")
    assert is_game_creation_request("Create a 3d platformer with 5 coins")


def test_propose_patch_completes_game(tmp_path):
    """Verify propose_patch completes an empty game with combat bots, weapons, and arena layout."""
    spec = get_preset_spec("platformer")
    spec.meta.project_name = "CounterStrikeLite"
    save_gds(tmp_path, spec)

    prop = propose_patch(spec, "Complete the counterstrike lite game , only a box is present right now.")
    assert prop.status == "OK"
    assert len(prop.ops) > 0
    assert "spawner" in prop.summary.lower()

    updated = apply_patch(spec, prop.ops)
    assert any(e.kind.value == "spawner" for e in updated.entities)
    player = next(e for e in updated.entities if e.kind.value == "player")
    assert player.props.get("attack_mode") == "projectile"
    assert updated.scene.levels[0].layout.value == "arena"


def test_agent_runtime_routes_active_project_completion(tmp_path):
    """Verify AgentRuntime yields open_design card mapped to active project."""
    spec = get_preset_spec("platformer")
    spec.meta.project_name = "CounterStrikeLite"
    save_gds(tmp_path, spec)

    sm = SessionManager(tmp_path)
    router = ModelRouter()
    runtime = AgentRuntime(tmp_path, sm, router, studio_mode=True)
    sid = sm.create_session("t", "none", "ollama").session_id

    async def collect():
        return [e async for e in runtime.execute_task_stream(sid, "Complete the counterstrike lite game , only a box is present right now.")]

    events = asyncio.run(collect())
    ready = [e for e in events if e.event_type == "status" and e.content == "READY"]
    assert ready, "Expected READY status event"
    card = ready[0].metadata.get("card", {})
    assert card.get("type") == "open_design"
    assert card.get("mode") == "change"


def test_fs_tools_handles_redundant_project_prefix(tmp_path):
    """Verify tool_list_dir handles subpaths prefixed with project name."""
    proj_dir = tmp_path / "MyProject"
    content_dir = proj_dir / "Content"
    content_dir.mkdir(parents=True)
    (content_dir / "Test.txt").write_text("hello", encoding="utf-8")

    boundary = BoundaryManager(proj_dir)
    res = tool_list_dir(boundary, subpath="MyProject/Content")
    assert res.get("status") == "SUCCESS"
    assert res.get("count", 0) > 0

def test_conversational_questions_not_routed_to_open_design():
    """Verify informational and meta-questions are treated as conversational, not routed to design."""
    assert AgentRuntime._is_conversational("what does the chat even actually do")
    assert AgentRuntime._is_conversational("the gameforge chat always just sends all of the prompts to build design, what does the chat even actually do")
    assert AgentRuntime._is_conversational("how do weapon sockets work in Unreal Engine?")
    assert AgentRuntime._is_conversational("can you explain GAS abilities?")


def test_propose_patch_weapons_arsenal(tmp_path):
    """Verify propose_patch adds pistol, rifle, and knife to player props when requested."""
    spec = get_preset_spec("arena_combat")
    spec.meta.project_name = "TeamArena"
    save_gds(tmp_path, spec)

    prop = propose_patch(spec, "Complete the game , each player can have 1 pistol, 1 rifle, and a knife")
    assert prop.status == "OK"
    updated = apply_patch(spec, prop.ops)
    player = next(e for e in updated.entities if e.kind.value == "player")
    assert "weapons" in player.props
    assert player.props["weapons"] == ["pistol", "rifle", "knife"]

def test_cpp_source_code_requests_not_routed_to_open_design(tmp_path):
    """Verify direct C++ code requests bypass studio open_design routing."""
    spec = get_preset_spec("arena_combat")
    spec.meta.project_name = "TeamArena"
    save_gds(tmp_path, spec)

    sm = SessionManager(tmp_path)
    router = ModelRouter()
    runtime = AgentRuntime(tmp_path, sm, router, studio_mode=True)
    sid = sm.create_session("t", "none", "ollama").session_id

    async def collect():
        return [e async for e in runtime.execute_task_stream(sid, "Write a C++ class for a weapon in Source/TeamArena/Weapon_Pistol.h")]

    events = asyncio.run(collect())
    open_design_events = [
        e for e in events
        if e.event_type == "status" and e.metadata.get("card", {}).get("type") == "open_design"
    ]
    assert len(open_design_events) == 0, "Direct C++ code requests must not be routed to open_design"


def test_project_status_inquiries_not_treated_as_game_creation():
    """Verify inquiries about game/project completion or status are not misclassified as game creation."""
    inquiries = [
        "Is the sudoku game complete",
        "Is the platformer complete?",
        "Status of the sudoku game",
        "Check if the game is ready",
        "How is the game progress",
        "Did the package build succeed",
        "Are the levels complete",
    ]
    for prompt in inquiries:
        assert not is_game_creation_request(prompt), f"'{prompt}' must NOT be classified as a game creation request"

    # In contrast, actual creation commands must remain classified as creation requests:
    creations = [
        "Create me a Sudoku game.",
        "Complete the counterstrike lite game , only a box is present right now.",
        "Finish the game and add enemies",
        "Build out the shooter game with weapons and score",
    ]
    for prompt in creations:
        assert is_game_creation_request(prompt), f"'{prompt}' must be classified as a game creation request"


def test_narrative_promise_interception():
    """Verify narrative promises to check files without tool execution are detected."""
    assert AgentRuntime._is_narrative_promise("Let me check the project files.")
    assert AgentRuntime._is_narrative_promise("I will inspect the workspace structure.")
    assert AgentRuntime._is_narrative_promise("Let me search for Sudoku-related files in the workspace.")
    assert AgentRuntime._is_narrative_promise("Checking the project files now.")
    assert not AgentRuntime._is_narrative_promise("The game is complete and has 5 levels.")
    assert not AgentRuntime._is_narrative_promise("No Sudoku project was found in the workspace.")


def test_is_conversational_project_queries_have_tools():
    """Verify project queries preserve tools rather than being treated as pure conversational chit-chat."""
    assert not AgentRuntime._is_conversational("Is the sudoku game complete")
    assert not AgentRuntime._is_conversational("What is the status of the project files")
    assert not AgentRuntime._is_conversational("Check if the game compiles without errors")
    # Pure conversational prompts without project terms remain conversational:
    assert AgentRuntime._is_conversational("Hello there!")
    assert AgentRuntime._is_conversational("Thanks!")
