"""Scenario runners: execute scenarios in packaged builds or editor games (WI-3.5)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from ..core import jobs
from ..unreal.toolchain import UnrealToolchain
from .scenario import Scenario, ScenarioResult


def _extract_crash_diagnostics(exe: Path, proc_log: Path, exit_code: Optional[int]) -> str:
    """Find crash or error clues from process stdout or game Saved/Logs."""
    clues: List[str] = []
    tail_lines: List[str] = []

    err_keywords = (
        "Critical error",
        "Fatal error",
        "Unhandled Exception",
        "Assertion failed",
        "Ensure:",
        "Callstack:",
        "CrashReportClient",
        "Failed to enter",
        "LoadPackage: SkipPackage",
        "Failed to load",
        "Error:",
        "Exception",
    )

    if proc_log.is_file():
        try:
            lines = proc_log.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-60:]:
                stripped = line.strip()
                if stripped:
                    tail_lines.append(stripped)
                if any(err_word in line for err_word in err_keywords):
                    clues.append(stripped)
        except Exception:
            pass

    log_candidates = [
        exe.parent / exe.stem / "Saved" / "Logs" / f"{exe.stem}.log",
        exe.parent / "Saved" / "Logs" / f"{exe.stem}.log",
        exe.parent.parent.parent / "Saved" / "Logs" / f"{exe.stem}.log",
    ]
    for lc in log_candidates:
        if lc.is_file():
            try:
                lines = lc.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines[-80:]:
                    stripped = line.strip()
                    if stripped and not tail_lines:
                        tail_lines.append(stripped)
                    if any(err_word in line for err_word in err_keywords):
                        clues.append(stripped)
                if clues:
                    break
            except Exception:
                pass

    if clues:
        unique = list(dict.fromkeys(clues))
        return " | ".join(unique[-3:])
    if exit_code is not None and exit_code != 0:
        tail = (" | Tail: " + " | ".join(tail_lines[-2:])) if tail_lines else ""
        return f"Process terminated with exit code {exit_code}{tail}"
    if tail_lines:
        return "Tail: " + " | ".join(tail_lines[-3:])
    return ""


def run_packaged(
    exe: Path,
    scenario: Scenario,
    out_dir: Path,
    timeout_s: float = 120.0,
    extra_args: Sequence[str] = (),
    map_path: Optional[str] = None,
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

    if map_path:
        clean_map = map_path.strip().split("?")[0]
        url = f"{clean_map}?game=/Script/GameForgeRuntime.GameForgeGameMode"
    else:
        url = "?game=/Script/GameForgeRuntime.GameForgeGameMode"

    argv: List[str] = [
        str(exe),
        url,
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

    proc_log = out_dir / f"{scenario.scenario_id}_stdout.log"
    plog = None
    try:
        plog = open(proc_log, "w", encoding="utf-8", errors="replace")
    except Exception:
        pass

    stdout_target = plog if plog is not None else subprocess.DEVNULL
    stderr_target = plog if plog is not None else subprocess.DEVNULL

    proc = None
    try:
        try:
            proc = jobs.spawn(argv, stdout=stdout_target, stderr=stderr_target)
        except Exception as spawn_exc:
            return ScenarioResult(
                schema="scenario_result/1",
                scenario_id=scenario.scenario_id,
                passed=False,
                failures=[f"SPAWN_FAILED: {spawn_exc}"],
            )

        try:
            proc.wait(timeout=timeout_s)
        except Exception as exc:
            UnrealToolchain.kill_tree(proc)
            if plog is not None:
                try:
                    plog.flush()
                    plog.close()
                    plog = None
                except Exception:
                    pass
            diag = _extract_crash_diagnostics(exe, proc_log, getattr(proc, "returncode", None))
            diag_str = f" | Diagnostics: {diag}" if diag else ""
            return ScenarioResult(
                schema="scenario_result/1",
                scenario_id=scenario.scenario_id,
                passed=False,
                failures=[f"TIMEOUT after {timeout_s}s ({exc}){diag_str}"],
            )
    finally:
        if plog is not None:
            try:
                plog.flush()
                plog.close()
            except Exception:
                pass

    if not scenario_out.is_file():
        return_code = getattr(proc, "returncode", None)
        diag = _extract_crash_diagnostics(exe, proc_log, return_code)
        fail_msg = f"NO_RESULT: {diag}" if diag else "NO_RESULT"
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=scenario.scenario_id,
            passed=False,
            failures=[fail_msg],
        )

    return ScenarioResult.from_file(scenario_out)


def run_editor_game(
    uproject: Path,
    scenario: Scenario,
    out_dir: Path,
    timeout_s: float = 120.0,
    extra_args: Sequence[str] = (),
    map_path: Optional[str] = None,
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
    ]
    if map_path:
        clean_map = map_path.strip().split("?")[0]
        argv.append(f"{clean_map}?game=/Script/GameForgeRuntime.GameForgeGameMode")
    argv.extend([
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
    ])
    argv.extend(extra_args)

    proc_log = out_dir / f"{scenario.scenario_id}_stdout.log"
    plog = None
    try:
        plog = open(proc_log, "w", encoding="utf-8", errors="replace")
    except Exception:
        pass

    stdout_target = plog if plog is not None else subprocess.DEVNULL
    stderr_target = plog if plog is not None else subprocess.DEVNULL

    proc = None
    try:
        try:
            proc = jobs.spawn(argv, stdout=stdout_target, stderr=stderr_target)
        except Exception as spawn_exc:
            return ScenarioResult(
                schema="scenario_result/1",
                scenario_id=scenario.scenario_id,
                passed=False,
                failures=[f"SPAWN_FAILED: {spawn_exc}"],
            )

        try:
            proc.wait(timeout=timeout_s)
        except Exception as exc:
            UnrealToolchain.kill_tree(proc)
            if plog is not None:
                try:
                    plog.flush()
                    plog.close()
                    plog = None
                except Exception:
                    pass
            diag = _extract_crash_diagnostics(exe, proc_log, getattr(proc, "returncode", None))
            diag_str = f" | Diagnostics: {diag}" if diag else ""
            return ScenarioResult(
                schema="scenario_result/1",
                scenario_id=scenario.scenario_id,
                passed=False,
                failures=[f"TIMEOUT after {timeout_s}s ({exc}){diag_str}"],
            )
    finally:
        if plog is not None:
            try:
                plog.flush()
                plog.close()
            except Exception:
                pass

    if not scenario_out.is_file():
        return_code = getattr(proc, "returncode", None)
        diag = _extract_crash_diagnostics(editor_exe, proc_log, return_code)
        fail_msg = f"NO_RESULT: {diag}" if diag else "NO_RESULT"
        return ScenarioResult(
            schema="scenario_result/1",
            scenario_id=scenario.scenario_id,
            passed=False,
            failures=[fail_msg],
        )

    return ScenarioResult.from_file(scenario_out)
