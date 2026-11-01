"""Test that every asset in the asset registry carries a truthful licence and provenance (P7 gate)."""
from pathlib import Path
import pytest

from src.gameforge_ide.backend.assets.registry import AssetRegistry, AssetRecord, PROVENANCE


def test_registry_licence_complete(tmp_path):
    registry = AssetRegistry(tmp_path)

    # Register assets across different provenance and licence classes
    assets = [
        AssetRecord(
            name="SKM_Manny_Simple",
            asset_type="skeletal_mesh",
            purpose="Player hero model",
            provenance="EPIC_CONTENT",
            backend="engine-template",
            backend_version="5.7.4",
            license="Unreal Engine EULA (engine template content)",
            spec={"rel_path": "Meshes/SKM_Manny_Simple.uasset"},
        ),
        AssetRecord(
            name="SM_Crate",
            asset_type="mesh",
            purpose="Loot crate prop",
            provenance="NATIVE",
            backend="GeometryScript",
            backend_version="5.7.4",
            license="GameForge-Generated (project-owned)",
            spec={"recipe": "crate"},
        ),
        AssetRecord(
            name="T_Cobblestone_BaseColor",
            asset_type="texture",
            purpose="Floor texture",
            provenance="PROC",
            backend="PBRTextureGenerator",
            backend_version="1.0.0",
            license="GameForge-Generated (project-owned)",
            spec={"theme": "stone_wood"},
        ),
        AssetRecord(
            name="S_PickupChime",
            asset_type="sound",
            purpose="Pickup audio chime",
            provenance="PROC",
            backend="SFXSynth",
            backend_version="1.0.0",
            license="GameForge-Generated (project-owned)",
            spec={"kind": "pickup"},
        ),
    ]

    for a in assets:
        aid = registry.register(a)
        # Advance through verify and promote
        registry.advance(aid, "GENERATE", True)
        registry.advance(aid, "ENGINE_VERIFY", True)
        registry.advance(aid, "PROMOTE", True, unreal_path=f"/Game/Assets/{a.name}")

    all_rows = registry.search()
    assert len(all_rows) == 4

    for row in all_rows:
        assert row["license"].strip(), f"Asset {row['name']} has empty licence"
        assert row["provenance"] in PROVENANCE, f"Asset {row['name']} has invalid provenance {row['provenance']}"
        assert row["backend"].strip(), f"Asset {row['name']} has empty backend"
        assert row["backend_version"].strip(), f"Asset {row['name']} has empty backend_version"
        assert row["stage"] == "PROMOTE", f"Asset {row['name']} was not promoted"
        assert row["unreal_path"], f"Asset {row['name']} missing unreal_path"
