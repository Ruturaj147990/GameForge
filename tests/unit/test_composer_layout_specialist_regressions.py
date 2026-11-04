"""Regression tests for Composer & Layout Specialist audit (DEF-103 to DEF-113).

Verifies permanent fixes for:
- DEF-103: Ballistic jump reachability formula solvable jumps and non-zero allowable gap
- DEF-104: Layouts generate watertight geometry with explicit static_mesh and material
- DEF-105: Dungeon floor centering and safety floor in rooms layout
- DEF-106: 3D course Euclidean platform matching and scatter snapping
- DEF-107: Multiple pickup entities in course layout coexistence without hijacking
- DEF-108: C++ codegen runtime and gameplay includes
- DEF-109: Duplicate PlayerStart spawning prevention
- DEF-110: Actor transform readback tolerance parser and yaw verification
- DEF-111: Direct Unreal property overrides preservation and asset flag emission
- DEF-112: Placement empty/degenerate polygon guards
- DEF-113: Intro cinematics dynamic focus kind mapping
"""
from __future__ import annotations

import math
import random
import pytest

from src.gameforge_ide.composer.layouts.course import validate_jump_reachability, plan_level as plan_course_level
from src.gameforge_ide.composer.layouts.rooms import plan_level as plan_rooms_level
from src.gameforge_ide.composer.layouts.open_world import plan_level as plan_open_world_level
from src.gameforge_ide.composer.layouts.arena import plan_level as plan_arena_level
from src.gameforge_ide.composer.layouts.board import plan_level as plan_board_level
from src.gameforge_ide.composer.layouts.lanes import plan_level as plan_lanes_level
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.composer.level_ops import plan_to_op_calls, verify_placed_actor_transforms
from src.gameforge_ide.composer.codegen import generate_source, generate_header, safety_scan
from src.gameforge_ide.composer.placement import is_point_in_polygon, scatter, along_path
from src.gameforge_ide.composer.cinematics import generate_intro_cinematic
from src.gameforge_ide.composer.model import LevelPlan, PlacedActor, OpCall
from src.gameforge_ide.design.presets import preset_platformer, preset_tic_tac_toe, preset_relic_hunt
from src.gameforge_ide.design.gds import EntitySpec, GameDesignSpec, PresentationSpec, IntroSpec, LevelSpec, Vec2


# ---------------------------------------------------------------------------
# DEF-103: Ballistic Jump Reachability Formula & Course Level Generation
# ---------------------------------------------------------------------------

def test_def103_ballistic_jump_reachability_solvable_jumps_and_nonzero_gap():
    """Verify solvable jumps reach and exceeding heights return positive allowable gaps."""
    # Standard solvable jump (speed=600, v=650, g=1.2 -> max_h ~ 179.6cm)
    reachable, max_h, max_g = validate_jump_reachability(gap_cm=280.0, height_delta_cm=60.0)
    assert reachable is True
    assert max_h > 150.0
    assert max_g > 300.0

    # High jump solvable in physical reach (e.g. 150cm)
    reachable_150, max_h_150, max_g_150 = validate_jump_reachability(gap_cm=100.0, height_delta_cm=150.0)
    assert max_h_150 > 150.0
    assert max_g_150 > 0.0

    # High jump exceeding max height must return a positive max_allowable_gap (> 0), never 0.0
    reachable_high, _, max_g_high = validate_jump_reachability(gap_cm=100.0, height_delta_cm=350.0)
    assert reachable_high is False
    assert max_g_high > 100.0, f"max_g must be positive at apex, got {max_g_high}"

    # Downward jump (height_delta_cm < 0) has increased airtime and greater allowable gap
    _, _, max_g_down = validate_jump_reachability(gap_cm=300.0, height_delta_cm=-80.0)
    _, _, max_g_flat = validate_jump_reachability(gap_cm=300.0, height_delta_cm=0.0)
    assert max_g_down > max_g_flat


