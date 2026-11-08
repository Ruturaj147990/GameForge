"""Legacy game recipes (GridBoard, Platformer, ArenaCombat, CardBattler, ProceduralWorld, freeform host).

These modules are imported by product code (design/legacy.py, pipeline/*, forge/handlers/legacy_stages.py,
backend/tools/game_tools.py). They previously lived under ``tests/fixtures/legacy_recipes``, which the
PyInstaller spec excludes (``excludes=['tests']``), so a frozen build failed with ModuleNotFoundError as soon
as any of those product modules was imported. They now live inside the product package;
``tests/fixtures/legacy_recipes`` remains as a thin alias so existing tests keep working.
"""
