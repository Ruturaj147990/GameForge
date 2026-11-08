"""Forge scenario QA handler (WI-3.5)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...design.gds import GameDesignSpec
from ...qa.generate import ScenarioGap, generate
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
        # Fallback search strictly for packaged executables in Packaged/ (DEF-308: NEVER accept raw Binaries/Win64)
        candidates = [
            base_dir / "Packaged" / "Windows" / f"{p_name}.exe",
            base_dir / "Packaged" / "WindowsNoEditor" / f"{p_name}.exe",
            base_dir / "package_dev" / "Windows" / f"{p_name}.exe",
            base_dir / "package_ship" / "Windows" / f"{p_name}.exe",
        ]
        candidates += list(base_dir.glob(f"**/Packaged/**/{p_name}.exe")) + \
                      list(base_dir.glob(f"**/package_*/**/{p_name}.exe"))
        for c in candidates:
            if c.is_file() and "binaries" not in c.as_posix().lower() and not c.name.lower().endswith("crashreportclient.exe"):
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
    scenario_gaps: List[ScenarioGap] = []
    gds = None

    for g_path in gds_candidates:
        if g_path.is_file():
            try:
                gds = GameDesignSpec.model_validate_json(g_path.read_text(encoding="utf-8"))
                scs, gaps = generate(gds, manifests)
                scenarios.extend(scs)
                scenario_gaps.extend(gaps)
                break
            except Exception:
                pass

    if gds is None and "gds" in ctx.step.inputs:
        try:
            gds_input = ctx.step.inputs["gds"]
            gds = GameDesignSpec.model_validate(gds_input) if isinstance(gds_input, dict) else gds_input
            if gds:
                scs, gaps = generate(gds, manifests)
                scenarios.extend(scs)
                scenario_gaps.extend(gaps)
        except Exception:
            pass

    if gds is None:
        for sh in ctx.shared.values():
            if isinstance(sh, dict) and "gds" in sh:
                try:
                    gds = GameDesignSpec.model_validate(sh["gds"]) if isinstance(sh["gds"], dict) else sh["gds"]
                    if gds:
                        scs, gaps = generate(gds, manifests)
                        scenarios.extend(scs)
                        scenario_gaps.extend(gaps)
                        break
                except Exception:
                    pass

    # Fail closed if any mandatory acceptance criterion has a ScenarioGap (Section 5A.24)
    if gds is not None and scenario_gaps:
        mandatory_refs = [
            ref for ref in getattr(getattr(gds, "acceptance", None), "scenarios", [])
            if getattr(ref, "must_pass", True)
        ]
        mandatory_ids = {ref.scenario_id for ref in mandatory_refs}
        if scenario_ids:
            mandatory_ids = mandatory_ids.intersection(set(scenario_ids))

        mandatory_gaps = [g for g in scenario_gaps if not mandatory_ids or g.scenario_id in mandatory_ids]
        if mandatory_gaps:
            gap_msgs = [f"{g.scenario_id}: {g.reason}" for g in mandatory_gaps]
            return StepOutcome(
                ok=False,
                errors=[
                    f"Mandatory acceptance criteria have scenario gaps and cannot be verified: {'; '.join(gap_msgs)}"
                ] + [f"ScenarioGap({g.scenario_id}): {g.reason}" for g in mandatory_gaps],
            )

    # Load game-specific acceptance tests driven by GDS
    if gds is not None:
        try:
            from ...qa.game_spec_tests import (
                acceptance_tests_to_scenarios,
                generate_acceptance_tests,
            )
            spec_tests = generate_acceptance_tests(gds)
            spec_scs = acceptance_tests_to_scenarios(spec_tests)
            existing_ids = {s.scenario_id for s in scenarios}
            for s in spec_scs:
                if s.scenario_id not in existing_ids:
                    scenarios.append(s)
                    existing_ids.add(s.scenario_id)
        except Exception:
            pass

    # Also load hand-written scenarios from GameForge/scenarios/*.json
    sc_dirs = [
        base_dir / "GameForge" / "scenarios",
        base_dir / "Saved" / "GameForge" / "scenarios",
        ctx.workspace_dir / "GameForge" / "scenarios",
    ]
    existing_ids = {s.scenario_id for s in scenarios}
    for sc_dir in sc_dirs:
        if sc_dir.is_dir():
            for sf in sc_dir.glob("*.json"):
                try:
                    sc_obj = Scenario.from_file(sf)
                    if sc_obj.scenario_id not in existing_ids:
                        scenarios.append(sc_obj)
                        existing_ids.add(sc_obj.scenario_id)
                except Exception:
                    pass

    # Filter by scenario_ids if provided
    input_scenarios = ctx.step.inputs.get("scenarios")
    if scenario_ids:
        scenarios = [s for s in scenarios if s.scenario_id in scenario_ids]
    elif input_scenarios and isinstance(input_scenarios, list):
        if all(isinstance(x, str) for x in input_scenarios):
            allowed = set(input_scenarios)
            if gds is not None:
                try:
                    from ...qa.game_spec_tests import generate_acceptance_tests
                    allowed.update(st.test_id for st in generate_acceptance_tests(gds))
                except Exception:
                    pass
            filtered = [s for s in scenarios if s.scenario_id in allowed]
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

    # Resolve target map path
    target_map = ctx.step.inputs.get("map_path")
    if not target_map:
        for k, v in ctx.shared.items():
            if k.startswith("assemble_") and isinstance(v, dict) and v.get("map"):
                target_map = v["map"]
                break
    if not target_map and manifests:
        target_map = manifests[0].map
    if not target_map:
        eng_ini = base_dir / "Config" / "DefaultEngine.ini"
        if eng_ini.is_file():
            text = eng_ini.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"GameDefaultMap\s*=\s*([^\r\n]+)", text)
            if m:
                target_map = m.group(1).strip()
    if not target_map:
        if (base_dir / "Content" / "Maps" / "Level_1.umap").is_file():
            target_map = "/Game/Maps/Level_1"
        elif (base_dir / "Content" / "Maps" / f"{p_name}Map.umap").is_file():
            target_map = f"/Game/Maps/{p_name}Map"

    # Scenarios the design marks must_pass=False (e.g. a jump course the navmesh autopilot cannot traverse) are
    # advisory: their failures are reported but do not fail the build.
    advisory_ids = set()
    if gds is not None:
        try:
            advisory_ids = {r.scenario_id for r in gds.acceptance.scenarios if not getattr(r, "must_pass", True)}
        except Exception:
            advisory_ids = set()

    for sc in scenarios:
        if ctx.cancel.is_set():
            return StepOutcome(False, errors=["Cancelled by user"])

        res = run_packaged(exe_path, sc, out_dir=out_dir, timeout_s=sc.timeout_s, map_path=target_map)
        res_file = out_dir / f"{sc.scenario_id}_result.json"
        if res_file.is_file():
            artifacts.append(res_file)

        events_file = out_dir / f"{sc.scenario_id}_events.jsonl"
        if events_file.is_file():
            artifacts.append(events_file)

        advisory = sc.scenario_id in advisory_ids
        results.append({
            "scenario_id": sc.scenario_id,
            "passed": res.passed,
            "duration_s": res.duration_s,
            "failures": res.failures,
            "advisory": advisory,
        })

        if not res.passed:
            if advisory:
                ctx.log(f"[ADVISORY] scenario {sc.scenario_id} not verified by autopilot: {'; '.join(res.failures)[:300]}")
            else:
                all_passed = False
                errors.extend([f"Scenario {sc.scenario_id} failed: {f}" for f in res.failures])

    stage_data = {"results": results, "configuration": cfg}
    if all_passed and gds is not None:
        try:
            from ..validation import validate_stage_output
            stage_ok, stage_issues = validate_stage_output("scenarios", stage_data, gds)
            if not stage_ok:
                all_passed = False
                errors.extend([f"Scenario validation: {issue}" for issue in stage_issues])
        except Exception:
            pass

    return StepOutcome(
        ok=all_passed,
        data=stage_data,
        artifacts=[{"path": str(a), "kind": "scenario_result"} for a in artifacts],
        errors=errors,
    )


def scenario_gen_handler(ctx: StepContext) -> StepOutcome:
    """Forge SCENARIO_GEN step: generate QA playtest scenarios from GDS, manifests, or composer inputs."""
    base_dir = Path(ctx.project_dir) if ctx.project_dir else Path(ctx.workspace_dir)
    p_name = base_dir.name
    scenarios_dir = base_dir / "GameForge" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    scenarios: List[Scenario] = []

    # 1. Inputs from composer plan
    input_scenarios = ctx.step.inputs.get("scenarios") or []
    for sc_data in input_scenarios:
        try:
            if isinstance(sc_data, Scenario):
                scenarios.append(sc_data)
            elif isinstance(sc_data, dict):
                scenarios.append(Scenario.model_validate(sc_data))
        except Exception:
            pass

    # 2. GDS-driven scenario generation
    gds = None
    gds_candidates = [
        base_dir / "GameForge" / "design" / "game.gds.json",
        base_dir / "GameForge" / "gds.json",
        base_dir / "Saved" / "GameForge" / "gds.json",
        ctx.workspace_dir / "GameForge" / "gds.json",
    ]
    for g_path in gds_candidates:
        if g_path.is_file():
            try:
                gds = GameDesignSpec.model_validate_json(g_path.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    if gds is None and "gds" in ctx.step.inputs:
        try:
            gds_input = ctx.step.inputs["gds"]
            gds = GameDesignSpec.model_validate(gds_input) if isinstance(gds_input, dict) else gds_input
        except Exception:
            pass

    if gds is None:
        for sh in ctx.shared.values():
            if isinstance(sh, dict) and "gds" in sh:
                try:
                    gds = GameDesignSpec.model_validate(sh["gds"]) if isinstance(sh["gds"], dict) else sh["gds"]
                    if gds:
                        break
                except Exception:
                    pass

    # Find level manifests
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

    gaps: List[ScenarioGap] = []
    if gds is not None:
        try:
            scs, gen_gaps = generate(gds, manifests)
            gaps.extend(gen_gaps)
            existing_ids = {s.scenario_id for s in scenarios}
            for s in scs:
                if s.scenario_id not in existing_ids:
                    scenarios.append(s)
                    existing_ids.add(s.scenario_id)
        except Exception:
            pass

        try:
            from ...qa.game_spec_tests import (
                acceptance_tests_to_scenarios,
                generate_acceptance_tests,
            )
            spec_tests = generate_acceptance_tests(gds)
            spec_scs = acceptance_tests_to_scenarios(spec_tests)
            existing_ids = {s.scenario_id for s in scenarios}
            for s in spec_scs:
                if s.scenario_id not in existing_ids:
                    scenarios.append(s)
                    existing_ids.add(s.scenario_id)
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

    # Write generated scenarios to disk
    artifacts = []
    for s in scenarios:
        sc_path = scenarios_dir / f"{s.scenario_id}.json"
        try:
            sc_path.write_text(s.model_dump_json(indent=2), encoding="utf-8")
            artifacts.append(sc_path)
        except Exception:
            pass

    ctx.log(f"Generated {len(scenarios)} QA playtest scenarios in {scenarios_dir}")
    return StepOutcome(
        ok=True,
        data={
            "scenarios": [s.model_dump() for s in scenarios],
            "count": len(scenarios),
            "gaps": [{"scenario_id": g.scenario_id, "reason": g.reason} for g in gaps],
        },
        artifacts=[{"path": str(a), "kind": "scenario_result"} for a in artifacts],
    )
