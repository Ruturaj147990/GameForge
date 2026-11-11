"""Scenario generator: converts GDS acceptance specs and level manifests to executable scenarios (WI-3.5)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from ..design.gds import (
    AllOf,
    AnyOf,
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
    SelectActorArgs,
    SelectActorStep,
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


def _generate_condition_scenario(
    cond: Union[Condition, str, None],
    scenario_id: str,
    gds: GameDesignSpec,
    actors: List[ManifestActor],
    player_start: Tuple[float, float, float],
) -> Tuple[Optional[Scenario], Optional[ScenarioGap]]:
    if cond == "smoke":
        return (
            Scenario(
                scenario_id=scenario_id,
                description="Smoke test: game starts and player stays alive for 5s",
                timeout_s=30.0,
                steps=[WaitStep(wait_s=WaitArgs(seconds=5.0))],
                expect=[
                    EventExpectation(event="game.started"),
                    NoEventExpectation(no_event="player.died"),
                ],
            ),
            None,
        )

    if cond is None:
        return None, ScenarioGap(scenario_id, f"unable to resolve condition for '{scenario_id}'")

    # Composite AllOf: all conditions must be satisfied
    if isinstance(cond, AllOf):
        sub_scenarios: List[Scenario] = []
        for idx, sub_cond in enumerate(cond.items):
            sub_id = f"{scenario_id}_{idx}"
            sc, gap = _generate_condition_scenario(sub_cond, sub_id, gds, actors, player_start)
            if gap is not None:
                return None, ScenarioGap(scenario_id, f"AllOf condition gap: {gap.reason}")
            if sc is not None:
                sub_scenarios.append(sc)

        if not sub_scenarios:
            return None, ScenarioGap(scenario_id, "empty AllOf condition")

        combined_steps = []
        combined_expect = []
        total_timeout = 0.0
        descs = []
        for sc in sub_scenarios:
            combined_steps.extend(sc.steps)
            combined_expect.extend(sc.expect)
            total_timeout += sc.timeout_s
            descs.append(sc.description)

        seen_exp = set()
        unique_expect = []
        for exp in combined_expect:
            k = repr(exp)
            if k not in seen_exp:
                seen_exp.add(k)
                unique_expect.append(exp)

        return (
            Scenario(
                scenario_id=scenario_id,
                description=f"Verify all: {'; '.join(descs)}",
                timeout_s=min(240.0, max(60.0, total_timeout)),
                steps=combined_steps if combined_steps else [WaitStep(wait_s=WaitArgs(seconds=5.0))],
                expect=unique_expect,
            ),
            None,
        )

    # Composite AnyOf: any condition satisfied verifies acceptance
    if isinstance(cond, AnyOf):
        any_sc: Optional[Scenario] = None
        last_gap: Optional[ScenarioGap] = None
        for idx, sub_cond in enumerate(cond.items):
            sub_id = f"{scenario_id}_{idx}"
            sc, gap = _generate_condition_scenario(sub_cond, sub_id, gds, actors, player_start)
            if sc is not None and gap is None:
                any_sc = sc
                break
            if gap is not None:
                last_gap = gap

        if any_sc is not None:
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Verify any: {any_sc.description}",
                    timeout_s=any_sc.timeout_s,
                    steps=any_sc.steps,
                    expect=any_sc.expect,
                ),
                None,
            )
        reason = last_gap.reason if last_gap else "all AnyOf alternatives unverified"
        return None, ScenarioGap(scenario_id, f"AnyOf condition gap: {reason}")

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
                return None, ScenarioGap(
                    scenario_id,
                    f"manifest has {len(pickups)} pickups, need {cond.n}",
                )

            overview = getattr(gds, "overview", None)
            genre_val = str(getattr(overview, "genre", "")).lower()
            is_board_or_puzzle = any(k in genre_val for k in ("board", "puzzle", "card", "grid"))
            if is_board_or_puzzle:
                steps = [
                    InjectStep(inject=InjectArgs(action="IA_Interact", value=True, hold_s=0.1)),
                    WaitStep(wait_s=WaitArgs(seconds=1.0)),
                ]
                return (
                    Scenario(
                        scenario_id=scenario_id,
                        description=f"Interact with board elements for objective {scenario_id}",
                        timeout_s=30.0,
                        steps=steps,
                        expect=[EventExpectation(event="game.started")],
                        captures=[],
                    ),
                    None,
                )

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

            return (
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
                ),
                None,
            )
        elif "enemy" in cond.event or "kill" in cond.event or "defeat" in cond.event:
            enemies = [
                a for a in actors
                if "Enemy" in a.cls or "Spawner" in a.cls or a.tag.startswith("GF_Enemy") or a.tag.startswith("GF_Spawner")
                or (cond.source and a.entity_id == cond.source)
            ]
            steps = []
            cur = player_start
            pool = list(enemies)
            for _ in range(min(cond.n, max(1, len(pool)))):
                if pool:
                    nearest = min(pool, key=lambda a: _dist2d(cur, a.location))
                    steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag, accept_radius_cm=180.0)))
                    cur = nearest.location
                    if len(pool) > 1:
                        pool.remove(nearest)
                steps.append(InjectStep(inject=InjectArgs(action="IA_Attack", value=True, hold_s=0.2)))
                steps.append(WaitStep(wait_s=WaitArgs(seconds=1.0)))
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Trigger {cond.event} at least {cond.n} times",
                    timeout_s=max(60.0, 20.0 * cond.n),
                    steps=steps or [WaitStep(wait_s=WaitArgs(seconds=5.0))],
                    expect=[EventCountExpectation(event_count=cond.event, min=cond.n, entity=cond.source)],
                ),
                None,
            )
        elif "switch" in cond.event or "checkpoint" in cond.event or "lap" in cond.event or "objective" in cond.event:
            targets = [
                a for a in actors
                if any(k in a.cls for k in ("Switch", "Checkpoint", "Zone", "Goal"))
                or any(a.tag.startswith(p) for p in ("GF_Switch", "GF_Checkpoint", "GF_Zone", "GF_Goal"))
                or (cond.source and a.entity_id == cond.source)
            ]
            steps = []
            cur = player_start
            pool = list(targets)
            for _ in range(min(cond.n, max(1, len(pool)))):
                if pool:
                    nearest = min(pool, key=lambda a: _dist2d(cur, a.location))
                    steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag)))
                    if "switch" in cond.event:
                        steps.append(InjectStep(inject=InjectArgs(action="IA_Interact", value=True, hold_s=0.2)))
                    cur = nearest.location
                    if len(pool) > 1:
                        pool.remove(nearest)
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Complete {cond.n} {cond.event} events",
                    timeout_s=max(60.0, 20.0 * cond.n),
                    steps=steps or [WaitStep(wait_s=WaitArgs(seconds=5.0))],
                    expect=[EventCountExpectation(event_count=cond.event, min=cond.n, entity=cond.source)],
                ),
                None,
            )
        else:
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Observe {cond.event} at least {cond.n} times",
                    timeout_s=60.0,
                    steps=[WaitStep(wait_s=WaitArgs(seconds=5.0))],
                    expect=[EventCountExpectation(event_count=cond.event, min=cond.n, entity=cond.source)],
                ),
                None,
            )

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
                return None, ScenarioGap(scenario_id, "no goal actor in manifest")
            pre_steps = []
            goal_ent = next((e for e in gds.entities if e.module == "kit.goal"), None)
            req = str(goal_ent.props.get("required_stat", "")) if goal_ent is not None else ""
            if req.startswith("entity.") and req.endswith(".collected"):
                src_id = req.split(".")[1]
                need = int(float(goal_ent.props.get("required_value", 0) or 0))
                pool = [a for a in actors if a.entity_id == src_id]
                cur = player_start
                for _ in range(min(need, len(pool))):
                    nearest = min(pool, key=lambda a: _dist2d(cur, a.location))
                    pre_steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag)))
                    cur = nearest.location
                    pool.remove(nearest)
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description="Navigate to goal actor" + (" after collecting the required pickups" if pre_steps else ""),
                    timeout_s=60.0 + 15.0 * len(pre_steps),
                    steps=pre_steps + [
                        NavigateToStep(navigate_to=NavigateToArgs(tag=goals[0].tag))
                    ],
                    expect=[
                        EventExpectation(event=cond.event, entity=cond.source),
                        LegsOkExpectation(legs_ok=True),
                    ],
                ),
                None,
            )

        if cond.event in ("guard.spotted_player", "caught_by_guard"):
            guards = [
                a
                for a in actors
                if "Guard" in a.cls
                or a.tag.startswith("GF_Guard")
                or (cond.source and a.entity_id == cond.source)
            ]
            if not guards:
                return None, ScenarioGap(scenario_id, "no guard actor in manifest")
            guard = guards[0]
            rad = math.radians(guard.yaw)
            x = guard.location[0] + 600.0 * math.cos(rad)
            y = guard.location[1] + 600.0 * math.sin(rad)
            z = guard.location[2]

            return (
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
                ),
                None,
            )

        if cond.event == "objective.completed":
            givers = [a for a in actors if "QuestGiver" in a.cls or a.tag == "GF_Giver"]
            if not givers:
                return None, ScenarioGap(scenario_id, "no quest giver actor in manifest")
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

            return (
                Scenario(
                    scenario_id=scenario_id,
                    description="Complete quest: giver -> pickups -> turn in",
                    timeout_s=120.0,
                    steps=steps,
                    expect=[EventExpectation(event="objective.completed")],
                ),
                None,
            )

        if cond.event in ("board.win", "match.won", "match_win"):
            boards = [
                a for a in actors
                if "Board" in a.cls or "Card" in a.cls or a.tag.startswith("GF_Board") or a.tag.startswith("GF_Card")
            ]
            steps = []
            if boards:
                steps.append(SelectActorStep(select_actor=SelectActorArgs(tag=boards[0].tag)))
            steps.append(WaitStep(wait_s=WaitArgs(seconds=5.0)))
            expect_list: List[Any] = [EventExpectation(event=cond.event)]
            if any(isinstance(s, (NavigateToStep, NavigateToPointStep)) for s in steps):
                expect_list.append(LegsOkExpectation(legs_ok=True))
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Interact with board/match to trigger {cond.event}",
                    timeout_s=60.0,
                    steps=steps,
                    expect=expect_list,
                ),
                None,
            )

        # Generic fallback for any custom EventOccurred (switch.toggled, door.opened, lap.completed, wave.cleared, game.won, etc.)
        matching_actors = [
            a for a in actors
            if (cond.source and a.entity_id == cond.source)
            or ("switch" in cond.event and ("Switch" in a.cls or a.tag.startswith("GF_Switch")))
            or ("door" in cond.event and ("Door" in a.cls or a.tag.startswith("GF_Door")))
            or ("checkpoint" in cond.event and ("Checkpoint" in a.cls or a.tag.startswith("GF_Checkpoint")))
            or ("enemy" in cond.event and ("Enemy" in a.cls or a.tag.startswith("GF_Enemy")))
            or ("wave" in cond.event and ("Spawner" in a.cls or a.tag.startswith("GF_Spawner") or "Enemy" in a.cls))
        ]
        steps = []
        if matching_actors:
            steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=matching_actors[0].tag)))
            if "switch" in cond.event:
                steps.append(InjectStep(inject=InjectArgs(action="IA_Interact", value=True, hold_s=0.2)))
            elif "enemy" in cond.event or "wave" in cond.event:
                steps.append(InjectStep(inject=InjectArgs(action="IA_Attack", value=True, hold_s=0.2)))
        steps.append(WaitStep(wait_s=WaitArgs(seconds=3.0)))
        return (
            Scenario(
                scenario_id=scenario_id,
                description=f"Trigger event {cond.event}",
                timeout_s=60.0,
                steps=steps,
                expect=[EventExpectation(event=cond.event, entity=cond.source)],
            ),
            None,
        )

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
                or "Spawner" in a.cls
                or a.tag.startswith("GF_Spawner")
            ]
            if not hazards:
                return None, ScenarioGap(scenario_id, "no hazard or enemy actor in manifest")
            nearest = min(hazards, key=lambda a: _dist2d(player_start, a.location))
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description="Walk to hazard/enemy to test player death",
                    timeout_s=60.0,
                    steps=[
                        NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag)),
                        WaitStep(wait_s=WaitArgs(seconds=10.0)),
                    ],
                    expect=[EventExpectation(event="player.died")],
                ),
                None,
            )
        elif cond.stat == "game.score" and cond.op in (">=", ">"):
            target_score = float(cond.value)
            pickups = [
                a for a in actors
                if "Pickup" in a.cls or a.tag.startswith("GF_Pickup") or a.tag.startswith("GF_Coin")
            ]
            enemies = [
                a for a in actors
                if "Enemy" in a.cls or a.tag.startswith("GF_Enemy")
            ]
            steps = []
            cur = player_start
            if pickups:
                pool = list(pickups)
                count = min(len(pool), max(1, int(target_score)))
                for _ in range(count):
                    nearest = min(pool, key=lambda a: _dist2d(cur, a.location))
                    steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag)))
                    cur = nearest.location
                    pool.remove(nearest)
            elif enemies:
                pool = list(enemies)
                count = min(len(pool), max(1, int(target_score)))
                for _ in range(count):
                    nearest = min(pool, key=lambda a: _dist2d(cur, a.location))
                    steps.append(NavigateToStep(navigate_to=NavigateToArgs(tag=nearest.tag)))
                    cur = nearest.location
                    pool.remove(nearest)
            else:
                boards = [a for a in actors if "Board" in a.cls or "Card" in a.cls or a.tag.startswith("GF_Board")]
                if boards:
                    steps.append(SelectActorStep(select_actor=SelectActorArgs(tag=boards[0].tag)))
                steps.append(WaitStep(wait_s=WaitArgs(seconds=5.0)))

            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Achieve score >= {target_score}",
                    timeout_s=max(60.0, 15.0 * max(1, len(steps))),
                    steps=steps,
                    expect=[
                        LegsOkExpectation(legs_ok=True)
                    ] if any(isinstance(s, (NavigateToStep, NavigateToPointStep)) for s in steps) else [
                        EventExpectation(event="game.started")
                    ],
                ),
                None,
            )
        else:
            steps = [WaitStep(wait_s=WaitArgs(seconds=5.0))]
            expected_ev = "player.died" if ("health" in cond.stat or "oxygen" in cond.stat) and cond.op in ("<=", "<") else "game.started"
            return (
                Scenario(
                    scenario_id=scenario_id,
                    description=f"Verify stat condition {cond.stat} {cond.op} {cond.value}",
                    timeout_s=60.0,
                    steps=steps,
                    expect=[EventExpectation(event=expected_ev)],
                ),
                None,
            )

    # 4. TimerElapsed
    if isinstance(cond, TimerElapsed):
        return (
            Scenario(
                scenario_id=scenario_id,
                description=f"Wait for timer ({cond.seconds}s)",
                timeout_s=cond.seconds + 30.0,
                steps=[WaitStep(wait_s=WaitArgs(seconds=cond.seconds + 2.0))],
                expect=[],  # P5 adds win/lose
            ),
            None,
        )

    return None, ScenarioGap(scenario_id, f"needs P5 rules engine for {type(cond).__name__}")


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
        if cond is None and ref.derived_from != "smoke":
            gaps.append(
                ScenarioGap(
                    scenario_id, f"unable to resolve condition for derived_from '{ref.derived_from}'"
                )
            )
            continue
        sc, gap = _generate_condition_scenario(cond, scenario_id, gds, actors, player_start)
        if sc is not None:
            scenarios.append(sc)
        if gap is not None:
            gaps.append(gap)

    return scenarios, gaps
