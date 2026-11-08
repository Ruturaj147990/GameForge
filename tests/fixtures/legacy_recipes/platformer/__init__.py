"""Test-only alias package; implementation lives in src.gameforge_ide.legacy_recipes.platformer.

Only leaf modules are aliased in sys.modules (aliasing the package itself would make
``tests.fixtures.legacy_recipes.platformer.<module>`` load a second copy of the module).
"""
from src.gameforge_ide.legacy_recipes.platformer import *  # noqa: F401,F403
