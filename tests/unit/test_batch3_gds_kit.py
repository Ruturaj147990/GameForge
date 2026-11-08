"""Unit tests for Batch 3: Prompt intelligence, Kit evaluator, RuntimeDef, Composer contracts, and Forge legacy adapter."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from unittest.mock import MagicMock

import pytest

from src.gameforge_ide.design.draft import DesignDraft, DraftWin, DraftLose
from src.gameforge_ide.design.gds import (
    CameraKind,
    CustomCode,
    EntityKind,
    EntitySpec,
    EventRef,
    GameDesignSpec,
    Genre,
    Placement,
    RuleSpec,
)
from src.gameforge_ide.design.presets import preset_platformer, preset_tic_tac_toe
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
from src.gameforge_ide.pipeline.spec_from_prompt import match_prompt, is_game_creation_request
from src.gameforge_ide.kit.evaluator import ConditionEvaluator, EvaluationContext
from src.gameforge_ide.kit.runtime_def import build_runtime_def, validate_runtime_def
from src.gameforge_ide.composer import compose, composition_to_run_spec
from src.gameforge_ide.composer.model import CodegenTask
from src.gameforge_ide.forge.executor import StepContext, StepOutcome
from src.gameforge_ide.forge.model import RunSpec, StepKind, StepRecord, StepSpec
from src.gameforge_ide.forge.handlers.legacy_stages import legacy_assemble, legacy_scaffold, legacy_sources, RECIPE_IMPL
from src.gameforge_ide.backend.tools.game_tools import GameTools


# ── 1. Prompt Intelligence & Presets ──────────────────────────────────────────

def test_explicit_preset_syntax_in_prompt_to_gds():
    """Verify that explicit preset:<id> routes directly to preset even with model allowed."""
    mock_complete = MagicMock()
    res1 = prompt_to_gds("preset:platformer", complete_json=mock_complete, allow_model=True)
    assert res1.status == "OK"
    assert res1.path == "preset"
    assert res1.gds is not None
    assert res1.gds.overview.genre == Genre.PLATFORMER
    mock_complete.assert_not_called()

    res2 = prompt_to_gds("preset:tic_tac_toe", complete_json=mock_complete, allow_model=True)
    assert res2.status == "OK"
    assert res2.path == "preset"
    assert res2.gds is not None
    assert res2.gds.overview.genre == Genre.GRID_BOARD
    mock_complete.assert_not_called()


def test_explicit_preset_syntax_in_spec_from_prompt():
    """Verify is_game_creation_request and match_prompt recognise explicit presets."""
    assert is_game_creation_request("preset:tic_tac_toe") is True
    assert is_game_creation_request("preset:platformer") is True
    assert is_game_creation_request("preset:arena_combat") is True

    spec = match_prompt("preset:platformer")
    assert spec.matched is True
    assert spec.recipe_id == "platformer"

    spec_board = match_prompt("preset:tic_tac_toe")
    assert spec_board.matched is True
    assert spec_board.recipe_id == "grid_board_game"


def test_greedy_substring_hijacking_prevented():
    """Conflicting multi-genre natural-language prompts should not be greedily hijacked by single keywords."""
    spec = match_prompt("create an open world RPG with an arena where you fight bosses")
    # Should NOT hijack into arena_combat because RPG/open world indicates another distinct genre
    assert spec.matched is False


# ── 2. Kit Evaluator Normalization ────────────────────────────────────────────

def test_evaluator_allof_anyof_and_conflict_rejection():
    """Verify ConditionEvaluator normalizes AllOf/AnyOf, items/conditions, and rejects conflicts."""
    stats = {"a": 10.0, "b": 20.0}
    ctx = EvaluationContext(get_stat=lambda s: stats.get(s, float("nan")))

    # 1. AllOf with items list
    cond_all_items = {
        "kind": "AllOf",
        "items": [
            {"kind": "stat", "stat": "a", "op": "==", "value": 10.0},
            {"kind": "stat", "stat": "b", "op": "==", "value": 20.0},
        ],
    }
    ok, err = ConditionEvaluator.evaluate(cond_all_items, ctx)
    assert ok is True and err is None

    # 2. AnyOf with legacy conditions list
    cond_any_legacy = {
        "kind": "AnyOf",
        "conditions": [
            {"kind": "stat", "stat": "a", "op": "==", "value": 99.0},
            {"kind": "stat", "stat": "b", "op": "==", "value": 20.0},
        ],
    }
    ok, err = ConditionEvaluator.evaluate(cond_any_legacy, ctx)
    assert ok is True and err is None

    # 3. Conflicting items and conditions lists must be rejected
    cond_conflict = {
        "kind": "all",
        "items": [{"kind": "stat", "stat": "a", "op": "==", "value": 10.0}],
        "conditions": [{"kind": "stat", "stat": "a", "op": "==", "value": 99.0}],
    }
    ok, err = ConditionEvaluator.evaluate(cond_conflict, ctx)
    assert ok is False
    assert "conflicting" in err.lower()


# ── 3. RuntimeDef Remaining Counters ──────────────────────────────────────────

def test_runtime_def_remaining_counters():
    """Verify entity.<id>.remaining counters are initialized for ENEMY, RANGED_ENEMY, GUARD from spawn count."""
    gds = preset_platformer()
    # Add an enemy, a ranged enemy, and a guard
    gds.entities.extend([
        EntitySpec(entity_id="boss_enemy", kind=EntityKind.ENEMY, module="kit.enemy_melee", level_id="level_1", count=3),
        EntitySpec(entity_id="sniper_enemy", kind=EntityKind.RANGED_ENEMY, module="kit.enemy_ranged", level_id="level_1", count=5),
        EntitySpec(entity_id="patrol_guard", kind=EntityKind.GUARD, module="kit.guard", level_id="level_1", count=2),
    ])

    gfdef = build_runtime_def(gds)
    assert gfdef["stats"]["entity.boss_enemy.remaining"]["initial"] == 3.0
    assert gfdef["stats"]["entity.boss_enemy.remaining"]["min"] == 0.0

    assert gfdef["stats"]["entity.sniper_enemy.remaining"]["initial"] == 5.0
    assert gfdef["stats"]["entity.patrol_guard.remaining"]["initial"] == 2.0


# ── 4. Composer Codegen & Serialization ───────────────────────────────────────

def test_composer_custom_rule_handler_naming_and_gfdef_serialization(tmp_path: Path):
    """Verify eff.handler_name canonicalization, event/tick body on CodegenTask, and gfdef in assemble step inputs."""
    gds = preset_platformer()
    gds.rules.append(
        RuleSpec(
            rule_id="rule_score_boost",
            description="Boost score on player spawned",
            when=EventRef(event="player.spawned"),
            effects=[
                CustomCode(
                    kind="custom_code",
                    description="Boost player score when event fires",
                    handler_name="ScoreBoostRule",
                    on_event_body="GameState()->SetStat(FName(TEXT('game.score')), 100.0f);",
                    tick_body="// tick update",
                )
            ],
        )
    )

    comp = compose(gds)
    assert len(comp.codegen) == 1
    task = comp.codegen[0]
    assert task.handler_name == "ScoreBoostRule"
    assert "SetStat" in task.on_event_body
    assert "// tick update" in task.tick_body

    run_spec = composition_to_run_spec(comp, workspace_dir=str(tmp_path))
    assemble_step = next(s for s in run_spec.steps if s.step_id == "assemble_level_1")
    assert "gfdef" in assemble_step.inputs
    assert assemble_step.inputs["gfdef"] == comp.gfdef
    assert validate_runtime_def(assemble_step.inputs["gfdef"]) == []


# ── 5. Forge Legacy Adapter Handlers ──────────────────────────────────────────

def test_forge_legacy_scaffold_gamemode_resolution(tmp_path: Path):
    """Verify scaffold resolves recipe GameMode from RECIPE_IMPL[recipe_id][3]."""
    pdir = tmp_path / "TestProject"
    pdir.mkdir(parents=True)
    step = StepSpec(
        step_id="scaffold",
        title="Scaffold project",
        kind=StepKind.SCAFFOLD,
        inputs={"project_name": "TestProject", "recipe_id": "platformer"},
    )
    run = RunSpec(run_id="run_1", title="Run 1", workspace_dir=str(tmp_path), steps=[step])
    ctx = StepContext(
        run=run,
        step=step,
        record=StepRecord(step_id="scaffold"),
        shared={},
        project_dir=pdir,
        workspace_dir=tmp_path,
        cancel=threading.Event(),
        log=lambda l: None,
    )
    outcome = legacy_scaffold(ctx)
    assert outcome.ok is True
    uproj = json.loads((pdir / "TestProject.uproject").read_text(encoding="utf-8"))
    assert uproj["Modules"][0]["Name"] == "TestProject"


def test_forge_legacy_sources_codegen_safety_and_generation(tmp_path: Path):
    """Verify legacy_sources compiles codegen tasks with safety scan."""
    pdir = tmp_path / "TestProject"
    pdir.mkdir(parents=True)
    step = StepSpec(
        step_id="codegen",
        title="Codegen rules",
        kind=StepKind.CODEGEN,
        inputs={
            "project_name": "TestProject",
            "tasks": [
                {
                    "handler_name": "CustomSafeHandler",
                    "on_event_body": "GameState()->SetStat(FName(TEXT('player.health')), 50.0f);",
                    "tick_body": "",
                }
            ],
        },
    )
    run = RunSpec(run_id="run_1", title="Run 1", workspace_dir=str(tmp_path), steps=[step])
    ctx = StepContext(
        run=run,
        step=step,
        record=StepRecord(step_id="codegen"),
        shared={},
        project_dir=pdir,
        workspace_dir=tmp_path,
        cancel=threading.Event(),
        log=lambda l: None,
    )
    outcome = legacy_sources(ctx)
    assert outcome.ok is True
    cpp_file = pdir / "Source" / "TestProject" / "Private" / "CustomSafeHandler.cpp"
    assert cpp_file.is_file()
    assert "CustomSafeHandler" in cpp_file.read_text(encoding="utf-8")


def test_forge_legacy_assemble_validates_gfdef(tmp_path: Path):
    """Verify assemble rejects malformed or invalid gfdef input."""
    pdir = tmp_path / "TestProject"
    pdir.mkdir(parents=True)
    gds = preset_platformer()
    comp = compose(gds)
    plan = comp.levels[0].model_dump()
    step = StepSpec(
        step_id="assemble_level_1",
        title="Assemble level 1",
        kind=StepKind.ASSEMBLE,
        inputs={
            "project_name": "TestProject",
            "plan": plan,
            "gfdef": "not a dictionary",  # Invalid type
        },
    )
    run = RunSpec(run_id="run_1", title="Run 1", workspace_dir=str(tmp_path), steps=[step])
    ctx = StepContext(
        run=run,
        step=step,
        record=StepRecord(step_id="assemble_level_1"),
        shared={},
        project_dir=pdir,
        workspace_dir=tmp_path,
        cancel=threading.Event(),
        log=lambda l: None,
    )
    outcome = legacy_assemble(ctx)
    assert outcome.ok is False
    assert any("must be an object" in e for e in outcome.errors)


# ── 6. GameTools Fallback & Explicit Responses ────────────────────────────────

def test_game_tools_explicit_status_handling(tmp_path: Path):
    """Verify create_game returns explicit NEEDS_INPUT/UNSUPPORTED/FAILED without stubs."""
    tools = GameTools(tmp_path, projects_root=tmp_path / "projects")

    # Unsupported prompt returns UNSUPPORTED
    res_unsupported = tools.create_game(prompt="fix the build error in Foo.cpp")
    assert res_unsupported["status"] == "UNSUPPORTED"
    assert res_unsupported["ok"] is False

    # Empty / nonsense prompt returns FAILED without generic stub
    res_failed = tools.create_game(prompt="")
    assert res_failed["status"] == "FAILED"
    assert res_failed["ok"] is False
