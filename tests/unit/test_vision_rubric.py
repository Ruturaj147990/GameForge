"""Tests for vision rubric and mesh audit gate (WI-7.10)."""
from pathlib import Path
import pytest

from src.gameforge_ide.review.vision_rubric import (
    VisionRubricScore,
    run_mesh_audit,
    evaluate_vision_rubric,
)


def test_vision_rubric_scoring():
    score = VisionRubricScore(
        readability=0.85,
        not_placeholder=0.90,
        lighting=0.80,
        composition=0.82,
        hud_legible=0.88,
        style_consistency=0.87,
    )
    assert 0.85 <= score.overall <= 0.86
    assert score.is_passing()

    failing_score = VisionRubricScore(readability=0.40)
    assert not failing_score.is_passing()


def test_mesh_audit_clean_art_passes():
    actors = [
        {
            "label": "GF_Pillar_1",
            "mesh": "/Game/GameForge/Props/SM_Pillar",
            "materials": ["/Game/GameForge/Materials/Themes/default/MI_Wall"],
        },
        {
            "label": "GF_Floor_1",
            "mesh": "/Game/GameForge/Props/SM_Floor",
            "materials": ["/Game/GameForge/Materials/Themes/default/MI_Floor"],
        },
        {
            "label": "GF_Character_1",
            "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
            "materials": ["/Game/Characters/Mannequins/Materials/MI_Manny"],
        },
    ]

    res = run_mesh_audit(actors, placeholder_ok=False)
    assert res.passed
    assert res.placeholder_components == 0
    assert not res.unthemed_actors


def test_mesh_audit_detects_unthemed_placeholders():
    actors = [
        {
            "label": "GF_Unthemed_Cube",
            "mesh": "/Engine/BasicShapes/Cube.Cube",
            "materials": ["/Engine/EngineMaterials/DefaultMaterial"],
        },
        {
            "label": "GF_Clean_Prop",
            "mesh": "/Game/GameForge/Props/SM_Crate",
            "materials": ["/Game/GameForge/Materials/Themes/default/MI_Prop"],
        },
    ]

    res = run_mesh_audit(actors, placeholder_ok=False)
    assert not res.passed
    assert res.placeholder_components == 1
    assert "GF_Unthemed_Cube" in res.unthemed_actors[0]

    # When placeholder_ok is True, audit passes
    res_allowed = run_mesh_audit(actors, placeholder_ok=True)
    assert res_allowed.passed
