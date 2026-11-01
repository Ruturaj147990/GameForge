"""Forge scenario QA handler (WI-3.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...design.gds import GameDesignSpec
from ...qa.generate import generate
from ...qa.manifest import LevelManifest
from ...qa.runner import run_packaged
from ...qa.scenario import (
    EventExpectation,
    NoEventExpectation,
    Scenario,
    ScenarioResult,
    WaitArgs,
    WaitStep,
)
from ..executor import StepContext, StepOutcome


def scenario_handler(ctx: StepContext) -> StepOutcome:
    """Execute scenario playtests on the packaged build."""
    cfg = ctx.step.inputs.get("configuration", "Development")
    scenario_ids = ctx.step.inputs.get("scenario_ids")

    # Find exe from shared context or search workspace
    exe_str = ctx.shared.get("package", {}).get("exe")
    exe_path: Optional[Path] = Path(exe_str) if exe_str else None

    base_dir = Path(ctx.project_dir) if ctx.project_dir else Path(ctx.workspace_dir)
    p_name = base_dir.name

    if not exe_path or not exe_path.is_file():
        # Fallback search in project_dir and workspace
        candidates = [
            base_dir / "Packaged" / "Windows" / f"{p_name}.exe",
            base_dir / "Binaries" / "Win64" / f"{p_name}.exe",
        ]
        candidates += list(base_dir.glob(f"**/{cfg}/**/{p_name}.exe")) + \
                      list(base_dir.glob(f"**/Windows/**/{p_name}.exe")) + \
                      list(base_dir.glob(f"**/Packaged/**/{p_name}.exe")) + \
                      list(ctx.workspace_dir.glob(f"**/{p_name}.exe"))
        for c in candidates:
            if c.is_file():
                exe_path = c
                break

    if not exe_path or not exe_path.is_file():
        return StepOutcome(
            False,
            errors=[f"Packaged executable not found for configuration '{cfg}' (checked shared and workspace)"],
        )

    artifacts_dir = getattr(ctx, "artifacts_dir", None) or (base_dir / "Saved" / "GameForge" / "evidence")
    out_dir = artifacts_dir / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load manifests if present
    manifests: List[LevelManifest] = []
    manifest_dirs = [
        base_dir / "GameForge" / "levels",
        base_dir / "Saved" / "GameForge" / "levels",
        ctx.workspace_dir / "GameForge" / "levels",
    ]
    for m_dir in manifest_dirs:
        if m_dir.is_dir():
            for mf in m_dir.glob("*.manifest.json"):
                try:
                    manifests.append(LevelManifest.from_file(mf))
                except Exception:
                    pass

    # Load GDS if present
    gds_candidates = [
        base_dir / "GameForge" / "design" / "game.gds.json",
        base_dir / "GameForge" / "gds.json",
        base_dir / "Saved" / "GameForge" / "gds.json",
        ctx.workspace_dir / "GameForge" / "gds.json",
    ]
    scenarios: List[Scenario] = []

    for g_path in gds_candidates:
        if g_path.is_file():
            try:
                gds = GameDesignSpec.model_validate_json(g_path.read_text(encoding="utf-8"))
                scs, _ = generate(gds, manifests)
                scenarios.extend(scs)
                break
            except Exception:
                pass

    # Also load hand-written scenarios from GameForge/scenarios/*.json
    sc_dirs = [
        base_dir / "GameForge" / "scenarios",
        base_dir / "Saved" / "GameForge" / "scenarios",
        ctx.workspace_dir / "GameForge" / "scenarios",
    ]
    for sc_dir in sc_dirs:
        if sc_dir.is_dir():
            for sf in sc_dir.glob("*.json"):
                try:
                    scenarios.append(Scenario.from_file(sf))
                except Exception:
                    pass

    # Filter by scenario_ids if provided
    input_scenarios = ctx.step.inputs.get("scenarios")
    if scenario_ids:
        scenarios = [s for s in scenarios if s.scenario_id in scenario_ids]
    elif input_scenarios and isinstance(input_scenarios, list):
        if all(isinstance(x, str) for x in input_scenarios):
            filtered = [s for s in scenarios if s.scenario_id in input_scenarios]
            if filtered:
                scenarios = filtered
        elif all(isinstance(x, dict) for x in input_scenarios):
            for x in input_scenarios:
                try:
                    scenarios.append(Scenario.model_validate(x))
                except Exception:
                    pass

    if not scenarios:
        # Default fallback smoke scenario
        scenarios.append(
            Scenario(
                scenario_id="smoke",
                description=f"Smoke test for {p_name}: launch and stay alive",
                timeout_s=30.0,
                steps=[WaitStep(wait_s=WaitArgs(seconds=5.0))],
                expect=[
                    EventExpectation(event="game.started"),
                    NoEventExpectation(no_event="player.died"),
                ],
                captures=[],
            )
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
        data={"results": results, "configuration": cfg},
        artifacts=[{"path": str(a), "kind": "scenario_result"} for a in artifacts],
        errors=errors,
    )
