"""Unit tests for IDE-wide scenario map resolution, cooking sync, and execution."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.gameforge_ide.forge.executor import StepContext
from src.gameforge_ide.forge.handlers.legacy_stages import (
    _sync_project_map_settings,
    legacy_package,
    legacy_scaffold,
)
from src.gameforge_ide.forge.handlers.scenario import scenario_handler
from src.gameforge_ide.forge.model import StepKind, StepSpec, StepStatus
from src.gameforge_ide.qa.runner import run_packaged
from src.gameforge_ide.qa.scenario import Scenario, WaitStep, WaitArgs


def test_sync_project_map_settings(tmp_path: Path):
    pdir = tmp_path / "TestGame"
    config_dir = pdir / "Config"
    config_dir.mkdir(parents=True)
    eng_ini = config_dir / "DefaultEngine.ini"
    eng_ini.write_text(
        "[/Script/EngineSettings.GameMapsSettings]\n"
        "GameDefaultMap=/Game/Maps/OldStaleMap\n"
        "EditorStartupMap=/Game/Maps/OldStaleMap\n",
        encoding="utf-8",
    )

    _sync_project_map_settings(pdir, "/Game/Maps/Level_1")

    eng_text = eng_ini.read_text(encoding="utf-8")
    assert "GameDefaultMap=/Game/Maps/Level_1" in eng_text
    assert "EditorStartupMap=/Game/Maps/Level_1" in eng_text

    game_ini = config_dir / "DefaultGame.ini"
    assert game_ini.is_file()
    game_text = game_ini.read_text(encoding="utf-8")
    assert '+DirectoriesToAlwaysCook=(Path="/Game/Maps")' in game_text


def test_legacy_package_auto_heals_stale_map(tmp_path: Path):
    pdir = tmp_path / "MyShooter"
    pdir.mkdir(parents=True)
    (pdir / "MyShooter.uproject").write_text("{}", encoding="utf-8")

    # Create Level_1.umap on disk, but DefaultEngine.ini points to MyShooterMap
    maps_dir = pdir / "Content" / "Maps"
    maps_dir.mkdir(parents=True)
    (maps_dir / "Level_1.umap").touch()

    config_dir = pdir / "Config"
    config_dir.mkdir()
    eng_ini = config_dir / "DefaultEngine.ini"
    eng_ini.write_text(
        "[/Script/EngineSettings.GameMapsSettings]\n"
        "GameDefaultMap=/Game/Maps/MyShooterMap\n"
        "EditorStartupMap=/Game/Maps/MyShooterMap\n",
        encoding="utf-8",
    )

    # Create a real (non-empty) fake exe so validate_stage_output("package") passes
    fake_exe = tmp_path / "fake.exe"
    fake_exe.write_bytes(b"\x4d\x5a")  # Minimal PE header marker (non-empty)

    ctx = MagicMock()
    ctx.project_dir = pdir
    ctx.workspace_dir = tmp_path
    ctx.step = StepSpec(step_id="package", kind=StepKind.PACKAGE, title="Package", inputs={"project_name": "MyShooter"})
    ctx.shared = {}
    ctx.log = MagicMock()

    with patch("src.gameforge_ide.pipeline.stages.package", return_value=(True, {"exe": str(fake_exe)}, [])):
        res = legacy_package(ctx)

    assert res.ok is True
    eng_text = eng_ini.read_text(encoding="utf-8")
    assert "GameDefaultMap=/Game/Maps/Level_1" in eng_text


def test_run_packaged_with_map_path(tmp_path: Path):
    scenario = Scenario(
        scenario_id="smoke_map_test",
        steps=[WaitStep(wait_s=WaitArgs(seconds=1.0))],
    )
    fake_exe = tmp_path / "Game.exe"
    fake_exe.touch()
    out_dir = tmp_path / "out"

    captured_argv = []

    def fake_spawn(argv, **kwargs):
        captured_argv.extend(argv)
        class FakeProc:
            returncode = 0
            def wait(self, timeout=None):
                result_path = out_dir / "smoke_map_test_result.json"
                result_path.write_text(json.dumps({
                    "schema": "scenario_result/1",
                    "scenario_id": "smoke_map_test",
                    "passed": True,
                    "duration_s": 1.0,
                    "steps": [],
                    "legs": [],
                    "expect": [],
                    "failures": [],
                }), encoding="utf-8")
                return 0
        return FakeProc()

    with patch("src.gameforge_ide.qa.runner.jobs.spawn", side_effect=fake_spawn):
        res = run_packaged(fake_exe, scenario, out_dir=out_dir, map_path="/Game/Maps/Level_1")

    assert res.passed is True
    assert any("/Game/Maps/Level_1" in arg for arg in captured_argv)
    assert not any("?game=" in arg for arg in captured_argv), "No ?game= override allowed in packaged argv"
    assert Path(captured_argv[0]) == fake_exe.resolve()
    assert any(arg.startswith("-GFScenario=") for arg in captured_argv)
    assert any(arg.startswith("-GFScenarioOut=") for arg in captured_argv)
    assert any(arg.startswith("-GFEventsOut=") for arg in captured_argv)


def test_scenario_handler_resolves_and_forwards_map(tmp_path: Path):
    pdir = tmp_path / "MyAdventure"
    pdir.mkdir(parents=True)
    fake_exe = pdir / "Packaged" / "Windows" / "MyAdventure.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()

    # Create Level_1.umap
    maps_dir = pdir / "Content" / "Maps"
    maps_dir.mkdir(parents=True)
    (maps_dir / "Level_1.umap").touch()

    ctx = MagicMock()
    ctx.project_dir = pdir
    ctx.workspace_dir = tmp_path
    ctx.step = StepSpec(step_id="scenarios", kind=StepKind.SCENARIO, title="Scenarios", inputs={"configuration": "Development"})
    ctx.shared = {}
    ctx.cancel = MagicMock()
    ctx.cancel.is_set.return_value = False

    captured_kwargs = {}

    def fake_run_packaged(exe, sc, **kwargs):
        captured_kwargs.update(kwargs)
        from src.gameforge_ide.qa.scenario import ScenarioResult
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=sc.scenario_id,
            passed=True,
            duration_s=0.5,
            steps=[],
            legs=[],
            expect=[],
            failures=[],
        )

    with patch("src.gameforge_ide.forge.handlers.scenario.run_packaged", side_effect=fake_run_packaged):
        outcome = scenario_handler(ctx)

    assert outcome.ok is True
    assert captured_kwargs.get("map_path") == "/Game/Maps/Level_1"


def test_run_editor_game_argv_distinct_and_no_game_override(tmp_path: Path):
    from src.gameforge_ide.qa.runner import run_editor_game
    uproject = tmp_path / "MyEditorGame" / "MyEditorGame.uproject"
    uproject.parent.mkdir(parents=True)
    uproject.touch()

    scenario = Scenario(
        scenario_id="editor_argv_test",
        steps=[WaitStep(wait_s=WaitArgs(seconds=1.0))],
    )
    out_dir = tmp_path / "out_editor"

    captured_argv = []

    def fake_spawn(argv, **kwargs):
        captured_argv.extend(argv)
        class FakeProc:
            returncode = 0
            def wait(self, timeout=None):
                result_path = out_dir / "editor_argv_test_result.json"
                result_path.write_text(json.dumps({
                    "schema": "scenario_result/1",
                    "scenario_id": "editor_argv_test",
                    "passed": True,
                    "duration_s": 1.0,
                    "steps": [],
                    "legs": [],
                    "expect": [],
                    "failures": [],
                }), encoding="utf-8")
                return 0
        return FakeProc()

    fake_editor = tmp_path / "UnrealEditor.exe"
    fake_editor.touch()

    with patch("src.gameforge_ide.qa.runner.UnrealToolchain") as mock_tc_cls:
        mock_tc = MagicMock()
        mock_tc.engine_root = tmp_path
        mock_tc.editor_cmd = fake_editor
        mock_tc_cls.return_value = mock_tc

        with patch("src.gameforge_ide.qa.runner.jobs.spawn", side_effect=fake_spawn):
            res = run_editor_game(
                uproject,
                scenario,
                out_dir=out_dir,
                map_path="/Game/Maps/Level_1?game=/Script/GameForgeRuntime.GameForgeGameMode",
            )

    assert res.passed is True
    # Confirm no ?game= option remains
    assert not any("?game=" in arg for arg in captured_argv), "No ?game= override allowed in editor argv"
    # Confirm editor argv structure: [editor_exe, uproject, clean_map, -game, ...]
    assert Path(captured_argv[1]) == uproject.resolve()
    assert captured_argv[2] == "/Game/Maps/Level_1"
    assert "-game" in captured_argv
    assert any(arg.startswith("-GFScenario=") for arg in captured_argv)
    assert any(arg.startswith("-GFScenarioOut=") for arg in captured_argv)
    assert any(arg.startswith("-GFEventsOut=") for arg in captured_argv)


def test_scenario_handler_fails_on_mandatory_scenario_gap(tmp_path: Path):
    from src.gameforge_ide.qa.generate import ScenarioGap

    pdir = tmp_path / "GapGame"
    pdir.mkdir(parents=True)
    fake_exe = pdir / "Packaged" / "Windows" / "GapGame.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()

    ctx = MagicMock()
    ctx.project_dir = pdir
    ctx.workspace_dir = tmp_path
    ctx.step = StepSpec(step_id="scenarios", kind=StepKind.SCENARIO, title="Scenarios", inputs={"configuration": "Development"})
    ctx.shared = {}
    ctx.cancel = MagicMock()
    ctx.cancel.is_set.return_value = False

    fake_gds = MagicMock()
    ref = MagicMock()
    ref.scenario_id = "test_gap_scenario"
    ref.must_pass = True
    fake_gds.acceptance.scenarios = [ref]

    mock_gap = ScenarioGap(scenario_id="test_gap_scenario", reason="Missing target actor in manifest")

    with patch("src.gameforge_ide.forge.handlers.scenario.generate", return_value=([], [mock_gap])):
        ctx.step.inputs["gds"] = fake_gds
        outcome = scenario_handler(ctx)

    assert outcome.ok is False
    assert any("test_gap_scenario" in err for err in outcome.errors)
    assert any("scenario gaps" in err.lower() for err in outcome.errors)


def test_scenario_gen_handler_preserves_gaps(tmp_path: Path):
    from src.gameforge_ide.forge.handlers.scenario import scenario_gen_handler
    from src.gameforge_ide.qa.generate import ScenarioGap

    pdir = tmp_path / "GenGame"
    pdir.mkdir(parents=True)

    ctx = MagicMock()
    ctx.project_dir = pdir
    ctx.workspace_dir = tmp_path
    ctx.step = StepSpec(step_id="scenario_gen", kind=StepKind.SCENARIO, title="Scenario Gen", inputs={})
    ctx.shared = {}
    ctx.cancel = MagicMock()
    ctx.cancel.is_set.return_value = False

    fake_gds = MagicMock()
    mock_gap = ScenarioGap(scenario_id="gap_sc", reason="No quest giver found")

    with patch("src.gameforge_ide.forge.handlers.scenario.generate", return_value=([], [mock_gap])):
        with patch("src.gameforge_ide.qa.game_spec_tests.generate_acceptance_tests", return_value=[]):
            ctx.step.inputs["gds"] = fake_gds
            outcome = scenario_gen_handler(ctx)

    assert outcome.ok is True
    assert "gaps" in outcome.data
    assert len(outcome.data["gaps"]) == 1
    assert outcome.data["gaps"][0]["scenario_id"] == "gap_sc"
    assert outcome.data["gaps"][0]["reason"] == "No quest giver found"
