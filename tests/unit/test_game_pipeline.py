"""Offline tests for the prompt -> game pipeline layers.

The live end-to-end run (real UBT build, editor, automation tests, packaging, packaged
self-test with screenshot) is recorded in E:\\GameForge\\projects\\TicTacToe\\Saved\\GameForge\\.
"""

import asyncio
import json
from pathlib import Path

import pytest

from src.gameforge_ide.backend.tools.game_tools import ApprovalStore, GameTools
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.pipeline.spec_from_prompt import (
    is_game_creation_request, match_prompt, refine_with_model)
from src.gameforge_ide.recipes.grid_board_game.recipe import GridBoardParams, generate
from src.gameforge_ide.unreal.toolchain import (
    UnrealToolchain, parse_automation_report, parse_build_diagnostics)


# ── spec ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "create a tic tac toe game in unreal engine",
    "Make me a Tic-Tac-Toe game",
    "build noughts and crosses",
])
def test_tictactoe_prompts_match(prompt):
    spec = match_prompt(prompt)
    assert spec.matched and spec.params.board_size == 3 and spec.params.win_length == 3
    assert spec.params.vs_ai and spec.params.ai_level == "perfect"
    assert any(a.startswith("packaged_selftest") for a in spec.acceptance)


def test_prompt_parameters_are_extracted():
    spec = match_prompt("make a 9x9 gomoku with 4 in a row called Stone Duel, two player, red and blue")
    p = spec.params
    assert (p.board_size, p.win_length, p.vs_ai) == (9, 4, False)
    assert p.display_title.startswith("Stone Duel") and p.project_name.startswith("StoneDuel")
    assert p.player1_color == (1.0, 0.22, 0.2) and p.player2_color == (0.1, 0.45, 1.0)


def test_unknown_game_is_not_faked():
    spec = match_prompt("create an open world RPG with dragons")
    assert not spec.matched
    assert "no installed recipe" in spec.reasons[0]


def test_creation_intent_detection():
    assert is_game_creation_request("create a tic tac toe game")
    assert not is_game_creation_request("what is a tic tac toe game?")


def test_model_refinement_is_validated():
    spec = match_prompt("create a tic tac toe game")
    bad = refine_with_model(spec, "x", lambda _p, _s: json.dumps({"display_title": "T", "board_size": 99,
                                                                  "win_length": 3, "vs_ai": True,
                                                                  "ai_level": "perfect"}))
    assert bad.params.board_size == 3 and any("rejected" in r for r in bad.reasons)
    good = refine_with_model(match_prompt("create a tic tac toe game"), "x",
                             lambda _p, _s: json.dumps({"display_title": "Mega Grid", "board_size": 6,
                                                        "win_length": 4, "vs_ai": False, "ai_level": "greedy"}))
    assert good.params.board_size == 6 and good.params.project_name == "MegaGrid"
    junk = refine_with_model(match_prompt("create a tic tac toe game"), "x", lambda _p, _s: "not json")
    assert junk.params.board_size == 3


# ── recipe ───────────────────────────────────────────────────────────────────

def test_recipe_renders_complete_module():
    files = generate(GridBoardParams(project_name="Demo", display_title="Demo Game"))
    names = {Path(k).name for k in files}
    assert {"GridRules.h", "GridRules.cpp", "GFBoard.cpp", "GFGameMode.cpp", "GFRulesTests.cpp", "GFConfig.h"} <= names
    assert all(k.startswith("Source/Demo/") for k in files)
    joined = "\n".join(files.values())
    assert "DEMO_API" in joined and "__API__" not in joined and "__NAME__" not in joined
    assert "GameForge.Demo.Rules.PerfectAIUnbeatable" in joined
    assert "bAutoManageActiveCameraTarget = false" in joined


@pytest.mark.parametrize("kwargs", [
    {"project_name": "bad name"}, {"board_size": 2}, {"win_length": 9}, {"ai_level": "godlike"},
    {"display_title": 'quote"injection'}, {"player1_color": (2, 0, 0)},
])
def test_recipe_rejects_invalid_params(kwargs):
    with pytest.raises(ValueError):
        GridBoardParams(**kwargs).validate()


def test_scaffold_writes_valid_project(tmp_path):
    tc = UnrealToolchain(Path(r"E:\UE\UE_5.7"))
    if not (tc.engine_root / "Engine" / "Build" / "Build.version").is_file():
        pytest.skip("engine not installed")
    info = tc.scaffold_cpp_project(tmp_path / "P", "Probe", default_map="/Game/Maps/M",
                                   game_mode="/Script/Probe.GFGameMode")
    up = json.loads((tmp_path / "P" / "Probe.uproject").read_text(encoding="utf-8"))
    assert up["Modules"][0]["Name"] == "Probe"
    ini = (tmp_path / "P" / "Config" / "DefaultEngine.ini").read_text(encoding="utf-8")
    assert "GlobalDefaultGameMode=/Script/Probe.GFGameMode" in ini
    assert "Source/Probe/Probe.Build.cs" in info["files"]
    with pytest.raises(ValueError):
        tc.scaffold_cpp_project(tmp_path / "Q", "1bad")


