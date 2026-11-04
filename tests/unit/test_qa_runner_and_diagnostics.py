"""Unit and regression tests for scenario runner, timeout diagnostics, and log piping (WI-3.5)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.gameforge_ide.qa.runner import _extract_crash_diagnostics, run_packaged, run_editor_game
from src.gameforge_ide.qa.scenario import Scenario, ScenarioResult


def test_extract_crash_diagnostics_error_keywords(tmp_path: Path):
    log_file = tmp_path / "proc.log"
    log_file.write_text(
        "LogInit: Display: Starting game...\n"
        "LogEngine: Warning: Texture streaming pool full\n"
        "Assertion failed: Character != nullptr [File:Character.cpp] [Line: 42]\n"
        "Fatal error: [File:Unknown] [Line: 0] Unreal Engine is exiting due to fatal error\n",
        encoding="utf-8",
    )
    exe = tmp_path / "Game.exe"
    diag = _extract_crash_diagnostics(exe, log_file, exit_code=1)
    assert "Assertion failed" in diag
    assert "Fatal error" in diag


def test_extract_crash_diagnostics_tail_lines_on_crash(tmp_path: Path):
    log_file = tmp_path / "proc.log"
    log_file.write_text(
        "LogInit: Display: Initializing engine subsystems...\n"
        "LogWorld: Level loaded successfully\n"
        "LogGameForge: Ready for replay\n",
        encoding="utf-8",
    )
    exe = tmp_path / "Game.exe"
    diag = _extract_crash_diagnostics(exe, log_file, exit_code=-1073741819)
    assert "exit code -1073741819" in diag
    assert "Tail:" in diag
    assert "LogGameForge: Ready for replay" in diag


def test_run_packaged_spawn_failure_handled_cleanly(tmp_path: Path):
    scenario = Scenario(scenario_id="spawn_fail_test", steps=[], expect=[])
    out_dir = tmp_path / "qa_out"
    # Provide non-existent executable to trigger FileNotFoundError on spawn
    non_existent_exe = tmp_path / "DoesNotExist.exe"

    result = run_packaged(non_existent_exe, scenario, out_dir, timeout_s=5.0)
    assert isinstance(result, ScenarioResult)
    assert result.passed is False
    assert any("SPAWN_FAILED" in f or "NO_RESULT" in f for f in result.failures)


def test_run_packaged_timeout_includes_diagnostics(tmp_path: Path):
    scenario = Scenario(scenario_id="timeout_diag_test", steps=[], expect=[])
    out_dir = tmp_path / "qa_out"
    exe = tmp_path / "MockGame.exe"
    exe.write_text("dummy", encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd=["MockGame.exe"], timeout=1.0)
    mock_proc.returncode = None

    def _mock_spawn(argv, stdout=None, stderr=None):
        if stdout and hasattr(stdout, "write"):
            stdout.write("Fatal error: GPU device lost\n")
            stdout.flush()
        return mock_proc

    with patch("src.gameforge_ide.core.jobs.spawn", side_effect=_mock_spawn):
        with patch("src.gameforge_ide.unreal.toolchain.UnrealToolchain.kill_tree") as mock_kill:
            result = run_packaged(exe, scenario, out_dir, timeout_s=1.0)
            assert result.passed is False
            assert mock_kill.called
            assert any("TIMEOUT after 1.0s" in f for f in result.failures)
            assert any("Fatal error: GPU device lost" in f for f in result.failures)
