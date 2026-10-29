"""Prompt -> playable game pipeline (Master Blueprint v2, section 3 worked example).

Stages, each producing evidence and a pass/fail verdict (fail closed, stop at first failure):
  spec -> scaffold -> sources -> build_editor -> assemble_level -> automation_tests
       -> package -> packaged_smoke -> report

The orchestrator is model-agnostic: it consumes a validated recipe parameter set. Turning a
natural-language prompt into that parameter set is done by spec_from_prompt (LLM, schema-
constrained) or by deterministic keyword matching when no model is available.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from ..recipes.arena_combat.recipe import (
    RECIPE_ID as ARENA_RECIPE_ID, RECIPE_VERSION as ARENA_RECIPE_VERSION,
    SELFTEST_LOG_PASS as ARENA_SELFTEST_PASS, ArenaCombatParams, generate as arena_generate)
from ..recipes.card_battler.recipe import (
    RECIPE_ID as CARD_RECIPE_ID, RECIPE_VERSION as CARD_RECIPE_VERSION,
    SELFTEST_LOG_PASS as CARD_SELFTEST_PASS, CardBattlerParams, generate as card_generate)
from ..recipes.grid_board_game.recipe import (
    RECIPE_ID as GRID_RECIPE_ID, RECIPE_VERSION as GRID_RECIPE_VERSION,
    SELFTEST_LOG_PASS as GRID_SELFTEST_PASS, GridBoardParams, generate as grid_generate)
from ..recipes.platformer.recipe import (
    RECIPE_ID as PLATFORMER_RECIPE_ID, RECIPE_VERSION as PLATFORMER_RECIPE_VERSION,
    SELFTEST_LOG_PASS as PLATFORMER_SELFTEST_PASS, PlatformerParams, generate as platformer_generate)
from . import stages as engine_stages
from ..unreal.toolchain import UnrealToolchain

STAGES = ["spec", "scaffold", "sources", "build_editor", "assemble_level",
          "automation_tests", "package", "packaged_smoke", "report"]


@dataclass
class StageRecord:
    stage: str
    ok: bool
    duration_s: float
    data: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    ok: bool
    project_dir: str
    stages: List[StageRecord]
    report_path: Optional[str] = None
    failed_stage: Optional[str] = None

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "project_dir": self.project_dir, "report_path": self.report_path,
                "failed_stage": self.failed_stage,
                "stages": [s.__dict__ for s in self.stages]}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_content(path: Path) -> Dict:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"checked": False}
    img = Image.open(path).convert("L")
    hist = img.histogram()
    lit = sum(hist[16:]) / max(1, sum(hist))
    sd = ImageStat.Stat(img).stddev[0]
    return {"checked": True, "size": list(img.size), "lit_fraction": round(lit, 4), "stddev": round(sd, 2),
            "has_content": lit > 0.05 and sd > 5}


class GamePipeline:
    def __init__(self, projects_root: Path = Path(r"E:\GameForge\projects"),
                 engine_root: Path = Path(r"E:\UE\UE_5.7"),
                 on_event: Optional[Callable[[str, Dict], None]] = None,
                 max_parallel_actions: Optional[int] = None, cancel_event=None):
        self.projects_root = Path(projects_root)
        self.engine_root = Path(engine_root)
        self.toolchain = UnrealToolchain(self.engine_root, max_parallel_actions=max_parallel_actions)
        self.on_event = on_event or (lambda kind, data: None)
        self.cancel_event = cancel_event
        self.toolchain.cancel_event = cancel_event

    def _emit(self, kind: str, **data) -> None:
        try:
            self.on_event(kind, data)
        except Exception:
            pass

    def run(self, params: Union[GridBoardParams, PlatformerParams, ArenaCombatParams, CardBattlerParams], skip_package: bool = False,
            stop_after: Optional[str] = None) -> PipelineResult:
        is_platformer = isinstance(params, PlatformerParams)
        is_arena = isinstance(params, ArenaCombatParams)
        is_card = isinstance(params, CardBattlerParams)
        if is_card:
            recipe_id = CARD_RECIPE_ID
            recipe_version = CARD_RECIPE_VERSION
            selftest_pass = CARD_SELFTEST_PASS
            default_gm = f"/Script/{params.project_name}.GFCardGameMode"
        elif is_arena:
            recipe_id = ARENA_RECIPE_ID
            recipe_version = ARENA_RECIPE_VERSION
            selftest_pass = ARENA_SELFTEST_PASS
            default_gm = f"/Script/{params.project_name}.GFArenaGameMode"
        elif is_platformer:
            recipe_id = PLATFORMER_RECIPE_ID
            recipe_version = PLATFORMER_RECIPE_VERSION
            selftest_pass = PLATFORMER_SELFTEST_PASS
            default_gm = f"/Script/{params.project_name}.GFPlatformerGameMode"
        else:
            recipe_id = GRID_RECIPE_ID
            recipe_version = GRID_RECIPE_VERSION
            selftest_pass = GRID_SELFTEST_PASS
            default_gm = f"/Script/{params.project_name}.GFGameMode"

        project_dir = self.projects_root / params.project_name
        uproject = project_dir / f"{params.project_name}.uproject"
        evidence_dir = project_dir / "Saved" / "GameForge"
        stages: List[StageRecord] = []
        ctx: Dict = {}

        def stage(name: str, fn: Callable[[], StageRecord]) -> bool:
            if self.cancel_event is not None and self.cancel_event.is_set():
                stages.append(StageRecord(name, False, 0.0, errors=["CANCELLED by user"]))
                self._emit("stage_finished", stage=name, ok=False, duration_s=0.0, errors=["CANCELLED by user"])
                return False
            self._emit("stage_started", stage=name)
            t0 = time.monotonic()
            try:
                rec = fn()
            except Exception as exc:  # any unexpected failure is a typed stage failure
                rec = StageRecord(name, False, 0.0, errors=[f"{type(exc).__name__}: {exc}"])
            rec.duration_s = round(time.monotonic() - t0, 1)
            stages.append(rec)
            self._emit("stage_finished", stage=name, ok=rec.ok, duration_s=rec.duration_s, errors=rec.errors)
            return rec.ok

        def finish(failed: Optional[str]) -> PipelineResult:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            report = evidence_dir / "pipeline_report.json"
            res = PipelineResult(failed is None, str(project_dir), stages, str(report), failed)
            payload = res.to_dict()
            payload.update({"recipe": recipe_id, "recipe_version": recipe_version, "params": params.to_dict(),
                            "engine_version": self.toolchain.engine_version(),
                            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            report.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
            (evidence_dir / "pipeline_report.md").write_text(render_markdown(payload), encoding="utf-8")
            self._emit("pipeline_finished", ok=res.ok, report=str(report), failed_stage=failed)
            return res

        # 1 spec
        def s_spec():
            params.validate()
            missing = [k for k, v in self.toolchain.check().items() if not v]
            if missing:
                return StageRecord("spec", False, 0, errors=[f"engine tools missing: {missing}"])
            return StageRecord("spec", True, 0, {"params": params.to_dict(), "engine": self.toolchain.engine_version()})

        # 2 scaffold
        def s_scaffold():
            name = params.project_name
            if is_card:
                deps = ["UMG", "Slate", "SlateCore"]
            elif is_arena:
                deps = ["AIModule", "NavigationSystem", "UMG", "Slate", "SlateCore"]
            elif is_platformer:
                deps = ["UMG", "Slate", "SlateCore"]
            else:
                deps = None
            info = self.toolchain.scaffold_cpp_project(
                project_dir, name, default_map=f"/Game/Maps/{name}Map",
                game_mode=default_gm, module_deps=deps, display_title=params.display_title)
            return StageRecord("scaffold", uproject.is_file(), 0, info)

        # 3 sources
        def s_sources():
            if is_card:
                files = card_generate(params)
            elif is_arena:
                files = arena_generate(params)
            elif is_platformer:
                files = platformer_generate(params)
            else:
                files = grid_generate(params)
            for rel, content in files.items():
                path = project_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
            return StageRecord("sources", True, 0, {"files": sorted(files)})

        # 4 build editor target
        def s_build():
            r = self.toolchain.build(uproject, f"{params.project_name}Editor")
            d = r.to_dict()
            ctx["build"] = d
            return StageRecord("build_editor", r.ok, r.duration_s,
                               {"exit_code": r.exit_code, "log": r.log_path, "errors": d["error_count"],
                                "warnings": d["warning_count"],
                                "diagnostics": [x.__dict__ for x in r.diagnostics[:20]]}, r.errors)

        # 5 assemble level in the live editor
        def s_assemble():
            if is_card:
                ok, data, errors = engine_stages.assemble_card_level(
                    self.engine_root, uproject, evidence_dir, params.project_name)
            elif is_arena:
                ok, data, errors = engine_stages.assemble_arena_level(
                    self.engine_root, uproject, evidence_dir, params.project_name)
            elif is_platformer:
                ok, data, errors = engine_stages.assemble_platformer_level(
                    self.engine_root, uproject, evidence_dir, params.project_name, params.collectible_target)
            else:
                ok, data, errors = engine_stages.assemble_level(
                    self.engine_root, uproject, evidence_dir, params.project_name,
                    params.cell_size_cm * params.board_size)
            return StageRecord("assemble_level", ok, 0, data, errors)

        # 6 automation tests
        def s_tests():
            r = self.toolchain.run_automation_tests(uproject, f"GameForge.{params.project_name}")
            return StageRecord("automation_tests", r.ok, r.duration_s,
                               {"exit_code": r.exit_code, "log": r.log_path, **r.data}, r.errors)

        # 7 package
        def s_package():
            ok, data, errors = engine_stages.package(self.toolchain, uproject)
            ctx["exe"] = data.get("exe")
            return StageRecord("package", ok, 0, data, errors)

        # 8 packaged smoke test (self-test inside the shipped build + screenshot)
        def s_smoke():
            ok, data, errors = engine_stages.packaged_smoke(
                self.toolchain, Path(ctx["exe"]), evidence_dir, params.project_name, expect_log=selftest_pass)
            return StageRecord("packaged_smoke", ok, 0, data, errors)

        plan = [("spec", s_spec), ("scaffold", s_scaffold), ("sources", s_sources), ("build_editor", s_build),
                ("assemble_level", s_assemble), ("automation_tests", s_tests)]
        if not skip_package:
            plan += [("package", s_package), ("packaged_smoke", s_smoke)]
        for name, fn in plan:
            if not stage(name, fn):
                return finish(name)
            if stop_after == name:
                break
        return finish(None)


def render_markdown(payload: Dict) -> str:
    lines = [f"# GameForge pipeline report — {payload['params']['project_name']}", "",
             f"- Result: **{'PASS' if payload['ok'] else 'FAIL at ' + str(payload['failed_stage'])}**",
             f"- Recipe: `{payload['recipe']}` v{payload['recipe_version']}",
             f"- Engine: {payload['engine_version']}", f"- Finished: {payload['finished']}", "",
             "| Stage | Result | Time (s) | Notes |", "|---|---|---|---|"]
    for s in payload["stages"]:
        d = s["data"]
        note = ""
        if s["stage"] == "automation_tests":
            note = f"{d.get('succeeded', 0)} passed, {d.get('failed', 0)} failed"
        elif s["stage"] in ("build_editor", "package"):
            note = f"exit {d.get('exit_code')}, {d.get('errors', 0)} errors"
        elif s["stage"] == "packaged_smoke":
            note = "; ".join(d.get("matched_lines", [])[-1:])[:160]
        if s["errors"]:
            note = (note + " | " if note else "") + "; ".join(s["errors"])[:200]
        lines.append(f"| {s['stage']} | {'PASS' if s['ok'] else 'FAIL'} | {s['duration_s']} | {note} |")
    return "\n".join(lines) + "\n"
