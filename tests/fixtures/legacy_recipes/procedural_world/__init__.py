"""Test-only alias package; implementation lives in src.gameforge_ide.legacy_recipes.procedural_world.

Only leaf modules are aliased in sys.modules (aliasing the package itself would make
``tests.fixtures.legacy_recipes.procedural_world.<module>`` load a second copy of the module).
"""
from src.gameforge_ide.legacy_recipes.procedural_world import *  # noqa: F401,F403
