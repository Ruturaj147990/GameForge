"""Unit tests for core.projects module — project discovery, directory resolution, and lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from src.gameforge_ide.core.projects import (
    find_packaged_executable,
    find_gds,
    find_uproject,
    is_gameforge_project,
    list_all_project_dirs,
    open_folder_in_file_manager,
    resolve_project_dir,
)


def test_find_uproject_and_gds(tmp_path: Path):
    proj_dir = tmp_path / "MySpecialGame"
    proj_dir.mkdir()

    # Initially empty
    assert find_uproject(proj_dir) is None
    assert find_gds(proj_dir) is None
    assert is_gameforge_project(proj_dir) is False

    # Add .uproject
    uproj = proj_dir / "MySpecialGame.uproject"
    uproj.write_text("{}", encoding="utf-8")
    assert find_uproject(proj_dir) == uproj
    assert is_gameforge_project(proj_dir) is True

    # Add GDS
    gds_dir = proj_dir / "GameForge" / "design"
    gds_dir.mkdir(parents=True)
    gds_file = gds_dir / "game.gds.json"
    gds_file.write_text("{}", encoding="utf-8")
    assert find_gds(proj_dir) == gds_file
    assert is_gameforge_project(proj_dir) is True


def test_resolve_project_dir_direct_path(tmp_path: Path):
    proj_dir = tmp_path / "DirectGame"
    proj_dir.mkdir()
    (proj_dir / "DirectGame.uproject").write_text("{}", encoding="utf-8")

    # Direct directory path
    resolved = resolve_project_dir(proj_dir)
    assert resolved == proj_dir.resolve()

    # String path
    resolved_str = resolve_project_dir(str(proj_dir))
    assert resolved_str == proj_dir.resolve()


def test_resolve_project_dir_with_spaces_and_unicode(tmp_path: Path):
    special_name = "Game 🎮 With Spaces & Unicode"
    proj_dir = tmp_path / special_name
    proj_dir.mkdir()
    (proj_dir / f"{special_name}.uproject").write_text("{}", encoding="utf-8")

    # Resolves directly
    assert resolve_project_dir(proj_dir) == proj_dir.resolve()

    # Resolves with workspace_dir provided
    resolved = resolve_project_dir(special_name, workspace_dir=tmp_path)
    assert resolved == proj_dir.resolve()


def test_resolve_project_dir_workspace_self(tmp_path: Path):
    proj_dir = tmp_path / "StandaloneProject"
    proj_dir.mkdir()
    (proj_dir / "StandaloneProject.uproject").write_text("{}", encoding="utf-8")

    # When workspace_dir is itself the project
    resolved = resolve_project_dir("StandaloneProject", workspace_dir=proj_dir)
    assert resolved == proj_dir.resolve()


def test_list_all_project_dirs(tmp_path: Path):
    ws = tmp_path / "UserWorkspace"
    ws.mkdir()

    p1 = ws / "GameAlpha"
    p1.mkdir()
    (p1 / "GameAlpha.uproject").write_text("{}", encoding="utf-8")

    p2 = ws / "GameBeta"
    p2.mkdir()
    gds_dir = p2 / "GameForge" / "design"
    gds_dir.mkdir(parents=True)
    (gds_dir / "game.gds.json").write_text("{}", encoding="utf-8")

    not_a_proj = ws / "RandomFolder"
    not_a_proj.mkdir()

    discovered = list_all_project_dirs(workspace_dir=ws)
    assert "GameAlpha" in discovered
    assert "GameBeta" in discovered
    assert "RandomFolder" not in discovered
    assert discovered["GameAlpha"] == p1.resolve()
    assert discovered["GameBeta"] == p2.resolve()


def test_find_packaged_executable(tmp_path: Path):
    proj = tmp_path / "PackagedGame"
    proj.mkdir()

    # Candidate: Packaged/Windows/PackagedGame.exe
    pkg_dir = proj / "Packaged" / "Windows"
    pkg_dir.mkdir(parents=True)
    exe = pkg_dir / "PackagedGame.exe"
    exe.write_text("mock binary", encoding="utf-8")

    found = find_packaged_executable(proj, "PackagedGame")
    assert found == exe

    # Should ignore CrashReportClient.exe
    crc = pkg_dir / "CrashReportClient.exe"
    crc.write_text("crc", encoding="utf-8")
    assert find_packaged_executable(proj, "PackagedGame") == exe


def test_open_folder_in_file_manager_missing():
    assert open_folder_in_file_manager("Z:/NonExistentPath/123456") is False
