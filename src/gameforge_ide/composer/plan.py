"""Composer plan to Forge RunSpec generator (WI-6.7).

Translates a Composition into a typed, verified Forge RunSpec DAG with
proper dependencies, locks, input hashes, and step configurations.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from .model import Composition
from ..forge.model import RunSpec, StepKind, StepSpec


def composition_to_run_spec(
    comp: Composition,
    workspace_dir: str,
    project_dir: Optional[str] = None,
    origin: str = "cli",
) -> RunSpec:
    """Generate a Forge RunSpec DAG from a Composition."""
    steps: List[StepSpec] = []

    genre = getattr(comp, "genre", None)
    if not genre and isinstance(comp.gfdef, dict):
        genre = comp.gfdef.get("genre", "Platformer")
    genre = genre or "Platformer"

    pitch = getattr(comp, "pitch", "") or f"{comp.project_name} — dynamic {genre} gameplay"

    # 1. Design step
    steps.append(
        StepSpec(
            step_id="design",
            kind=StepKind.DESIGN,
            title="Design: save GDS revision and composition",
            depends_on=[],
            engine_lock=False,
            inputs={
                "project_name": comp.project_name,
                "genre": genre,
                "pitch": pitch,
                "gds_id": comp.gds_id,
                "gds_revision": comp.gds_revision,
            },
        )
    )

    primary_map = comp.levels[0].map_path if comp.levels else "/Game/Maps/Level_1"

    # 2. Scaffold step
    steps.append(
        StepSpec(
            step_id="scaffold",
            kind=StepKind.SCAFFOLD,
            title=f"Scaffold project {comp.project_name}",
            depends_on=[],
            engine_lock=False,
            inputs={
                "project_name": comp.project_name,
                "plugins": comp.plugins,
                "module_deps": comp.module_deps,
                "default_map": primary_map,
            },
        )
    )

    # 3. Codegen step (if codegen tasks exist)
    last_code_step = "scaffold"
    if comp.codegen:
        steps.append(
            StepSpec(
                step_id="codegen",
                kind=StepKind.CODEGEN,
                title="Codegen: compile custom C++ rule handlers",
                depends_on=["scaffold"],
                engine_lock=False,
                inputs={"tasks": [t.model_dump() for t in comp.codegen]},
            )
        )
        last_code_step = "codegen"

    # 4. Build Editor step
    build_deps = ["scaffold"]
    if comp.codegen:
        build_deps.append("codegen")
    steps.append(
        StepSpec(
            step_id="build_editor",
            kind=StepKind.BUILD,
            title="Build editor target",
            depends_on=build_deps,
            engine_lock=True,
            max_attempts=3,
            inputs={"target": f"{comp.project_name}Editor", "configuration": "Development"},
        )
    )

    # 5. Content step
    steps.append(
        StepSpec(
            step_id="content",
            kind=StepKind.CONTENT,
            title="Content preparation (VFX/SFX presets)",
            depends_on=["build_editor"],
            engine_lock=True,
            inputs={"requests": comp.content_requests},
        )
    )

    # 6. Assemble steps (one per level)
    assemble_step_ids = []
    for level in comp.levels:
        s_id = f"assemble_{level.level_id}"
        assemble_step_ids.append(s_id)
        steps.append(
            StepSpec(
                step_id=s_id,
                kind=StepKind.ASSEMBLE,
                title=f"Assemble level {level.level_id}",
                depends_on=["content"],
                engine_lock=True,
                inputs={
                    "level_id": level.level_id,
                    "map_path": level.map_path,
                    "plan": level.model_dump(),
                    "genre": genre,
                    "project_name": comp.project_name,
                    "gfdef": comp.gfdef,
                },
            )
        )

    # 7. Scenario gen step
    steps.append(
        StepSpec(
            step_id="scenario_gen",
            kind=StepKind.DESIGN,
            title="Generate QA testbed scenarios",
            depends_on=assemble_step_ids,
            engine_lock=False,
            inputs={"scenarios": comp.scenarios},
        )
    )

    # 8. Automation tests step
    steps.append(
        StepSpec(
            step_id="automation",
            kind=StepKind.AUTOMATION,
            title="Run C++ automation tests",
            depends_on=assemble_step_ids,
            engine_lock=True,
            inputs={"tests": ["GameForge.Kit"]},
        )
    )

    # 9. Package step
    steps.append(
        StepSpec(
            step_id="package",
            kind=StepKind.PACKAGE,
            title="Package Development executable",
            depends_on=["automation"],
            engine_lock=True,
            inputs={"configuration": "Development"},
        )
    )

    # 10. Scenario runs step
    steps.append(
        StepSpec(
            step_id="scenarios",
            kind=StepKind.SCENARIO,
            title="Execute packaged QA scenarios",
            depends_on=["package", "scenario_gen"],
            engine_lock=True,
            inputs={"scenarios": comp.scenarios, "map_path": primary_map},
        )
    )

    # 11. Review step
    steps.append(
        StepSpec(
            step_id="review",
            kind=StepKind.REVIEW,
            title="Review vision and quality rubric",
            depends_on=["scenarios"],
            engine_lock=False,
            inputs={},
        )
    )

    # 12. Report step
    steps.append(
        StepSpec(
            step_id="report",
            kind=StepKind.REPORT,
            title="Compile final build and test evidence report",
            depends_on=["review"],
            engine_lock=False,
            inputs={},
        )
    )

    return RunSpec(
        title=f"Compose & Build {comp.project_name}",
        origin=origin,  # type: ignore
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        gds_revision=comp.gds_revision,
        steps=steps,
    )
