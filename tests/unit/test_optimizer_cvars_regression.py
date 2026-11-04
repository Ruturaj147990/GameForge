"""Regression tests for closed-loop optimizer CVars and ini updates (WI-10.1)."""
from __future__ import annotations

from pathlib import Path
import pytest

from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.qa.optimize import OptimizationLoop, PerformanceProfile


def test_optimizer_writes_to_system_settings(tmp_path: Path):
    loop = OptimizationLoop(tmp_path)
    applied = loop._append_engine_ini("r.Shadow.DistanceScale", "0.75")
    assert applied is True

    ini_path = tmp_path / "Config" / "DefaultEngine.ini"
    assert ini_path.is_file()
    content = ini_path.read_text(encoding="utf-8")
    assert "[SystemSettings]" in content
    assert "r.Shadow.DistanceScale=0.75" in content


def test_optimizer_uses_valid_nanite_cvar(tmp_path: Path):
    loop = OptimizationLoop(tmp_path)
    gds = preset_platformer()
    applied = loop._apply_enable_nanite(gds)
    assert applied is True

    content = (tmp_path / "Config" / "DefaultEngine.ini").read_text(encoding="utf-8")
    # Must use r.Nanite=1, NOT invalid r.Nanite.ProjectEnabled
    assert "r.Nanite=1" in content
    assert "r.Nanite.ProjectEnabled" not in content


def test_optimizer_updates_existing_cvar_value(tmp_path: Path):
    ini_dir = tmp_path / "Config"
    ini_dir.mkdir(parents=True)
    ini_file = ini_dir / "DefaultEngine.ini"
    ini_file.write_text("[SystemSettings]\nr.ScreenPercentage=100\n", encoding="utf-8")

    loop = OptimizationLoop(tmp_path)
    gds = preset_platformer()
    # Apply screen percentage 85%
    applied = loop._apply_screen_pct(gds)
    assert applied is True

    updated_content = ini_file.read_text(encoding="utf-8")
    assert "r.ScreenPercentage=85" in updated_content
    assert "r.ScreenPercentage=100" not in updated_content


def test_optimization_loop_runs_and_reverts_on_failure(tmp_path: Path):
    gds = preset_platformer()
    ini_dir = tmp_path / "Config"
    ini_dir.mkdir(parents=True)
    ini_file = ini_dir / "DefaultEngine.ini"
    ini_file.write_text("[SystemSettings]\nr.ScreenPercentage=100\n", encoding="utf-8")

    eval_calls = 0

    def mock_evaluator(candidate_gds):
        nonlocal eval_calls
        eval_calls += 1
        if eval_calls == 1:
            # Baseline
            return PerformanceProfile(
                avg_fps=45.0,
                frame_time_p95_ms=22.0,
                frame_time_mean_ms=20.0,
                game_thread_p95_ms=15.0,
                gpu_time_p95_ms=21.0,
                scenarios_passed=True,
                vision_rubric_score=4.5,
            )
        else:
            # Improvement
            return PerformanceProfile(
                avg_fps=62.0,
                frame_time_p95_ms=15.5,
                frame_time_mean_ms=14.0,
                game_thread_p95_ms=11.0,
                gpu_time_p95_ms=14.5,
                scenarios_passed=True,
                vision_rubric_score=4.48,
            )

    loop = OptimizationLoop(tmp_path, profile_evaluator=mock_evaluator)
    report = loop.run(gds, target_fps=60.0, max_frame_ms=16.67)

    assert report.success is True
    assert len(report.attempts) >= 1
    assert any(a.accepted for a in report.attempts)
