"""Master composition algorithm (WI-6.2).

Transforms a validated GameDesignSpec into a fully realized, deterministic
Composition with level plans, actor placements, gfdef, and Forge run specs.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from .model import CodegenTask, Composition, CompositionError, LevelPlan, PlacedActor
from .layouts import LAYOUTS
from .placement import scatter
from .runtime_def import build as build_gfdef
from ..kit.registry import get_module, KIT, _ensure_modules_loaded
from ..design.gds import GameDesignSpec


def compose(gds: GameDesignSpec, allow_partial: bool = False) -> Composition:
    """Compose a GameDesignSpec into a concrete playable game Composition."""
    _ensure_modules_loaded()

    problems: List[str] = []
    suggestions: List[str] = []
    warnings: List[str] = []

    # 1. Module status validation
    used_modules: Set[str] = set()
    for ent in gds.entities:
        mod_id = ent.module
        used_modules.add(mod_id)
        try:
            m = get_module(mod_id)
            if m.status != "PASS" and not (allow_partial and m.status == "PARTIAL"):
                problems.append(f"module {mod_id} is {m.status}")
                if mod_id == "kit.enemy_ranged":
                    suggestions.append("use kit.enemy_melee or allow partial modules")
        except KeyError:
            problems.append(f"module {mod_id} is not registered in kit")

    if problems:
        raise CompositionError(problems, suggestions)

    # 1b. Feature validation from acceptance requirements (kit/rules.py)
    from ..kit.rules import check_composition_features
    check_composition_features(gds)

    # 2. Plugins & module dependencies
    required_plugins: Set[str] = {"GameForge", "EnhancedInput", "GameplayAbilities", "Niagara"}
    required_deps: Set[str] = {"EnhancedInput", "GameForgeRuntime", "GameplayAbilities", "GameplayTags"}

    for mod_id in sorted(used_modules):
        try:
            m = get_module(mod_id)
            required_plugins.update(m.required_plugins)
            required_deps.update(m.game_module_deps)
        except KeyError:
            pass

    # 3. Codegen tasks from custom code rules
    codegen_tasks: List[CodegenTask] = []
    task_idx = 0
    if hasattr(gds, "rules") and gds.rules:
        for rule in gds.rules:
            r_id = getattr(rule, "rule_id", getattr(rule, "id", f"rule_{task_idx}"))
            for eff in rule.effects:
                if eff.kind == "custom_code" or getattr(eff, "custom_code", None):
                    h_name = getattr(eff, "handler_name", None) or f"Custom{task_idx}Rule"
                    if any(task.handler_name == h_name for task in codegen_tasks):
                        raise CompositionError([f"duplicate custom rule handler_name {h_name!r}"])
                    desc = getattr(eff, "description", rule.description or f"Custom rule {r_id}")
                    on_event = getattr(eff, "on_event_body", "") or getattr(eff, "code", "") or ""
                    tick = getattr(eff, "tick_body", "") or ""
                    codegen_tasks.append(
                        CodegenTask(
                            handler_name=h_name,
                            description=desc,
                            rule_id=r_id,
                            on_event_body=on_event,
                            tick_body=tick,
                        )
                    )
                    task_idx += 1

    # 4. Build levels
    level_plans: List[LevelPlan] = []
    levels = gds.scene.levels if hasattr(gds, "scene") and gds.scene.levels else []

    # Fallback default level if none specified
    if not levels:
        from ..design.gds import LevelSpec, Vec2
        from ..kit.rules import get_layout_for_game_type, GAME_TYPE_LAYOUT_MAP
        genre_val = gds.overview.genre.value if hasattr(gds.overview.genre, "value") else str(gds.overview.genre)
        cam_val = getattr(gds.overview.camera, "value", str(gds.overview.camera)) if hasattr(gds.overview, "camera") else ""
        meta_title = getattr(gds.meta, "title", "") if hasattr(gds, "meta") else ""
        meta_proj = getattr(gds.meta, "project_name", "") if hasattr(gds, "meta") else ""
        meta_prompt = getattr(gds.meta, "source_prompt", "") if hasattr(gds, "meta") else ""
        overview_pitch = getattr(gds.overview, "pitch", "") if hasattr(gds, "overview") else ""
        title_pitch = f"{meta_title} {meta_proj} {meta_prompt} {overview_pitch}".lower()

        layout_name = None
        for gt in GAME_TYPE_LAYOUT_MAP:
            if gt in title_pitch or gt.replace("_", " ") in title_pitch:
                try:
                    layout_name = get_layout_for_game_type(gt)
                    break
                except KeyError:
                    pass

        if not layout_name:
            if "counter" in title_pitch or "strike" in title_pitch or "bomb" in title_pitch or "defus" in title_pitch or (cam_val == "first_person" and "shoot" in title_pitch):
                layout_name = "tactical_fps"
            elif genre_val in ("grid_board", "board"):
                layout_name = "board"
            elif genre_val in ("card_battler", "card"):
                layout_name = "lanes"
            elif genre_val == "puzzle":
                layout_name = "board"
            elif genre_val == "dungeon_crawler":
                layout_name = "rooms"
            elif genre_val in ("exploration", "action_adventure"):
                layout_name = "open_world"
            elif genre_val == "platformer":
                layout_name = "course"
            else:
                layout_name = "arena"
        levels = [LevelSpec(level_id="level_1", layout=layout_name, size_m=Vec2(x=60.0, y=60.0), seed=2026)]

    for level in levels:
        layout_name = level.layout.value if hasattr(level.layout, "value") else str(level.layout)
        meta_title = getattr(gds.meta, "title", "") if hasattr(gds, "meta") else ""
        meta_proj = getattr(gds.meta, "project_name", "") if hasattr(gds, "meta") else ""
        meta_prompt = getattr(gds.meta, "source_prompt", "") if hasattr(gds, "meta") else ""
        overview_pitch = getattr(gds.overview, "pitch", "") if hasattr(gds, "overview") else ""
        title_pitch = f"{meta_title} {meta_proj} {meta_prompt} {overview_pitch}".lower()
        if layout_name == "arena" and ("counter" in title_pitch or "strike" in title_pitch or "bomb" in title_pitch or "defus" in title_pitch or "fps" in title_pitch):
            layout_name = "tactical_fps"
        if layout_name not in LAYOUTS:
            problems.append(f"layout {layout_name!r} not found in LAYOUTS; supported: {sorted(LAYOUTS.keys())}")
            continue

        level_rng = random.Random(level.seed)
        layout_plan = LAYOUTS[layout_name](level, gds, level_rng)

        # Place entities that are not yet placed by the layout
        already_placed_entities = {a.entity_id for a in layout_plan.actors if a.entity_id}
        if "card_table" in already_placed_entities or "cards" in already_placed_entities:
            already_placed_entities.update({"card_table", "cards"})
        if "board" in already_placed_entities or "grid_board" in already_placed_entities:
            already_placed_entities.update({"board", "grid_board"})
        if "pickup" in already_placed_entities or "pickups" in already_placed_entities:
            already_placed_entities.update({"pickup", "pickups"})

        unplaced = [
            e for e in gds.entities
            if e.entity_id not in already_placed_entities
            and e.kind not in ("player", "character", "hero")
            and e.module != "kit.player_character"
        ]

        # Gather layout free-area polygon from nav_bounds
        center, extent = layout_plan.nav_bounds
        half_w = extent[0] * 0.8
        half_h = extent[1] * 0.8
        free_poly = [
            (center[0] - half_w, center[1] - half_h),
            (center[0] + half_w, center[1] - half_h),
            (center[0] + half_w, center[1] + half_h),
            (center[0] - half_w, center[1] + half_h),
        ]

        # Avoid player start, existing actors, and solid obstacles (walls, cover blocks, pillars)
        avoid_zones: List[Tuple[float, float, float]] = [
            (layout_plan.player_start[0], layout_plan.player_start[1], 400.0)
        ]
        for a in layout_plan.actors:
            avoid_zones.append((a.location[0], a.location[1], 300.0))

        solid_obstacles: List[Tuple[float, float, float]] = []
        for g_op in layout_plan.geometry_ops:
            if g_op.args.get("actor_class") == "StaticMeshActor":
                lbl = str(g_op.args.get("label", ""))
                # Skip ground floors, safety floors, walkways, ramps, and platforms
                if any(floor_kw in lbl.lower() for floor_kw in ("floor", "walkway", "ramp", "platform")):
                    continue
                loc_g = g_op.args.get("location", {})
                scale_g = g_op.args.get("scale", {})
                gx = float(loc_g.get("x", 0.0))
                gy = float(loc_g.get("y", 0.0))
                sx = float(scale_g.get("x", 1.0)) * 50.0
                sy = float(scale_g.get("y", 1.0)) * 50.0
                obs_radius = math.hypot(sx, sy) + 100.0
                solid_obstacles.append((gx, gy, obs_radius))
                avoid_zones.append((gx, gy, obs_radius))

        # Scatter unplaced entities
        total_to_place = 0
        entity_scatter_requests: List[Tuple[Any, int]] = []
        for e in unplaced:
            count = 1
            if getattr(e, "count", None) and int(e.count) > 1:
                count = int(e.count)
            elif "count" in getattr(e, "props", {}) and int(e.props["count"]) > 1:
                count = int(e.props["count"])
            total_to_place += count
            entity_scatter_requests.append((e, count))

        scattered_points, scatter_warn = scatter(
            area_polygon=free_poly,
            n=total_to_place,
            min_spacing_cm=400.0,
            rng=level_rng,
            avoid=avoid_zones,
        )
        if scatter_warn:
            warnings.append(scatter_warn)

        # For platformer courses, find available platforms to place entities securely
        platform_locs = [
            op.args["location"]
            for op in layout_plan.geometry_ops
            if op.args.get("actor_class") == "StaticMeshActor"
            and "Platform" in op.args.get("label", "")
            and "location" in op.args
        ]

        # For dungeon rooms, find floor pieces to avoid mid-air voids
        room_floor_locs = [
            op.args["location"]
            for op in layout_plan.geometry_ops
            if op.args.get("actor_class") == "StaticMeshActor"
            and "Dungeon_Floor" in op.args.get("label", "")
            and "location" in op.args
        ]

        is_course_layout = layout_name in ("course", "platformer")
        pt_idx = 0
        placed_actors = list(layout_plan.actors)
        for e, count in entity_scatter_requests:
            mod = get_module(e.module)
            for c_i in range(count):
                spread_offset = ((c_i % 3) - 1) * 60.0
                if pt_idx < len(scattered_points):
                    pos_2d = scattered_points[pt_idx]
                    if is_course_layout and platform_locs:
                        # 2D Euclidean distance matching across 3D course platforms
                        nearest_p = min(
                            platform_locs,
                            key=lambda p: math.hypot(float(p.get("x", 0.0)) - pos_2d[0], float(p.get("y", 0.0)) - pos_2d[1])
                        )
                        loc = (float(nearest_p.get("x", 0.0)) + spread_offset, float(nearest_p.get("y", 0.0)), float(nearest_p.get("z", 0.0)) + 75.0)
                    elif layout_name == "rooms" and room_floor_locs:
                        nearest_rf = min(
                            room_floor_locs,
                            key=lambda rf: math.hypot(float(rf.get("x", 0.0)) - pos_2d[0], float(rf.get("y", 0.0)) - pos_2d[1])
                        )
                        loc = (float(nearest_rf.get("x", 0.0)) + spread_offset, float(nearest_rf.get("y", 0.0)), 50.0)
                    else:
                        loc = (pos_2d[0], pos_2d[1], 100.0)
                    pt_idx += 1
                else:
                    # Fallback offset
                    if is_course_layout and platform_locs:
                        p_idx = min(c_i, len(platform_locs) - 1)
                        p_loc = platform_locs[p_idx]
                        loc = (float(p_loc.get("x", 0.0)) + spread_offset, float(p_loc.get("y", 0.0)), float(p_loc.get("z", 0.0)) + 75.0)
                    elif layout_name == "rooms" and room_floor_locs:
                        rf_idx = min(c_i, len(room_floor_locs) - 1)
                        rf_loc = room_floor_locs[rf_idx]
                        loc = (float(rf_loc.get("x", 0.0)) + spread_offset, float(rf_loc.get("y", 0.0)), 50.0)
                    else:
                        loc = (center[0] + c_i * 200.0, center[1] + c_i * 200.0, 100.0)

                # Validate coordinates: ensure actors cannot spawn inside colliders, under terrain, or past world bounds
                nav_center, nav_extent = layout_plan.nav_bounds
                min_bx = nav_center[0] - nav_extent[0] * 0.95
                max_bx = nav_center[0] + nav_extent[0] * 0.95
                min_by = nav_center[1] - nav_extent[1] * 0.95
                max_by = nav_center[1] + nav_extent[1] * 0.95
                min_safe_z = -350.0 if is_course_layout else 0.0

                lx = max(min_bx, min(max_bx, loc[0]))
                ly = max(min_by, min(max_by, loc[1]))
                lz = max(min_safe_z + 50.0, loc[2])

                # Check and push away from any solid obstacle collider
                for ox, oy, orad in solid_obstacles:
                    dist_sq = (lx - ox) ** 2 + (ly - oy) ** 2
                    if dist_sq < orad ** 2:
                        dist = math.sqrt(max(1e-4, dist_sq))
                        push_dir_x = (lx - ox) / dist if dist > 1e-4 else 1.0
                        push_dir_y = (ly - oy) / dist if dist > 1e-4 else 0.0
                        lx = ox + push_dir_x * (orad + 50.0)
                        ly = oy + push_dir_y * (orad + 50.0)
                        lx = max(min_bx, min(max_bx, lx))
                        ly = max(min_by, min(max_by, ly))

                loc = (round(lx, 1), round(ly, 1), round(lz, 1))

                actor_id = f"{e.entity_id}_{c_i}"
                kind_raw = str(getattr(e.kind, "value", e.kind)).lower()
                kind_cap = kind_raw.capitalize()
                tags = [
                    f"GF_E_{e.entity_id}",
                    "GF_Owned",
                    kind_raw,
                    kind_cap,
                    f"{kind_raw}_{c_i + 1}",
                    f"{kind_cap}_{c_i + 1}",
                    f"GF_{kind_raw}_{c_i + 1}",
                    f"GF_{kind_cap}_{c_i + 1}",
                    actor_id,
                ]
                if kind_raw in ("enemy", "spawner", "ranged_enemy"):
                    tags.extend(["enemy", "Enemy", f"Enemy_{c_i + 1}", f"enemy_{c_i + 1}"])
                elif kind_raw in ("pickup", "collectible", "relic", "coin"):
                    tags.extend(["pickup", "Pickup", f"Pickup_{c_i + 1}", f"pickup_{c_i + 1}"])
                elif kind_raw in ("goal", "exit", "flag"):
                    tags.extend(["goal", "Goal", f"Goal_{c_i + 1}", f"goal_{c_i + 1}"])
                # Deduplicate while preserving order
                tags = list(dict.fromkeys(tags))

                # Map props: support aliases, direct PascalCase overrides, and nested property_overrides
                props: Dict[str, Any] = {}
                for gds_p, unreal_p in mod.property_map.items():
                    if gds_p in e.props:
                        props[unreal_p] = e.props[gds_p]
                    elif unreal_p in e.props:
                        props[unreal_p] = e.props[unreal_p]

                for p_key, p_val in e.props.items():
                    if p_key == "property_overrides" and isinstance(p_val, dict):
                        for sub_k, sub_v in p_val.items():
                            props[sub_k] = sub_v
                    elif p_key not in mod.property_map and p_key not in mod.property_map.values():
                        props[p_key] = p_val

                placed_actors.append(
                    PlacedActor(
                        actor_id=actor_id,
                        entity_id=e.entity_id,
                        runtime_class=mod.runtime_class,
                        location=loc,
                        yaw=0.0,
                        tags=tags,
                        properties=props,
                    )
                )

        layout_plan.actors = placed_actors
        level_plans.append(layout_plan)

    if problems:
        raise CompositionError(problems, suggestions)

    # 5. Extract scenario IDs
    scenarios: List[str] = []
    if hasattr(gds, "acceptance") and hasattr(gds.acceptance, "scenarios"):
        scenarios = [s.scenario_id for s in gds.acceptance.scenarios]

    # Include game-specific acceptance scenarios derived from GDS
    try:
        from ..qa.game_spec_tests import generate_acceptance_tests
        for spec_test in generate_acceptance_tests(gds):
            if spec_test.test_id not in scenarios:
                scenarios.append(spec_test.test_id)
    except Exception:
        pass

    # 6. Content requests
    content_requests: List[Dict[str, Any]] = []
    if hasattr(gds, "feedback") and gds.feedback:
        for fb in gds.feedback:
            if getattr(fb, "vfx", None):
                content_requests.append({"kind": "vfx", "preset": fb.vfx})
            if getattr(fb, "sfx", None):
                content_requests.append({"kind": "sfx", "preset": fb.sfx})

    if hasattr(gds, "meta") and getattr(gds.meta, "project_name", None):
        project_name = gds.meta.project_name
    elif hasattr(gds, "meta") and getattr(gds.meta, "title", None):
        project_name = gds.meta.title.replace(" ", "").replace("-", "_")
    else:
        project_name = "GameForgeGame"

    # Genre and pitch extraction
    genre_val = "Platformer"
    if hasattr(gds, "overview") and getattr(gds.overview, "genre", None):
        g = gds.overview.genre
        genre_val = g.value if hasattr(g, "value") else str(g)

    pitch_val = getattr(gds.overview, "pitch", "") if hasattr(gds, "overview") else ""
    if not pitch_val and hasattr(gds, "meta") and getattr(gds.meta, "source_prompt", None):
        pitch_val = gds.meta.source_prompt
    if not pitch_val:
        pitch_val = f"{project_name} — {genre_val} game experience"

    # Temporary composition object for gfdef builder
    prelim_comp = Composition(
        gds_id=getattr(gds.meta, "id", "gds_0"),
        gds_revision=getattr(gds.meta, "revision", 1),
        project_name=project_name,
        genre=genre_val,
        pitch=pitch_val,
        modules=sorted(used_modules),
        plugins=sorted(required_plugins),
        module_deps=sorted(required_deps),
        levels=level_plans,
        gfdef={},
        codegen=codegen_tasks,
        scenarios=scenarios,
        content_requests=content_requests,
        warnings=warnings,
    )

    # 7. Generate gfdef
    gfdef = build_gfdef(gds, prelim_comp)
    prelim_comp.gfdef = gfdef

    return prelim_comp
