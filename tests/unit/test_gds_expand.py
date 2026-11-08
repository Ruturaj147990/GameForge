"""Unit tests for draft expansion into GameDesignSpec (P1 WI-1.4)."""
from __future__ import annotations

from src.gameforge_ide.design.draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.design.gds import (
    CameraKind,
    EntityKind,
    GameDesignSpec,
    Genre,
)


def test_expand_platformer_draft():
    draft = DesignDraft(
        title="Super Jump",
        genre=Genre.PLATFORMER,
        camera=CameraKind.THIRD_PERSON,
        pitch="Jump to collect all coins and reach the goal",
        win=[DraftWin(type="collect_all", target=8), DraftWin(type="reach_goal")],
        lose=[DraftLose(type="fall_off")],
    )
    gds = expand_draft(draft)
    assert gds.meta.project_name == "SuperJump"
    assert gds.meta.title == "Super Jump"
    assert any(e.kind == EntityKind.PLAYER for e in gds.entities)
    assert any(e.kind == EntityKind.PICKUP for e in gds.entities)
    assert any(e.kind == EntityKind.GOAL for e in gds.entities)
    assert len(gds.goals.win) == 1 and gds.goals.win[0].event == "goal.reached"
    assert len(gds.goals.lose) == 1
    # Verify round-trip validation
    reloaded = GameDesignSpec.model_validate_json(gds.to_json())
    assert reloaded == gds


def test_expand_grid_board_draft():
    draft = DesignDraft(
        title="Tic Tac Toe",
        genre=Genre.GRID_BOARD,
        camera=CameraKind.FIXED_BOARD,
        pitch="Align three in a row",
        win=[DraftWin(type="board_win")],
        lose=[DraftLose(type="board_loss")],
    )
    gds = expand_draft(draft)
    assert gds.meta.project_name == "TicTacToe"
    assert any(e.kind == EntityKind.BOARD for e in gds.entities)
    assert len(gds.goals.win) == 1
    assert any(r.rule_id == "rule_1" for r in gds.rules)
    reloaded = GameDesignSpec.model_validate_json(gds.to_json())
    assert reloaded == gds


def test_expand_arena_combat_with_spawner():
    draft = DesignDraft(
        title="Gladiator Arena",
        genre=Genre.ARENA_COMBAT,
        camera=CameraKind.TOP_DOWN,
        pitch="Fight waves of enemies",
        win=[DraftWin(type="defeat_all", target=4)],
        lose=[DraftLose(type="health_zero")],
    )
    gds = expand_draft(draft)
    assert any(e.kind == EntityKind.SPAWNER for e in gds.entities)
    assert len(gds.goals.win) == 1
    assert gds.goals.win[0].kind == "all"
    reloaded = GameDesignSpec.model_validate_json(gds.to_json())
    assert reloaded == gds


def test_expand_card_battler():
    draft = DesignDraft(
        title="Card Quest",
        genre=Genre.CARD_BATTLER,
        camera=CameraKind.FIXED_BOARD,
        pitch="Card lane duel",
        win=[DraftWin(type="match_win")],
        lose=[DraftLose(type="match_loss")],
    )
    gds = expand_draft(draft)
    assert any(e.kind == EntityKind.CARD_TABLE for e in gds.entities)
    reloaded = GameDesignSpec.model_validate_json(gds.to_json())
    assert reloaded == gds


def test_expand_custom_rules_and_acceptance():
    draft = DesignDraft(
        title="Custom Adventure",
        genre=Genre.ACTION_ADVENTURE,
        camera=CameraKind.THIRD_PERSON,
        pitch="Custom quest with special mechanic",
        entities=[DraftEntity(kind=EntityKind.NPC, count=1, note="Elder")],
        win=[DraftWin(type="survive_seconds", target=120)],
        lose=[DraftLose(type="health_zero")],
        custom_rules=["Players gain stealth when crouching"],
    )
    gds = expand_draft(draft)
    assert any("briefing" in r.rule_id for r in gds.rules)
    assert any(s.scenario_id == "smoke" for s in gds.acceptance.scenarios)
    assert any(s.scenario_id == "win_1" for s in gds.acceptance.scenarios)
    reloaded = GameDesignSpec.model_validate_json(gds.to_json())
    assert reloaded == gds
