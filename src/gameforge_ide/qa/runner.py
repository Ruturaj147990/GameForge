"""Scenario runners: execute scenarios in packaged builds or editor games (WI-3.5)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from ..core import jobs
from ..unreal.toolchain import UnrealToolchain
from .scenario import Scenario, ScenarioResult


def run_packaged(
    exe: Path,
    scenario: Scenario,
    out_dir: Path,
    timeout_s: float = 120.0,
    extra_args: Sequence[str] = (),
) -> ScenarioResult:
    """Launch the packaged game binary via core.jobs.spawn with scenario arguments."""
    exe = Path(exe)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_path = out_dir / f"{scenario.scenario_id}.json"
    scenario.to_file(scenario_path)

    scenario_out = out_dir / f"{scenario.scenario_id}_result.json"
    if scenario_out.exists():
        scenario_out.unlink()

    events_out = out_dir / f"{scenario.scenario_id}_events.jsonl"
    if events_out.exists():
        events_out.unlink()

    argv: List[str] = [
        str(exe),
        "?game=/Script/GameForgeRuntime.GameForgeGameModeBase",
        f"-GFScenario={scenario_path.resolve()}",
        f"-GFScenarioOut={scenario_out.resolve()}",
        f"-GFEventsOut={events_out.resolve()}",
        "-RenderOffscreen",
        "-ResX=1280",
        "-ResY=720",
        "-unattended",
        "-nosplash",
        "-nosound",
    ]
    argv.extend(extra_args)

    proc = jobs.spawn(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=timeout_s)
    except Exception as exc:
        UnrealToolchain.kill_tree(proc)
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=scenario.scenario_id,
            passed=False,
            failures=[f"TIMEOUT after {timeout_s}s ({exc})"],
        )

    if not scenario_out.is_file():
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=scenario.scenario_id,
            passed=False,
            failures=["NO_RESULT"],
        )

    return ScenarioResult.from_file(scenario_out)


def run_editor_game(
    uproject: Path,
    scenario: Scenario,
    out_dir: Path,
    timeout_s: float = 120.0,
    extra_args: Sequence[str] = (),
) -> ScenarioResult:
    """Run scenario in editor build (-game mode)."""
    tc = UnrealToolchain()
    editor_exe = tc.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
    if not editor_exe.is_file():
        editor_exe = tc.editor_cmd

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_path = out_dir / f"{scenario.scenario_id}.json"
    scenario.to_file(scenario_path)

    scenario_out = out_dir / f"{scenario.scenario_id}_result.json"
    if scenario_out.exists():
        scenario_out.unlink()

    events_out = out_dir / f"{scenario.scenario_id}_events.jsonl"
    if events_out.exists():
        events_out.unlink()

    argv: List[str] = [
        str(editor_exe),
        str(uproject.resolve()),
        "-game",
        f"-GFScenario={scenario_path.resolve()}",
        f"-GFScenarioOut={scenario_out.resolve()}",
        f"-GFEventsOut={events_out.resolve()}",
        "-RenderOffscreen",
        "-ResX=1280",
        "-ResY=720",
        "-unattended",
        "-nosplash",
        "-nosound",
    ]
    argv.extend(extra_args)

    proc = jobs.spawn(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=timeout_s)
    except Exception as exc:
        UnrealToolchain.kill_tree(proc)
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=scenario.scenario_id,
            passed=False,
            failures=[f"TIMEOUT after {timeout_s}s ({exc})"],
        )

    if not scenario_out.is_file():
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=scenario.scenario_id,
            passed=False,
            failures=["NO_RESULT"],
        )

    return ScenarioResult.from_file(scenario_out)
