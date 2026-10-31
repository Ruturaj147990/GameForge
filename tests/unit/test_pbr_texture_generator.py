"""Roadmap M11 step 4: procedural PBR texture generator."""

import json
from pathlib import Path

import numpy as np
import pytest

from src.gameforge_ide.backend.assets.registry import AssetRegistry
from src.gameforge_ide.backend.tools.pbr_texture_generator import (
    PBRTextureSpec,
    generate_texture_set,
    read_png,
    validate_texture_set,
    write_png,
)


def test_texture_set_is_complete_valid_and_tileable(tmp_path):
    manifest = generate_texture_set(PBRTextureSpec(name="Rock", size=128, seed=7), tmp_path)
    assert set(manifest["files"]) == {"BaseColor", "Normal", "ORM", "Height"}
    assert manifest["provenance"] == "procedural"
    assert manifest["files"]["BaseColor"]["srgb"] is True
    assert manifest["files"]["Normal"]["compression"] == "TC_Normalmap"
    assert manifest["files"]["ORM"]["compression"] == "TC_Masks" and not manifest["files"]["ORM"]["srgb"]
    report = validate_texture_set(manifest)
    assert report["valid"], report["errors"]
    assert json.loads((tmp_path / "Rock_pbr_manifest.json").read_text(encoding="utf-8"))["name"] == "Rock"


def test_generation_is_deterministic_per_seed(tmp_path):
    a = generate_texture_set(PBRTextureSpec(name="A", size=64, seed=3), tmp_path / "a")
    b = generate_texture_set(PBRTextureSpec(name="A", size=64, seed=3), tmp_path / "b")
    c = generate_texture_set(PBRTextureSpec(name="A", size=64, seed=4), tmp_path / "c")
    assert a["files"]["Height"]["sha256"] == b["files"]["Height"]["sha256"]
    assert a["files"]["Height"]["sha256"] != c["files"]["Height"]["sha256"]


@pytest.mark.parametrize("kwargs", [{"size": 100}, {"size": 8}, {"roughness_range": (0.9, 0.1)},
                                    {"base_color": (1.5, 0, 0)}, {"name": "bad name"}, {"base_frequency": 3}])
def test_invalid_specs_are_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        generate_texture_set(PBRTextureSpec(**{"name": "X", "size": 64, **kwargs}), tmp_path)


def test_validator_catches_tampering_seams_and_flat_maps(tmp_path):
    manifest = generate_texture_set(PBRTextureSpec(name="T", size=64, seed=1), tmp_path)
    height = Path(manifest["files"]["Height"]["path"])
    ramp = np.tile(np.linspace(0.0, 1.0, 64), (64, 1))  # a ramp has a hard seam at the wrap
    write_png(height, ramp)
    manifest["files"]["Height"]["sha256"] = __import__("hashlib").sha256(height.read_bytes()).hexdigest()
    write_png(Path(manifest["files"]["BaseColor"]["path"]), np.full((64, 64, 3), 0.5))  # flat, hash now stale
    errors = validate_texture_set(manifest)["errors"]
    assert any("Height: does not tile" in e for e in errors)
    assert any("BaseColor: sha256 mismatch" in e for e in errors)
    assert any("BaseColor: a channel is (near) constant" in e for e in errors)


def test_png_round_trip_and_pillow_agreement(tmp_path):
    img = np.random.default_rng(0).random((16, 24, 3))
    write_png(tmp_path / "x.png", img)
    back = read_png(tmp_path / "x.png")
    assert back.shape == (16, 24, 3)
    assert np.array_equal(back, np.clip(np.rint(img * 255), 0, 255).astype(np.uint8))
    pil = pytest.importorskip("PIL.Image")
    assert np.array_equal(np.asarray(pil.open(tmp_path / "x.png")), back)


def test_registry_records_each_map_as_procedural_texture(tmp_path):
    reg = AssetRegistry(tmp_path / "ws")
    manifest = generate_texture_set(PBRTextureSpec(name="Moss", size=32, seed=2), tmp_path / "out", reg)
    assert set(manifest["registry_ids"]) == set(manifest["files"])
    for rid in manifest["registry_ids"].values():
        row = reg.get(rid)
        assert row["asset_type"] == "texture" and row["provenance"] == "procedural" and row["stage"] == "GENERATE"
        assert reg.artifact_unchanged(rid)
