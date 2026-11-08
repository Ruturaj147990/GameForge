import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.tools.game_tools import GameTools
from src.gameforge_ide.core.projects import find_gds, is_gameforge_project
from src.gameforge_ide.desktop.services.projects_service import list_games


def test_find_gds_matches_custom_gds_filename(tmp_path: Path):
    proj_dir = tmp_path / "Sudoku"
    design_dir = proj_dir / "GameForge" / "design"
    design_dir.mkdir(parents=True)
    sudoku_gds = design_dir / "sudoku.gds.json"
    sudoku_gds.write_text('{"meta": {"title": "Sudoku"}}', encoding="utf-8")

    found = find_gds(proj_dir)
    assert found is not None
    assert found.name == "sudoku.gds.json"


def test_list_games_includes_in_progress_projects_with_dot_gameforge(tmp_path: Path):
    proj_dir = tmp_path / "Sudoku"
    (proj_dir / ".gameforge").mkdir(parents=True)
    (proj_dir / "Saved" / "GameForge" / "runs").mkdir(parents=True)

    # In-progress project with Forge runs is recognized as a GameForge project
    assert is_gameforge_project(proj_dir)

    games = list_games(projects_root=tmp_path)
    assert len(games) == 1
    assert games[0].name == "Sudoku"
    assert games[0].title == "Sudoku"


def test_clean_narrative_text_strips_think_tags_and_cat_heredocs():
    dirty_text = (
        "Understood. Let's actually build the Sudoku game.\n"
        "</think>\n"
        "ls -la\n"
        "mkdir -p Source/SudokuGame/Private\n"
        "cat > GameForge/design/sudoku.gds.json << 'EOF'\n"
        '{\n  "game_title": "Sudoku"\n}\n'
        "EOF\n"
        "Now I will generate the GameInstance header.\n"
        "cat > Source/SudokuGame/Public/SudokuGameInstance.h << 'EOF'\n"
        "class ASudokuGameInstance;\n"
        "EOF\n"
    )

    cleaned = AgentRuntime._clean_narrative_text(dirty_text)
    assert "</think>" not in cleaned
    assert "cat >" not in cleaned
    assert "mkdir -p" not in cleaned
    assert "ls -la" not in cleaned
    assert "Understood. Let's actually build the Sudoku game." in cleaned
    assert "Now I will generate the GameInstance header." in cleaned


def test_clean_narrative_text_handles_unclosed_cat_heredoc():
    dirty_text = (
        "Scaffolding solver logic...\n"
        "cat > Source/SudokuGame/Private/SudokuGridManager.cpp << 'EOF'\n"
        "USudokuGridManager::USudokuGridManager() {\n"
        "    m_Board = TArray<TArray<int32>>(9,"
    )

    cleaned = AgentRuntime._clean_narrative_text(dirty_text)
    assert "cat >" not in cleaned
    assert "m_Board" not in cleaned
    assert "Scaffolding solver logic..." in cleaned


def test_build_system_prompt_injects_active_project_grounding(tmp_path: Path):
    proj_dir = tmp_path / "Sudoku"
    proj_dir.mkdir()

    cm = ContextManager(tmp_path)
    prompt = cm.build_system_prompt(
        tools_description="",
        active_project_dir=proj_dir,
    )

    assert "=== ACTIVE PROJECT STATE ===" in prompt
    assert "Project Name: Sudoku" in prompt
    assert "NOT PACKAGED YET" in prompt
    assert "Playable: False" in prompt
    assert "NEVER claim the game is playable" in prompt


def test_play_game_relative_path_and_unbuilt_diagnostic(tmp_path: Path):
    tools = GameTools(tmp_path, tmp_path)
    res = tools.play_game("Packaged/Windows/NonExistent.exe")
    assert res["status"] == "ERROR"
    assert "Not a packaged game executable" in res["error"]
    assert "Please package the game first" in res["error"]
