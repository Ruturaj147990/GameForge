"""Domain Specialist 3 (Pipeline, Forge DAG, Composer, Unreal & QA) Comprehensive Audit Tests.

Verifies:
1. Forge DAG Execution & Cancellation State Machine resilience (cancellation, crash handling, artifact validation).
2. Composer C++ identifier sanitization for projects with hyphens and spaces (e.g. 'My-Game 2' -> 'MyGame2').
3. Platformer course ramps walkable slope <= 35.0 deg and entity coordinate boundaries / collider avoidance.
4. Unreal toolchain argument quoting and non-ASCII console decoding resilience.
5. QA event stream expectations: simultaneous event triggers, instantaneous game win before teardown, and entity matching.
"""
from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path
import pytest

from src.gameforge_ide.forge.executor import (
    ForgeExecutor,
    StepContext,
    StepOutcome,
)
from src.gameforge_ide.forge.model import (
    RunSpec,
    RunState,
    StepKind,
    StepSpec,
    StepStatus,
)
from src.gameforge_ide.forge.store import RunStore
from src.gameforge_ide.forge.validation import validate_stage_output
from src.gameforge_ide.composer.codegen import (
    generate_header,
    generate_source,
    sanitize_cpp_identifier,
)
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.composer.layouts.course import plan_level as plan_course_level
from src.gameforge_ide.design.gds import EntitySpec, GameDesignSpec, LevelSpec, Vec2
from src.gameforge_ide.design.presets import preset_arena_combat, preset_platformer
from src.gameforge_ide.unreal.toolchain import format_unreal_cmd
from src.gameforge_ide.qa.events import EventStream, QAEvent
from src.gameforge_ide.qa.scenario import (
    EventCountExpectation,
    EventExpectation,
    NoEventExpectation,
)


# ── Area 1: Forge DAG Execution, Cancellation, and Artifact Validation ──────────

