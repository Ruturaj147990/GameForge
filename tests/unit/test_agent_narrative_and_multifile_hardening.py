"""Unit tests for Agent Runtime multi-file extraction, narrative text cleaning, and grounding guards."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel


def test_extract_all_file_writes_and_mkdir(tmp_path: Path):
    sample_text = """
Understood. Let's build the Sudoku game.
mkdir -p Source/SudokuGame/Private Source/SudokuGame/Public
mkdir -p Content/SudokuGame/Maps

cat > GameForge/design/sudoku.gds.json << 'EOF'
{
  "game_title": "Sudoku",
  "genre": "Puzzle"
}
EOF

Now, I will create the core C++ header:
cat > Source/SudokuGame/Public/SudokuGameInstance.h << 'EOF'
#pragma once
#include "CoreMinimal.h"
UCLASS()
class SUDOKUGAME_API ASudokuGameInstance : public UGameInstanceBase {};
EOF

Next, the cpp implementation:
cat > Source/SudokuGame/Private/SudokuGameInstance.cpp << 'EOF'
#include "SudokuGameInstance.h"
EOF
"""
    writes, created_dirs = AgentRuntime._extract_all_file_writes_and_mkdir(
        sample_text, workspace_root=tmp_path
    )

    # Check directories created
    assert "Source/SudokuGame/Private" in created_dirs
    assert "Source/SudokuGame/Public" in created_dirs
    assert "Content/SudokuGame/Maps" in created_dirs
    assert (tmp_path / "Source/SudokuGame/Private").is_dir()
    assert (tmp_path / "Source/SudokuGame/Public").is_dir()
    assert (tmp_path / "Content/SudokuGame/Maps").is_dir()

    # Check extracted file writes
    paths = [p for p, _ in writes]
    assert len(writes) == 3
    assert "GameForge/design/sudoku.gds.json" in paths
    assert "Source/SudokuGame/Public/SudokuGameInstance.h" in paths
    assert "Source/SudokuGame/Private/SudokuGameInstance.cpp" in paths

    # Verify content of one file
    gds_content = next(c for p, c in writes if p == "GameForge/design/sudoku.gds.json")
    assert '"game_title": "Sudoku"' in gds_content


def test_clean_narrative_text():
    raw_response = """
<think>
I need to check the project files to see if Sudoku is complete.
</think>
To determine if the Sudoku game is complete, I will inspect the project.
</think>
ls -la
"""
    cleaned = AgentRuntime._clean_narrative_text(raw_response)
    assert "<think>" not in cleaned
    assert "</think>" not in cleaned
    assert "ls -la" not in cleaned
    assert cleaned == "To determine if the Sudoku game is complete, I will inspect the project."


def test_clean_narrative_text_removes_heredocs_and_mkdir():
    raw_response = """
Understood. Since the previous generic plan didn't contain Sudoku-specific logic, let's actually build the Sudoku game.
mkdir -p Source/SudokuGame/Private Source/SudokuGame/Public
cat > GameForge/design/sudoku.gds.json << 'EOF'
{
  "game_title": "Sudoku"
}
EOF
Now I will write the header.
cat > Source/SudokuGame/Public/SudokuGameInstance.h << 'EOF'
#pragma once
EOF
All files are prepared.
"""
    cleaned = AgentRuntime._clean_narrative_text(raw_response)
    assert "mkdir -p" not in cleaned
    assert "cat >" not in cleaned
    assert "EOF" not in cleaned
    assert "Understood. Since the previous generic plan didn't contain Sudoku-specific logic, let's actually build the Sudoku game." in cleaned
    assert "Now I will write the header." in cleaned
    assert "All files are prepared." in cleaned


def test_chat_panel_raw_tool_and_shell_suppression():
    # ChatPanel._is_raw_tool_json should detect heredocs, raw commands, and think tags
    assert ChatPanel._is_raw_tool_json("cat > Source/Game.cpp << 'EOF'")
    assert ChatPanel._is_raw_tool_json("mkdir -p Source/Private")
    assert ChatPanel._is_raw_tool_json("ls -la")
    assert ChatPanel._is_raw_tool_json("dir /w")
    assert ChatPanel._is_raw_tool_json("</think>\nls -la")
    assert ChatPanel._is_raw_tool_json('{"name": "read_file", "arguments": {"subpath": "test.txt"}}')
    assert not ChatPanel._is_raw_tool_json("The Sudoku game logic has been implemented successfully.")
