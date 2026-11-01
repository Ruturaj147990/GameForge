"""Unit tests for performance optimization loop (WI-10.1)."""
from pathlib import Path
import pytest

from src.gameforge_ide.design.presets import get_preset_spec
from src.gameforge_ide.qa.optimize import (
    OptimizationLoop,
    PerformanceProfile,
)


def test_optimization_loop_already_meets_budget(tmp_path: Path):
    gds = get_preset_spec("relic_hunt")
    
    def perfect_evaluator(_):
        return PerformanceProfile(
            avg_fps=62.0,
            frame_time_p95_ms=15.5,
            frame_time_mean_ms=14.0,
            game_thread_p95_ms=10.0,
            gpu_time_p95_ms=13.0,
            scenarios_passed=True,
            vision_rubric_score=4.5,
        )

    loop = OptimizationLoop(tmp_path, profile_evaluator=perfect_evaluator)
    report = loop.run(gds, target_fps=60.0, max_frame_ms=16.67)
    
    assert report.success
    assert len(report.attempts) == 0


def test_optimization_loop_applies_accepted_rule(tmp_path: Path):
    gds = get_preset_spec("relic_hunt")
    calls = 0

    def progressive_evaluator(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Baseline: 52 FPS, 19.2ms p95
            return PerformanceProfile(
                avg_fps=52.0,
                frame_time_p95_ms=19.2,
                frame_time_mean_ms=17.5,
                game_thread_p95_ms=12.0,
                gpu_time_p95_ms=17.0,
                scenarios_passed=True,
                vision_rubric_score=4.5,
            )
        elif calls == 2:
            # After rule 1 (reduce_pcg): 58 FPS, 16.8ms p95 (12.5% improvement, stable vision)
            return PerformanceProfile(
                avg_fps=58.0,
                frame_time_p95_ms=16.8,
                frame_time_mean_ms=15.2,
                game_thread_p95_ms=11.0,
                gpu_time_p95_ms=15.0,
                scenarios_passed=True,
                vision_rubric_score=4.48,
            )
        else:
            # After rule 2 (cap_shadows): 63 FPS, 15.0ms p95 (meets budget!)
            return PerformanceProfile(
                avg_fps=63.0,
                frame_time_p95_ms=15.0,
                frame_time_mean_ms=13.8,
                game_thread_p95_ms=10.0,
                gpu_time_p95_ms=13.5,
                scenarios_passed=True,
                vision_rubric_score=4.46,
            )

    loop = OptimizationLoop(tmp_path, profile_evaluator=progressive_evaluator)
    report = loop.run(gds, target_fps=60.0, max_frame_ms=16.67)

    assert report.success
    assert len(report.attempts) == 2
    assert report.attempts[0].accepted
    assert report.attempts[1].accepted
    assert report.final.avg_fps >= 60.0


def test_optimization_loop_rejects_visual_regression(tmp_path: Path):
    gds = get_preset_spec("relic_hunt")
    step = 0

    def degrading_evaluator(_):
        nonlocal step
        step += 1
        if step == 1:
            return PerformanceProfile(50.0, 20.0, 18.0, 12.0, 18.0, True, 4.5)
        # Fast but terrible visual score
        return PerformanceProfile(70.0, 14.0, 12.0, 8.0, 12.0, True, 3.8)

    loop = OptimizationLoop(tmp_path, profile_evaluator=degrading_evaluator)
    report = loop.run(gds, target_fps=60.0, max_frame_ms=16.67)

    # First attempt must be rejected because visual score dropped > 0.05
    assert len(report.attempts) > 0
    assert not report.attempts[0].accepted
    assert "vision rubric degraded" in report.attempts[0].reason
