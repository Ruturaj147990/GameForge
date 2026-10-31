"""Legacy recipe pipeline stages adapted as Forge handlers (AD-11)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type, Union

from ...core.settings import engine_root_or_missing, get_settings
from ...pipeline import stages as engine_stages
from ...recipes.arena_combat.recipe import (
    RECIPE_ID as ARENA_RECIPE_ID,
    RECIPE_VERSION as ARENA_RECIPE_VERSION,
    SELFTEST_LOG_PASS as ARENA_SELFTEST_PASS,
    ArenaCombatParams,
    generate as arena_generate,
)
from ...recipes.card_battler.recipe import (
    RECIPE_ID as CARD_RECIPE_ID,
    RECIPE_VERSION as CARD_RECIPE_VERSION,
    SELFTEST_LOG_PASS as CARD_SELFTEST_PASS,
    CardBattlerParams,
    generate as card_generate,
)
from ...recipes.grid_board_game.recipe import (
    RECIPE_ID as GRID_RECIPE_ID,
    RECIPE_VERSION as GRID_RECIPE_VERSION,
    SELFTEST_LOG_PASS as GRID_SELFTEST_PASS,
    GridBoardParams,
    generate as grid_generate,
)
from ...recipes.platformer.recipe import (
    RECIPE_ID as PLATFORMER_RECIPE_ID,
    RECIPE_VERSION as PLATFORMER_RECIPE_VERSION,
    SELFTEST_LOG_PASS as PLATFORMER_SELFTEST_PASS,
    PlatformerParams,
    generate as platformer_generate,
)
from ...recipes.procedural_world.recipe import (
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
    params = get_params(ctx)
    params.validate()
    tc = _get_toolchain(ctx)
    missing = [k for k, v in tc.check().items() if not v]
    if missing:
        return StepOutcome(False, errors=[f"engine tools missing: {missing}"], blocked=True)
    return StepOutcome(True, data={"params": params.to_dict(), "engine": tc.engine_version()})


def legacy_scaffold(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    uproject = pdir / f"{params.project_name}.uproject"
    recipe_id = get_recipe_id(params)
    impl = RECIPE_IMPL[recipe_id]
    default_gm = impl[3].format(name=params.project_name)
    deps = impl[2]
    tc = _get_toolchain(ctx)
    info = tc.scaffold_cpp_project(
        pdir,
        params.project_name,
        default_map=f"/Game/Maps/{params.project_name}Map",
        game_mode=default_gm,
        module_deps=deps,
        display_title=params.display_title,
    )
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

    return StepOutcome(uproject.is_file(), data=info, errors=[] if uproject.is_file() else ["uproject not found"])


def legacy_sources(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    recipe_id = get_recipe_id(params)
    generator = RECIPE_IMPL[recipe_id][0]
    files = generator(params)
    for rel, content in files.items():
        path = pdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return StepOutcome(True, data={"files": sorted(files)})


def legacy_build(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    uproject = pdir / f"{params.project_name}.uproject"
    tc = _get_toolchain(ctx)
    r = tc.build(uproject, f"{params.project_name}Editor")
    d = r.to_dict()
    data = {
        "exit_code": r.exit_code,
        "log": r.log_path,
        "errors": d.get("error_count", len(r.errors)),
        "warnings": d.get("warning_count", 0),
        "diagnostics": [x.__dict__ for x in r.diagnostics[:20]],
    }
    artifacts = [{"path": str(r.log_path), "kind": "log"}] if r.log_path else []
    return StepOutcome(r.ok, data=data, errors=r.errors, artifacts=artifacts)


def legacy_assemble(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    uproject = pdir / f"{params.project_name}.uproject"
    evidence_dir = pdir / "Saved" / "GameForge"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    recipe_id = get_recipe_id(params)
    assemble_fn = RECIPE_IMPL[recipe_id][1]
    eng_root = Path(ctx.step.inputs.get("engine_root") or engine_root_or_missing())
    ok, data, errors = assemble_fn(eng_root, uproject, evidence_dir, params.project_name, params)
    return StepOutcome(ok, data=data, errors=errors)


def legacy_tests(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    uproject = pdir / f"{params.project_name}.uproject"
    tc = _get_toolchain(ctx)
    r = tc.run_automation_tests(uproject, f"GameForge.{params.project_name}")
    return StepOutcome(r.ok, data={"exit_code": r.exit_code, "log": r.log_path, **r.data}, errors=r.errors)


def legacy_package(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    uproject = pdir / f"{params.project_name}.uproject"
    tc = _get_toolchain(ctx)
    ok, data, errors = engine_stages.package(tc, uproject)
    return StepOutcome(ok, data=data, errors=errors)


def legacy_smoke(ctx: StepContext) -> StepOutcome:
    params = get_params(ctx)
    pdir = ctx.project_dir or (ctx.workspace_dir / params.project_name)
    evidence_dir = pdir / "Saved" / "GameForge"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    recipe_id = get_recipe_id(params)
    selftest_pass = RECIPE_IMPL[recipe_id][4]
    tc = _get_toolchain(ctx)
    exe = ctx.shared.get("package", {}).get("exe") or ctx.step.inputs.get("exe")
    if not exe:
        return StepOutcome(False, errors=["packaged executable path not found in package step outputs"])
    ok, data, errors = engine_stages.packaged_smoke(
        tc, Path(exe), evidence_dir, params.project_name, expect_log=selftest_pass
    )
    return StepOutcome(ok, data=data, errors=errors)