def test_def103_course_platforms_no_overlap_and_safe_z():
    """Verify course layout platforms never stack at identical X and stay above KillZ."""
    gds = preset_platformer()
    rng = random.Random(42)
    level_spec = LevelSpec(level_id="level_1", layout="course", size_m=Vec2(x=60.0, y=60.0), seed=42)
    plan = plan_course_level(level_spec, gds, rng)

    platform_ops = [
        op for op in plan.geometry_ops
        if op.op == "spawn_actor" and "GF_Platform_" in op.args.get("label", "")
    ]
    assert len(platform_ops) >= 7

    xs = [op.args["location"]["x"] for op in platform_ops]
    zs = [op.args["location"]["z"] for op in platform_ops]

    # Verify each subsequent platform has strictly increasing X (no overlapping platforms)
    for i in range(1, len(xs)):
        assert xs[i] > xs[i - 1] + 100.0, f"Platform {i} at x={xs[i]} overlapped platform {i-1} at x={xs[i-1]}"

    # Verify no platform drops below -400.0cm (safely above player KillZ of -500cm)
    for i, z in enumerate(zs):
        assert z >= -350.0, f"Platform {i} at z={z} dropped dangerously close to KillZ (-500)"


# ---------------------------------------------------------------------------
# DEF-104: Complete Watertight Geometry with Static Mesh and Material
# ---------------------------------------------------------------------------

def test_def104_all_six_layouts_generate_watertight_geometry_with_mesh_and_material():
    """Verify all 6 layouts emit static_mesh and material on every StaticMeshActor."""
    rng = random.Random(101)
    lvl = LevelSpec(level_id="level_1", layout="arena", size_m=Vec2(x=60.0, y=60.0), seed=101)
    gds = preset_platformer()

    layout_factories = [
        ("course", plan_course_level),
        ("rooms", plan_rooms_level),
        ("open_world", plan_open_world_level),
        ("arena", plan_arena_level),
        ("board", plan_board_level),
        ("lanes", plan_lanes_level),
    ]

    for name, factory in layout_factories:
        plan = factory(lvl, gds, rng)
        assert len(plan.geometry_ops) >= 1, f"Layout {name} has no geometry ops"

        for op in plan.geometry_ops:
            if op.op == "spawn_actor" and op.args.get("actor_class") == "StaticMeshActor":
                label = op.args.get("label", "")
                assert "static_mesh" in op.args, f"Layout {name} op {label} missing 'static_mesh'"
                assert op.args["static_mesh"] == "/Engine/BasicShapes/Cube.Cube"
                assert "material" in op.args, f"Layout {name} op {label} missing 'material'"
                assert op.args["material"].startswith("/Game/LevelPrototyping/Materials/")


# ---------------------------------------------------------------------------
# DEF-105: Rooms Layout Dungeon Floor Centering & Safety Floor
# ---------------------------------------------------------------------------

def test_def105_rooms_floor_centering_and_safety_floor():
    """Verify dungeon floor cubes are centered on grid cells and safety floor covers bounds."""
    gds = preset_relic_hunt()
    rng = random.Random(2026)
    lvl = LevelSpec(level_id="level_1", layout="rooms", size_m=Vec2(x=80.0, y=80.0), seed=2026)
    plan = plan_rooms_level(lvl, gds, rng)

    floor_ops = [
        op for op in plan.geometry_ops
        if op.op == "spawn_actor" and "GF_Dungeon_Floor_" in op.args.get("label", "")
    ]
    assert len(floor_ops) >= 10

    # Floors must be centered at x*grid + grid/2, y*grid + grid/2 (mod 400 == 200)
    for op in floor_ops:
        loc = op.args["location"]
        assert (loc["x"] % 400.0) == pytest.approx(200.0, abs=1.0)
        assert (loc["y"] % 400.0) == pytest.approx(200.0, abs=1.0)
        assert loc["z"] == -10.0

    # Verify dungeon safety floor exists covering extent
    safety_floors = [
        op for op in plan.geometry_ops
        if op.op == "spawn_actor" and op.args.get("label") == "GF_Dungeon_SafetyFloor"
    ]
    assert len(safety_floors) == 1
    assert safety_floors[0].args["location"]["z"] == -25.0
    assert safety_floors[0].args["scale"]["x"] >= 10.0


# ---------------------------------------------------------------------------
# DEF-106: 3D Course Euclidean Matching & Spread Offsets
# ---------------------------------------------------------------------------

def test_def106_compose_3d_course_euclidean_and_spread_offsets():
    """Verify scattered entities in course and rooms layouts snap safely without stacking."""
    gds = preset_platformer()
    # Add multiple unplaced entities (e.g. patrol enemies)
    gds.entities.append(
        EntitySpec(
            entity_id="patrol_guard",
            level_id="level_1",
            kind="enemy",
            module="kit.enemy_melee",
            props={"count": 3, "attack_damage": 25.0},
        )
    )
    comp = compose(gds)
    level = comp.levels[0]

    guard_actors = [a for a in level.actors if a.entity_id == "patrol_guard"]
    assert len(guard_actors) == 3

    # Verify guard actors do not share identical locations (spread offset applied)
    locs = [a.location for a in guard_actors]
    for i in range(len(locs)):
        for j in range(i + 1, len(locs)):
            dist = math.hypot(locs[i][0] - locs[j][0], locs[i][1] - locs[j][1])
            assert dist > 10.0, f"Entities {guard_actors[i].actor_id} and {guard_actors[j].actor_id} stacked at {locs[i]}"


