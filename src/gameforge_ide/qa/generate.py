"""Scenario generator: converts GDS acceptance specs and level manifests to executable scenarios (WI-3.5)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from ..design.gds import (
    Condition,
    CountAtLeast,
    EventOccurred,
    GameDesignSpec,
    ScenarioRef,
    StatCompare,
    TimerElapsed,
)
from .manifest import LevelManifest, ManifestActor
from .scenario import (
    EventCountExpectation,
    EventExpectation,
    InjectArgs,
    InjectStep,
    LegsOkExpectation,
    NavigateToArgs,
    NavigateToPointArgs,
    NavigateToPointStep,
    NavigateToStep,
    NoEventExpectation,
    Scenario,
    WaitArgs,
    WaitEventArgs,
    WaitEventStep,
    WaitStep,
)


@dataclass
class ScenarioGap:
    scenario_id: str
    reason: str


def _dist2d(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _resolve_condition(gds: GameDesignSpec, derived_from: str) -> Optional[Union[Condition, str]]:
    if derived_from == "smoke":
        return "smoke"
    if derived_from.startswith("goals.win["):
        try:
            idx = int(derived_from[len("goals.win[") : -1])
            return gds.goals.win[idx]
        except (ValueError, IndexError):
            return None
    if derived_from.startswith("goals.lose["):
        try:
            idx = int(derived_from[len("goals.lose[") : -1])
            return gds.goals.lose[idx]
        except (ValueError, IndexError):
            return None
    return None


def generate(
    gds: GameDesignSpec, manifests: List[LevelManifest]
) -> Tuple[List[Scenario], List[ScenarioGap]]:
    scenarios: List[Scenario] = []
    gaps: List[ScenarioGap] = []

    manifest = manifests[0] if manifests else None
    actors: List[ManifestActor] = manifest.actors if manifest else []
    player_start = manifest.player_start if manifest else (0.0, 0.0, 100.0)

    for ref in gds.acceptance.scenarios:
        scenario_id = ref.scenario_id
        cond = _resolve_condition(gds, ref.derived_from)

        if cond == "smoke":
            scenarios.append(
                Scenario(
                    scenario_id=scenario_id,
                    description="Smoke test: game starts and player stays alive for 5s",
                    timeout_s=30.0,
                    steps=[WaitStep(wait_s=WaitArgs(seconds=5.0))],
                    expect=[
                        EventExpectation(event="game.started"),
                        NoEventExpectation(no_event="player.died"),
                    ],
                )
            )
            continue

        if cond is None:
            gaps.append(
                ScenarioGap(
                    scenario_id, f"unable to resolve condition for derived_from '{ref.derived_from}'"
                )
            )
            continue

        # 1. CountAtLeast (e.g. pickup collection)
        if isinstance(cond, CountAtLeast):
            if cond.event == "pickup.collected" or "pickup" in cond.event:
                pickups = [
                    a
                    for a in actors
                    if "Pickup" in a.cls
                    or a.tag.startswith("GF_Pickup")
                    or (cond.source and a.entity_id == cond.source)
                ]
                if len(pickups) < cond.n:
                    gaps.append(
                        ScenarioGap(
                            scenario_id,
                            f"manifest has {len(pickups)} pickups, need {cond.n}",
                        )
                    )
                    continue

                # Greedy nearest-neighbour traversal
                steps = []
                cur = player_start
                remaining = list(pickups)
                for _ in range(cond.n):
                    nearest = min(remaining, key=lambda a: _dist2d(cur, a.location))
                    steps.append(
                        NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag))
                    )
                    cur = nearest.location
                    remaining.remove(nearest)

                scenarios.append(
                    Scenario(
                        scenario_id=scenario_id,
                        description=f"Collect {cond.n} pickups nearest to player start",
                        timeout_s=120.0,
                        steps=steps,
                        expect=[
                            EventCountExpectation(
                                event_count=cond.event,
                                min=cond.n,
                                entity=cond.source,
                            ),
                            LegsOkExpectation(legs_ok=True),
                        ],
                    )
                )
                continue
            else:
                gaps.append(
                    ScenarioGap(scenario_id, f"no strategy for CountAtLeast on {cond.event}")
                )
                continue

        # 2. EventOccurred
        if isinstance(cond, EventOccurred):
            if cond.event == "goal.reached":
                goals = [
                    a
                    for a in actors
                    if "Goal" in a.cls
                    or a.tag == "GF_Goal"
                    or (cond.source and a.entity_id == cond.source)
                ]
                if not goals:
                    gaps.append(ScenarioGap(scenario_id, "no goal actor in manifest"))
                    continue
                scenarios.append(
                    Scenario(
                        scenario_id=scenario_id,
                        description="Navigate to goal actor",
                        timeout_s=60.0,
                        steps=[
                            NavigateToStep(navigate_to=NavigateToArgs(tag=goals[0].tag))
                        ],
                        expect=[
                            EventExpectation(event=cond.event, entity=cond.source),
                            LegsOkExpectation(legs_ok=True),
                        ],
                    )
                )
                continue

            if cond.event in ("guard.spotted_player", "caught_by_guard"):
                guards = [
                    a
                    for a in actors
                    if "Guard" in a.cls
                    or a.tag.startswith("GF_Guard")
                    or (cond.source and a.entity_id == cond.source)
                ]
                if not guards:
                    gaps.append(ScenarioGap(scenario_id, "no guard actor in manifest"))
                    continue
                guard = guards[0]
                rad = math.radians(guard.yaw)
                x = guard.location[0] + 600.0 * math.cos(rad)
                y = guard.location[1] + 600.0 * math.sin(rad)
                z = guard.location[2]

                scenarios.append(
                    Scenario(
                        scenario_id=scenario_id,
                        description="Walk 600cm in front of guard to trigger spotted",
                        timeout_s=60.0,
                        steps=[
                            NavigateToPointStep(
                                navigate_to_point=NavigateToPointArgs(x=x, y=y, z=z)
                            ),
                            WaitEventStep(
                                wait_event=WaitEventArgs(
                                    e="guard.spotted_player",
                                    count=1,
                                    entity=cond.source,
                                    timeout_s=30.0,
                                )
                            ),
                        ],
                        expect=[EventExpectation(event="guard.spotted_player", entity=cond.source)],
                    )
                )
                continue

            if cond.event == "objective.completed":
                givers = [a for a in actors if "QuestGiver" in a.cls or a.tag == "GF_Giver"]
                if not givers:
                    gaps.append(ScenarioGap(scenario_id, "no quest giver actor in manifest"))
                    continue
                giver = givers[0]
                obj_id = cond.source or "relics"
                obj_pickups = [
                    a
                    for a in actors
                    if "Pickup" in a.cls
                    and (a.entity_id == obj_id or a.tag.startswith("GF_Relic") or a.tag.startswith("GF_Pickup"))
                ]
                steps = [NavigateToStep(navigate_to=NavigateToArgs(tag=giver.tag))]
                cur = giver.location
                remaining = list(obj_pickups)
                while remaining:
                    nearest = min(remaining, key=lambda a: _dist2d(cur, a.location))
                    steps.append(
                        NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag))
                    )
                    cur = nearest.location
                    remaining.remove(nearest)
                steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=giver.tag)))

                scenarios.append(
                    Scenario(
                        scenario_id=scenario_id,
                        description="Complete quest: giver -> pickups -> turn in",
                        timeout_s=120.0,
                        steps=steps,
                        expect=[EventExpectation(event="objective.completed")],
                    )
                )
                continue

            gaps.append(
                ScenarioGap(scenario_id, f"no strategy for EventOccurred on {cond.event}")
            )
            continue

        # 3. StatCompare (e.g. player.health <= 0)
        if isinstance(cond, StatCompare):
            if cond.stat == "player.health" and cond.op in ("<=", "<") and cond.value <= 0:
                hazards = [
                    a
                    for a in actors
                    if "Hazard" in a.cls
                    or "Enemy" in a.cls
                    or a.tag.startswith("GF_Hazard")
                    or a.tag.startswith("GF_Enemy")
                ]
                if not hazards:
                    gaps.append(ScenarioGap(scenario_id, "no hazard or enemy actor in manifest"))
                    continue
                nearest = min(hazards, key=lambda a: _dist2d(player_start, a.location))
                scenarios.append(
                    Scenario(
                        scenario_id=scenario_id,
                        description="Walk to hazard/enemy to test player death",
                        timeout_s=60.0,
                        steps=[
                            NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag)),
                            WaitStep(wait_s=WaitArgs(seconds=10.0)),
                        ],
                        expect=[EventExpectation(event="player.died")],
                    )
                )
                continue
            else:
                gaps.append(
                    ScenarioGap(scenario_id, f"no strategy for StatCompare on {cond.stat}")
                )
                continue

        # 4. TimerElapsed
        if isinstance(cond, TimerElapsed):
            scenarios.append(
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Wait for timer ({cond.seconds}s)",
                    timeout_s=cond.seconds + 30.0,
                    steps=[WaitStep(wait_s=WaitArgs(seconds=cond.seconds + 2.0))],
                    expect=[],  # P5 adds win/lose
                )
            )
            continue

        gaps.append(ScenarioGap(scenario_id, f"needs P5 rules engine for {type(cond).__name__}"))

    return scenarios, gaps
