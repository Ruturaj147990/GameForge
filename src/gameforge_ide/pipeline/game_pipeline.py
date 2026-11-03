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
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

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
from . import stages as engine_stages
from ..design import store as design_store
from ..design.legacy import to_legacy_params
from ..design.gds import GameDesignSpec
from ..unreal.toolchain import UnrealToolchain
from ..core.settings import engine_root_or_missing, get_settings

STAGES = [
    "spec",
    "scaffold",
    "sources",
    "build_editor",
    "assemble_level",
    "automation_tests",
    "package",
    "packaged_smoke",
    "report",
]


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
        return {
            "ok": self.ok,
            "project_dir": self.project_dir,
            "report_path": self.report_path,
            "failed_stage": self.failed_stage,
            "stages": [s.__dict__ for s in self.stages],
        }


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
    return {
        "checked": True,
        "size": list(img.size),
        "lit_fraction": round(lit, 4),
        "stddev": round(sd, 2),
        "has_content": lit > 0.05 and sd > 5,
    }


class GamePipeline:
    def __init__(
        self,
        projects_root: Optional[Path] = None,
        engine_root: Optional[Path] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
        max_parallel_actions: Optional[int] = None,
        cancel_event=None,
        on_project_dir_ready: Optional[Callable[[Path], None]] = None,
    ):
        self.projects_root = Path(projects_root or get_settings().projects_root)
        self.engine_root = Path(engine_root or engine_root_or_missing())
        self.toolchain = UnrealToolchain(self.engine_root, max_parallel_actions=max_parallel_actions)
        self.on_event = on_event or (lambda kind, data: None)
        self.cancel_event = cancel_event
        self.toolchain.cancel_event = cancel_event
        self.max_parallel_actions = max_parallel_actions
        self.on_project_dir_ready = on_project_dir_ready

    def _emit(self, kind: str, **data) -> None:
        try:
            self.on_event(kind, data)
        except Exception:
            pass

    def run(
        self,
        params: Union[
            GameDesignSpec,
            GridBoardParams,
            PlatformerParams,
            ArenaCombatParams,
            CardBattlerParams,
            ProceduralWorldParams,
        ],
        skip_package: bool = False,
        stop_after: Optional[str] = None,
    ) -> PipelineResult:
        if isinstance(params, GameDesignSpec):
            gds = params
            params = to_legacy_params(gds)
            if self.on_project_dir_ready is None:
                self.on_project_dir_ready = lambda pdir: design_store.save(pdir, gds)

        project_dir = self.projects_root / params.project_name
        evidence_dir = project_dir / "Saved" / "GameForge"

        if self.cancel_event is not None and self.cancel_event.is_set():
            evidence_dir.mkdir(parents=True, exist_ok=True)
            report = evidence_dir / "pipeline_report.json"
            res = PipelineResult(
                False,
                str(project_dir),
                [StageRecord("spec", False, 0.0, errors=["CANCELLED by user"])],
                str(report),
                "spec",
            )
            self._emit("stage_finished", stage="spec", ok=False, duration_s=0.0, errors=["CANCELLED by user"])
            self._emit("pipeline_finished", ok=False, report=str(report), failed_stage="spec")
            return res

        from ..forge.legacy_adapter import plan_legacy, register_project_ready_hook, run_state_to_pipeline_result
        from ..forge.executor import ForgeExecutor
        from ..forge.handlers import HANDLERS
        from ..forge.model import RunState, StepStatus
        from ..forge.store import RunStore
        from ..core.events import default_bus

        run_spec = plan_legacy(
            params,
            projects_root=self.projects_root,
            skip_package=skip_package,
            engine_root=self.engine_root,
            max_parallel_actions=self.max_parallel_actions,
            on_project_dir_ready=self.on_project_dir_ready,
        )

        if self.on_project_dir_ready:
            register_project_ready_hook(run_spec.run_id, self.on_project_dir_ready)

        state = RunState.new(run_spec)

        if stop_after:
            stop_idx = None
            topo = run_spec.topo_order()
            for idx, s in enumerate(topo):
                if s.step_id == stop_after:
                    stop_idx = idx
                    break
            if stop_idx is not None:
                for s in topo[stop_idx + 1:]:
                    state.records[s.step_id].status = StepStatus.SKIPPED

        store = RunStore(project_dir=project_dir, workspace_dir=self.projects_root)

        bus = default_bus()

        def on_bus_event(topic: str, ev: Dict[str, Any]) -> None:
            kind = ev.get("kind")
            if kind == "step_started":
                self._emit("stage_started", stage=ev.get("step_id"))
            elif kind == "step_finished":
                self._emit(
                    "stage_finished",
                    stage=ev.get("step_id"),
                    ok=ev.get("ok", False),
                    duration_s=ev.get("duration_s", 0.0),
                    errors=ev.get("errors", []),
                )

        unsub = bus.subscribe("forge", on_bus_event)
        try:
            executor = ForgeExecutor(HANDLERS, bus=bus)
            if self.cancel_event is not None and self.cancel_event.is_set():
                executor.request_cancel()
            state = executor.run(state, store)
        finally:
            unsub()

        res = run_state_to_pipeline_result(
            state,
            params,
            engine_version=self.toolchain.engine_version(),
        )
        self._emit("pipeline_finished", ok=res.ok, report=str(res.report_path), failed_stage=res.failed_stage)
        return res

    @classmethod
    def resume(
        cls,
        project_dir: Union[Path, str],
        projects_root: Optional[Path] = None,
        engine_root: Optional[Path] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
    ) -> PipelineResult:
        """Resume a previous Forge run for a project directory."""
        from ..forge.legacy_adapter import run_state_to_pipeline_result
        from ..forge.executor import ForgeExecutor
        from ..forge.handlers import HANDLERS
        from ..forge.handlers.legacy_stages import get_params
        from ..forge.model import StepStatus
        from ..forge.executor import StepContext
        from ..forge.store import RunStore
        from ..core.events import default_bus

        pdir = Path(project_dir).resolve()
        proot = Path(projects_root or pdir.parent)
        store = RunStore(project_dir=pdir, workspace_dir=proot)
        state = store.latest_for_project(pdir)
        if state is None:
            raise RuntimeError(f"No previous Forge run found in {pdir}")

        for rec in state.records.values():
            if rec.status in (StepStatus.SKIPPED, StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.BLOCKED):
                rec.status = StepStatus.PENDING
                rec.ok = None
                rec.errors = []

        pipe = cls(projects_root=proot, engine_root=engine_root, on_event=on_event)

        bus = default_bus()

        def on_bus_event(topic: str, ev: Dict[str, Any]) -> None:
            kind = ev.get("kind")
            if kind == "step_started":
                pipe._emit("stage_started", stage=ev.get("step_id"))
            elif kind == "step_finished":
                pipe._emit(
                    "stage_finished",
                    stage=ev.get("step_id"),
                    ok=ev.get("ok", False),
                    duration_s=ev.get("duration_s", 0.0),
                    errors=ev.get("errors", []),
                )

        unsub = bus.subscribe("forge", on_bus_event)
        try:
            executor = ForgeExecutor(HANDLERS, bus=bus)
            state = executor.run(state, store)
        finally:
            unsub()

        # Reconstruct params from step 0
        dummy_ctx = StepContext(
            run=state.run,
            step=state.run.steps[0],
            record=state.records[state.run.steps[0].step_id],
            shared={},
            project_dir=pdir,
            workspace_dir=proot,
            cancel=threading.Event(),
            log=lambda l: None,
        )
        params = get_params(dummy_ctx)

        res = run_state_to_pipeline_result(
            state,
            params,
            engine_version=pipe.toolchain.engine_version(),
        )
        pipe._emit("pipeline_finished", ok=res.ok, report=str(res.report_path), failed_stage=res.failed_stage)
        return res


def render_markdown(payload: Dict) -> str:
    lines = [
        f"# GameForge pipeline report — {payload['params']['project_name']}",
        "",
        f"- Result: **{'PASS' if payload['ok'] else 'FAIL at ' + str(payload['failed_stage'])}**",
        f"- Recipe: `{payload['recipe']}` v{payload['recipe_version']}",
        f"- Engine: {payload['engine_version']}",
        f"- Finished: {payload['finished']}",
        "",
        "| Stage | Result | Time (s) | Notes |",
        "|---|---|---|---|",
    ]
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
