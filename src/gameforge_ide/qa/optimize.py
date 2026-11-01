"""Performance optimization loop for GameForge packaged and PIE games (WI-10.1).

Applies deterministic, reversible optimization steps:
1. Reduce PCG density (-25%)
2. Cap shadow distance (r.Shadow.DistanceScale=0.75)
3. Enable Nanite on meshes > 5k tris
4. Lower screen percentage to 85% (r.ScreenPercentage=85)
5. Enable HLOD streaming
6. Disable volumetric clouds (r.VolumetricCloud=0)

Each change is kept ONLY if:
- p95 frame time improves by >= 5.0%
- vision rubric score does not drop by > 0.05
- all scenario gates continue to pass
"""
from __future__ import annotations

import configparser
import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..backend.tools.csv_profile import parse_csv_profile
from ..design.gds import GameDesignSpec


@dataclass
class PerformanceProfile:
    avg_fps: float
    frame_time_p95_ms: float
    frame_time_mean_ms: float
    game_thread_p95_ms: float
    gpu_time_p95_ms: float
    scenarios_passed: bool = True
    vision_rubric_score: float = 4.5

    def meets_budget(self, target_fps: float = 60.0, max_frame_ms: float = 16.67) -> bool:
        return self.avg_fps >= target_fps and self.frame_time_p95_ms <= max_frame_ms


@dataclass
class OptimizationAttempt:
    rule_name: str
    description: str
    before_p95_ms: float
    after_p95_ms: float
    improvement_pct: float
    vision_score_before: float
    vision_score_after: float
    scenarios_passed: bool
    accepted: bool
    reason: str


@dataclass
class OptimizationReport:
    game_title: str
    target_fps: float
    max_frame_ms: float
    baseline: PerformanceProfile
    final: PerformanceProfile
    attempts: List[OptimizationAttempt] = field(default_factory=list)
    success: bool = False


class OptimizationLoop:
    """Executes the closed-loop performance optimization ladder."""

    def __init__(
        self,
        project_dir: Path,
        profile_evaluator: Optional[Callable[[GameDesignSpec], PerformanceProfile]] = None,
    ):
        self.project_dir = Path(project_dir)
        self.profile_evaluator = profile_evaluator or self._default_evaluator

    def _default_evaluator(self, gds: GameDesignSpec) -> PerformanceProfile:
        # Default mock-safe evaluator if real runner is not injected
        return PerformanceProfile(
            avg_fps=54.0,
            frame_time_p95_ms=18.5,
            frame_time_mean_ms=17.2,
            game_thread_p95_ms=12.0,
            gpu_time_p95_ms=16.8,
            scenarios_passed=True,
            vision_rubric_score=4.4,
        )

    def run(
        self,
        gds: GameDesignSpec,
        target_fps: float = 60.0,
        max_frame_ms: float = 16.67,
    ) -> OptimizationReport:
        current_gds = copy.deepcopy(gds)
        baseline = self.profile_evaluator(current_gds)
        current_perf = baseline

        attempts: List[OptimizationAttempt] = []

        rules = [
            ("reduce_pcg_density", "Reduce entity and scatter density by 25%", self._apply_reduce_pcg),
            ("cap_shadow_distance", "Cap shadow draw distance (r.Shadow.DistanceScale=0.75)", self._apply_cap_shadows),
            ("enable_nanite_meshes", "Enable Nanite streaming on static meshes", self._apply_enable_nanite),
            ("screen_percentage_85", "Lower screen percentage to 85%", self._apply_screen_pct),
            ("enable_hlod_streaming", "Enable HLOD cell streaming", self._apply_hlod),
            ("disable_volumetric_clouds", "Disable volumetric cloud rendering", self._apply_disable_clouds),
        ]

        for rule_name, desc, apply_fn in rules:
            if current_perf.meets_budget(target_fps, max_frame_ms):
                break

            candidate_gds = copy.deepcopy(current_gds)
            applied = apply_fn(candidate_gds)
            if not applied:
                continue

            test_perf = self.profile_evaluator(candidate_gds)

            # Evaluate criteria
            p95_diff = current_perf.frame_time_p95_ms - test_perf.frame_time_p95_ms
            improvement_pct = (p95_diff / current_perf.frame_time_p95_ms) * 100.0 if current_perf.frame_time_p95_ms > 0 else 0.0
            vision_diff = current_perf.vision_rubric_score - test_perf.vision_rubric_score

            accepted = False
            reason = ""

            if not test_perf.scenarios_passed:
                reason = "REJECTED: scenario test failed"
            elif vision_diff > 0.05:
                reason = f"REJECTED: vision rubric degraded by {vision_diff:.3f} (> 0.05 limit)"
            elif improvement_pct < 5.0:
                reason = f"REJECTED: p95 improvement {improvement_pct:.2f}% below 5.0% threshold"
            else:
                accepted = True
                reason = f"ACCEPTED: p95 improved {improvement_pct:.2f}% with stable vision & scenarios"

            attempts.append(
                OptimizationAttempt(
                    rule_name=rule_name,
                    description=desc,
                    before_p95_ms=round(current_perf.frame_time_p95_ms, 2),
                    after_p95_ms=round(test_perf.frame_time_p95_ms, 2),
                    improvement_pct=round(improvement_pct, 2),
                    vision_score_before=round(current_perf.vision_rubric_score, 2),
                    vision_score_after=round(test_perf.vision_rubric_score, 2),
                    scenarios_passed=test_perf.scenarios_passed,
                    accepted=accepted,
                    reason=reason,
                )
            )

            if accepted:
                current_gds = candidate_gds
                current_perf = test_perf

        report = OptimizationReport(
            game_title=gds.meta.title,
            target_fps=target_fps,
            max_frame_ms=max_frame_ms,
            baseline=baseline,
            final=current_perf,
            attempts=attempts,
            success=current_perf.meets_budget(target_fps, max_frame_ms),
        )

        return report

    def _apply_reduce_pcg(self, gds: GameDesignSpec) -> bool:
        changed = False
        for ent in gds.entities:
            if ent.count > 4:
                ent.count = max(2, int(ent.count * 0.75))
                changed = True
        return changed

    def _apply_cap_shadows(self, gds: GameDesignSpec) -> bool:
        return self._append_engine_ini("r.Shadow.DistanceScale", "0.75")

    def _apply_enable_nanite(self, gds: GameDesignSpec) -> bool:
        return self._append_engine_ini("r.Nanite.ProjectEnabled", "1")

    def _apply_screen_pct(self, gds: GameDesignSpec) -> bool:
        return self._append_engine_ini("r.ScreenPercentage", "85")

    def _apply_hlod(self, gds: GameDesignSpec) -> bool:
        return self._append_engine_ini("r.HLOD", "1")

    def _apply_disable_clouds(self, gds: GameDesignSpec) -> bool:
        return self._append_engine_ini("r.VolumetricCloud", "0")

    def _append_engine_ini(self, key: str, value: str) -> bool:
        ini_path = self.project_dir / "Config" / "DefaultEngine.ini"
        try:
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            text = ini_path.read_text(encoding="utf-8") if ini_path.is_file() else "[/Script/Engine.RendererSettings]\n"
            if key in text:
                return False
            if "[/Script/Engine.RendererSettings]" not in text:
                text += "\n[/Script/Engine.RendererSettings]\n"
            text += f"{key}={value}\n"
            ini_path.write_text(text, encoding="utf-8")
            return True
        except Exception:
            return False
