"""Unit tests for GDS markdown renderer and sentence formatting (P1 WI-1.7)."""
from __future__ import annotations

import pytest

from src.gameforge_ide.design.events_catalog import all_events
from src.gameforge_ide.design.gds import (
    AddStat,
    AllOf,
    AnyOf,
    CountAtLeast,
    CustomCode,
    Emit,
    EndGame,
    EventOccurred,
    SetStat,
    Spawn,
    StatCompare,
    TimerElapsed,
)
from src.gameforge_ide.design.presets import (
    preset_arena_combat,
    preset_platformer,
    preset_tic_tac_toe,
)
from src.gameforge_ide.design.render import (
    EVENT_PHRASES,
    render_markdown,
    sentence,
)


def test_all_catalogue_events_have_phrases():
    catalog_events = all_events()
    for ev in catalog_events:
        assert ev in EVENT_PHRASES, f"Event {ev!r} is missing from EVENT_PHRASES"
        assert len(EVENT_PHRASES[ev]) > 0


def test_sentence_conditions():
    c1 = CountAtLeast(event="pickup.collected", n=5)
    assert sentence(c1) == "the player has collected 5 pickups"

    c2 = StatCompare(stat="player.health", op="<=", value=0)
    assert sentence(c2) == "player health drops to 0 or below"

    c3 = StatCompare(stat="entity.enemies.remaining", op="<=", value=0)
    assert sentence(c3) == "all enemies are defeated"

    c4 = TimerElapsed(seconds=60)
    assert sentence(c4) == "60 seconds pass"

    c5 = EventOccurred(event="goal.reached")
    assert sentence(c5) == "goal is reached"

    c6 = AllOf(items=[c1, c4])
    assert sentence(c6) == "all of: the player has collected 5 pickups, 60 seconds pass"

    c7 = AnyOf(items=[c2, c4])
    assert sentence(c7) == "any of: player health drops to 0 or below, 60 seconds pass"


def test_sentence_effects():
    e1 = AddStat(stat="game.score", delta=10)
    assert sentence(e1) == "add 10 to game.score"

    e2 = SetStat(stat="player.health", value=100)
    assert sentence(e2) == "set player.health to 100"

    e3 = EndGame(outcome="win")
    assert sentence(e3) == "the player wins"

    e4 = EndGame(outcome="lose")
    assert sentence(e4) == "the player loses"

    e5 = CustomCode(description="trigger earthquake", handler_name="EarthquakeRule")
    assert sentence(e5) == "custom behaviour: trigger earthquake"

    e6 = Spawn(entity_id="enemy", count=3)
    assert sentence(e6) == "spawn 3 enemy"

    e7 = Emit(event="wave.cleared")
    assert sentence(e7) == "emit wave is cleared"


def test_render_markdown_presets():
    # Platformer
    gds_plat = preset_platformer(title="Sky Climber")
    md_plat = render_markdown(gds_plat)
    assert "# Sky Climber" in md_plat
    assert "## Levels" in md_plat
    assert "## Entities" in md_plat
    assert "| `player` |" in md_plat
    assert "| `pickups` |" in md_plat
    assert "## Goals" in md_plat
    assert "Win Conditions" in md_plat
    assert "Lose Conditions" in md_plat
    assert "## User Interface" in md_plat
    assert "## Art & Audio" in md_plat
    assert "## Acceptance Scenarios" in md_plat

    # Tic Tac Toe
    gds_ttt = preset_tic_tac_toe()
    md_ttt = render_markdown(gds_ttt)
    assert "# Tic-Tac-Toe" in md_ttt
    assert "grid_board" in md_ttt
    assert "| `board` |" in md_ttt

    # Arena Combat
    gds_arena = preset_arena_combat()
    md_arena = render_markdown(gds_arena)
    assert "# Arena Combat" in md_arena
    assert "arena_combat" in md_arena
    assert "| `spawner` |" in md_arena
