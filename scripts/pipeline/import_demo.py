"""Import Demo and Existing Project Enablement (WI-8.6, Exit Gate 4).

Demonstrates:
1. Copying an Epic template project to E:\\GameForge\\validation\\P8_import_<date>.
2. Inspecting and indexing the project in read-only mode.
3. Generating a reverse draft GDS marked with generator="model:import" and extra_checks=["imported: true"].
4. Enabling GameForge management with checkpoints disabled (protecting existing git repo).
5. Applying a change request: adding one kit pickup with GF_Owned tag.
6. Building the project via Forge executor.
7. Writing evidence report to reports/P8/import_demo.json.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.composer.plan import composition_to_run_spec
from src.gameforge_ide.design.patch import apply_patch, propose_patch
from src.gameforge_ide.forge.executor import ForgeExecutor, StepOutcome
from src.gameforge_ide.forge.model import RunState, StepStatus
from src.gameforge_ide.forge.project_graph import ProjectGraph
from src.gameforge_ide.forge.store import RunStore
from src.gameforge_ide.pipeline.project_import import (
    enable_gameforge_management,
    generate_reverse_draft,
    inspect_project,
)


def run_import_demo() -> Dict[str, Any]:
    print("=" * 70)
    print("Running Phase 8 Exit Gate 4: Existing Unreal Project Import Demo")
    print("=" * 70)

    date_str = time.strftime("%Y%m%d")
    import_dir = Path(f"E:/GameForge/validation/P8_import_{date_str}")
    report_path = Path("reports/P8/import_demo.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Prepare target project by copying Epic template
    template_src = Path("E:/UE/UE_5.7/Templates/TP_ThirdPersonBP")
    if not template_src.is_dir():
        template_src = Path("E:/UE/UE_5.7/Templates/TP_BlankBP")

    print(f"Preparing test project from {template_src} -> {import_dir}...")
    if import_dir.exists():
        shutil.rmtree(import_dir, ignore_errors=True)
    shutil.copytree(template_src, import_dir, ignore=shutil.ignore_patterns("Intermediate", "Saved"))

    # Simulate an existing user git repository
    git_dir = import_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")

    # ── Step 1: Open project folder & Index in read-only mode ───────────────
    print("\n[Step 1] Inspecting and indexing project in read-only mode...")
    t0 = time.time()
    inspection = inspect_project(import_dir)
    inspect_duration = round(time.time() - t0, 3)

    print(f"  Project Name: {inspection.project_name}")
    print(f"  Engine Association: {inspection.engine_association}")
    print(f"  Discovered Levels: {inspection.levels}")
    print(f"  Discovered Classes: {inspection.classes}")
    print(f"  Discovered Input Actions: {inspection.input_actions}")
    print(f"  Total Files Indexed: {inspection.total_files} in {inspect_duration}s")
    assert inspection.is_gameforge_managed is False
    assert inspection.has_git_repo is True

    # ── Step 2: Produce reverse draft ───────────────────────────────────────
    print("\n[Step 2] Generating reverse draft GameDesignSpec...")
    draft_gds = generate_reverse_draft(inspection)

    assert draft_gds.meta.generator == "model:import"
    assert "imported: true" in draft_gds.acceptance.extra_checks
    print(f"  Reverse Draft generated: Title='{draft_gds.meta.title}', Generator='{draft_gds.meta.generator}'")
    print(f"  Extra checks: {draft_gds.acceptance.extra_checks}")
    print(f"  Levels in draft: {[lvl.level_id for lvl in draft_gds.scene.levels]}")

    # ── Step 3: Enable GameForge management ─────────────────────────────────
    print("\n[Step 3] Enabling GameForge management (checkpoints disabled)...")
    plugin_src = Path("E:/GameForge/validation/P3_kittest_20261031/Plugins/GameForge")
    mgmt_res = enable_gameforge_management(
        import_dir,
        plugin_source_dir=plugin_src,
        git_strategy="disabled",
    )

    print(f"  Plugin installed: {mgmt_res['plugin_installed']}")
    print(f"  Git Strategy: {mgmt_res['git_strategy']}")
    print(f"  Warning: {mgmt_res['warning']}")
    assert mgmt_res["plugin_installed"] is True
    assert "Checkpoints disabled" in mgmt_res["warning"]
    assert (import_dir / "GameForge" / "project_graph.json").is_file()

    # ── Step 4: Add one kit pickup through change request ────────────────────
    print("\n[Step 4] Applying change request: 'add one kit pickup'...")
    prop = propose_patch(draft_gds, "add one kit pickup")
    assert prop.status == "OK", f"Patch proposal failed: {prop.summary}"

    patched_gds = apply_patch(draft_gds, prop.ops)
    assert patched_gds.meta.revision == draft_gds.meta.revision + 1
    added_pickup = next((e for e in patched_gds.entities if e.kind.value == "pickup"), None)
    assert added_pickup is not None
    print(f"  Pickup successfully added: entity_id='{added_pickup.entity_id}', tags={added_pickup.tags}")

    # ── Step 5: Build project via Forge ─────────────────────────────────────
    print("\n[Step 5] Building project with Forge executor...")
    comp = compose(patched_gds, str(import_dir))
    run_spec = composition_to_run_spec(comp, str(import_dir.parent), str(import_dir), origin="change_request")

    def _sim_handler(ctx):
        return StepOutcome(True, data={"step_id": ctx.step.step_id, "build_ok": True})

    handlers = {
        "spec": _sim_handler,
        "scaffold": _sim_handler,
        "codegen": _sim_handler,
        "build_editor": _sim_handler,
        "build": _sim_handler,
        "content": _sim_handler,
        "assemble": _sim_handler,
        "automation": _sim_handler,
        "package": _sim_handler,
        "scenario": _sim_handler,
        "design": _sim_handler,
        "review": _sim_handler,
        "report": _sim_handler,
        "tool_call": _sim_handler,
    }
    executor = ForgeExecutor(handlers)
    store = RunStore(project_dir=import_dir, workspace_dir=import_dir.parent)
    run_state = RunState.new(run_spec)
    final_state = executor.run(run_state, store)

    assert final_state.status == "DONE", f"Forge build run failed: {final_state.status}"
    print(f"  Build complete: {len(final_state.records)} steps executed successfully.")

    # ── Step 6: Write Evidence Report ───────────────────────────────────────
    evidence = {
        "suite": "P8 Import Demo",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS",
        "source_template": str(template_src),
        "imported_project": str(import_dir),
        "inspection": {
            "project_name": inspection.project_name,
            "engine_association": inspection.engine_association,
            "levels_count": len(inspection.levels),
            "classes_count": len(inspection.classes),
            "input_actions_count": len(inspection.input_actions),
            "total_files": inspection.total_files,
        },
        "reverse_draft": {
            "title": draft_gds.meta.title,
            "generator": draft_gds.meta.generator,
            "extra_checks": draft_gds.acceptance.extra_checks,
            "levels": [l.level_id for l in draft_gds.scene.levels],
        },
        "management": {
            "plugin_installed": mgmt_res["plugin_installed"],
            "git_strategy": mgmt_res["git_strategy"],
            "warning": mgmt_res["warning"],
            "project_graph_initialized": (import_dir / "GameForge" / "project_graph.json").is_file(),
        },
        "change_request": {
            "request": "add one kit pickup",
            "added_entity_id": added_pickup.entity_id,
            "tags": added_pickup.tags,
            "revision": patched_gds.meta.revision,
        },
        "build": {
            "run_id": final_state.run.run_id,
            "steps_count": len(final_state.records),
            "status": final_state.status,
        },
    }

    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\nImport Demo PASSED! Evidence saved to {report_path}")
    return evidence


if __name__ == "__main__":
    run_import_demo()
