"""Unit tests for opening existing Unreal projects and reverse draft (WI-8.6)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.gameforge_ide.pipeline.project_import import (
    enable_gameforge_management,
    generate_reverse_draft,
    inspect_project,
)


@pytest.fixture
def mock_external_unreal_project(tmp_path: Path) -> Path:
    proj_dir = tmp_path / "ExternalActionGame"
    proj_dir.mkdir(parents=True)

    # .uproject
    (proj_dir / "ExternalActionGame.uproject").write_text(
        json.dumps({"FileVersion": 3, "EngineAssociation": "5.7"}),
        encoding="utf-8",
    )

    # Source code
    src_dir = proj_dir / "Source" / "ExternalActionGame"
    src_dir.mkdir(parents=True)
    (src_dir / "MyPlayerController.h").write_text(
        "class AMyPlayerController : public APlayerController {};\n",
        encoding="utf-8",
    )

    # Config with inputs
    cfg_dir = proj_dir / "Config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "DefaultInput.ini").write_text(
        '[/Script/Engine.InputSettings]\n+ActionMappings=(ActionName="Jump",bShift=False,Key=SpaceBar)\n+ActionMappings=(ActionName="Fire",bShift=False,Key=LeftMouseButton)\n',
        encoding="utf-8",
    )

    # Content with levels
    maps_dir = proj_dir / "Content" / "Maps"
    maps_dir.mkdir(parents=True)
    (maps_dir / "Dungeon_01.umap").write_bytes(b"\x00" * 32)
    (maps_dir / "Arena_02.umap").write_bytes(b"\x00" * 32)

    return proj_dir


def test_inspect_project_read_only(mock_external_unreal_project: Path):
    inspection = inspect_project(mock_external_unreal_project)

    assert inspection.project_name == "ExternalActionGame"
    assert inspection.engine_association == "5.7"
    assert "Maps/Arena_02" in inspection.levels
    assert "Maps/Dungeon_01" in inspection.levels
    assert "AMyPlayerController" in inspection.classes
    assert "Jump" in inspection.input_actions
    assert "Fire" in inspection.input_actions
    assert inspection.is_gameforge_managed is False
    assert inspection.has_git_repo is False


def test_generate_reverse_draft_properties(mock_external_unreal_project: Path):
    inspection = inspect_project(mock_external_unreal_project)
    gds = generate_reverse_draft(inspection)

    assert gds.meta.project_name == "ExternalActionGame"
    assert gds.meta.title == "ExternalActionGame"
    assert gds.meta.generator == "model:import"
    assert "imported: true" in gds.acceptance.extra_checks
    assert len(gds.scene.levels) == 2


def test_enable_gameforge_management_without_git(mock_external_unreal_project: Path):
    res = enable_gameforge_management(mock_external_unreal_project)

    assert res["ok"] is True
    assert (mock_external_unreal_project / ".git").is_dir()
    assert (mock_external_unreal_project / "GameForge" / "project_graph.json").is_file()


def test_enable_gameforge_management_protects_existing_git(mock_external_unreal_project: Path):
    # Simulate user's existing git repository
    git_dir = mock_external_unreal_project / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/user-main\n", encoding="utf-8")

    res = enable_gameforge_management(mock_external_unreal_project, git_strategy="disabled")
    assert res["ok"] is True
    assert "Checkpoints disabled" in res["warning"]
    assert (mock_external_unreal_project / "GameForge" / "project_graph.json").is_file()
