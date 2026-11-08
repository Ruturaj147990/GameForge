"""Test-only alias package; implementation lives in src.gameforge_ide.legacy_recipes.grid_board_game.

Only leaf modules are aliased in sys.modules (aliasing the package itself would make
``tests.fixtures.legacy_recipes.grid_board_game.<module>`` load a second copy of the module).
"""
from src.gameforge_ide.legacy_recipes.grid_board_game import *  # noqa: F401,F403
