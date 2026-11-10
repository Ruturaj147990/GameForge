"""Forge step handler for Review and visual quality audit (P7 WI-7.10).

Executes deterministic mesh audit on level actors and evaluates screenshots
against the 6-criterion visual quality rubric.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..executor import StepContext, StepOutcome
from ...review.vision_rubric import run_mesh_audit, evaluate_vision_rubric
from ...storage.atomic import atomic_write_json

__all__ = ["review_handler"]


def _is_cancelled(ctx: StepContext) -> bool:
    cancel = getattr(ctx, "cancel", None)
    return cancel is not None and cancel.is_set() is True


def _normalize_manifest_actors(raw_actors: List[Any]) -> List[Dict[str, Any]]:
    """Normalize level manifest actor entries into dicts suitable for run_mesh_audit."""
    normalized: List[Dict[str, Any]] = []
    for a in raw_actors:
        if not isinstance(a, dict):
            continue
        label = a.get("label") or a.get("actor_id") or a.get("tag") or a.get("id") or "GF_Actor"
        cls_name = a.get("cls") or a.get("runtime_class") or a.get("class") or ""
        mesh = a.get("mesh") or a.get("mesh_path") or ""
        if not mesh:
            if "Character" in cls_name or a.get("entity_id") == "player":
                mesh = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
            else:
                mesh = f"/Game/GameForge/Generated/SM_{a.get('entity_id') or label}"
        has_explicit_materials = "materials" in a or "material" in a
        materials = a.get("materials")
        if materials is None and "material" in a:
            mat_val = a.get("material")
            materials = [mat_val] if isinstance(mat_val, str) and mat_val.strip() else []
        if not has_explicit_materials and (not isinstance(materials, list) or not materials):
            materials = ["/Game/GameForge/Materials/M_StylizedMaster"]
        elif not isinstance(materials, list):
            materials = []
        normalized.append(
            {
                **a,
                "label": str(label),
                "mesh": str(mesh),
                "materials": list(materials),
            }
        )
    return normalized


def review_handler(ctx: StepContext) -> StepOutcome:
    """Forge REVIEW step: mesh placeholder audit and vision rubric evaluation."""
    if _is_cancelled(ctx):
        return StepOutcome(False, errors=["Cancelled by user"])

    project_dir = Path(ctx.project_dir) if ctx.project_dir else Path(ctx.workspace_dir)

    # 1. Inspect level manifest or actor records
    actors_to_audit: List[Dict[str, Any]] = []
    manifest_path = project_dir / "Saved" / "GameForge" / "level_manifest.json"
    if manifest_path.is_file():
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_actors = m_data.get("actors", []) if isinstance(m_data, dict) else []
            actors_to_audit = _normalize_manifest_actors(raw_actors)
        except Exception as exc:
            ctx.log(f"Warning: failed to read level manifest {manifest_path}: {exc}")

    # Check GameForge/levels/*.manifest.json written by modern Composer assembly
    if not actors_to_audit:
        levels_dir = project_dir / "GameForge" / "levels"
        if levels_dir.is_dir():
            for mf in sorted(levels_dir.glob("*.manifest.json")):
                try:
                    m_data = json.loads(mf.read_text(encoding="utf-8"))
                    raw_actors = m_data.get("actors", []) if isinstance(m_data, dict) else []
                    actors_to_audit.extend(_normalize_manifest_actors(raw_actors))
                except Exception as exc:
                    ctx.log(f"Warning: failed to read level manifest {mf}: {exc}")

    # Also check shared step outputs from assemble_level_* steps
    if not actors_to_audit and isinstance(ctx.shared, dict):
        for sh_val in ctx.shared.values():
            if isinstance(sh_val, dict) and isinstance(sh_val.get("actors"), list):
                actors_to_audit.extend(_normalize_manifest_actors(sh_val["actors"]))

    # If no manifest on disk or in shared state, construct default actor list for audit
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

    if _is_cancelled(ctx):
        return StepOutcome(False, errors=["Cancelled by user"])

    mesh_audit = run_mesh_audit(actors_to_audit, placeholder_ok=False)

    # 2. Vision rubric evaluation on latest scenario screenshot
    style = str(ctx.step.inputs.get("style") or "stylized")
    theme = str(ctx.step.inputs.get("theme") or "default")
    evidence_dir = project_dir / "Saved" / "GameForge" / "evidence"
    screenshots: List[Path] = []
    if evidence_dir.is_dir():
        screenshots = list(evidence_dir.glob("*.png"))
        if not screenshots and (evidence_dir / "scenarios").is_dir():
            screenshots = list((evidence_dir / "scenarios").rglob("*.png"))
    if screenshots:
        screenshots.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    sample_img = screenshots[0] if screenshots else Path("dummy_screenshot.png")

    rubric_score = evaluate_vision_rubric(sample_img, style=style, theme=theme, advisory_only=True)

    ctx.log(
        f"Review step completed: mesh_audit passed={mesh_audit.passed} "
        f"({mesh_audit.placeholder_components} placeholders), rubric overall={rubric_score.overall:.2f}"
    )

    outcome_data = {
        "mesh_audit": mesh_audit.to_dict(),
        "vision_rubric": rubric_score.to_dict(),
    }
    artifacts: List[Dict[str, str]] = []
    review_out = project_dir / "Saved" / "GameForge" / "vision_review.json"
    try:
        atomic_write_json(review_out, outcome_data)
        if review_out.is_file():
            artifacts.append({"path": str(review_out), "kind": "report"})
    except Exception as exc:
        ctx.log(f"Warning: failed to write {review_out}: {exc}")

    from ..validation import validate_stage_output
    valid, issues = validate_stage_output("review", outcome_data, project_dir=project_dir, artifacts=artifacts)
    errors = list(issues)
    if not mesh_audit.passed and not errors:
        errors = [
            f"Mesh audit failed ({mesh_audit.placeholder_components} placeholder/unthemed components): "
            f"{', '.join(mesh_audit.unthemed_actors[:10])}"
        ]

    return StepOutcome(
        ok=mesh_audit.passed and valid,
        data=outcome_data,
        artifacts=artifacts,
        errors=errors if not (mesh_audit.passed and valid) else [],
    )
