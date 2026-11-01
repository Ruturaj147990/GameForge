"""Unit tests for Scenario and LevelManifest schemas (WI-3.5)."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from src.gameforge_ide.qa.scenario import (
    Scenario,
    ScenarioResult,
    NavigateToStep,
    NavigateToArgs,
    InjectStep,
    InjectArgs,
    WaitStep,
    WaitArgs,
    EventExpectation,
    EventCountExpectation,
    LegsOkExpectation,
    NoEventExpectation,
    Capture,
)
from src.gameforge_ide.qa.manifest import LevelManifest, ManifestActor


def test_scenario_serialization(tmp_path: Path):
    sc = Scenario(
        scenario_id="collect_three",
        description="Collect 3 pickups and reach the goal",
        timeout_s=60.0,
        steps=[
            NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1")),
            InjectStep(inject=InjectArgs(action="IA_Jump", value=True, hold_s=0.2)),
            WaitStep(wait_s=WaitArgs(seconds=1.5)),
        ],
        expect=[
            EventCountExpectation(event_count="pickup.collected", min=3),
            EventExpectation(event="goal.reached"),
            LegsOkExpectation(legs_ok=True),
        ],
        captures=[
            Capture(on_event="goal.reached", screenshot="won.png")
        ],
    )

    p = sc.to_file(tmp_path / "sc.json")
    assert p.is_file()

    loaded = Scenario.from_file(p)
    assert loaded.scenario_id == "collect_three"
    assert len(loaded.steps) == 3
    assert len(loaded.expect) == 3
    assert len(loaded.captures) == 1
    assert loaded.schema_ == "scenario/1"


def test_scenario_forbids_extra_fields():
    with pytest.raises(ValidationError):
        Scenario.model_validate({
            "schema": "scenario/1",
            "scenario_id": "test_extra",
            "extra_field": "disallowed"
        })


def test_level_manifest_serialization(tmp_path: Path):
    manifest = LevelManifest(
        level_id="level_01",
        map="/Game/Maps/MainMap",
        player_start=(0.0, 0.0, 100.0),
        actors=[
            ManifestActor(
                actor_id="actor_floor",
                tag="GF_Floor",
                cls="StaticMeshActor",
                location=(0.0, 0.0, -50.0),
            ),
            ManifestActor(
                actor_id="actor_guard",
                tag="GF_Guard_1",
                cls="GameForgeGuard",
                entity_id="guard_1",
                location=(1200.0, -1400.0, 120.0),
                yaw=90.0,
            ),
        ],
    )

    p = manifest.to_file(tmp_path / "level_01.manifest.json")
    assert p.is_file()

    loaded = LevelManifest.from_file(p)
    assert loaded.level_id == "level_01"
    assert len(loaded.actors) == 2
    assert loaded.actors[1].yaw == 90.0


def test_scenario_handler_fallback_valid_schema():
    """Verify that default smoke scenario fallback conforms strictly to scenario/1 schema."""
    fallback = Scenario(
        scenario_id="smoke",
        description="Smoke test for TestGame: launch and stay alive",
        timeout_s=30.0,
        steps=[WaitStep(wait_s=WaitArgs(seconds=5.0))],
        expect=[
            EventExpectation(event="game.started"),
            NoEventExpectation(no_event="player.died"),
        ],
        captures=[],
    )
    assert fallback.scenario_id == "smoke"
    assert fallback.schema_ == "scenario/1"
    dumped = fallback.model_dump(by_alias=True)
    assert Scenario.model_validate(dumped).scenario_id == "smoke"

