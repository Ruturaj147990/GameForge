"""Tests for user content library and licence enforcement (WI-7.9)."""
from pathlib import Path
import pytest

from src.gameforge_ide.content.library import (
    ContentLibrary,
    LicenceDecl,
    infer_role_from_name,
)
from src.gameforge_ide.backend.assets.registry import AssetRegistry


def test_licence_decl_enforcement():
    # Fails without user confirmation
    decl_unconfirmed = LicenceDecl(licence_class="CC0", user_confirmed_rights=False)
    with pytest.raises(PermissionError, match="confirm"):
        decl_unconfirmed.validate()

    # CC_BY fails without attribution text
    decl_no_attrib = LicenceDecl(licence_class="CC_BY", user_confirmed_rights=True, attribution_text="")
    with pytest.raises(ValueError, match="attribution"):
        decl_no_attrib.validate()

    # Valid declaration passes
    decl_valid = LicenceDecl(
        licence_class="FAB_STANDARD",
        user_confirmed_rights=True,
    )
    decl_valid.validate()


def test_infer_role_from_name():
    assert infer_role_from_name("SM_Oak_Tree_01") == "tree"
    assert infer_role_from_name("SM_Granite_Boulder") == "rock"
    assert infer_role_from_name("SM_Wooden_Crate_Big") == "prop"
    assert infer_role_from_name("SM_Stone_Pillar_High") == "architecture"
    assert infer_role_from_name("SM_Fern_Bush") == "vegetation"
    assert infer_role_from_name("SKM_Hero_Knight") == "character"
    assert infer_role_from_name("Unknown_Thing_99") == "other"


def test_library_registration_and_project_import(tmp_path):
    # Setup source pack folder
    source_dir = tmp_path / "MyExternalPacks" / "DungeonKit"
    source_dir.mkdir(parents=True)
    (source_dir / "SM_Stone_Pillar.uasset").write_bytes(b"dummy_uasset_pillar")
    (source_dir / "SM_Wooden_Crate.uasset").write_bytes(b"dummy_uasset_crate")

    # Content library DB
    db_path = tmp_path / "artifacts" / "content_library.db"
    lib = ContentLibrary(db_path)

    decl = LicenceDecl(
        licence_class="CC0",
        user_confirmed_rights=True,
    )

    reg_res = lib.register_source("DungeonKit", source_dir, decl)
    assert reg_res["status"] == "PASS"
    assert reg_res["asset_count"] == 2

    # Import into project
    project_dir = tmp_path / "Projects" / "MyGame"
    project_dir.mkdir(parents=True)
    registry = AssetRegistry(project_dir)

    imp_res = lib.import_into_project("DungeonKit", project_dir, registry=registry)
    assert imp_res["status"] == "PASS"
    assert imp_res["imported_count"] == 2

    # Verify registered in project asset registry
    imported_assets = registry.search(stage="PROMOTE")
    assert len(imported_assets) == 2
    assert all(a["provenance"] == "LIBRARY" for a in imported_assets)
    assert all("CC0" in a["license"] for a in imported_assets)