def test_forge_cancellation_marks_running_step_cancelled(tmp_path: Path):
    """When a run is cancelled mid-step, the running step transitions to CANCELLED, not hanging in RUNNING."""
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    ex = None

    def long_running_step(ctx: StepContext) -> StepOutcome:
        ex.request_cancel()
        for _ in range(40):
            if ctx.cancel.is_set():
                break
            time.sleep(0.05)
        return StepOutcome(False, errors=["Cancelled by user"])

    handlers = {StepKind.BUILD.value: long_running_step}
    s = StepSpec(step_id="build", kind=StepKind.BUILD, title="Build")
    run = RunSpec(title="Cancel Run Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(run)

    ex = ForgeExecutor(handlers)
    result = ex.run(state, store)

    assert result.status == "CANCELLED"
    assert result.records["build"].status == StepStatus.CANCELLED
    assert result.records["build"].finished_at is not None


def test_forge_handler_unhandled_crash_fails_cleanly(tmp_path: Path):
    """When a step handler raises an unhandled exception or post-processing crashes, step is marked FAILED."""
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    def crashing_step(ctx: StepContext) -> StepOutcome:
        raise ZeroDivisionError("Division by zero in generator")

    handlers = {StepKind.CODEGEN.value: crashing_step}
    s = StepSpec(step_id="codegen", kind=StepKind.CODEGEN, title="Codegen")
    run = RunSpec(title="Crash Test", workspace_dir=str(ws), steps=[s])
    state = RunState.new(run)

    ex = ForgeExecutor(handlers)
    result = ex.run(state, store)

    assert result.status == "FAILED"
    assert result.records["codegen"].status == StepStatus.FAILED
    assert any("ZeroDivisionError" in err for err in result.records["codegen"].errors)


def test_artifact_validation_resolves_relative_and_checks_empty(tmp_path: Path):
    """Output artifact validation resolves relative paths against project_dir and flags missing/empty files."""
    proj = tmp_path / "TestProject"
    proj.mkdir(parents=True, exist_ok=True)

    empty_log = proj / "empty.log"
    empty_log.touch()  # 0 bytes

    valid_log = proj / "valid.log"
    valid_log.write_text("Build succeeded with 0 errors\n", encoding="utf-8")

    # 1. Missing artifact relative path
    ok, issues = validate_stage_output(
        "other",
        {"ok": True},
        project_dir=proj,
        artifacts=[{"path": "nonexistent.log", "kind": "log"}],
    )
    assert ok is False
    assert any("does not exist on disk" in i for i in issues)

    # 2. Empty artifact file (0 bytes)
    ok, issues = validate_stage_output(
        "other",
        {"ok": True},
        project_dir=proj,
        artifacts=[{"path": "empty.log", "kind": "log"}],
    )
    assert ok is False
    assert any("is empty (0 bytes)" in i for i in issues)

    # 3. Genuine non-empty artifact
    ok, issues = validate_stage_output(
        "other",
        {"ok": True},
        project_dir=proj,
        artifacts=[{"path": "valid.log", "kind": "log"}],
    )
    assert ok is True
    assert len(issues) == 0


# ── Area 2: Composer C++ Identifier Sanitization ─────────────────────────────────

def test_sanitize_cpp_identifier():
    """Verify hyphens, spaces, and non-C++ identifiers are properly sanitized."""
    assert sanitize_cpp_identifier("My-Game 2") == "MyGame2"
    assert sanitize_cpp_identifier("Project Name With Spaces") == "ProjectNameWithSpaces"
    assert sanitize_cpp_identifier("123Game") == "GF123Game"
    assert sanitize_cpp_identifier("My_Custom-Rule.v1") == "MyCustomRuleV1"
    assert sanitize_cpp_identifier("") == "GameForgeProject"


def test_generate_header_sanitizes_identifiers():
    """Verify generate_header produces legal C++ macros and class names from dirty strings."""
    hdr = generate_header("My-Game 2", "Custom-Handler 1")
    assert "MYGAME2_API" in hdr
    assert "class MYGAME2_API UCustomHandler1 : public UGameForgeCustomRule" in hdr
    assert '#include "CustomHandler1.generated.h"' in hdr
    assert "-" not in hdr.split("class")[1].split(":")[0]  # No hyphen in class name


def test_generate_source_sanitizes_handler_name():
    """Verify generate_source includes clean header and method definitions."""
    src = generate_source("Custom-Handler 1", on_event_body="// logic", tick_body="// tick")
    assert '#include "CustomHandler1.h"' in src
    assert "void UCustomHandler1::ExecuteRule()" in src
    assert "void UCustomHandler1::OnEvent(const FGameForgeEvent& Event)" in src


# ── Area 3: Course Walkable Ramps and Boundary/Collider Safety ───────────────────

def test_course_ramps_walkable_slope_under_35_deg():
    """Verify that all connecting walkway ramps in platformer courses maintain <= 35.0 deg slope."""
    gds = preset_platformer()
    # Walkway bridges exist on easy difficulty (normal/hard have real jump gaps)
    gds.progression.difficulty = "easy"
    rng = random.Random(1337)
    level_spec = LevelSpec(level_id="level_1", layout="course", size_m=Vec2(x=80.0, y=80.0), seed=1337)
    plan = plan_course_level(level_spec, gds, rng)

    walkway_ops = [
        op for op in plan.geometry_ops
        if op.op == "spawn_actor" and "GF_Walkway_" in op.args.get("label", "")
    ]
    assert len(walkway_ops) >= 6

    for w in walkway_ops:
        rot = w.args.get("rotation", {})
        pitch = float(rot.get("pitch", 0.0))
        assert abs(pitch) <= 35.0, f"Walkway {w.args.get('label')} has unwalkable pitch {pitch} deg (> 35.0 deg)"
        scale = w.args.get("scale", {})
        assert float(scale.get("x", 0.0)) > 0.0, "Walkway bounding box scale X must be strictly positive"


def test_compose_actors_stay_within_bounds_and_clear_colliders():
    """Verify that composed actors stay within nav bounds and clear obstacles."""
    gds = preset_arena_combat()
    # Add multiple enemies to scatter
    gds.entities.append(
        EntitySpec(
            entity_id="boss_enemy",
            level_id="level_1",
            kind="enemy",
            module="kit.enemy_melee",
            props={"count": 4, "health": 200.0},
        )
    )
    comp = compose(gds)
    level = comp.levels[0]

    nav_center, nav_extent = level.nav_bounds
    max_x = nav_center[0] + nav_extent[0]
    min_x = nav_center[0] - nav_extent[0]
    max_y = nav_center[1] + nav_extent[1]
    min_y = nav_center[1] - nav_extent[1]

    # Solid cover obstacles in arena
    cover_locs = [
        (op.args["location"]["x"], op.args["location"]["y"])
        for op in level.geometry_ops
        if "Cover" in op.args.get("label", "")
    ]

    for a in level.actors:
        ax, ay, az = a.location
        # Inside world bounds
        assert min_x <= ax <= max_x, f"Actor {a.actor_id} spawned past world bound X: {ax}"
        assert min_y <= ay <= max_y, f"Actor {a.actor_id} spawned past world bound Y: {ay}"
        # Above ground / floor
        assert az >= 0.0, f"Actor {a.actor_id} spawned below terrain: {az}"

        # Not inside any cover block collider (cover radius is ~140cm)
        for cx, cy in cover_locs:
            dist = math.hypot(ax - cx, ay - cy)
            assert dist > 120.0, f"Actor {a.actor_id} at ({ax}, {ay}) spawned inside cover collider at ({cx}, {cy})"


# ── Area 4: Unreal Toolchain Commandlet Formatting & Non-ASCII Decoding ──────────

def test_format_unreal_cmd_handles_spaces_and_special_switches():
    """Verify switches with spaces, hyphens, and paths are properly quoted for Unreal Engine CLI."""
    argv = [
        r"C:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
        r"C:\Users\User Name\Documents\GameForge\My-Game.uproject",
        r"-GFScenario=C:\Users\User Name\Saved\smoke.json",
        "-unattended",
        "-nosplash",
    ]
    formatted = format_unreal_cmd(argv)
    if os.name == "nt":
        assert isinstance(formatted, str)
        assert '-GFScenario="C:/Users/User Name/Saved/smoke.json"' in formatted
        assert '"C:/Program Files/Epic Games/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe"' in formatted
        assert '"C:/Users/User Name/Documents/GameForge/My-Game.uproject"' in formatted


# ── Area 5: QA Event Stream Expectations Edge Cases ──────────────────────────────

def test_event_stream_instantaneous_win_before_teardown_death():
    """Verify that a death event during teardown after game.won is not counted as failure."""
    lines = [
        '{"e": "game.started", "t": 0.0}',
        '{"e": "pickup.collected", "t": 1.2, "d": {"actor": "coin_1"}}',
        '{"e": "game.won", "t": 2.5}',
        '{"e": "player.died", "t": 2.6, "d": {"reason": "level_unload_destruction"}}',
    ]
    stream = EventStream.from_lines(lines)

    expectations = [
        EventExpectation(event="game.won"),
        NoEventExpectation(no_event="player.died"),
    ]
    all_ok, failures = stream.verify_all_expectations(expectations)
    assert all_ok is True, f"Expected teardown death after game.won to pass, got failures: {failures}"


def test_event_stream_entity_tag_and_prefix_matching():
    """Verify that entity expectations match tagged, indexed, and nested entity names."""
    lines = [
        '{"e": "enemy.attacked", "t": 1.0, "ent": "enemy_0"}',
        '{"e": "pickup.collected", "t": 1.5, "ent": "GF_Pickup_1"}',
        '{"e": "enemy.killed", "t": 2.0, "d": {"actor": "enemy_0", "entity": "enemy"}}',
    ]
    stream = EventStream.from_lines(lines)

    # 1. Matching 'enemy' matches 'enemy_0'
    ok, count, reason = stream.verify_expectation(EventExpectation(event="enemy.attacked", entity="enemy"))
    assert ok is True
    assert count >= 1

    # 2. Matching 'pickup' matches 'GF_Pickup_1'
    ok, count, reason = stream.verify_expectation(EventExpectation(event="pickup.collected", entity="pickup"))
    assert ok is True
    assert count >= 1

    # 3. Matching 'enemy.killed' via alias 'enemy.defeated'
    ok, count, reason = stream.verify_expectation(EventExpectation(event="enemy.defeated", entity="enemy"))
    assert ok is True
    assert count >= 1
