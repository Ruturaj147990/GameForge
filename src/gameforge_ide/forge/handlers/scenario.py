"""Forge scenario QA handler (WI-3.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...design.gds import GameDesignSpec
from ...qa.generate import generate
from ...qa.manifest import LevelManifest
from ...qa.runner import run_packaged
from ...qa.scenario import Scenario, ScenarioResult
from ..executor import StepContext, StepOutcome


def scenario_handler(ctx: StepContext) -> StepOutcome:
    """Execute scenario playtests on the packaged build."""
    cfg = ctx.step.inputs.get("configuration", "Development")
    scenario_ids = ctx.step.inputs.get("scenario_ids")

    # Find exe from shared context or search workspace
    exe_str = ctx.shared.get("package", {}).get("exe")
    exe_path: Optional[Path] = Path(exe_str) if exe_str else None

    if not exe_path or not exe_path.is_file():
        # Fallback search in workspace
        candidates = list(ctx.workspace_dir.glob(f"**/{cfg}/**/{ctx.workspace_dir.name}.exe")) + \
                     list(ctx.workspace_dir.glob(f"**/Windows/**/{ctx.workspace_dir.name}.exe")) + \
                     list(ctx.workspace_dir.glob(f"**/package*/**/{ctx.workspace_dir.name}.exe"))
        if candidates and candidates[0].is_file():
            exe_path = candidates[0]

    if not exe_path or not exe_path.is_file():
        return StepOutcome(
            False,
            errors=[f"Packaged executable not found for configuration '{cfg}' (checked shared and workspace)"],
        )

    out_dir = ctx.artifacts_dir / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load manifests if present
    manifests: List[LevelManifest] = []
    manifest_dir = ctx.workspace_dir / "GameForge" / "levels"
    if manifest_dir.is_dir():
        for mf in manifest_dir.glob("*.manifest.json"):
            try:
                manifests.append(LevelManifest.from_file(mf))
            except Exception:
                pass

    # Load GDS if present
    gds_path = ctx.workspace_dir / "GameForge" / "gds.json"
    scenarios: List[Scenario] = []

    if gds_path.is_file():
        try:
            gds = GameDesignSpec.from_file(gds_path)
            scs, _ = generate(gds, manifests)
            scenarios.extend(scs)
        except Exception as exc:
            pass

    # Also load hand-written scenarios from GameForge/scenarios/*.json
    sc_dir = ctx.workspace_dir / "GameForge" / "scenarios"
    if sc_dir.is_dir():
        for sf in sc_dir.glob("*.json"):
            try:
                scenarios.append(Scenario.from_file(sf))
            except Exception:
                pass

    # Filter by scenario_ids if provided
    if scenario_ids:
        scenarios = [s for s in scenarios if s.scenario_id in scenario_ids]

    if not scenarios:
        return StepOutcome(
            False,
            errors=["No scenarios found or generated to execute"],
        )

    results: List[Dict[str, Any]] = []
    artifacts: List[Path] = []
    errors: List[str] = []
    all_passed = True

    for sc in scenarios:
        if ctx.cancel.is_set():
            return StepOutcome(False, errors=["Cancelled by user"])

        res = run_packaged(exe_path, sc, out_dir=out_dir, timeout_s=sc.timeout_s)
        res_file = out_dir / f"{sc.scenario_id}_result.json"
        if res_file.is_file():
            artifacts.append(res_file)

        events_file = out_dir / f"{sc.scenario_id}_events.jsonl"
        if events_file.is_file():
            artifacts.append(events_file)

        results.append({
            "scenario_id": sc.scenario_id,
            "passed": res.passed,
            "duration_s": res.duration_s,
            "failures": res.failures,
        })

        if not res.passed:
            all_passed = False
            errors.extend([f"Scenario {sc.scenario_id} failed: {f}" for f in res.failures])

    return StepOutcome(
        ok=all_passed,
        outputs={"results": results, "configuration": cfg},
        artifacts=artifacts,
        errors=errors,
    )