# ---------------------------------------------------------------------------
# DEF-107: Course Multiple Pickup Entity Types Coexistence
# ---------------------------------------------------------------------------

def test_def107_course_multiple_pickup_entity_kinds_coexist():
    """Verify course layout supports multiple distinct pickup types without hijacking IDs."""
    gds = preset_platformer()
    # preset_platformer has 'pickups' with count 5. Add a secondary pickup entity 'health_flask' with count 2.
    gds.entities.append(
        EntitySpec(
            entity_id="health_flask",
            level_id="level_1",
            kind="pickup",
            module="kit.pickup",
            count=2,
            props={"value": 25},
        )
    )
    rng = random.Random(999)
    lvl = LevelSpec(level_id="level_1", layout="course", size_m=Vec2(x=60.0, y=60.0), seed=999)
    plan = plan_course_level(lvl, gds, rng)

    coin_actors = [a for a in plan.actors if a.entity_id == "pickups"]
    flask_actors = [a for a in plan.actors if a.entity_id == "health_flask"]

    assert len(coin_actors) == 5, f"Expected 5 coins, got {len(coin_actors)}"
    assert len(flask_actors) == 2, f"Expected 2 health flasks, got {len(flask_actors)}"


# ---------------------------------------------------------------------------
# DEF-108: C++ Codegen Essential Runtime & Gameplay Includes
# ---------------------------------------------------------------------------

def test_def108_codegen_gameplay_includes_and_safety_scan():
    """Verify generate_source emits required engine/runtime headers and passes safety scan."""
    src = generate_source(
        "CustomScoreRule",
        on_event_body="if (Event.EventName == GameForgeEvents::PickupCollected) { GameState()->SetStat(FName(TEXT(\"score\")), 10.0f); }",
        tick_body="",
    )
    assert '#include "Engine/World.h"' in src
    assert '#include "GameForgePlayer.h"' in src
    assert '#include "GameForgeKitActors.h"' in src
    assert '#include "GameForgeObjectives.h"' in src
    assert '#include "GameForgeEventNames.h"' in src
    assert '#include "Kismet/KismetSystemLibrary.h"' in src

    # Verify safety scan catches prohibited symbols
    assert safety_scan("GetWorld()->GetFirstPlayerController();")[0] is True
    assert safety_scan("#include <windows.h>")[0] is False
    assert safety_scan("system(\"dir\")")[0] is False


# ---------------------------------------------------------------------------
# DEF-109: Duplicate PlayerStart Actor Prevention
# ---------------------------------------------------------------------------

def test_def109_duplicate_player_start_prevention():
    """Verify that multiple PlayerStart actors in plan.actors or geometry_ops emit exactly one start."""
    plan = LevelPlan(
        level_id="level_1",
        map_path="/Game/Maps/Level_1",
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        geometry_ops=[],
        actors=[
            PlacedActor(actor_id="start_alpha", runtime_class="PlayerStart", location=(100.0, 0.0, 50.0)),
            PlacedActor(actor_id="start_beta", runtime_class="/Script/Engine.PlayerStart", location=(200.0, 0.0, 50.0)),
        ],
    )
    ops = plan_to_op_calls(plan)
    starts = [o for o in ops if o.op == "spawn_actor" and o.args.get("actor_class") in ("PlayerStart", "/Script/Engine.PlayerStart")]
    assert len(starts) == 1
    assert starts[0].args["label"] == "start_alpha"


# ---------------------------------------------------------------------------
# DEF-110: Actor Transform Readback Parser & Yaw Verification
# ---------------------------------------------------------------------------

