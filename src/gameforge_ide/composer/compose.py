"""Master composition algorithm (WI-6.2).

Transforms a validated GameDesignSpec into a fully realized, deterministic
Composition with level plans, actor placements, gfdef, and Forge run specs.
"""
from __future__ import annotations

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
                    h_name = f"Custom{task_idx}Rule"
                    desc = getattr(eff, "description", rule.description or f"Custom rule {r_id}")
                    codegen_tasks.append(
                        CodegenTask(
                            handler_name=h_name,
                            description=desc,
                            rule_id=r_id,
                        )
                    )
                    task_idx += 1

    # 4. Build levels
    level_plans: List[LevelPlan] = []
    levels = gds.scene.levels if hasattr(gds, "scene") and gds.scene.levels else []

    # Fallback default level if none specified
    if not levels:
        from ..design.gds import LevelSpec
        genre_val = gds.overview.genre.value if hasattr(gds.overview.genre, "value") else str(gds.overview.genre)
        cam_val = getattr(gds.overview.camera, "value", str(gds.overview.camera)) if hasattr(gds.overview, "camera") else ""
        meta_title = getattr(gds.meta, "title", "") if hasattr(gds, "meta") else ""
        meta_proj = getattr(gds.meta, "project_name", "") if hasattr(gds, "meta") else ""
        meta_prompt = getattr(gds.meta, "source_prompt", "") if hasattr(gds, "meta") else ""
        overview_pitch = getattr(gds.overview, "pitch", "") if hasattr(gds, "overview") else ""
        title_pitch = f"{meta_title} {meta_proj} {meta_prompt} {overview_pitch}".lower()

        if "counter" in title_pitch or "strike" in title_pitch or "bomb" in title_pitch or "defus" in title_pitch or (cam_val == "first_person" and "shoot" in title_pitch):
            layout_name = "tactical_fps"
        elif genre_val in ("board", "card"):
            layout_name = "board"
        elif genre_val == "dungeon_crawler":
            layout_name = "rooms"
        elif genre_val in ("exploration", "action_adventure"):
            layout_name = "open_world"
        elif genre_val == "platformer":
            layout_name = "course"
        else:
            layout_name = "arena"
        levels = [LevelSpec(level_id="level_1", layout=layout_name, seed=2026)]

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

        unplaced = [e for e in gds.entities if e.entity_id not in already_placed_entities and e.kind != "player"]

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

        # Avoid player start and existing actors
        avoid_zones: List[Tuple[float, float, float]] = [
            (layout_plan.player_start[0], layout_plan.player_start[1], 400.0)
        ]
        for a in layout_plan.actors:
            avoid_zones.append((a.location[0], a.location[1], 300.0))

        # Scatter unplaced entities
        total_to_place = 0
        entity_scatter_requests: List[Tuple[Any, int]] = []
        for e in unplaced:
            count = int(e.props.get("count", 1))
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

        pt_idx = 0
        placed_actors = list(layout_plan.actors)
        for e, count in entity_scatter_requests:
            mod = get_module(e.module)
            for c_i in range(count):
                if pt_idx < len(scattered_points):
                    pos_2d = scattered_points[pt_idx]
                    loc = (pos_2d[0], pos_2d[1], 100.0)
                    pt_idx += 1
                else:
                    # Fallback offset
                    loc = (center[0] + c_i * 200.0, center[1] + c_i * 200.0, 100.0)

                actor_id = f"{e.entity_id}_{c_i}"
                tags = [f"GF_E_{e.entity_id}", "GF_Owned", f"GF_{e.kind}_{c_i + 1}"]

                # Map props
                props: Dict[str, Any] = {}
                for gds_p, unreal_p in mod.property_map.items():
                    if gds_p in e.props:
                        props[unreal_p] = e.props[gds_p]

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

    # 6. Content requests
    content_requests: List[Dict[str, Any]] = []
    if hasattr(gds, "feedback") and gds.feedback:
        for fb in gds.feedback:
            if getattr(fb, "vfx", None):
                content_requests.append({"kind": "vfx", "preset": fb.vfx})
            if getattr(fb, "sfx", None):
                content_requests.append({"kind": "sfx", "preset": fb.sfx})

    project_name = gds.meta.title.replace(" ", "").replace("-", "_") if hasattr(gds, "meta") else "GameForgeGame"

    # Temporary composition object for gfdef builder
    prelim_comp = Composition(
        gds_id=getattr(gds.meta, "id", "gds_0"),
        gds_revision=getattr(gds.meta, "revision", 1),
        project_name=project_name,
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
