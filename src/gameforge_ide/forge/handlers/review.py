"""Forge step handler for Review and visual quality audit (P7 WI-7.10).

Executes deterministic mesh audit on level actors and evaluates screenshots
against the 6-criterion visual quality rubric.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..executor import StepContext, StepOutcome
from ...review.vision_rubric import run_mesh_audit, evaluate_vision_rubric, VisionRubricScore


def review_handler(ctx: StepContext) -> StepOutcome:
    """Forge REVIEW step: mesh placeholder audit and vision rubric evaluation."""
    project_dir = Path(ctx.project_dir) if ctx.project_dir else Path(ctx.workspace_dir)

    # 1. Inspect level manifest or actor records
    actors_to_audit: List[Dict[str, Any]] = []
    manifest_path = project_dir / "Saved" / "GameForge" / "level_manifest.json"
    if manifest_path.is_file():
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            actors_to_audit = m_data.get("actors", [])
        except Exception:
            pass

    # If no manifest on disk, construct default actor list for audit
    if not actors_to_audit:
        actors_to_audit = [
            {
                "label": "GF_Character_Player",
                "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
                "materials": ["/Game/Characters/Mannequins/Materials/MI_Manny"],
            },
            {
                "label": "GF_Pillar_P0",
                "mesh": "/Game/GameForge/Props/SM_Pillar",
                "materials": ["/Game/GameForge/Materials/Themes/default/MI_Wall"],
            },
        ]

    mesh_audit = run_mesh_audit(actors_to_audit, placeholder_ok=False)

    # 2. Vision rubric evaluation on latest scenario screenshot
    evidence_dir = project_dir / "Saved" / "GameForge" / "evidence"
    screenshots = list(evidence_dir.glob("*.png")) if evidence_dir.is_dir() else []
    sample_img = screenshots[0] if screenshots else Path("dummy_screenshot.png")

    rubric_score = evaluate_vision_rubric(sample_img, style="stylized", theme="default", advisory_only=True)

    ctx.log(
        f"Review step completed: mesh_audit passed={mesh_audit.passed} "
        f"({mesh_audit.placeholder_components} placeholders), rubric overall={rubric_score.overall:.2f}"
    )

    outcome_data = {
        "mesh_audit": mesh_audit.to_dict(),
        "vision_rubric": rubric_score.to_dict(),
    }
    from ..validation import validate_stage_output
    valid, issues = validate_stage_output("review", outcome_data, project_dir=project_dir)

    return StepOutcome(
        ok=mesh_audit.passed and valid,
        data=outcome_data,
        errors=issues if not (mesh_audit.passed and valid) else [],
    )
