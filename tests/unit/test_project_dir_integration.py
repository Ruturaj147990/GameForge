"""Tests for Project Directory Lifecycle and Multi-Workspace Integration."""

import json
from pathlib import Path
import pytest

from src.gameforge_ide.core.projects import (
    find_gds,
    find_uproject,
    is_gameforge_project,
    list_all_project_dirs,
    resolve_project_dir,
)
from src.gameforge_ide.desktop.services.projects_service import (
    delete_project,
    list_games,
)


@pytest.fixture
def multi_project_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects_root"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _create_mock_project(
    root: Path,
    name: str,
    title: str = "Test Game",
    genre: str = "action",
    with_uproject: bool = True,
    with_gds: bool = True,
) -> Path:
    proj_dir = root / name
    proj_dir.mkdir(parents=True, exist_ok=True)

    if with_uproject:
        (proj_dir / f"{name}.uproject").write_text(
            json.dumps({"FileVersion": 3, "EngineAssociation": "5.7"}),
            encoding="utf-8",
        )

    if with_gds:
        gds_dir = proj_dir / "GameForge" / "design"
        gds_dir.mkdir(parents=True, exist_ok=True)
        gds_data = {
            "meta": {"schema": "gds/1", "title": title, "revision": 1},
            "overview": {"genre": genre, "pitch": f"A great {genre} experience"},
        }
        (gds_dir / "game.gds.json").write_text(
            json.dumps(gds_data),
            encoding="utf-8",
        )

    # Project metadata dir
    (proj_dir / ".gameforge").mkdir(parents=True, exist_ok=True)
    return proj_dir


def test_multi_project_switching_and_isolation(multi_project_root: Path):
    """Test Project A vs Project B isolation."""
    proj_a = _create_mock_project(multi_project_root, "ProjectAlpha", title="Alpha Mission", genre="puzzle")
    proj_b = _create_mock_project(multi_project_root, "ProjectBeta", title="Beta Strike", genre="shooter")

    # Verify discovery
    games = list_games(projects_root=multi_project_root)
    assert len(games) == 2
    names = {g.name for g in games}
    assert names == {"ProjectAlpha", "ProjectBeta"}

    # Verify Project A metadata
    summary_a = next(g for g in games if g.name == "ProjectAlpha")
    assert summary_a.title == "Alpha Mission"
    assert summary_a.genre == "puzzle"
    assert summary_a.project_dir == proj_a

    # Verify Project B metadata
    summary_b = next(g for g in games if g.name == "ProjectBeta")
    assert summary_b.title == "Beta Strike"
    assert summary_b.genre == "shooter"
    assert summary_b.project_dir == proj_b

    # Verify file isolation: writing in Project A does not touch Project B
    (proj_a / "custom_asset.txt").write_text("Alpha Secret", encoding="utf-8")
    assert not (proj_b / "custom_asset.txt").exists()


def test_paths_with_spaces(multi_project_root: Path):
    """Verify projects with spaces in directory names work across all resolvers."""
    space_name = "Tactical Strike 2026 Special Edition"
    proj = _create_mock_project(
        multi_project_root,
        space_name,
        title="Tactical Strike",
        genre="fps",
    )

    assert is_gameforge_project(proj)
    assert find_uproject(proj) == proj / f"{space_name}.uproject"
    assert find_gds(proj) == proj / "GameForge" / "design" / "game.gds.json"

    # Resolution by name
    resolved = resolve_project_dir(space_name, workspace_dir=multi_project_root)
    assert resolved == proj

    # List games
    games = list_games(projects_root=multi_project_root)
    summary = next(g for g in games if g.name == space_name)
    assert summary.title == "Tactical Strike"
    assert summary.genre == "fps"


def test_paths_with_unicode(multi_project_root: Path):
    """Verify projects with Unicode characters and emojis."""
    unicode_name = "Projet_Éclair_🎮_日本語"
    proj = _create_mock_project(
        multi_project_root,
        unicode_name,
        title="Éclair Thunder ⚡",
        genre="rpg",
    )

    assert is_gameforge_project(proj)
    assert find_uproject(proj) == proj / f"{unicode_name}.uproject"
    assert find_gds(proj) == proj / "GameForge" / "design" / "game.gds.json"

    # Resolution
    resolved = resolve_project_dir(unicode_name, workspace_dir=multi_project_root)
    assert resolved == proj

    # Verify listing and UTF-8 roundtrip
    games = list_games(projects_root=multi_project_root)
    summary = next(g for g in games if g.name == unicode_name)
    assert summary.title == "Éclair Thunder ⚡"
    assert summary.genre == "rpg"


def test_workspace_rescan_and_deletion(multi_project_root: Path):
    """Test dynamic addition and safe deletion of projects."""
    _create_mock_project(multi_project_root, "EphemeralGame", title="To Be Deleted")
    games_initial = list_games(projects_root=multi_project_root)
    assert any(g.name == "EphemeralGame" for g in games_initial)

    # Delete project
    deleted = delete_project("EphemeralGame", projects_root=multi_project_root)
    assert deleted is True

    # Rescan
    games_after = list_games(projects_root=multi_project_root)
    assert not any(g.name == "EphemeralGame" for g in games_after)
    assert not (multi_project_root / "EphemeralGame").exists()
