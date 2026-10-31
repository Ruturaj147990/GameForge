"""Roadmap M12 step 1: static-mesh asset spec."""

import pytest

from src.gameforge_ide.backend.models.asset_spec import LODSpec, MaterialSlotSpec, StaticMeshAssetSpec


def crate(**kw):
    return StaticMeshAssetSpec(**{"asset_id": "prop_crate_01", "name": "WoodCrate", "purpose": "Breakable crate",
                                  "category": "container", "size_cm": (80, 80, 80), **kw})


def test_defaults_and_derived_values():
    spec = crate()
    assert spec.asset_name() == "SM_WoodCrate"
    assert spec.lod_count == 3
    assert spec.lod_triangle_targets(1000) == [1000, 500, 250]
    assert len(spec.compute_sha256()) == 64
    assert spec.compute_sha256() == crate().compute_sha256()
    assert spec.compute_sha256() != crate(triangle_budget=6000).compute_sha256()


@pytest.mark.parametrize("kw", [
    {"category": "spaceship"}, {"size_cm": (0, 10, 10)}, {"triangle_budget": 4}, {"collision": "mesh"},
    {"name": "Wood Crate"}, {"quarantine_path": "/Game/Props"}, {"destination_path": "/Game/Quarantine/X"},
    {"destination_path": "/Game/../Engine"}, {"material_slots": []},
    {"material_slots": [MaterialSlotSpec(slot_name="A"), MaterialSlotSpec(slot_name="A")]},
])
def test_invalid_specs_rejected(kw):
    with pytest.raises(ValueError):
        crate(**kw)


@pytest.mark.parametrize("reduction", [[0.5, 0.6], [1.0], [0.0], [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]])
def test_lod_reduction_must_strictly_decrease(reduction):
    with pytest.raises(ValueError):
        LODSpec(reduction=reduction)