# ── parsers ──────────────────────────────────────────────────────────────────

def test_build_diagnostics_parser():
    log = "\n".join([
        r"E:\P\Source\P\A.cpp(12): error C2065: 'Foo': undeclared identifier",
        r"E:\P\Source\P\A.cpp(12): error C2065: 'Foo': undeclared identifier",
        r"E:\P\Source\P\B.h(3): warning C4996: deprecated",
        r"E:\P\Source\P\C.h(40): Error: Missing GENERATED_BODY",
        r"Module.P.cpp.obj : error LNK2019: unresolved external symbol X",
        "ERROR: UnrealBuildTool failed",
        "noise line",
    ])
    d = parse_build_diagnostics(log)
    assert [x.code for x in d] == ["C2065", "C4996", "UHT", "LNK2019", "UBT"]
    assert d[0].line == 12 and d[0].file.endswith("A.cpp") and d[1].severity == "warning"


def test_automation_report_parser(tmp_path):
    rep = {"succeeded": 1, "failed": 1, "notRun": 0, "tests": [
        {"fullTestPath": "GameForge.X.A", "state": "Success", "entries": []},
        {"fullTestPath": "GameForge.X.B", "state": "Fail",
         "entries": [{"event": {"type": "Error", "message": "expected 3"}}]}]}
    (tmp_path / "index.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(rep).encode())
    r = parse_automation_report(tmp_path)
    assert r["found"] and r["failed"] == 1 and r["tests"][1]["errors"] == ["expected 3"]
    assert parse_automation_report(tmp_path / "missing")["found"] is False


# ── approvals and gateway ────────────────────────────────────────────────────

def test_approval_store_transitions_are_one_way(tmp_path):
    store = ApprovalStore(tmp_path)
    rec = store.create("create_game", {"params": {}}, "s", "c")
    assert [r["approval_id"] for r in store.list_pending()] == [rec["approval_id"]]
    assert store.transition(rec["approval_id"], "DONE") is None          # cannot skip APPROVED
    assert store.transition(rec["approval_id"], "APPROVED")["status"] == "APPROVED"
    assert store.transition(rec["approval_id"], "APPROVED") is None      # double click applies once
    assert store.transition(rec["approval_id"], "DONE")["status"] == "DONE"
    assert store.list_pending() == []


def test_gateway_gates_heavy_tools_but_not_readbacks(tmp_path):
    gw = ToolGateway(tmp_path)
    for tool, args in [("create_game", {"params": {}}), ("unreal_package", {"uproject": "x"}),
                       ("unreal_editor", {"uproject": "x", "op": "spawn_actor"}), ("play_game", {"exe": "x"})]:
        assert gw.execute_tool(tool, args)["status"] == "PENDING_APPROVAL", tool
    # read-back op is T0: no approval needed (fails only because the project does not exist)
    assert gw.execute_tool("unreal_editor", {"uproject": str(tmp_path / "none.uproject"), "op": "actors_in_level"})["status"] == "ERROR"


def test_play_game_refuses_executables_outside_projects_root(tmp_path):
    gt = GameTools(tmp_path, projects_root=tmp_path / "Games")
    evil = tmp_path / "evil.exe"
    evil.write_bytes(b"MZ")
    assert gt.play_game(str(evil))["status"] == "BLOCKED"


def test_runtime_fast_path_suspends_for_approval(tmp_path):
    from src.gameforge_ide.backend.agent.runtime import AgentRuntime
    from src.gameforge_ide.backend.providers.router import ModelRouter
    from src.gameforge_ide.backend.session_manager import SessionManager

    sm = SessionManager(tmp_path)
    rt = AgentRuntime(tmp_path, sm, ModelRouter())
    sid = sm.create_session(name="t", model_name="none", provider_type="ollama").session_id

    async def collect():
        return [e async for e in rt.execute_task_stream(sid, "create a tic tac toe game in unreal engine")]

    events = asyncio.run(collect())
    waiting = [e for e in events if e.event_type == "status" and e.content == "WAITING_APPROVAL"]
    assert waiting and waiting[0].metadata["approval"]["tool"] == "create_game"
    assert events[-1].event_type == "done"
    pending = ApprovalStore(tmp_path).list_pending()
    assert len(pending) == 1 and pending[0]["args"]["params"]["project_name"] == "TicTacToe"


# ── cancellation ─────────────────────────────────────────────────────────────

def test_cancel_kills_the_whole_process_tree(tmp_path):
    import sys
    import threading
    import psutil
    tc = UnrealToolchain(tmp_path)
    tc.cancel_event = threading.Event()
    # parent spawns a grandchild; both must die on cancel
    script = ("import subprocess,sys,time;"
              "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);time.sleep(60)")
    threading.Timer(1.5, tc.cancel_event.set).start()
    before = {p.pid for p in psutil.process_iter()}
    res = tc._run("probe", [sys.executable, "-c", script], tmp_path / "probe.log", timeout_s=60)
    assert not res.ok and res.errors == ["CANCELLED"] and res.duration_s < 10
    leaked = [p for p in psutil.process_iter(["cmdline"])
              if p.pid not in before and "time.sleep(60)" in " ".join(p.info.get("cmdline") or [])]
    assert leaked == []


def test_pipeline_honours_cancel_before_any_work(tmp_path):
    import threading
    from src.gameforge_ide.pipeline.game_pipeline import GamePipeline
    ev = threading.Event()
    ev.set()
    res = GamePipeline(tmp_path, cancel_event=ev).run(GridBoardParams(project_name="Never"))
    assert not res.ok and res.failed_stage == "spec"
    assert res.stages[0].errors == ["CANCELLED by user"]
    assert not (tmp_path / "Never" / "Never.uproject").exists()


@pytest.mark.parametrize("prompt,expected", [
    ("Create a new Unreal project at GameForgeProject/GameForgeProject.uproject", False),
    ("Create Source/GameMode.cpp", False),
    ("create a GameMode class for my game", False),
    ("add a health bar to the game", False),
    ("create a game mode", False),
    ("what is a game loop", False),
    ("create a tic tac toe game in unreal engine", True),
    ("make me a racing game", True),
    ("build noughts and crosses", True),
    ("create a whack-a-mole game", True),
    ("i want you to make a simple 2d platformer game with coins", True),
])
def test_game_creation_intent_is_not_hijacking_code_tasks(prompt, expected):
    assert is_game_creation_request(prompt) is expected


def test_idle_editors_are_closed_after_timeout(tmp_path):
    gt = GameTools(tmp_path, projects_root=tmp_path / "Games")
    now = [1000.0]
    gt._clock = lambda: now[0]
    stopped = []

    class FakeLink:
        def stop(self):
            stopped.append(True)
            return 0

    gt._links["p"] = FakeLink()
    gt._last_used["p"] = now[0]
    assert gt.close_idle_editors() == [] and not stopped
    now[0] += gt.editor_idle_timeout_s + 1
    assert gt.close_idle_editors() == ["p"] and stopped == [True] and gt._links == {}


def test_game_flags_expand_to_spec():
    from src.gameforge_ide.pipeline.spec_from_prompt import expand_game_flags
    idea = expand_game_flags('gomoku --size 9 --win 4 --hotseat --title "Stone Duel"')
    spec = match_prompt("create a " + idea)
    p = spec.params
    assert (p.board_size, p.win_length, p.vs_ai, p.display_title) == (9, 4, False, "Stone Duel")
    g = match_prompt("create a " + expand_game_flags("four in a row --gravity --ai easy")).params
    assert g.gravity and g.ai_level == "random"


def test_procedural_world_prompts_match():
    from src.gameforge_ide.recipes.procedural_world.recipe import ProceduralWorldParams
    spec = match_prompt("create a procedural landscape valley environment with a spline trail and ancient ruins called GFProceduralWorld")
    assert spec.matched and spec.recipe_id == "procedural_world"
    assert isinstance(spec.params, ProceduralWorldParams)
    assert spec.params.terrain_type == "Valley"
    assert spec.params.landmark_type == "Ruins"
    assert spec.params.project_name == "GFProceduralWorld"
    assert any("GF_PROCEDURAL_SELFTEST PASS" in a for a in spec.acceptance)


def test_procedural_world_params_validation():
    from src.gameforge_ide.recipes.procedural_world.recipe import ProceduralWorldParams
    p = ProceduralWorldParams(project_name="ValidWorld", elevation_scale=2500.0, road_width=400.0, foliage_density=50)
    p.validate()

    bad_elev = ProceduralWorldParams(elevation_scale=50.0)
    with pytest.raises(ValueError, match="elevation_scale"):
        bad_elev.validate()

    bad_terrain = ProceduralWorldParams(terrain_type="Swamp")
    with pytest.raises(ValueError, match="terrain_type"):
        bad_terrain.validate()


def test_procedural_world_sources_render():
    from src.gameforge_ide.recipes.procedural_world.recipe import ProceduralWorldParams, generate
    p = ProceduralWorldParams(project_name="GFWorldProbe", terrain_type="Mountains", elevation_scale=2200.0)
    files = generate(p)
    expected = [
        "Source/GFWorldProbe/GFProceduralConfig.h",
        "Source/GFWorldProbe/GFProceduralLandmark.h",
        "Source/GFWorldProbe/GFProceduralLandmark.cpp",
        "Source/GFWorldProbe/GFProceduralCharacter.h",
        "Source/GFWorldProbe/GFProceduralCharacter.cpp",
        "Source/GFWorldProbe/GFProceduralHUD.h",
        "Source/GFWorldProbe/GFProceduralHUD.cpp",
        "Source/GFWorldProbe/GFProceduralGameMode.h",
        "Source/GFWorldProbe/GFProceduralGameMode.cpp",
        "Source/GFWorldProbe/GFProceduralTests.cpp",
    ]
    for exp in expected:
        assert exp in files, f"Missing {exp} in generated sources"
        assert len(files[exp]) > 100
    assert "Mountains" in files["Source/GFWorldProbe/GFProceduralConfig.h"]
    assert "GFWorldProbe" in files["Source/GFWorldProbe/GFProceduralHUD.cpp"]

