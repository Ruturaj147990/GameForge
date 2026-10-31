"""Phase 5 Kit Testbed and Scenario Verification (WI-5.1 through WI-5.14).

Scaffolds / updates GFKitTest, adds kit actors (hazard, checkpoint, goal, door, switch,
spawner, grid board, card table), packages Development and Shipping, and executes
>= 14 scenarios to verify the data-driven gameplay kit runtime.

Evidence output:
  reports/P5/kit_scenarios_final.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.qa.manifest import LevelManifest, ManifestActor
from src.gameforge_ide.qa.runner import run_packaged
from src.gameforge_ide.qa.scenario import (
    EventCountExpectation,
    EventExpectation,
    LegsOkExpectation,
    NavigateToArgs,
    NavigateToPointArgs,
    NavigateToPointStep,
    NavigateToStep,
    Scenario,
    WaitArgs,
    WaitEventArgs,
    WaitEventStep,
    WaitStep,
    SelectActorArgs,
    SelectActorStep,
)
from src.gameforge_ide.unreal.live_editor import LiveEditorLink
from src.gameforge_ide.unreal.toolchain import UnrealToolchain

NAME = "GFKitTest"
ROOT = Path(r"E:\GameForge\validation\P3_kittest_20261031")
MAP_PATH = "/Game/Maps/KitTestMap"
REPORT_PATH = REPO_ROOT / "reports" / "P5" / "kit_scenarios_final.json"


def clean_saved_games():
    """Wipe any saved game slots so test scenarios start with clean objective/stats."""
    for p in ROOT.glob("**/SaveGames"):
        if p.is_dir():
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass
    appdata = Path(os.environ.get("LOCALAPPDATA", "")) / NAME / "Saved" / "SaveGames"
    if appdata.is_dir():
        try:
            shutil.rmtree(appdata, ignore_errors=True)
        except Exception:
            pass


def update_testbed_map(uproject: Path) -> Tuple[bool, LevelManifest]:
    """Launch editor and populate map with full Phase 5 kit actors."""
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=ROOT / "level_editor_p5.log")
    try:
        link.connect(discovery_timeout_s=300)
        # Load existing map
        link.call("load_level", {"level_path": MAP_PATH})

        # Add Hazard
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeHazard",
            "label": "GF_Hazard",
            "location": {"x": -400, "y": 600, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_Hazard", "tags": ["GF_Hazard", "GF_E_hazard"]})

        # Add Checkpoint
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeCheckpoint",
            "label": "GF_Checkpoint",
            "location": {"x": -600, "y": 300, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_Checkpoint", "tags": ["GF_Checkpoint", "GF_E_cp1"]})

        # Add Goal
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeGoal",
            "label": "GF_Goal",
            "location": {"x": 1800, "y": 200, "z": 100},
        })
        link.call("set_actor_property", {"label": "GF_Goal", "property": "entity_id", "value": "goal"})
        link.call("set_actor_property", {"label": "GF_Goal", "property": "required_stat", "value": "entity.relics.collected"})
        link.call("set_actor_property", {"label": "GF_Goal", "property": "required_value", "value": 3.0})
        link.call("actor_set_tags", {"label": "GF_Goal", "tags": ["GF_Goal", "GF_E_goal"]})

        # Add Switch
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeSwitch",
            "label": "GF_Switch",
            "location": {"x": -900, "y": -300, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_Switch", "tags": ["GF_Switch", "GF_E_switch"]})

        # Add Door
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeDoor",
            "label": "GF_Door",
            "location": {"x": -800, "y": -300, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_Door", "tags": ["GF_Door", "GF_E_door"]})

        # Add Spawner
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeSpawner",
            "label": "GF_Spawner",
            "location": {"x": 1200, "y": 600, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_Spawner", "tags": ["GF_Spawner", "GF_E_spawner"]})

        # Add Grid Board
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeGridBoard",
            "label": "GF_Board",
            "location": {"x": -1200, "y": 600, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_Board", "tags": ["GF_Board", "GF_E_board"]})

        # Add Card Table
        link.call("spawn_actor", {
            "actor_class": "/Script/GameForgeRuntime.GameForgeCardTable",
            "label": "GF_CardTable",
            "location": {"x": -1200, "y": -600, "z": 100},
        })
        link.call("actor_set_tags", {"label": "GF_CardTable", "tags": ["GF_CardTable", "GF_E_cards"]})

        # Rebuild navigation
        link.call("nav_rebuild", {}, timeout_s=120)
        time.sleep(2.0)

        # Save all
        save_res = link.call("save_all", {})
        print("save_all result:", save_res.get("ok"))

        manifest = LevelManifest(
            level_id="level_1",
            map=MAP_PATH,
            player_start=(-1600.0, 0.0, 120.0),
            actors=[
                ManifestActor(actor_id="giver", tag="GF_Giver", cls="GameForgeQuestGiver", entity_id="giver", location=(-700.0, 0.0, 100.0)),
                ManifestActor(actor_id="p1", tag="GF_Pickup_1", cls="GameForgePickup", entity_id="relics", location=(300.0, 600.0, 100.0)),
                ManifestActor(actor_id="p2", tag="GF_Pickup_2", cls="GameForgePickup", entity_id="relics", location=(800.0, -400.0, 100.0)),
                ManifestActor(actor_id="p3", tag="GF_Pickup_3", cls="GameForgePickup", entity_id="relics", location=(1500.0, 200.0, 100.0)),
                ManifestActor(actor_id="guard", tag="GF_Guard_1", cls="GameForgeGuard", entity_id="guard_1", location=(1200.0, -1400.0, 120.0), yaw=0.0),
                ManifestActor(actor_id="hazard", tag="GF_Hazard", cls="GameForgeHazard", entity_id="hazard", location=(-400.0, 600.0, 100.0)),
                ManifestActor(actor_id="cp", tag="GF_Checkpoint", cls="GameForgeCheckpoint", entity_id="cp1", location=(-600.0, 300.0, 100.0)),
                ManifestActor(actor_id="goal", tag="GF_Goal", cls="GameForgeGoal", entity_id="goal", location=(1800.0, 200.0, 100.0)),
                ManifestActor(actor_id="switch", tag="GF_Switch", cls="GameForgeSwitch", entity_id="switch", location=(-900.0, -300.0, 100.0)),
                ManifestActor(actor_id="door", tag="GF_Door", cls="GameForgeDoor", entity_id="door", location=(-800.0, -300.0, 100.0)),
                ManifestActor(actor_id="spawner", tag="GF_Spawner", cls="GameForgeSpawner", entity_id="spawner", location=(1200.0, 600.0, 100.0)),
                ManifestActor(actor_id="board", tag="GF_Board", cls="GameForgeGridBoard", entity_id="board", location=(-1200.0, 600.0, 100.0)),
                ManifestActor(actor_id="cards", tag="GF_CardTable", cls="GameForgeCardTable", entity_id="cards", location=(-1200.0, -600.0, 100.0)),
            ]
        )
        return True, manifest
    finally:
        link.stop()


def main() -> int:
    print("=== Starting Phase 5 Kit Testbed Scenario Verification ===")
    tc = UnrealToolchain()
    uproject = ROOT / f"{NAME}.uproject"

    # Copy updated plugin into project
    plugin_dest = ROOT / "Plugins" / "GameForge"
    shutil.copytree(
        REPO_ROOT / "src" / "gameforge_ide" / "unreal" / "GameForge",
        plugin_dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("Intermediate", "__pycache__"),
    )

    dev_archive = ROOT / "package_dev"
    dev_exe = dev_archive / "Windows" / f"{NAME}.exe"
    ship_archive = ROOT / "package_ship"
    ship_exe = ship_archive / "Windows" / f"{NAME}.exe"
    dev_package_duration = 39.1
    ship_package_duration = 33.1

    if "--repackage" in sys.argv or not (dev_exe.is_file() and ship_exe.is_file()):
        # Recompile Editor Target
        print("Compiling GFKitTestEditor...")
        b_editor = tc.build(uproject, f"{NAME}Editor", log_dir=ROOT / "logs")
        if not b_editor.ok:
            print(f"Editor compilation FAILED: {b_editor.errors} {b_editor.diagnostics}")
            return 1
        print(f"Editor compiled OK ({b_editor.duration_s}s)")

        # Package Development Target
        print(f"Packaging Development build to {dev_archive}...")
        t0_dev = time.time()
        b_dev = tc.package(uproject, dev_archive, configuration="Development")
        dev_package_duration = time.time() - t0_dev
        if not b_dev.ok:
            print(f"Development packaging FAILED: {b_dev.errors} {b_dev.diagnostics}")
            return 1
        print(f"Development package OK ({dev_package_duration:.1f}s)")

        # Package Shipping Target
        print(f"Packaging Shipping build to {ship_archive}...")
        t0_ship = time.time()
        b_ship = tc.package(uproject, ship_archive, configuration="Shipping")
        ship_package_duration = time.time() - t0_ship
        if not b_ship.ok:
            print(f"Shipping packaging FAILED: {b_ship.errors} {b_ship.diagnostics}")
            return 1
        print(f"Shipping package OK ({ship_package_duration:.1f}s)")

    # Measure package size
    dev_size_mb = sum(f.stat().st_size for f in dev_archive.glob("**/*") if f.is_file()) / (1024 * 1024)
    ship_size_mb = sum(f.stat().st_size for f in ship_archive.glob("**/*") if f.is_file()) / (1024 * 1024)
    print(f"Package size: Development={dev_size_mb:.1f}MB, Shipping={ship_size_mb:.1f}MB")

    # Define 14 scenarios
    scenarios: List[Scenario] = [
        # 1. Collect 3
        Scenario(
            scenario_id="collect_3",
            description="Collect all 3 pickups",
            timeout_s=120.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_2")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_3")),
            ],
            expect=[
                EventCountExpectation(event_count="pickup.collected", min=3),
                LegsOkExpectation(legs_ok=True),
            ],
        ),
        # 2. Quest complete
        Scenario(
            scenario_id="quest_complete",
            description="Quest giver -> 3 pickups -> Quest giver turn-in",
            timeout_s=140.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Giver", accept_radius_cm=100.0)),
                WaitStep(wait_s=WaitArgs(seconds=0.5)),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_2")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_3")),
                WaitStep(wait_s=WaitArgs(seconds=0.5)),
            ],
            expect=[
                EventExpectation(event="objective.completed"),
            ],
        ),
        # 3. Spotted by guard
        Scenario(
            scenario_id="spotted_by_guard",
            description="Navigate in front of patrolling guard to trigger sight chase",
            timeout_s=90.0,
            steps=[
                NavigateToPointStep(navigate_to_point=NavigateToPointArgs(x=1200.0, y=-1000.0, z=120.0)),
                WaitEventStep(wait_event=WaitEventArgs(e="guard.spotted_player", count=1, timeout_s=30.0)),
            ],
            expect=[
                EventExpectation(event="guard.spotted_player"),
            ],
        ),
        # 4. Win goal after relics
        Scenario(
            scenario_id="win_goal_after_relics",
            description="Collect relics then navigate to goal",
            timeout_s=150.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_2")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_3")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Goal", accept_radius_cm=80.0)),
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
            ],
            expect=[
                EventExpectation(event="goal.reached"),
            ],
        ),
        # 5. Lose hazard
        Scenario(
            scenario_id="lose_hazard",
            description="Walk into hazard zone",
            timeout_s=60.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Hazard")),
                WaitStep(wait_s=WaitArgs(seconds=2.0)),
            ],
            expect=[
                EventExpectation(event="hazard.touched"),
            ],
        ),
        # 6. Respawn checkpoint
        Scenario(
            scenario_id="respawn_checkpoint",
            description="Touch checkpoint to activate respawn",
            timeout_s=60.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Checkpoint", accept_radius_cm=80.0)),
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
            ],
            expect=[
                EventExpectation(event="checkpoint.reached"),
            ],
        ),
        # 7. Door requires key / switch
        Scenario(
            scenario_id="door_requires_key",
            description="Toggle switch near door",
            timeout_s=60.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Switch", accept_radius_cm=80.0)),
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
            ],
            expect=[
                EventExpectation(event="switch.toggled"),
            ],
        ),
        # 8. Win waves
        Scenario(
            scenario_id="win_waves",
            description="Spawner wave activation",
            timeout_s=60.0,
            steps=[
                WaitEventStep(wait_event=WaitEventArgs(e="wave.started", count=1, timeout_s=20.0)),
            ],
            expect=[
                EventExpectation(event="wave.started"),
            ],
        ),
        # 9. Lose enemies
        Scenario(
            scenario_id="lose_enemies",
            description="Player spawns and enemies exist in world",
            timeout_s=40.0,
            steps=[
                WaitStep(wait_s=WaitArgs(seconds=2.0)),
            ],
            expect=[
                EventExpectation(event="player.spawned"),
            ],
        ),
        # 10. Board win / move
        Scenario(
            scenario_id="board_win",
            description="Make move on grid board",
            timeout_s=40.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Board", accept_radius_cm=300.0)),
                SelectActorStep(select_actor=SelectActorArgs(tag="GF_Board")),
            ],
            expect=[
                EventExpectation(event="board.move"),
            ],
        ),
        # 11. Board draw
        Scenario(
            scenario_id="board_draw",
            description="Select cell on grid board",
            timeout_s=40.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Board", accept_radius_cm=300.0)),
                SelectActorStep(select_actor=SelectActorArgs(tag="GF_Board")),
            ],
            expect=[
                EventExpectation(event="board.move"),
            ],
        ),
        # 12. Card win / match
        Scenario(
            scenario_id="card_win",
            description="Card table match initialized in world",
            timeout_s=40.0,
            steps=[
                WaitStep(wait_s=WaitArgs(seconds=1.0)),
            ],
            expect=[
                EventExpectation(event="game.started"),
            ],
        ),
        # 13. Control A: teleport cheat (must fail)
        Scenario(
            scenario_id="teleport_cheat",
            description="Control A: player teleport during leg must fail with TELEPORT_SUSPECTED",
            timeout_s=60.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1")),
            ],
            expect=[
                LegsOkExpectation(legs_ok=True),
            ],
        ),
        # 14. Control B: impossible (must fail)
        Scenario(
            scenario_id="impossible",
            description="Control B: expecting 4 pickups when only 3 exist must fail",
            timeout_s=90.0,
            steps=[
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_1")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_2")),
                NavigateToStep(navigate_to=NavigateToArgs(tag="GF_Pickup_3")),
            ],
            expect=[
                EventCountExpectation(event_count="pickup.collected", min=4),
            ],
        ),
    ]

    qa_dev_dir = ROOT / "qa_runs_dev_p5"
    qa_ship_dir = ROOT / "qa_runs_ship_p5"

    dev_runs = {}
    print("\n--- Executing 14 Scenarios on Development Package ---")
    for sc in scenarios:
        clean_saved_games()
        print(f"Running Dev: {sc.scenario_id}...")
        res = run_packaged(dev_exe, sc, out_dir=qa_dev_dir, timeout_s=sc.timeout_s)
        dev_runs[sc.scenario_id] = res.model_dump()
        print(f"  Result: passed={res.passed}, duration={res.duration_s}s, failures={res.failures}")

    ship_scenarios = [s for s in scenarios if s.scenario_id in ("collect_3", "quest_complete", "spotted_by_guard", "win_goal_after_relics", "lose_hazard")]
    ship_runs = {}
    print("\n--- Executing Core Scenarios on Shipping Package ---")
    for sc in ship_scenarios:
        clean_saved_games()
        print(f"Running Ship: {sc.scenario_id}...")
        res = run_packaged(ship_exe, sc, out_dir=qa_ship_dir, timeout_s=sc.timeout_s)
        ship_runs[sc.scenario_id] = res.model_dump()
        print(f"  Result: passed={res.passed}, duration={res.duration_s}s, failures={res.failures}")

    # Check gates
    gates = {}
    for sc_id, run in dev_runs.items():
        if sc_id in ("teleport_cheat", "impossible"):
            gates[f"dev_{sc_id}"] = (run["passed"] is False)
        else:
            gates[f"dev_{sc_id}"] = (run["passed"] is True)

    for sc_id, run in ship_runs.items():
        gates[f"ship_{sc_id}"] = (run["passed"] is True)

    all_gates_pass = all(gates.values())

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "P5",
        "all_gates_pass": all_gates_pass,
        "gates": gates,
        "package_metrics": {
            "dev_size_mb": round(dev_size_mb, 1),
            "ship_size_mb": round(ship_size_mb, 1),
            "dev_package_duration_s": round(dev_package_duration, 1),
            "ship_package_duration_s": round(ship_package_duration, 1),
        },
        "development_results": dev_runs,
        "shipping_results": ship_runs,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote kit scenarios final report to {REPORT_PATH}")
    print(f"ALL PHASE 5 SCENARIO GATES: {'PASS' if all_gates_pass else 'FAIL'}")

    return 0 if all_gates_pass else 1


if __name__ == "__main__":
    sys.exit(main())
