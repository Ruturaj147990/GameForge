"""Unit tests for Scenario generator (WI-3.5)."""

from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.design.gds import ScenarioRef, EventOccurred
from src.gameforge_ide.qa.generate import generate
from src.gameforge_ide.qa.manifest import LevelManifest, ManifestActor


def test_scenario_generation_smoke_and_pickups():
    gds = preset_platformer()
    from src.gameforge_ide.design.gds import CountAtLeast
    gds.goals.win = [CountAtLeast(kind="count_at_least", event="pickup.collected", n=5)]
    # Add explicit scenario refs
    gds.acceptance.scenarios = [
        ScenarioRef(scenario_id="smoke_test", derived_from="smoke"),
        ScenarioRef(scenario_id="win_test", derived_from="goals.win[0]"),
    ]

    manifest = LevelManifest(
        level_id="lvl1",
        map="/Game/Maps/KitTest",
        player_start=(0.0, 0.0, 100.0),
        actors=[
            ManifestActor(
                actor_id="p1",
                tag="GF_Pickup_1",
                cls="GameForgePickup",
                location=(500.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="p2",
                tag="GF_Pickup_2",
                cls="GameForgePickup",
                location=(1000.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="p3",
                tag="GF_Pickup_3",
                cls="GameForgePickup",
                location=(1500.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="p4",
                tag="GF_Pickup_4",
                cls="GameForgePickup",
                location=(2000.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="p5",
                tag="GF_Pickup_5",
                cls="GameForgePickup",
                location=(2500.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="goal",
                tag="GF_Goal",
                cls="GameForgeGoal",
                location=(3000.0, 0.0, 100.0),
            ),
        ],
    )

    scenarios, gaps = generate(gds, [manifest])
    assert len(gaps) == 0, f"Unexpected gaps: {gaps}"
    assert len(scenarios) == 2

    # Check smoke scenario
    smoke = next(s for s in scenarios if s.scenario_id == "smoke_test")
    assert any(getattr(step, "wait_s", None) is not None for step in smoke.steps)

    # Check win scenario (pickups nearest-neighbour)
    win_sc = next(s for s in scenarios if s.scenario_id == "win_test")
    assert len(win_sc.steps) == 5
    tags = [step.navigate_to.tag for step in win_sc.steps]
    assert tags == ["GF_Pickup_1", "GF_Pickup_2", "GF_Pickup_3", "GF_Pickup_4", "GF_Pickup_5"]


def test_scenario_generation_score_and_board_win():
    from src.gameforge_ide.design.presets import preset_platformer
    from src.gameforge_ide.design.gds import StatCompare, EventOccurred, ScenarioRef
    from src.gameforge_ide.qa.manifest import LevelManifest, ManifestActor
    from src.gameforge_ide.qa.generate import generate

    gds = preset_platformer()
    gds.goals.win = [
        StatCompare(stat="game.score", op=">=", value=2.0),
        EventOccurred(event="board.win"),
    ]
    gds.acceptance.scenarios = [
        ScenarioRef(scenario_id="win_score", derived_from="goals.win[0]"),
        ScenarioRef(scenario_id="win_board", derived_from="goals.win[1]"),
    ]

    manifest = LevelManifest(
        level_id="lvl1",
        map="/Game/Maps/BoardTest",
        player_start=(0.0, 0.0, 100.0),
        actors=[
            ManifestActor(
                actor_id="p1",
                tag="GF_Pickup_1",
                cls="GameForgePickup",
                location=(200.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="p2",
                tag="GF_Pickup_2",
                cls="GameForgePickup",
                location=(400.0, 0.0, 100.0),
            ),
            ManifestActor(
                actor_id="b1",
                tag="GF_Board_1",
                cls="AGameForgeGridBoard",
                location=(600.0, 0.0, 100.0),
            ),
        ],
    )

    scenarios, gaps = generate(gds, [manifest])
    assert len(gaps) == 0, f"Unexpected gaps: {gaps}"
    assert len(scenarios) == 2

    sc_score = next(s for s in scenarios if s.scenario_id == "win_score")
    assert len(sc_score.steps) == 2
    assert sc_score.steps[0].navigate_to.tag == "GF_Pickup_1"
    assert sc_score.steps[1].navigate_to.tag == "GF_Pickup_2"

    sc_board = next(s for s in scenarios if s.scenario_id == "win_board")
    assert any(getattr(step, "select_actor", None) is not None for step in sc_board.steps)
    assert sc_board.expect[0].event == "board.win" 
