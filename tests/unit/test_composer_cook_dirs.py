"""Tests for Epic packs installer and cooker directory configuration (WI-7.1)."""
from pathlib import Path
import pytest

from src.gameforge_ide.content.epic_packs import (
    EPIC_PACKS,
    collect_cook_directories,
    update_default_game_ini_cook_dirs,
    install_pack,
)
from src.gameforge_ide.backend.assets.registry import AssetRegistry


def test_collect_cook_directories_from_gfdef():
    sample_gfdef = {
        "schema_": "gfdef/1",
        "player": {
            "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
            "anim_class": "/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C",
        },
        "entities": {
            "enemy_1": {
                "visual": {
                    "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple",
                }
            },
            "prop_1": {
                "mesh": "/Game/LevelPrototyping/Meshes/SM_ChamferCube",
            },
            "system": {
                "gamedef": "/Game/GameForge/GD_Main",  # should be excluded or included as top-level /Game/GameForge
            }
        }
    }

    dirs = collect_cook_directories(sample_gfdef)
    assert "/Game/Characters" in dirs
    assert "/Game/LevelPrototyping" in dirs


def test_update_default_game_ini_cook_dirs(tmp_path):
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir(parents=True)
    ini_path = project_dir / "Config" / "DefaultGame.ini"
    ini_path.parent.mkdir()
    ini_path.write_text("[/Script/EngineSettings.GeneralProjectSettings]\nProjectName=Test\n", encoding="utf-8")

    cook_dirs = ["/Game/Characters", "/Game/LevelPrototyping"]
    update_default_game_ini_cook_dirs(project_dir, cook_dirs)

    content = ini_path.read_text(encoding="utf-8")
    assert "[/Script/UnrealEd.ProjectPackagingSettings]" in content
    assert '+DirectoriesToAlwaysCook=(Path="/Game/Characters")' in content
    assert '+DirectoriesToAlwaysCook=(Path="/Game/LevelPrototyping")' in content

    # Test idempotence
    update_default_game_ini_cook_dirs(project_dir, cook_dirs)
    assert content.count('+DirectoriesToAlwaysCook=(Path="/Game/Characters")') == 1


def test_install_pack_copies_and_registers(tmp_path):
    # Mock engine root with template content
    engine_root = tmp_path / "MockUE"
    mannequins_src = engine_root / "Templates" / "TemplateResources" / "High" / "Characters" / "Content" / "Mannequins"
    (mannequins_src / "Meshes").mkdir(parents=True)
    (mannequins_src / "Meshes" / "SKM_Manny_Simple.uasset").write_bytes(b"dummy_uasset_content")

    project_dir = tmp_path / "TestProject"
    registry = AssetRegistry(project_dir)

    res = install_pack(project_dir, "mannequins", engine_root, registry=registry)
    assert res["status"] == "PASS"
    assert res["installed_count"] >= 1
    assert res["registered_count"] >= 1

    # Verify asset is promoted in registry
    promoted = registry.search(stage="PROMOTE")
    assert any("SKM_Manny_Simple" in r["name"] for r in promoted)
    rec = promoted[0]
    assert rec["provenance"] == "EPIC_CONTENT"
    assert "EULA" in rec["license"]
