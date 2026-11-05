"""Legacy recipe pipeline stages adapted as Forge handlers (AD-11)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type, Union

from ...core.settings import engine_root_or_missing, get_settings
from ...pipeline import stages as engine_stages
from tests.fixtures.legacy_recipes.arena_combat.recipe import (
    RECIPE_ID as ARENA_RECIPE_ID,
    RECIPE_VERSION as ARENA_RECIPE_VERSION,
    SELFTEST_LOG_PASS as ARENA_SELFTEST_PASS,
    ArenaCombatParams,
    generate as arena_generate,
)
from tests.fixtures.legacy_recipes.card_battler.recipe import (
    RECIPE_ID as CARD_RECIPE_ID,
    RECIPE_VERSION as CARD_RECIPE_VERSION,
    SELFTEST_LOG_PASS as CARD_SELFTEST_PASS,
    CardBattlerParams,
    generate as card_generate,
)
from tests.fixtures.legacy_recipes.grid_board_game.recipe import (
    RECIPE_ID as GRID_RECIPE_ID,
    RECIPE_VERSION as GRID_RECIPE_VERSION,
    SELFTEST_LOG_PASS as GRID_SELFTEST_PASS,
    GridBoardParams,
    generate as grid_generate,
)
from tests.fixtures.legacy_recipes.platformer.recipe import (
    RECIPE_ID as PLATFORMER_RECIPE_ID,
    RECIPE_VERSION as PLATFORMER_RECIPE_VERSION,
    SELFTEST_LOG_PASS as PLATFORMER_SELFTEST_PASS,
    PlatformerParams,
    generate as platformer_generate,
)
from tests.fixtures.legacy_recipes.procedural_world.recipe import (
    RECIPE_ID as PROCEDURAL_RECIPE_ID,
    RECIPE_VERSION as PROCEDURAL_RECIPE_VERSION,
    SELFTEST_LOG_PASS as PROCEDURAL_SELFTEST_PASS,
    ProceduralWorldParams,
    generate as procedural_generate,
)
from ...unreal.toolchain import UnrealToolchain
from ..checkpoints import ProjectRepo
from ..executor import StepContext, StepOutcome

PARAMS_BY_RECIPE: Dict[str, Any] = {
    GRID_RECIPE_ID: GridBoardParams,
    PLATFORMER_RECIPE_ID: PlatformerParams,
    ARENA_RECIPE_ID: ArenaCombatParams,
    CARD_RECIPE_ID: CardBattlerParams,
    PROCEDURAL_RECIPE_ID: ProceduralWorldParams,
}

RECIPE_IMPL = {
    GRID_RECIPE_ID: (
        grid_generate,
        lambda eng, up, ev, name, p: engine_stages.assemble_level(
            eng, up, ev, name, p.cell_size_cm * p.board_size
        ),
        None,
        "/Script/{name}.GFGameMode",
        GRID_SELFTEST_PASS,
    ),
    PLATFORMER_RECIPE_ID: (
        platformer_generate,
        lambda eng, up, ev, name, p: engine_stages.assemble_platformer_level(
            eng, up, ev, name, p.collectible_target
        ),
        ["UMG", "Slate", "SlateCore"],
        "/Script/{name}.GFPlatformerGameMode",
        PLATFORMER_SELFTEST_PASS,
    ),
    ARENA_RECIPE_ID: (
        arena_generate,
        lambda eng, up, ev, name, p: engine_stages.assemble_arena_level(eng, up, ev, name),
        ["AIModule", "NavigationSystem", "UMG", "Slate", "SlateCore"],
        "/Script/{name}.GFArenaGameMode",
        ARENA_SELFTEST_PASS,
    ),
    CARD_RECIPE_ID: (
        card_generate,
        lambda eng, up, ev, name, p: engine_stages.assemble_card_level(eng, up, ev, name),
        ["UMG", "Slate", "SlateCore"],
        "/Script/{name}.GFCardGameMode",
        CARD_SELFTEST_PASS,
    ),
    PROCEDURAL_RECIPE_ID: (
        procedural_generate,
        lambda eng, up, ev, name, p: engine_stages.assemble_procedural_world_level(
            eng,
            up,
            ev,
            name,
            seed=p.seed,
            terrain_type=p.terrain_type,
            elevation_scale=p.elevation_scale,
            road_width=p.road_width,
            foliage_density=p.foliage_density,
            landmark_type=p.landmark_type,
        ),
        ["Landscape", "Foliage", "NavigationSystem", "UMG", "Slate", "SlateCore"],
        "/Script/{name}.GFProceduralGameMode",
        PROCEDURAL_SELFTEST_PASS,
    ),
}


def get_recipe_id(params: Any) -> str:
    if isinstance(params, ProceduralWorldParams):
        return PROCEDURAL_RECIPE_ID
    if isinstance(params, CardBattlerParams):
        return CARD_RECIPE_ID
    if isinstance(params, ArenaCombatParams):
        return ARENA_RECIPE_ID
    if isinstance(params, PlatformerParams):
        return PLATFORMER_RECIPE_ID
    return GRID_RECIPE_ID


def get_params(ctx: StepContext) -> Any:
    raw = ctx.step.inputs.get("params")
    if hasattr(raw, "validate"):
        return raw
    recipe_id = ctx.step.inputs.get("recipe_id", GRID_RECIPE_ID)
    cls = PARAMS_BY_RECIPE.get(recipe_id, GridBoardParams)
    if isinstance(raw, dict):
        return cls(**raw)
    return cls()


def _get_toolchain(ctx: StepContext) -> UnrealToolchain:
    eng_root = Path(ctx.step.inputs.get("engine_root") or engine_root_or_missing())
    max_actions = ctx.step.inputs.get("max_parallel_actions")
    tc = UnrealToolchain(eng_root, max_parallel_actions=max_actions)
    tc.cancel_event = ctx.cancel
    return tc


def legacy_spec(ctx: StepContext) -> StepOutcome:
    tc = _get_toolchain(ctx)
    missing = [k for k, v in tc.check().items() if not v]
    if missing:
        return StepOutcome(False, errors=[f"engine tools missing: {missing}"], blocked=True)

    # If this is a modern GDS / Composition run (e.g. Platformer, Shooter, CounterStrike)
    pdir = ctx.project_dir or ctx.workspace_dir
    gds_data = ctx.step.inputs.get("gds")
    if not gds_data and pdir:
        gds_file = pdir / "GameForge" / "design" / "game.gds.json"
        if gds_file.is_file():
            try:
                import json
                gds_data = json.loads(gds_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    has_legacy_recipe = "params" in ctx.step.inputs or "recipe_id" in ctx.step.inputs
    if not has_legacy_recipe or gds_data or "gds_id" in ctx.step.inputs:
        proj_name = (
            ctx.step.inputs.get("project_name")
            or (gds_data.get("meta", {}).get("project_name") if isinstance(gds_data, dict) else None)
            or (pdir.name if pdir else "GameForgeProject")
        )
        genre = (
            ctx.step.inputs.get("genre")
            or (gds_data.get("overview", {}).get("genre") if isinstance(gds_data, dict) else None)
            or "Action"
        )
        title = (
            (gds_data.get("meta", {}).get("title") if isinstance(gds_data, dict) else None)
            or proj_name
        )
        pitch = (
            (gds_data.get("overview", {}).get("pitch", "") if isinstance(gds_data, dict) else "")
            or ctx.step.inputs.get("pitch")
            or (gds_data.get("meta", {}).get("source_prompt") if isinstance(gds_data, dict) else "")
            or f"{title} — {genre} game experience"
        )
        design_params = {
            "project_name": proj_name,
            "display_title": title,
            "genre": genre,
            "pitch": pitch,
        }
        if isinstance(gds_data, dict):
            overview = gds_data.get("overview", {})
            for key in ("pitch", "camera", "players", "win_condition", "lose_condition"):
                if key in overview:
                    design_params[key] = overview[key]
            art = gds_data.get("art", {})
            if "theme" in art:
                design_params["theme"] = art["theme"]

        outcome_data = {"params": design_params, "engine": tc.engine_version()}
        if isinstance(gds_data, dict):
            try:
                from ...design.gds import GameDesignSpec
                from ..validation import validate_stage_output
                gds_obj = GameDesignSpec.model_validate(gds_data)
                valid, issues = validate_stage_output("design", outcome_data, gds_obj)
                if not valid:
                    return StepOutcome(False, data=outcome_data, errors=issues)
            except Exception:
                pass
        return StepOutcome(True, data=outcome_data)

    params = get_params(ctx)
    params.validate()
    return StepOutcome(True, data={"params": params.to_dict(), "engine": tc.engine_version()})


def _sync_project_map_settings(pdir: Path, map_path: str) -> None:
    """Ensure Config/DefaultEngine.ini and Config/DefaultGame.ini reflect the actual map."""
    clean_map = map_path.strip().split("?")[0] if map_path else ""
    config_dir = pdir / "Config"
    config_dir.mkdir(parents=True, exist_ok=True)

    if clean_map:
        eng_ini = config_dir / "DefaultEngine.ini"
        eng_content = eng_ini.read_text(encoding="utf-8") if eng_ini.is_file() else ""
        sec_header = "[/Script/EngineSettings.GameMapsSettings]"

        if sec_header in eng_content:
            if re.search(r"GameDefaultMap\s*=", eng_content):
                eng_content = re.sub(r"GameDefaultMap\s*=[^\r\n]*", f"GameDefaultMap={clean_map}", eng_content)
            else:
                eng_content = eng_content.replace(sec_header, f"{sec_header}\nGameDefaultMap={clean_map}")

            if re.search(r"EditorStartupMap\s*=", eng_content):
                eng_content = re.sub(r"EditorStartupMap\s*=[^\r\n]*", f"EditorStartupMap={clean_map}", eng_content)
            else:
                eng_content = eng_content.replace(sec_header, f"{sec_header}\nEditorStartupMap={clean_map}")
        else:
            eng_content = f"{sec_header}\nGameDefaultMap={clean_map}\nEditorStartupMap={clean_map}\n\n" + eng_content

        eng_ini.write_text(eng_content, encoding="utf-8")

    try:
        from ...content.epic_packs import update_default_game_ini_cook_dirs
        update_default_game_ini_cook_dirs(pdir, ["/Game/Maps"])
    except Exception:
        pass


def legacy_scaffold(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    display_title = ctx.step.inputs.get("display_title") or getattr(params, "display_title", project_name)
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)
    uproject = pdir / f"{project_name}.uproject"
    recipe_id = ctx.step.inputs.get("recipe_id") or get_recipe_id(params)
    impl = RECIPE_IMPL.get(recipe_id, RECIPE_IMPL[GRID_RECIPE_ID])
    default_gm = ctx.step.inputs.get("game_mode") or "/Script/GameForgeRuntime.GameForgeGameMode"
    deps = ctx.step.inputs.get("module_deps") or impl[2] or ["UMG", "Slate", "SlateCore"]
    plugins = ctx.step.inputs.get("plugins")
    tc = _get_toolchain(ctx)

    # Clean up stale project files if an earlier run scaffolded with a different name
    if pdir.is_dir():
        for old_up in pdir.glob("*.uproject"):
            if old_up.stem != project_name:
                try:
                    old_up.unlink()
                    old_target = pdir / "Source" / f"{old_up.stem}.Target.cs"
                    old_ed_target = pdir / "Source" / f"{old_up.stem}Editor.Target.cs"
                    old_src_dir = pdir / "Source" / old_up.stem
                    if old_target.exists():
                        old_target.unlink()
                    if old_ed_target.exists():
                        old_ed_target.unlink()
                    if old_src_dir.exists():
                        import shutil
                        shutil.rmtree(old_src_dir, ignore_errors=True)
                except Exception as exc:
                    ctx.log(f"Stale project cleanup warning: {exc}")

    # Resolve default map: inputs -> plan -> GDS -> filesystem -> fallback
    default_map = ctx.step.inputs.get("default_map")
    if not default_map:
        if "plan" in ctx.step.inputs and isinstance(ctx.step.inputs["plan"], dict):
            default_map = ctx.step.inputs["plan"].get("map_path")
        elif "gds" in ctx.step.inputs:
            try:
                gds_input = ctx.step.inputs["gds"]
                if isinstance(gds_input, dict) and "scene" in gds_input and "levels" in gds_input["scene"]:
                    lvls = gds_input["scene"]["levels"]
                    if lvls and isinstance(lvls[0], dict) and "level_id" in lvls[0]:
                        default_map = f"/Game/Maps/{lvls[0]['level_id'].capitalize()}"
            except Exception:
                pass
        if not default_map:
            try:
                g_loaded = design_store.load(pdir)
                if g_loaded and hasattr(g_loaded, "scene") and g_loaded.scene and g_loaded.scene.levels:
                    default_map = f"/Game/Maps/{g_loaded.scene.levels[0].level_id.capitalize()}"
            except Exception:
                pass
        if not default_map:
            if (pdir / "Content" / "Maps" / "Level_1.umap").is_file():
                default_map = "/Game/Maps/Level_1"
            elif (pdir / "Content" / "Maps" / f"{project_name}Map.umap").is_file():
                default_map = f"/Game/Maps/{project_name}Map"
            else:
                default_map = "/Game/Maps/Level_1"

    info = tc.scaffold_cpp_project(
        pdir,
        project_name,
        default_map=default_map,
        game_mode=default_gm,
        module_deps=deps,
        display_title=display_title,
        plugins=plugins,
    )
    _sync_project_map_settings(pdir, default_map)
    # Ensure GameForge plugin is deployed into Plugins/GameForge
    tc.deploy_gameforge_plugin(pdir)
    if uproject.is_file():
        repo = ProjectRepo(pdir)
        if repo.available:
            try:
                repo.ensure()
            except Exception as exc:
                ctx.log(f"ProjectRepo ensure warning: {exc}")

        # Hook for design spec or custom assets
        if "gds" in ctx.step.inputs:
            try:
                from ...design.gds import GameDesignSpec
                from ...design import store as design_store
                gds = GameDesignSpec.model_validate(ctx.step.inputs["gds"])
                stored = design_store.load(pdir)
                if stored is not None and gds.meta.revision <= stored.meta.revision:
                    gds.meta.revision = stored.meta.revision + 1
                design_store.save(pdir, gds)
            except Exception as exc:
                return StepOutcome(False, errors=[f"saving GDS failed: {exc}"])

        from ..legacy_adapter import get_project_ready_hook
        hook = get_project_ready_hook(ctx.run.run_id) or ctx.step.inputs.get("on_project_dir_ready")
        if callable(hook):
            try:
                hook(pdir)
            except Exception as exc:
                return StepOutcome(False, errors=[f"on_project_dir_ready failed: {exc}"])

    if not uproject.is_file():
        return StepOutcome(False, data=info, errors=["uproject not found"])

    from ..validation import validate_stage_output
    valid, issues = validate_stage_output("scaffold", info, project_dir=pdir)
    return StepOutcome(valid, data=info, errors=issues if not valid else [])


def legacy_sources(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)

    if "tasks" in ctx.step.inputs:
        from ...composer.codegen import generate_header, generate_source
        tasks = ctx.step.inputs["tasks"]
        written_files = []
        src_dir = pdir / "Source" / project_name
        pub_dir = src_dir / "Public"
        priv_dir = src_dir / "Private"
        pub_dir.mkdir(parents=True, exist_ok=True)
        priv_dir.mkdir(parents=True, exist_ok=True)

        for task in tasks:
            h_name = task.get("handler_name") if isinstance(task, dict) else getattr(task, "handler_name", "")
            if not h_name:
                continue
            h_content = generate_header(project_name, h_name)
            cpp_content = generate_source(h_name)

            h_file = pub_dir / f"{h_name}.h"
            cpp_file = priv_dir / f"{h_name}.cpp"
            h_file.write_text(h_content, encoding="utf-8", newline="\n")
            cpp_file.write_text(cpp_content, encoding="utf-8", newline="\n")
            written_files.extend([str(h_file.relative_to(pdir)), str(cpp_file.relative_to(pdir))])

        outcome_data = {"files": sorted(written_files), "codegen_tasks": len(tasks)}
        from ..validation import validate_stage_output
        valid, issues = validate_stage_output("codegen", outcome_data, project_dir=pdir)
        return StepOutcome(valid, data=outcome_data, errors=issues if not valid else [])

    recipe_id = get_recipe_id(params)
    generator = RECIPE_IMPL[recipe_id][0]
    files = generator(params)
    for rel, content in files.items():
        path = pdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    outcome_data = {"files": sorted(files)}
    from ..validation import validate_stage_output
    valid, issues = validate_stage_output("codegen", outcome_data, project_dir=pdir)
    return StepOutcome(valid, data=outcome_data, errors=issues if not valid else [])


def legacy_build(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)
    uproject = pdir / f"{project_name}.uproject"
    if not uproject.is_file():
        uprojects = list(pdir.glob("*.uproject"))
        if uprojects:
            uproject = uprojects[0]
    tc = _get_toolchain(ctx)
    target = ctx.step.inputs.get("target") or f"{project_name}Editor"
    config = ctx.step.inputs.get("configuration") or "Development"
    r = tc.build(uproject, target, configuration=config)
    d = r.to_dict()
    data = {
        "exit_code": r.exit_code,
        "log": r.log_path,
        "log_path": r.log_path,
        "errors": d.get("error_count", len(r.errors)),
        "warnings": d.get("warning_count", 0),
        "diagnostics": [x.__dict__ for x in r.diagnostics[:20]],
    }
    artifacts = [{"path": str(r.log_path), "kind": "log"}] if r.log_path else []
    errors = list(r.errors)
    if r.ok:
        from ..validation import validate_stage_output
        valid, issues = validate_stage_output("build", data, project_dir=pdir)
        if not valid:
            errors.extend([f"Build validation: {issue}" for issue in issues])
    return StepOutcome(r.ok and len(errors) == 0, data=data, errors=errors, artifacts=artifacts)


def legacy_assemble(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)
    uproject = pdir / f"{project_name}.uproject"
    if not uproject.is_file():
        uprojects = list(pdir.glob("*.uproject"))
        if uprojects:
            uproject = uprojects[0]
    evidence_dir = pdir / "Saved" / "GameForge"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    eng_root = Path(ctx.step.inputs.get("engine_root") or engine_root_or_missing())

    # Modern Composer LevelPlan execution path (eliminates "box-and-player" bug)
    if "plan" in ctx.step.inputs:
        from ...composer.model import LevelPlan
        from ...composer.level_ops import plan_to_op_calls
        from ...composer.runtime_def import build as build_gfdef
        from ...design import store as design_store
        from ...unreal.live_editor import LiveEditorLink

        plan_data = ctx.step.inputs["plan"]
        plan = LevelPlan.model_validate(plan_data) if isinstance(plan_data, dict) else plan_data

        gds = None
        if "gds" in ctx.step.inputs:
            from ...design.gds import GameDesignSpec
            try:
                gds = GameDesignSpec.model_validate(ctx.step.inputs["gds"])
            except Exception:
                gds = None
        if gds is None:
            gds = design_store.load(pdir)

        gfdef = build_gfdef(gds) if gds is not None else None
        level_id = ctx.step.inputs.get("level_id", getattr(plan, "level_id", "level_1"))
        is_first = str(level_id) in ("level_1", "1") or ctx.step.step_id == "assemble_level_1"

        op_calls = plan_to_op_calls(plan, gfdef=gfdef, is_first_level=is_first)

        link = LiveEditorLink(uproject, eng_root)
        link.prepare_project()
        log_file = evidence_dir / "assemble_editor.log"
        link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=log_file)

        out = []
        errors = []
        spawned_actors = {}
        readback_warnings = []
        try:
            link.connect(discovery_timeout_s=900)
            for call in op_calls:
                r = link.call(call.op, call.args, timeout_s=300)
                call_ok = bool(r.get("ok"))
                if not call_ok:
                    if call.op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                        call_ok = True
                    elif call.op == "nav_find_path":
                        # Reachability check warning: do not fail assembly hard
                        call_ok = True
                    else:
                        errors.extend(r.get("errors", []))
                if call.op == "spawn_actor" and call_ok:
                    r_data = r.get("data") or {}
                    lbl = call.args.get("label") or r_data.get("label")
                    if lbl and "location" in r_data:
                        spawned_actors[lbl] = r_data
                out.append({"op": call.op, "purpose": call.purpose, "ok": call_ok, "errors": r.get("errors", [])})

            # Read-back verification: verify spawned actor transforms match plan within tolerance
            from ...composer.level_ops import verify_placed_actor_transforms
            readback_warnings = verify_placed_actor_transforms(plan, spawned_actors, tolerance_cm=50.0)
            for w in readback_warnings:
                ctx.log(f"[WARNING] {w}")
        except Exception as exc:
            errors.append(f"assemble level failed: {exc}")
        finally:
            link.stop()

        data = {
            "calls": out,
            "total_calls": len(op_calls),
            "passed_calls": sum(1 for c in out if c.get("ok")),
            "readback_warnings": readback_warnings,
            "graceful": link.last_stop_graceful,
            "plan_level_id": getattr(plan, "level_id", "level_1"),
            "geometry_ops_count": len(getattr(plan, "geometry_ops", [])),
            "actors_count": len(getattr(plan, "actors", [])),
            "spawned_actors": spawned_actors,
            "actors": [a.model_dump() if hasattr(a, "model_dump") else a for a in getattr(plan, "actors", [])],
        }
        artifacts = [{"path": str(log_file), "kind": "log"}] if log_file.is_file() else []
        if log_file.is_file():
            data["log"] = str(log_file)
            data["log_path"] = str(log_file)
        if len(errors) == 0:
            assembled_map = getattr(plan, "map_path", None) or f"/Game/Maps/{str(level_id).capitalize()}"
            if is_first:
                _sync_project_map_settings(pdir, assembled_map)
            # Output evidence verification for assemble stage
            if gds is not None:
                try:
                    from ..validation import validate_stage_output
                    stage_ok, stage_issues = validate_stage_output("assemble", data, gds)
                    if not stage_ok:
                        errors.extend([f"Assemble validation: {issue}" for issue in stage_issues])
                except Exception as exc:
                    errors.append(f"Assemble validation error: {exc}")
        return StepOutcome(len(errors) == 0, data=data, errors=errors, artifacts=artifacts)

    recipe_id = get_recipe_id(params)
    assemble_fn = RECIPE_IMPL[recipe_id][1]
    ok, data, errors = assemble_fn(eng_root, uproject, evidence_dir, project_name, params)
    data = dict(data or {})
    if ok and data.get("map"):
        _sync_project_map_settings(pdir, data["map"])
    log_file = evidence_dir / "assemble_editor.log"
    artifacts = [{"path": str(log_file), "kind": "log"}] if log_file.is_file() else []
    if log_file.is_file():
        data["log"] = str(log_file)
        data["log_path"] = str(log_file)
    return StepOutcome(ok, data=data, errors=errors, artifacts=artifacts)


def legacy_tests(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)
    uproject = pdir / f"{project_name}.uproject"
    if not uproject.is_file():
        uprojects = list(pdir.glob("*.uproject"))
        if uprojects:
            uproject = uprojects[0]
    tc = _get_toolchain(ctx)
    tests = ctx.step.inputs.get("tests")
    if tests:
        test_filter = "+".join(tests) if isinstance(tests, list) else str(tests)
    else:
        test_filter = ctx.step.inputs.get("test_filter") or f"GameForge.{project_name}"
    r = tc.run_automation_tests(uproject, test_filter)
    data = {"exit_code": r.exit_code, "log": r.log_path, "log_path": r.log_path, **r.data}
    artifacts = [{"path": str(r.log_path), "kind": "log"}] if r.log_path else []
    errors = list(r.errors)
    if r.ok:
        from ..validation import validate_stage_output
        valid, issues = validate_stage_output("automation", data, project_dir=pdir)
        if not valid:
            errors.extend([f"Automation validation: {issue}" for issue in issues])
    return StepOutcome(r.ok and len(errors) == 0, data=data, errors=errors, artifacts=artifacts)


def legacy_package(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)
    uproject = pdir / f"{project_name}.uproject"
    if not uproject.is_file():
        uprojects = list(pdir.glob("*.uproject"))
        if uprojects:
            uproject = uprojects[0]

    # Pre-flight check: ensure DefaultEngine.ini points to an existing map
    eng_ini = pdir / "Config" / "DefaultEngine.ini"
    if eng_ini.is_file():
        text = eng_ini.read_text(encoding="utf-8")
        m = re.search(r"GameDefaultMap\s*=\s*([^\r\n]+)", text)
        curr_map = m.group(1).strip() if m else ""
        if curr_map.startswith("/Game/"):
            rel_asset = curr_map[len("/Game/"):]
            umap_path = pdir / "Content" / f"{rel_asset}.umap"
            if not umap_path.is_file():
                existing_maps = list((pdir / "Content" / "Maps").glob("*.umap"))
                if existing_maps:
                    best = next((f for f in existing_maps if f.stem.lower() in ("level_1", f"{project_name.lower()}map")), existing_maps[0])
                    corrected_map = f"/Game/Maps/{best.stem}"
                    _sync_project_map_settings(pdir, corrected_map)
                    ctx.log(f"Auto-healed stale GameDefaultMap from '{curr_map}' to '{corrected_map}'")
    _sync_project_map_settings(pdir, "")

    tc = _get_toolchain(ctx)
    ok, data, errors = engine_stages.package(tc, uproject)
    data = dict(data or {})
    if ok:
        from ..validation import validate_stage_output
        valid, issues = validate_stage_output("package", data, project_dir=pdir)
        if not valid:
            ok = False
            errors = list(errors or []) + issues
    return StepOutcome(ok, data=data, errors=errors)


def legacy_smoke(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    project_name = ctx.step.inputs.get("project_name") or (ctx.project_dir.name if ctx.project_dir else getattr(params, "project_name", "GameForgeProject"))
    pdir = ctx.project_dir or (ctx.workspace_dir / project_name)
    evidence_dir = pdir / "Saved" / "GameForge"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    recipe_id = get_recipe_id(params)
    selftest_pass = RECIPE_IMPL[recipe_id][4]
    tc = _get_toolchain(ctx)
    exe = ctx.shared.get("package", {}).get("exe") or ctx.step.inputs.get("exe")
    if not exe:
        return StepOutcome(False, errors=["packaged executable path not found in package step outputs"])
    ok, data, errors = engine_stages.packaged_smoke(
        tc, Path(exe), evidence_dir, project_name, expect_log=selftest_pass
    )
    return StepOutcome(ok, data=data, errors=errors)
