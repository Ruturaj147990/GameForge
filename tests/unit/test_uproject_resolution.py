"""Unit tests for robust .uproject resolution by project name, directory, or file path."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.gameforge_ide.backend.tools.game_tools import GameTools
from src.gameforge_ide.backend.tools.unreal_tools import UnrealEngineTools


def test_game_tools_resolve_uproject_by_name_and_path(tmp_path):
    """Verify GameTools._resolve_uproject resolves project names, folders, and relative paths."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    projects_root = tmp_path / "projects"
    projects_root.mkdir()

    # Create dummy project under projects_root
    proj_dir = projects_root / "SnakeAndLadders"
    proj_dir.mkdir()
    up_file = proj_dir / "SnakeAndLadders.uproject"
    up_file.write_text("{}", encoding="utf-8")

    gt = GameTools(workspace_root=ws, projects_root=projects_root)

    # 1. Project name
    assert gt._resolve_uproject("SnakeAndLadders") == up_file.resolve()

    # 2. Case-insensitive name
    assert gt._resolve_uproject("snakeandladders") == up_file.resolve()

    # 3. Filename
    assert gt._resolve_uproject("SnakeAndLadders.uproject") == up_file.resolve()

    # 4. Folder path as string
    assert gt._resolve_uproject(str(proj_dir)) == up_file.resolve()

    # 5. Folder path as Path
    assert gt._resolve_uproject(proj_dir) == up_file.resolve()

    # 6. Direct file path
    assert gt._resolve_uproject(str(up_file)) == up_file.resolve()

    # 7. Non-existent returns None
    assert gt._resolve_uproject("NonExistentProject") is None


def test_unreal_editor_tool_accepts_project_name(tmp_path):
    """Verify unreal_editor tool call resolves project name without 'uproject not found' error."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    projects_root = tmp_path / "projects"
    projects_root.mkdir()

    proj_dir = projects_root / "SnakeAndLadders"
    proj_dir.mkdir()
    up_file = proj_dir / "SnakeAndLadders.uproject"
    up_file.write_text("{}", encoding="utf-8")

    gt = GameTools(workspace_root=ws, projects_root=projects_root)

    # Mock _link so no real Unreal Editor needs to be spawned
    mock_link = MagicMock()
    mock_link.call.return_value = {"ok": True, "op": "nav_rebuild", "data": {"requested": True}}

    with patch.object(gt, "_link", return_value=mock_link) as mock_link_factory:
        res = gt.unreal_editor(uproject="SnakeAndLadders", op="nav_rebuild", args={})
        assert res["status"] == "SUCCESS"
        assert res["result"]["ok"] is True
        mock_link_factory.assert_called_once_with(up_file.resolve())
        mock_link.call.assert_called_once_with("nav_rebuild", {})


def test_unreal_tools_resolve_uproject_path(tmp_path):
    """Verify UnrealTools._resolve_uproject_path resolves project name and directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    projects_root = tmp_path / "projects"
    projects_root.mkdir()

    proj_dir = projects_root / "SnakeAndLadders"
    proj_dir.mkdir()
    up_file = proj_dir / "SnakeAndLadders.uproject"
    up_file.write_text("{}", encoding="utf-8")

    ut = UnrealEngineTools(workspace_root=ws)
    with patch("src.gameforge_ide.core.projects.get_settings") as mock_settings:
        mock_settings.return_value.projects_root = str(projects_root)
        mock_settings.return_value.host_profile = {}
        mock_settings.return_value.artifacts_root = None
        mock_settings.return_value.validation_root = None
        mock_settings.return_value.default_workspace = None

        resolved = ut._resolve_uproject_path("SnakeAndLadders")
        assert resolved == up_file.resolve()
