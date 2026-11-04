"""Regression tests for vision rubric detecting missing textures, blank frames, and unassigned materials."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw
import pytest

from src.gameforge_ide.review.vision_rubric import (
    VisionRubricScore,
    evaluate_vision_rubric,
    run_mesh_audit,
)


def test_missing_image_file_fails_rubric(tmp_path: Path):
    missing_file = tmp_path / "non_existent.png"
    score = evaluate_vision_rubric(missing_file)
    assert score.is_passing() is False
    assert score.overall == 0.0
    assert any("not found or empty" in n for n in score.notes)


def test_empty_image_file_fails_rubric(tmp_path: Path):
    empty_file = tmp_path / "empty.png"
    empty_file.write_bytes(b"")
    score = evaluate_vision_rubric(empty_file)
    assert score.is_passing() is False
    assert any("not found or empty" in n for n in score.notes)


def test_blank_black_frame_fails_rubric(tmp_path: Path):
    black_img = tmp_path / "black_frame.png"
    img = Image.new("RGB", (256, 256), color=(0, 0, 0))
    img.save(black_img)

    score = evaluate_vision_rubric(black_img)
    assert score.is_passing() is False
    assert any("Blank or black frame" in n for n in score.notes)


def test_missing_texture_magenta_artifact_fails_rubric(tmp_path: Path):
    magenta_img = tmp_path / "magenta_missing_texture.png"
    img = Image.new("RGB", (256, 256), color=(50, 50, 50))
    draw = ImageDraw.Draw(img)
    # Draw significant magenta missing texture checkerboard patches
    draw.rectangle([20, 20, 150, 150], fill=(255, 0, 255))
    draw.rectangle([160, 160, 240, 240], fill=(255, 0, 255))
    img.save(magenta_img)

    score = evaluate_vision_rubric(magenta_img)
    assert score.is_passing() is False
    assert any("Missing texture" in n for n in score.notes)
    assert score.not_placeholder < 0.50


def test_healthy_rendered_screenshot_passes_rubric(tmp_path: Path):
    healthy_img = tmp_path / "game_screen.png"
    # Create an image with varied colors (sky, terrain, character)
    img = Image.new("RGB", (256, 256), color=(100, 150, 220))
    draw = ImageDraw.Draw(img)
    # Terrain (green)
    draw.rectangle([0, 150, 256, 256], fill=(60, 160, 60))
    # Character (orange/gray)
    draw.rectangle([110, 100, 145, 170], fill=(210, 120, 40))
    img.save(healthy_img)

    score = evaluate_vision_rubric(healthy_img)
    assert score.is_passing() is True
    assert score.overall >= 0.80


def test_mesh_audit_detects_unassigned_missing_materials():
    actors = [
        {
            "label": "SM_Rock_NoMat",
            "mesh": "/Game/Environment/SM_Rock",
            "materials": [],  # Unassigned material!
        },
        {
            "label": "SM_Wall_Themed",
            "mesh": "/Game/Environment/SM_Wall",
            "materials": ["/Game/Themes/MI_Wall"],
        },
    ]

    res = run_mesh_audit(actors, placeholder_ok=False)
    assert res.passed is False
    assert res.placeholder_components == 1
    assert any("SM_Rock_NoMat" in u for u in res.unthemed_actors)
    assert any("unassigned" in m.lower() for m in res.default_materials_detected)
