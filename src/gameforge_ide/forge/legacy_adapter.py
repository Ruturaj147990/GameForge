"""Legacy pipeline adapter on top of Forge (AD-11)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ..design.gds import GameDesignSpec
from ..design.legacy import to_legacy_params
from ..pipeline.game_pipeline import PipelineResult, StageRecord, render_markdown
from .handlers.legacy_stages import (
    ARENA_RECIPE_ID,
    ARENA_RECIPE_VERSION,
    CARD_RECIPE_ID,
    CARD_RECIPE_VERSION,
    GRID_RECIPE_ID,
    GRID_RECIPE_VERSION,
    PLATFORMER_RECIPE_ID,
    PLATFORMER_RECIPE_VERSION,
    PROCEDURAL_RECIPE_ID,
    PROCEDURAL_RECIPE_VERSION,
    get_recipe_id,
)
from .model import RunSpec, RunState, StepKind, StepSpec, StepStatus


RECIPE_VERSIONS = {
    GRID_RECIPE_ID: GRID_RECIPE_VERSION,
    PLATFORMER_RECIPE_ID: PLATFORMER_RECIPE_VERSION,
    ARENA_RECIPE_ID: ARENA_RECIPE_VERSION,
    CARD_RECIPE_ID: CARD_RECIPE_VERSION,
    PROCEDURAL_RECIPE_ID: PROCEDURAL_RECIPE_VERSION,
}

_PROJECT_READY_HOOKS: Dict[str, Callable[[Path], None]] = {}


def register_project_ready_hook(run_id: str, hook: Callable[[Path], None]) -> None:
    _PROJECT_READY_HOOKS[run_id] = hook


def get_project_ready_hook(run_id: str) -> Optional[Callable[[Path], None]]:
    return _PROJECT_READY_HOOKS.get(run_id)


def plan_legacy(
    params: Any,
    projects_root: Union[Path, str],
    skip_package: bool = False,
    engine_root: Optional[Union[Path, str]] = None,
    max_parallel_actions: Optional[int] = None,
    on_project_dir_ready: Optional[Callable[[Path], None]] = None,
) -> RunSpec:
    """Build a linear 8-step RunSpec from legacy recipe parameters."""
    gds_dict = None
    if isinstance(params, GameDesignSpec):
        gds_dict = params.model_dump()
        params = to_legacy_params(params)

    recipe_id = get_recipe_id(params)
    project_dir = str(Path(projects_root) / params.project_name)

    common_inputs: Dict[str, Any] = {
        "params": params.to_dict() if hasattr(params, "to_dict") else params,
        "recipe_id": recipe_id,
        "engine_root": str(engine_root) if engine_root else None,
        "max_parallel_actions": max_parallel_actions,
    }
    if gds_dict:
        common_inputs["gds"] = gds_dict

    scaffold_inputs = dict(common_inputs)
    if on_project_dir_ready:
        scaffold_inputs["has_on_project_dir_ready_hook"] = True

    steps = [
        StepSpec(
            step_id="spec",
            kind=StepKind.DESIGN,
            title="Validate Spec",
            inputs=common_inputs,
            approval="none",
            checkpoint=False,
        ),
        StepSpec(
            step_id="scaffold",
            kind=StepKind.SCAFFOLD,
            title="Scaffold C++ Project",
            depends_on=["spec"],
            inputs=scaffold_inputs,
            approval="none",
            checkpoint=True,
        ),
        StepSpec(
            step_id="sources",
            kind=StepKind.CODEGEN,
            title="Generate Game Sources",
            depends_on=["scaffold"],
            inputs=common_inputs,
            approval="none",
            checkpoint=True,
        ),
        StepSpec(
            step_id="build_editor",
            kind=StepKind.BUILD,
            title="Build Editor Target",
            depends_on=["sources"],
            inputs=common_inputs,
            engine_lock=True,
            approval="none",
            checkpoint=True,
        ),
        StepSpec(
            step_id="assemble_level",
            kind=StepKind.ASSEMBLE,
            title="Assemble Level",
            depends_on=["build_editor"],
            inputs=common_inputs,
            engine_lock=True,
            approval="none",
            checkpoint=True,
        ),
        StepSpec(
            step_id="automation_tests",
            kind=StepKind.AUTOMATION,
            title="Run Automation Tests",
            depends_on=["assemble_level"],
            inputs=common_inputs,
            engine_lock=True,
            approval="none",
            checkpoint=True,
        ),
    ]

    if not skip_package:
        steps.extend(
            [
                StepSpec(
                    step_id="package",
                    kind=StepKind.PACKAGE,
                    title="Package Win64 Game",
                    depends_on=["automation_tests"],
                    inputs=common_inputs,
                    engine_lock=True,
                    approval="none",
                    checkpoint=False,
                ),
                StepSpec(
                    step_id="packaged_smoke",
                    kind=StepKind.SCENARIO,
                    title="Packaged Smoke Test",
                    depends_on=["package"],
                    inputs=common_inputs,
                    engine_lock=True,
                    approval="none",
                    checkpoint=False,
                ),
            ]
        )

    return RunSpec(
        title=f"GamePipeline: {params.project_name}",
        origin="prompt",
        project_dir=project_dir,
        workspace_dir=str(projects_root),
        steps=steps,
    )


def run_state_to_pipeline_result(
    state: RunState,
    params: Any,
    engine_version: str = "5.7.4",
) -> PipelineResult:
    """Translate Forge RunState to legacy PipelineResult and write pipeline_report.json / .md."""
    if isinstance(params, GameDesignSpec):
        params = to_legacy_params(params)

    project_dir = Path(state.run.project_dir or (Path(state.run.workspace_dir) / params.project_name))
    evidence_dir = project_dir / "Saved" / "GameForge"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_file = evidence_dir / "pipeline_report.json"

    stages: List[StageRecord] = []
    failed_stage: Optional[str] = None

    for step in state.run.steps:
        rec = state.records.get(step.step_id)
        if rec is None:
            continue
        # Translate to legacy StageRecord
        sr = StageRecord(
            stage=step.step_id,
            ok=bool(rec.ok if rec.ok is not None else (rec.status == StepStatus.DONE)),
            duration_s=rec.duration_s or 0.0,
            data=rec.data,
            errors=rec.errors,
        )
        stages.append(sr)
        if not sr.ok and failed_stage is None and rec.status != StepStatus.SKIPPED:
            failed_stage = step.step_id

    recipe_id = get_recipe_id(params)
    recipe_version = RECIPE_VERSIONS.get(recipe_id, "1.0.0")

    is_ok = state.status == "DONE" and failed_stage is None
    res = PipelineResult(
        ok=is_ok,
        project_dir=str(project_dir),
        stages=stages,
        report_path=str(report_file),
        failed_stage=failed_stage,
    )

    payload = res.to_dict()
    payload.update(
        {
            "recipe": recipe_id,
            "recipe_version": recipe_version,
            "params": params.to_dict() if hasattr(params, "to_dict") else params,
            "engine_version": engine_version,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "forge_run_id": state.run.run_id,
        }
    )

    report_file.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    (evidence_dir / "pipeline_report.md").write_text(render_markdown(payload), encoding="utf-8")
    return res
