"""Recipe: grid_board_game (tic-tac-toe, Gomoku-style N-in-a-row on an N x N board).

A recipe is a parameterised, pre-verified source set. This one produces a complete,
asset-free UE C++ game module:
  * FGridRules           pure rules (moves, win/draw detection, AI move choice)
  * AGFBoardCell         clickable cell actor (engine basic shapes + dynamic material colour)
  * AGFBoard             spawns cells, applies moves, draws marks, highlights the winning line
  * AGFPlayerController  mouse cursor + click events, R restarts, Esc quits
  * AGFHUD               canvas HUD: turn, result, controls
  * AGFGameMode          sets up camera, board and lighting fallback; -GFSelfTest scripted run
  * Automation tests     GameForge.<Game>.Rules.* (rows, columns, diagonals, draw, invalid, AI)

Parameters are validated here; the C++ is generated from templates in templates.py.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict

from .templates import render_sources

RECIPE_ID = "grid_board_game"
RECIPE_VERSION = "1.0.0"


@dataclass
class GridBoardParams:
    project_name: str = "TicTacToe"
    display_title: str = "Tic-Tac-Toe"
    board_size: int = 3
    win_length: int = 3
    vs_ai: bool = True           # player 2 is the computer
    gravity: bool = False        # Connect-Four style: pieces drop to the lowest free cell
    ai_level: str = "perfect"    # "random" | "greedy" | "perfect" (minimax for 3x3, greedy otherwise)
    cell_size_cm: float = 200.0
    player1_color: tuple = (0.10, 0.45, 1.00)
    player2_color: tuple = (1.00, 0.25, 0.20)
    board_color: tuple = (0.85, 0.85, 0.88)

    def validate(self) -> None:
        if not re.match(r"^[A-Z][A-Za-z0-9]{1,30}$", self.project_name):
            raise ValueError("project_name must be PascalCase alphanumeric")
        if not 3 <= self.board_size <= 15:
            raise ValueError("board_size must be 3..15")
        if not 3 <= self.win_length <= self.board_size:
            raise ValueError("win_length must be 3..board_size")
        if self.ai_level not in ("random", "greedy", "perfect"):
            raise ValueError("ai_level must be random|greedy|perfect")
        if len(self.display_title) > 60 or any(c in self.display_title for c in '"\\\n'):
            raise ValueError("display_title must be <= 60 chars without quotes, backslashes or newlines")
        for c in (self.player1_color, self.player2_color, self.board_color):
            if len(c) != 3 or not all(0.0 <= float(x) <= 1.0 for x in c):
                raise ValueError("colours are RGB triples in 0..1")

    def to_dict(self) -> Dict:
        return asdict(self)


def generate(params: GridBoardParams) -> Dict[str, str]:
    """Return {relative_path: content} for the game module sources."""
    params.validate()
    return render_sources(params)


TEST_FILTER_TEMPLATE = "GameForge.{name}"
SELFTEST_LOG_PASS = "GF_SELFTEST PASS"
