from pathlib import Path
import pytest

from src.gameforge_ide.forge.handlers import HANDLERS
from src.gameforge_ide.forge.legacy_adapter import plan_legacy, run_state_to_pipeline_result
from src.gameforge_ide.forge.model import StepKind, StepStatus
from src.gameforge_ide.pipeline.game_pipeline import GamePipeline
from tests.fixtures.legacy_recipes.grid_board_game.recipe import GridBoardParams


def test_plan_legacy_steps_and_dag(tmp_path: Path):
    params = GridBoardParams(project_name="TestGame", board_size=3)
    run_full = plan_legacy(params, projects_root=tmp_path, skip_package=False)
    assert len(run_full.steps) == 8
    ids = [s.step_id for s in run_full.steps]
    assert ids == [
        "spec",
        "scaffold",
        "sources",
        "build_editor",
        "assemble_level",
        "automation_tests",
        "package",
        "packaged_smoke",
    ]

    # Topological order matches linear chain
    assert [s.step_id for s in run_full.topo_order()] == ids

    # Check skip_package=True
    run_short = plan_legacy(params, projects_root=tmp_path, skip_package=True)
    assert len(run_short.steps) == 6
    assert [s.step_id for s in run_short.steps] == [
        "spec",
        "scaffold",
        "sources",
        "build_editor",
        "assemble_level",
        "automation_tests",
    ]


def _make_valid_stage_outcome(ctx, name: str):
    from src.gameforge_ide.forge.executor import StepOutcome
    pdir = Path(ctx.project_dir)
    pdir.mkdir(parents=True, exist_ok=True)
    if name == "spec":
        return StepOutcome(True, data={"recipe": "grid_board", "params": {"genre": "grid_board", "pitch": "Grid game pitch"}})
    elif name == "scaffold":
        uproj = pdir / f"{pdir.name}.uproject"
        uproj.write_text("{}", encoding="utf-8")
        (pdir / "Config").mkdir(parents=True, exist_ok=True)
        (pdir / "Config" / "DefaultGame.ini").write_text("[/Script/UnrealEd.ProjectPackagingSettings]\n+DirectoriesToAlwaysCook=(Path=\"/Game/Maps\")\n", encoding="utf-8")
        return StepOutcome(True, data={"uproject": str(uproj), "project_name": pdir.name})
    elif name == "sources":
        f = (pdir / "Source" / f"{pdir.name}" / "Main.cpp").resolve()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("// C++", encoding="utf-8")
        return StepOutcome(True, data={"files": [str(f)]})
    elif name == "build_editor":
        return StepOutcome(True, data={"exit_code": 0, "errors": 0})
    elif name == "assemble_level":
        return StepOutcome(True, data={
            "read_back_actors": [
                {"label": "PlayerStart_1", "class": "PlayerStart"},
                {"label": "GridBoard_1", "class": "GameForgeGridBoard"},
                {"label": "GoalTrigger_1", "class": "GameForgeGoal"},
            ]
        })
    elif name == "automation_tests":
        return StepOutcome(True, data={"tests": [{"name": "GameForge.Kit.Smoke", "state": "Success", "passed": True}]})
    elif name == "package":
        exe = pdir / "Packaged" / "Windows" / f"{pdir.name}.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("MZ", encoding="utf-8")
        return StepOutcome(True, data={"exe": str(exe)})
    elif name == "packaged_smoke":
        return StepOutcome(True, data={"results": [{"test_id": "game_spec_acceptance_grid", "passed": True}]})
    return StepOutcome(True, data={"ok": True})


def test_pipeline_run_with_fake_handlers(tmp_path: Path, monkeypatch):
    calls = []

    def make_fake_handler(name: str):
        def fn(ctx):
            calls.append(name)
            return _make_valid_stage_outcome(ctx, name)
        return fn

    for stage in [
        "spec",
        "scaffold",
        "sources",
        "build_editor",
        "assemble_level",
        "automation_tests",
        "package",
        "packaged_smoke",
    ]:
        monkeypatch.setitem(HANDLERS, stage, make_fake_handler(stage))

    events = []
    pipe = GamePipeline(
        projects_root=tmp_path,
        on_event=lambda k, d: events.append((k, d)),
    )

    params = GridBoardParams(project_name="GridGame")
    res = pipe.run(params)

    assert res.ok is True
    assert res.failed_stage is None
    assert len(res.stages) == 8
    assert calls == [
        "spec",
        "scaffold",
        "sources",
        "build_editor",
        "assemble_level",
        "automation_tests",
        "package",
        "packaged_smoke",
    ]

    # Verify event stream
    event_kinds = [k for k, _ in events]
    assert event_kinds.count("stage_started") == 8
    assert event_kinds.count("stage_finished") == 8
    assert event_kinds[-1] == "pipeline_finished"

    # Report files were created
    pdir = tmp_path / "GridGame"
    rep_json = pdir / "Saved" / "GameForge" / "pipeline_report.json"
    rep_md = pdir / "Saved" / "GameForge" / "pipeline_report.md"
    assert rep_json.is_file()
    assert rep_md.is_file()


def test_pipeline_resume_skips_done_steps(tmp_path: Path, monkeypatch):
    from src.gameforge_ide.forge.model import StepStatus

    counts = {}

    def make_counting_handler(name: str):
        def fn(ctx):
            counts[name] = counts.get(name, 0) + 1
            return _make_valid_stage_outcome(ctx, name)
        return fn

    for stage in [
        "spec",
        "scaffold",
        "sources",
        "build_editor",
        "assemble_level",
        "automation_tests",
        "package",
        "packaged_smoke",
    ]:
        monkeypatch.setitem(HANDLERS, stage, make_counting_handler(stage))

    pipe = GamePipeline(projects_root=tmp_path)
    params = GridBoardParams(project_name="ResumeGame")

    # Run up to build_editor
    res1 = pipe.run(params, stop_after="build_editor")
    assert res1.ok is True
    assert res1.failed_stage is None  # stopped early, remaining skipped

    # Verify 4 ran and 4 were skipped
    assert counts == {
        "spec": 1,
        "scaffold": 1,
        "sources": 1,
        "build_editor": 1,
    }

    # Now resume the pipeline
    pdir = tmp_path / "ResumeGame"
    res2 = GamePipeline.resume(pdir, projects_root=tmp_path)

    assert res2.ok is True
    # The first 4 steps should NOT run again (they were DONE)
    assert counts["spec"] == 1
    assert counts["scaffold"] == 1
    assert counts["sources"] == 1
    assert counts["build_editor"] == 1
    # The remaining steps ran to completion
    assert counts["assemble_level"] == 1
    assert counts["automation_tests"] == 1
    assert counts["package"] == 1
    assert counts["packaged_smoke"] == 1
