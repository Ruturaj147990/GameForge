"""Compatibility alias: the implementation moved to src.gameforge_ide.legacy_recipes.grid_board_game.recipe (product package)."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("src.gameforge_ide.legacy_recipes.grid_board_game.recipe")
