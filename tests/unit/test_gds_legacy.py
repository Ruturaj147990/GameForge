"""Unit tests for legacy recipe adapter losslessness and validation (P1 WI-1.8)."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from src.gameforge_ide.design.draft import DesignDraft
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.design.gds import CameraKind, Genre
from src.gameforge_ide.design.legacy import LegacyUnsupported, to_legacy_params
from src.gameforge_ide.design.presets import (
    preset_arena_combat,
    preset_card_battler,
    preset_connect_four,
    preset_gomoku,
    preset_platformer,
    preset_procedural_world,
    preset_tic_tac_toe,
)
from tests.fixtures.legacy_recipes.arena_combat.recipe import ArenaCombatParams
from tests.fixtures.legacy_recipes.card_battler.recipe import CardBattlerParams
from tests.fixtures.legacy_recipes.grid_board_game.recipe import GridBoardParams
from tests.fixtures.legacy_recipes.platformer.recipe import PlatformerParams
from tests.fixtures.legacy_recipes.procedural_world.recipe import ProceduralWorldParams


def _strip_names(d: dict) -> dict:
    copy = dict(d)
    copy.pop("project_name", None)
    copy.pop("display_title", None)
    return copy


def test_legacy_params_lossless_for_all_presets():
    # 1. Tic Tac Toe
    ttt_params = to_legacy_params(preset_tic_tac_toe())
    assert _strip_names(asdict(ttt_params)) == _strip_names(asdict(GridBoardParams()))

    # 2. Connect Four
    c4_params = to_legacy_params(preset_connect_four())
    assert c4_params.board_size == 7
    assert c4_params.win_length == 4
    assert c4_params.gravity is True
    assert c4_params.ai_level == "greedy"

    # 3. Gomoku
    gomoku_params = to_legacy_params(preset_gomoku())
    assert gomoku_params.board_size == 15
    assert gomoku_params.win_length == 5

    # 4. Platformer
    plat_params = to_legacy_params(preset_platformer())
    assert _strip_names(asdict(plat_params)) == _strip_names(asdict(PlatformerParams()))

    # 5. Arena Combat
    arena_params = to_legacy_params(preset_arena_combat())
    assert _strip_names(asdict(arena_params)) == _strip_names(asdict(ArenaCombatParams()))

    # 6. Card Battler
    card_params = to_legacy_params(preset_card_battler())
    assert _strip_names(asdict(card_params)) == _strip_names(asdict(CardBattlerParams()))

    # 7. Procedural World
    world_params = to_legacy_params(preset_procedural_world())
    assert _strip_names(asdict(world_params)) == _strip_names(asdict(ProceduralWorldParams()))


def test_legacy_unsupported_genre():
    draft = DesignDraft(
        title="Top Down Shooter",
        genre=Genre.TOP_DOWN_SHOOTER,
        camera=CameraKind.TOP_DOWN,
        pitch="Shoot incoming waves of aliens",
        win=[{"type": "survive_seconds", "target": 60}],
    )
    gds = expand_draft(draft)
    with pytest.raises(LegacyUnsupported, match="needs the composer"):
        to_legacy_params(gds)