def test_def110_verify_placed_actor_transforms_robust_formats_and_yaw():
    """Verify transform readback supports lists, tuples, direct coords, and yaw checking."""
    plan = LevelPlan(
        level_id="level_1",
        map_path="/Game/Maps/Level_1",
        player_start=(0.0, 0.0, 100.0),
        nav_bounds=((0.0, 0.0, 100.0), (1000.0, 1000.0, 500.0)),
        actors=[
            PlacedActor(actor_id="actor_list", runtime_class="StaticMeshActor", location=(100.0, 200.0, 50.0), yaw=90.0),
            PlacedActor(actor_id="actor_flat", runtime_class="StaticMeshActor", location=(300.0, 400.0, 50.0), yaw=0.0),
        ],
    )

    # Actual records with list location and matching yaw
    actual_records = {
        "actor_list": {"location": [100.2, 199.8, 50.1], "yaw": 88.5},
        # Direct flat coordinate dictionary without nested "location" key
        "actor_flat": {"x": 300.1, "y": 400.2, "z": 49.9},
        "PlayerStart": [0.0, 0.0, 100.0],
    }

    warnings = verify_placed_actor_transforms(plan, actual_records, tolerance_cm=50.0)
    assert len(warnings) == 0

    # Yaw discrepancy check
    bad_yaw_records = {
        "actor_list": {"location": [100.0, 200.0, 50.0], "yaw": 0.0},
    }
    yaw_warnings = verify_placed_actor_transforms(plan, bad_yaw_records, tolerance_cm=50.0, yaw_tolerance_deg=10.0)
    assert len(yaw_warnings) == 1
    assert "yaw mismatch" in yaw_warnings[0]


# ---------------------------------------------------------------------------
# DEF-111: Direct Property Overrides Preservation & Asset Flag Emission
# ---------------------------------------------------------------------------

def test_def111_property_overrides_preservation_and_asset_flag():
    """Verify direct PascalCase property overrides are preserved and asset paths get asset=True."""
    gds = preset_platformer()
    gds.entities.append(
        EntitySpec(
            entity_id="boss_guard",
            level_id="level_1",
            kind="enemy",
            module="kit.enemy_melee",
            props={
                "MaxHealth": 250.0,
                "attack_damage": 40.0,
                "MeshAsset": "/Game/Characters/BossMesh",
            },
        )
    )
    comp = compose(gds)
    boss_actors = [a for a in comp.levels[0].actors if a.entity_id == "boss_guard"]
    assert len(boss_actors) == 1
    boss = boss_actors[0]

    # Direct MaxHealth override preserved alongside mapped attack_damage
    assert boss.properties.get("MaxHealth") == 250.0
    assert boss.properties.get("AttackDamage") == 40.0
    assert boss.properties.get("MeshAsset") == "/Game/Characters/BossMesh"

    # plan_to_op_calls sets asset=True for asset paths
    ops = plan_to_op_calls(comp.levels[0], comp.gfdef)
    asset_prop_ops = [
        o for o in ops
        if o.op == "set_actor_property" and o.args.get("property") == "MeshAsset"
    ]
    assert len(asset_prop_ops) == 1
    assert asset_prop_ops[0].args.get("asset") is True


# ---------------------------------------------------------------------------
# DEF-112: Placement Empty / Degenerate Polygon Guards
# ---------------------------------------------------------------------------

def test_def112_placement_degenerate_polygon_guards():
    """Verify is_point_in_polygon and scatter do not crash on empty/degenerate polygons."""
    assert is_point_in_polygon((0.0, 0.0), []) is False
    assert is_point_in_polygon((0.0, 0.0), [(0.0, 0.0), (1.0, 1.0)]) is False

    rng = random.Random(42)
    pts, warn = scatter([], n=5, min_spacing_cm=100.0, rng=rng)
    assert len(pts) == 0
    assert "at least 3 points" in warn

    pts_line, warn_line = scatter([(0.0, 0.0), (10.0, 10.0)], n=5, min_spacing_cm=100.0, rng=rng)
    assert len(pts_line) == 0
    assert "at least 3 points" in warn_line


# ---------------------------------------------------------------------------
# DEF-113: Intro Cinematics Dynamic Focus Mapping
# ---------------------------------------------------------------------------

def test_def113_cinematics_dynamic_focus_mapping():
    """Verify intro cinematics maps shot segments dynamically based on presentation.intro.focus."""
    gds = preset_platformer()
    gds.presentation = PresentationSpec(
        intro=IntroSpec(enabled=True, seconds=10.0, focus=["boss", "treasure"])
    )
    cin = generate_intro_cinematic(gds)
    assert cin["duration_seconds"] == 10.0
    assert len(cin["shots"]) == 3
    assert "Boss" in cin["shots"][0]
    assert "Boss" in cin["shots"][1]
    assert "Treasure" in cin["shots"][2]
