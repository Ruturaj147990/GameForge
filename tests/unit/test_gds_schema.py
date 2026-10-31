"""Unit tests for Game Design Spec (GDS) schema (P1 WI-1.2)."""
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from src.gameforge_ide.design.gds import (
    AllOf,
    AnyOf,
    CameraKind,
    CountAtLeast,
    Emit,
    EntityKind,
    EntitySpec,
    EventOccurred,
    EventRef,
    GameDesignSpec,
    Genre,
    Goals,
    InputSpec,
    LayoutKind,
    LevelSpec,
    Meta,
    Overview,
    Placement,
    RuleSpec,
    Scene,
    Spawn,
    Vec2,
    Vec3,
)


def _make_minimal_gds(**kwargs) -> GameDesignSpec:
    data = {
        "meta": {
            "project_name": "TestGame",
            "title": "Minimal Test Game",
            "source_prompt": "A test game",
        },
        "overview": {
            "genre": Genre.PLATFORMER,
            "camera": CameraKind.THIRD_PERSON,
        },
        "scene": {
            "levels": [
                {
                    "level_id": "lvl_main",
                    "layout": LayoutKind.COURSE,
                    "size_m": {"x": 100, "y": 100},
                }
            ],
            "start_level": "lvl_main",
        },
        "entities": [
            {
                "entity_id": "ent_player",
                "kind": EntityKind.PLAYER,
                "module": "kit.player_character",
                "level_id": "lvl_main",
                "count": 1,
            },
            {
                "entity_id": "ent_relic",
                "kind": EntityKind.PICKUP,
                "module": "kit.pickup",
                "level_id": "lvl_main",
                "count": 5,
            },
        ],
        "goals": {
            "win": [
                {
                    "kind": "count_at_least",
                    "event": "pickup.collected",
                    "n": 5,
                    "source": "ent_relic",
                }
            ],
            "lose": [
                {
                    "kind": "event",
                    "event": "player.died",
                    "source": "ent_player",
                }
            ],
        },
    }
    data.update(kwargs)
    return GameDesignSpec.model_validate(data)


def test_valid_minimal_gds_round_trips():
    gds = _make_minimal_gds()
    dumped = gds.to_json()
    reloaded = GameDesignSpec.model_validate_json(dumped)
    assert reloaded.meta.project_name == "TestGame"
    assert reloaded.meta.title == "Minimal Test Game"
    assert len(reloaded.entities) == 2
    assert reloaded.goals.win[0].kind == "count_at_least"
    assert reloaded == gds


def test_nested_all_of_any_of_condition_validates():
    cond = AllOf(
        items=[
            AnyOf(
                items=[
                    CountAtLeast(event="pickup.collected", n=3, source="ent_relic"),
                    EventOccurred(event="player.jumped", source="ent_player"),
                ]
            )
        ]
    )
    gds = _make_minimal_gds()
    gds.goals.win.append(cond)
    dumped = gds.to_json()
    reloaded = GameDesignSpec.model_validate_json(dumped)
    assert reloaded.goals.win[1].kind == "all"
    assert reloaded.goals.win[1].items[0].kind == "any"


def test_model_json_schema_succeeds_and_is_bounded():
    schema = GameDesignSpec.model_json_schema()
    schema_str = json.dumps(schema)
    size_kb = len(schema_str.encode("utf-8")) / 1024
    assert size_kb <= 60, f"Schema size is {size_kb:.1f} KB, expected <= 60 KB"
    assert "$defs" in schema
    assert "properties" in schema


def test_cross_ref_error_unknown_event():
    with pytest.raises(ValidationError, match="event 'custom.unknown_event' is not emitted"):
        _make_minimal_gds(
            goals={
                "win": [
                    {
                        "kind": "event",
                        "event": "custom.unknown_event",
                    }
                ]
            }
        )


def test_cross_ref_error_unknown_entity_in_spawn():
    with pytest.raises(ValidationError, match="spawn of unknown entity 'ent_ghost'"):
        _make_minimal_gds(
            rules=[
                {
                    "rule_id": "rule_spawn",
                    "when": {"event": "player.jumped", "source": "ent_player"},
                    "effects": [{"kind": "spawn", "entity_id": "ent_ghost", "count": 1}],
                }
            ]
        )


def test_cross_ref_error_duplicate_entity_ids():
    with pytest.raises(ValidationError, match="duplicate entity_id"):
        _make_minimal_gds(
            entities=[
                {
                    "entity_id": "dup_ent",
                    "kind": EntityKind.PLAYER,
                    "module": "kit.player_character",
                    "level_id": "lvl_main",
                    "count": 1,
                },
                {
                    "entity_id": "dup_ent",
                    "kind": EntityKind.PICKUP,
                    "module": "kit.pickup",
                    "level_id": "lvl_main",
                    "count": 1,
                },
            ]
        )


def test_missing_win_without_sandbox():
    with pytest.raises(ValidationError, match="goals.win is empty; add a win condition or set sandbox=true"):
        _make_minimal_gds(
            goals={
                "win": [],
                "sandbox": False,
            }
        )


def test_fixed_placement_count_mismatch():
    with pytest.raises(ValidationError, match="fixed placement needs exactly count=2 points"):
        _make_minimal_gds(
            entities=[
                {
                    "entity_id": "ent_fixed",
                    "kind": EntityKind.PLAYER,
                    "module": "kit.player_character",
                    "level_id": "lvl_main",
                    "count": 2,
                    "placement": {
                        "strategy": "fixed",
                        "points_m": [{"x": 0, "y": 0, "z": 0}],
                    },
                }
            ]
        )


def test_unknown_module_rejected():
    with pytest.raises(ValidationError, match="unknown kit module 'kit.nonexistent'"):
        _make_minimal_gds(
            entities=[
                {
                    "entity_id": "ent_bad",
                    "kind": EntityKind.PLAYER,
                    "module": "kit.nonexistent",
                    "level_id": "lvl_main",
                    "count": 1,
                }
            ]
        )


def test_unsafe_title_rejected():
    with pytest.raises(ValidationError, match="text must not contain quotes, backslashes or newlines"):
        _make_minimal_gds(
            meta={
                "project_name": "TestGame",
                "title": 'Bad "Title" with quotes',
            }
        )
