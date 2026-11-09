"""Unit tests for GameForge events and stats catalog (P1 WI-1.1)."""
from __future__ import annotations

from src.gameforge_ide.design.events_catalog import (
    DEFAULT_MODULE,
    EVENT_RE,
    GAME_EVENTS,
    MODULE_EVENTS,
    STAT_RE,
    all_events,
)


def test_every_module_event_matches_event_regex():
    for mod_id, events in MODULE_EVENTS.items():
        assert mod_id.startswith("kit."), f"Module ID {mod_id} must start with 'kit.'"
        for event in events:
            assert EVENT_RE.match(event), f"Event '{event}' in module '{mod_id}' does not match EVENT_RE"


def test_every_game_event_matches_event_regex():
    for event in GAME_EVENTS:
        assert EVENT_RE.match(event), f"Game event '{event}' does not match EVENT_RE"


def test_every_default_module_is_in_module_events():
    for kind, mod_id in DEFAULT_MODULE.items():
        assert mod_id in MODULE_EVENTS, f"DEFAULT_MODULE['{kind}'] -> '{mod_id}' not found in MODULE_EVENTS"


def test_all_events_contains_game_and_module_events():
    events = all_events()
    for ge in GAME_EVENTS:
        assert ge in events
    for mod_events in MODULE_EVENTS.values():
        for me in mod_events:
            assert me in events


def test_stat_regex_patterns():
    valid_stats = [
        "player.health",
        "player.max_health",
        "player.stamina",
        "player.mana",
        "player.gold",
        "player.lives",
        "game.score",
        "game.time_s",
        "game.counter.wave",
        "entity.relic.collected",
        "entity.guard.killed",
        "entity.key.remaining",
    ]
    for s in valid_stats:
        assert STAT_RE.match(s), f"Valid stat '{s}' was rejected by STAT_RE"

    invalid_stats = [
        "player",
        "game",
        "entity",
        "player.invalid_stat_xyz",
        "game.invalid_stat_xyz",
        "custom.stat",
    ]
    for s in invalid_stats:
        assert not STAT_RE.match(s), f"Invalid stat '{s}' was accepted by STAT_RE"
