"""Game-production tools exposed through the ToolGateway.

  plan_game        T1  prompt -> Game Spec (recipe + parameters + acceptance), no side effects
  create_game      T3  run the full pipeline (scaffold, build, level, tests, package, self-test)
  unreal_editor    T0/T2  one live editor operation on a project (read-only ops need no approval)
  unreal_run_tests T3  run automation tests for a project
  unreal_package   T3  cook + package a project
  play_game        T3  launch a packaged game for the user

Approval-gated actions are persisted as pending actions in <workspace>/.gameforge/approvals/
so they survive restarts and can only be executed by a trusted UI path.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ...pipeline.game_pipeline import GamePipeline
from ...design.gds import GameDesignSpec
from ...design.legacy import LegacyUnsupported, to_legacy_params
from ...design.prompt_to_gds import PRESET_TITLES, prompt_to_gds
from ...design.render import render_markdown
from ...design import store as design_store
from ...pipeline.spec_from_prompt import is_game_creation_request, match_prompt
from src.gameforge_ide.legacy_recipes.grid_board_game.recipe import GridBoardParams
from ...unreal.live_editor import LiveEditorLink
from ...unreal import op_catalog, op_schemas
from ...unreal.toolchain import UnrealToolchain
from ...core.settings import engine_root_or_missing

# Generated from the op catalogue (single source of truth). The hand-kept list this replaced covered 13 of ~40
# read ops, so harmless reads of animation/PCG/material/audio state needed an approval card.
READ_ONLY_EDITOR_OPS = op_catalog.read_only_ops()
AGENT_EDITOR_OPS = frozenset(op_catalog.agent_ops())

from ...storage.approval_store import ApprovalStore



class GameTools:
    _links: Dict[str, LiveEditorLink] = {}
    _instances: List[Any] = []

    @classmethod
    def all_links(cls) -> Dict[str, LiveEditorLink]:
        return dict(cls._links)
    def __init__(self, workspace_root: Path, projects_root: Optional[Path] = None,
                 engine_root: Optional[Path] = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.projects_root = Path(projects_root or self._configured_projects_root())
        self.engine_root = Path(engine_root or engine_root_or_missing())
        self.approvals = ApprovalStore(self.workspace_root)
        self._links = GameTools._links
        GameTools._instances.append(self)
        self._last_used: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.editor_idle_timeout_s = 600.0
        self._reaper: Optional[threading.Thread] = None
        self._clock = time.monotonic

    def _configured_projects_root(self) -> Path:
        """Workspace setting > Core Settings > GAMEFORGE_PROJECTS_ROOT > <workspace>/Games."""
        settings = self.workspace_root / ".gameforge" / "settings.json"
        if settings.is_file():
            try:
                val = json.loads(settings.read_text(encoding="utf-8")).get("projects_root")
                if val:
                    return Path(val)
            except (OSError, json.JSONDecodeError):
                pass
        env = os.environ.get("GAMEFORGE_PROJECTS_ROOT")
        if env:
            return Path(env)
        try:
            from ...core.settings import get_settings
            core_root = get_settings().projects_root
            if core_root and Path(core_root).exists():
                return Path(core_root)
        except Exception:
            pass
        return self.workspace_root / "Games"

    def _get_complete_json(self):
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None, None
        try:
            from ..providers.ollama_provider import OllamaProvider
            from ...core.settings import get_settings
            settings = get_settings()
            provider = OllamaProvider(host=settings.ollama_url.replace("http://", "").replace("https://", ""))
            model = settings.model_for("design")
            return (lambda s, u, sch: provider.complete_json(model, s, u, sch)), model
        except Exception:
            return None, None

    # ── T1 ─────────────────────────────────────────────────────────────────
    def plan_game(self, prompt: str) -> Dict[str, Any]:
        complete_json, model = self._get_complete_json()
        result = prompt_to_gds(prompt, complete_json=complete_json, model=model)
        gds = result.gds
        if gds is not None:
            legacy_supported = True
            try:
                to_legacy_params(gds)
            except LegacyUnsupported:
                legacy_supported = False
            summary_md = render_markdown(gds)
            return {
                "status": "SUCCESS" if result.status == "OK" else result.status,
                "gds": gds.model_dump(),
                "summary_md": summary_md,
                "questions": result.questions,
                "legacy_supported": legacy_supported,
                "projects_root": str(self.projects_root),
                "project_dir": str(self.projects_root / gds.meta.project_name),
            }
        return {
            "status": result.status,
            "gds": None,
            "summary_md": "",
            "questions": result.questions,
            "legacy_supported": False,
            "projects_root": str(self.projects_root),
        }






    def propose_create_game(self, prompt: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """For a game-creation prompt, produce a GDS and persist a pending create_game action."""
        if not is_game_creation_request(prompt):
            return None
        complete_json, model = self._get_complete_json()
        res = prompt_to_gds(prompt, complete_json=complete_json, model=model)
        if res.gds is None:
            return self._propose_freeform(prompt, session_id)
        gds = res.gds
        summary_md = render_markdown(gds)
        project_dir = self.projects_root / gds.meta.project_name
        legacy_dict = None
        try:
            legacy_dict = to_legacy_params(gds).to_dict()
        except LegacyUnsupported:
            pass
        args_payload = {"gds": gds.to_json(), "package": True}
        if legacy_dict is not None:
            args_payload["params"] = legacy_dict

        rec = self.approvals.create(
            "create_game", args_payload,
            f"{gds.meta.title} ({gds.overview.genre.value})",
            consequence=(f"Writes a new Unreal C++ project to {project_dir}, compiles it, launches Unreal Editor "
                         "to build the level, runs automation tests, then cooks and packages a Windows build. "
                         "Typical time 5-20 minutes; uses CPU/GPU heavily while building."),
            session_id=session_id)
        rec["gds"] = gds.model_dump()
        rec["summary_md"] = summary_md
        rec["questions"] = res.questions
        rec["stages"] = ["spec", "scaffold", "sources", "build_editor", "assemble_level", "automation_tests",
                         "package", "packaged_smoke"]
        rec["plan_text"] = summary_md
        return rec

    def _propose_freeform(self, prompt: str, session_id: Optional[str]) -> Dict[str, Any]:
        """No recipe matches: offer model-authored C++ on the verified host framework."""
        from ...pipeline.freeform import FREEFORM_STAGES, derive_title, pascal
        from ..providers.router import ModelRouter
        title = derive_title(prompt)
        router = ModelRouter()
        router.attach_hosted(self.workspace_root)
        route = router.route_hosted("author")
        author = f"hosted {route[0]}/{route[1]}" if route else "local gameforge-qwen3.5-9b (bootstrap tier)"
        project_dir = self.projects_root / pascal(title)
        acceptance = ["model design + C++ pass the static safety scan (no process/file/network access)",
                      f"build_ok({pascal(title)}Editor) — up to 5 compiler-driven repair rounds",
                      "level_readback(Table, Sun, SkyFill)",
                      "package_ok(Win64)",
                      "packaged_selftest(GF_SELFTEST PASS from the game's own RunSelfTest) — up to 3 repair rounds",
                      "packaged_screenshot_has_content"]
        summary = f"{title}: free-form game written by {author} on the GameForge host framework."
        rec = self.approvals.create(
            "create_game_freeform", {"prompt": prompt, "title": title}, summary,
            consequence=(f"Experimental: no verified recipe matches this request, so a model writes the gameplay C++. "
                         f"Writes a new Unreal project to {project_dir}, compiles, repairs from compiler output, builds "
                         "the level, packages and play-tests it. It succeeds only if every gate passes; otherwise it "
                         "stops and shows why. Typical time 5-30 minutes."),
            session_id=session_id)
        rec["stages"] = FREEFORM_STAGES
        rec["spec"] = {"recipe_id": None, "recipe_title": "Free-form", "summary": summary, "acceptance": acceptance}
        rec["plan_text"] = (
            f"**Game plan — {title}** (free-form, no recipe)\n\n{summary}\n\n"
            "**Acceptance criteria (checked against the real engine):**\n"
            + "\n".join(f"- {a}" for a in acceptance)
            + "\n\nApprove below to build it. Nothing runs until you approve.")
        return rec

    def create_game_freeform(self, prompt: str, title: Optional[str] = None,
                             project_dir: Optional[Union[str, Path]] = None,
                             on_event: Optional[Callable[[str, Dict], None]] = None, cancel_event=None) -> Dict[str, Any]:
        from ...pipeline.freeform import FreeformGamePipeline
        self.release_llm_vram()
        proj_root = Path(project_dir).parent if project_dir else self.projects_root
        return FreeformGamePipeline(self.workspace_root, proj_root, self.engine_root,
                                    on_event=on_event, cancel_event=cancel_event).run(prompt, title)

    # ── T3 create game ─────────────────────────────────────────────────────
    @staticmethod
    def release_llm_vram(host: str = "127.0.0.1:11434") -> List[str]:
        """Unload resident Ollama models so the editor/cook get the GPU (one heavy GPU workload).

        Best effort and harmless when Ollama is not running; models reload on next use.
        """
        import urllib.request
        unloaded: List[str] = []
        try:
            with urllib.request.urlopen(f"http://{host}/api/ps", timeout=3) as r:
                running = json.loads(r.read().decode("utf-8")).get("models", [])
            for m in running:
                body = json.dumps({"model": m["name"], "keep_alive": 0}).encode("utf-8")
                req = urllib.request.Request(f"http://{host}/api/generate", data=body,
                                             headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=30).read()
                unloaded.append(m["name"])
        except Exception:
            pass
        return unloaded

    def create_game(self, gds_or_params: Any = None, package: bool = True,
                    on_event: Optional[Callable[[str, Dict], None]] = None, cancel_event=None,
                    **kwargs: Any) -> Dict[str, Any]:
        gds: Optional[GameDesignSpec] = None
        params = None

        if isinstance(gds_or_params, GameDesignSpec):
            gds = gds_or_params
        elif isinstance(gds_or_params, str):
            try:
                gds = GameDesignSpec.model_validate_json(gds_or_params)
            except Exception:
                pass
        elif isinstance(gds_or_params, dict):
            if "gds" in gds_or_params:
                raw = gds_or_params["gds"]
                gds = GameDesignSpec.model_validate_json(raw) if isinstance(raw, str) else GameDesignSpec.model_validate(raw)
            if "params" in gds_or_params:
                params = gds_or_params["params"]
            elif gds is None:
                params = gds_or_params
        elif isinstance(kwargs.get("gds"), str):
            gds = GameDesignSpec.model_validate_json(kwargs["gds"])
        elif isinstance(kwargs.get("gds"), dict):
            gds = GameDesignSpec.model_validate(kwargs["gds"])
        elif isinstance(kwargs.get("gds"), GameDesignSpec):
            gds = kwargs["gds"]
        elif "params" in kwargs:
            params = kwargs["params"]

        prompt_input = (
            kwargs.get("prompt")
            or (gds_or_params.get("prompt") if isinstance(gds_or_params, dict) else None)
            or (gds_or_params if isinstance(gds_or_params, str) and not gds_or_params.strip().startswith("{") else None)
        )
        # If prompt is a proceed/continue confirmation command, resolve existing GDS from project_dir
        if gds is None and params is None and prompt_input:
            norm_pi = prompt_input.strip().lower()
            if norm_pi in ("proceed", "continue", "start", "run", "go ahead", "apply", "confirm"):
                explicit_pdir = kwargs.get("project_dir") or (gds_or_params.get("project_dir") if isinstance(gds_or_params, dict) else None)
                if explicit_pdir:
                    try:
                        from ...core.projects import find_gds
                        found_gds = find_gds(explicit_pdir)
                        if found_gds and found_gds.is_file():
                            gds = GameDesignSpec.model_validate_json(found_gds.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                if gds is None:
                    return {
                        "status": "FAILED",
                        "ok": False,
                        "error": f"No GameDesignSpec found to execute for '{prompt_input}'. Please specify the game to create.",
                        "failed_stage": "spec",
                    }

        if gds is None and params is None and prompt_input:
            try:
                from ...design.prompt_to_gds import prompt_to_gds
                complete_json, model = self._get_complete_json()
                res = prompt_to_gds(
                    prompt_input,
                    complete_json=complete_json,
                    model=model,
                    allow_model=True,
                )
                if res.status == "OK" and res.gds is not None:
                    gds = res.gds
                elif res.status == "NEEDS_INPUT":
                    return {
                        "status": "NEEDS_INPUT",
                        "ok": False,
                        "questions": list(res.questions),
                        "errors": list(res.errors),
                        "failed_stage": "spec",
                    }
                elif res.status == "UNSUPPORTED":
                    return {
                        "status": "UNSUPPORTED",
                        "ok": False,
                        "error": "; ".join(res.errors) or "This is not a supported game-creation request.",
                        "failed_stage": "spec",
                    }
                else:
                    return {
                        "status": "FAILED",
                        "ok": False,
                        "error": "; ".join(res.errors) or "Could not produce a valid game specification.",
                        "failed_stage": "spec",
                    }
            except Exception as exc:
                logger.warning("prompt_to_gds invocation error: %s", exc)
                return {
                    "status": "FAILED",
                    "ok": False,
                    "error": f"Could not create game specification for prompt {prompt_input!r}: {exc}",
                    "failed_stage": "spec",
                }

            # Check match_prompt as offline fallback for explicit recipe/preset intents
            if gds is None:
                spec = match_prompt(prompt_input)
                if spec.matched and spec.params:
                    params = spec.params

            if gds is None and params is None:
                return {
                    "status": "FAILED",
                    "ok": False,
                    "error": f"Could not create game specification for prompt {prompt_input!r}",
                    "failed_stage": "spec",
                }

        hook = None
        if gds is not None:
            def _save_gds_auto_advance(pdir_path: Path) -> Path:
                stored = design_store.load(pdir_path)
                if stored is not None and gds.meta.revision <= stored.meta.revision:
                    gds.meta.revision = stored.meta.revision + 1
                return design_store.save(pdir_path, gds)

            try:
                recipe_params = to_legacy_params(gds)
                hook = _save_gds_auto_advance
            except (LegacyUnsupported, ValueError):
                # Modern Composer + Forge DAG path
                from ...composer import compose, composition_to_run_spec
                from ...forge.store import RunStore
                from ...forge.executor import ForgeExecutor
                from ...forge.handlers import HANDLERS
                from ...forge.model import RunState, StepStatus
                from ...core.events import default_bus

                explicit_pdir = (
                    kwargs.get("project_dir")
                    or (gds_or_params.get("project_dir") if isinstance(gds_or_params, dict) else None)
                    or getattr(gds.meta, "project_dir", None)
                )
                if explicit_pdir:
                    pdir = Path(explicit_pdir).resolve()
                else:
                    pdir = self.projects_root / gds.meta.project_name
                pdir.mkdir(parents=True, exist_ok=True)
                _save_gds_auto_advance(pdir)

                freed = self.release_llm_vram()
                if on_event and freed:
                    on_event("gpu_released", {"unloaded_models": freed})

                comp = compose(gds, allow_partial=True)
                run_spec = composition_to_run_spec(
                    comp,
                    str(self.workspace_root),
                    str(pdir),
                    origin="prompt",
                )
                if not package:
                    run_spec.steps = [s for s in run_spec.steps if s.step_id not in ("package", "scenarios")]
                    for s in run_spec.steps:
                        s.depends_on = [d for d in s.depends_on if d not in ("package", "scenarios")]

                rstore = RunStore(project_dir=pdir, workspace_dir=self.workspace_root)
                state = RunState.new(run_spec)
                rstore.save(state)
                bus = default_bus()

                def _on_ev(topic: str, ev: Dict[str, Any]):
                    kind = ev.get("kind")
                    sid = ev.get("step_id", "")
                    stage = sid
                    if sid.startswith("assemble_"):
                        stage = "assemble_level"
                    elif sid == "automation":
                        stage = "automation_tests"
                    elif sid == "scenarios":
                        stage = "packaged_smoke"
                    elif sid == "codegen":
                        stage = "sources"
                    elif sid == "design":
                        stage = "spec"

                    if kind == "step_started":
                        if on_event:
                            on_event("stage_started", {"stage": stage, "step_id": sid})
                    elif kind == "step_finished":
                        if on_event:
                            on_event("stage_finished", {
                                "stage": stage,
                                "step_id": sid,
                                "ok": ev.get("ok", False),
                                "duration_s": ev.get("duration_s", 0.0),
                                "errors": ev.get("errors", []),
                            })
                            if sid == "scaffold" and not comp.codegen:
                                on_event("stage_finished", {
                                    "stage": "sources",
                                    "step_id": "sources",
                                    "ok": True,
                                    "duration_s": 0.0,
                                    "errors": [],
                                })

                unsub = bus.subscribe("forge", _on_ev)
                executor = ForgeExecutor(HANDLERS, bus=bus)
                watcher_stop = threading.Event()

                def _watch_cancel() -> None:
                    # Forward a user cancel that arrives *during* the run (previously the event was
                    # only checked once, before the run started).
                    while not watcher_stop.wait(0.5):
                        if cancel_event is not None and cancel_event.is_set():
                            try:
                                executor.request_cancel()
                            except Exception:
                                pass
                            return

                watcher = None
                if cancel_event is not None:
                    if cancel_event.is_set():
                        executor.request_cancel()
                    watcher = threading.Thread(target=_watch_cancel, name="create-game-cancel", daemon=True)
                    watcher.start()
                try:
                    state = executor.run(state, rstore)
                finally:
                    watcher_stop.set()
                    unsub()

                ok = state.status == "DONE"
                exe_path = pdir / "Packaged" / "Windows" / f"{gds.meta.project_name}.exe"
                report_path = pdir / "Saved" / "GameForge" / "pipeline_report.json"
                first_failed = next((sid for sid, r in state.records.items() if r.status == StepStatus.FAILED), None)

                err_msg = None
                if not ok:
                    if first_failed and state.records[first_failed].errors:
                        err_msg = "; ".join(state.records[first_failed].errors)
                    else:
                        err_msg = f"Run status: {state.status}"

                out = {
                    "status": "SUCCESS" if ok else state.status,
                    "ok": ok,
                    "project_dir": str(pdir),
                    "run_id": state.run.run_id,
                    "report_path": str(report_path) if report_path.is_file() else None,
                    "failed_stage": first_failed,
                    "error": err_msg,
                }
                if exe_path.is_file():
                    out["exe"] = str(exe_path)
                out["stages"] = [
                    {"step_id": sid, "status": getattr(r.status, "value", str(r.status)),
                     "errors": list(r.errors or [])[:3]}
                    for sid, r in state.records.items()
                ]
                return out
        elif params is not None:
            # Backward compatibility branch for pre-P1 approval records
            from src.gameforge_ide.legacy_recipes.grid_board_game.recipe import GridBoardParams
            from src.gameforge_ide.legacy_recipes.platformer.recipe import PlatformerParams
            from src.gameforge_ide.legacy_recipes.arena_combat.recipe import ArenaCombatParams
            from src.gameforge_ide.legacy_recipes.card_battler.recipe import CardBattlerParams
            from src.gameforge_ide.legacy_recipes.procedural_world.recipe import ProceduralWorldParams
            if isinstance(params, (GridBoardParams, PlatformerParams, ArenaCombatParams, CardBattlerParams, ProceduralWorldParams)):
                recipe_params = params
            elif isinstance(params, dict):
                # Infer recipe type or default to GridBoardParams
                if "collectible_target" in params:
                    recipe_params = PlatformerParams(**params)
                elif "wave_count" in params:
                    recipe_params = ArenaCombatParams(**params)
                elif "lane_count" in params:
                    recipe_params = CardBattlerParams(**params)
                elif "elevation_scale" in params:
                    recipe_params = ProceduralWorldParams(**params)
                else:
                    recipe_params = GridBoardParams(**{k: tuple(v) if isinstance(v, list) else v for k, v in params.items()})
            else:
                recipe_params = params
        else:
            return {"status": "FAILED", "ok": False, "error": "No valid GDS or params provided", "failed_stage": "spec"}

        freed = self.release_llm_vram()
        if on_event and freed:
            on_event("gpu_released", {"unloaded_models": freed})
        pipe = GamePipeline(self.projects_root, self.engine_root, on_event=on_event,
                            max_parallel_actions=max(2, (os.cpu_count() or 4) - 2), cancel_event=cancel_event,
                            on_project_dir_ready=hook)
        res = pipe.run(recipe_params, skip_package=not package)
        out = {"status": "SUCCESS" if res.ok else "FAILED", **res.to_dict()}
        smoke = next((s for s in res.stages if s.stage == "packaged_smoke"), None)
        if smoke and smoke.ok:
            exe = Path(res.project_dir) / "Packaged" / "Windows" / f"{recipe_params.project_name}.exe"
            out["exe"] = str(exe)
            out["screenshot"] = smoke.data.get("screenshot")
        return out

    # ── live editor ────────────────────────────────────────────────────────
    def _resolve_uproject(self, uproject: Optional[Union[str, Path]] = None) -> Optional[Path]:
        """Resolve a .uproject file path from a project name, directory, relative path, or .uproject file."""
        from ...core.projects import find_uproject, resolve_project_dir, list_all_project_dirs

        if not uproject:
            found = find_uproject(self.workspace_root)
            return found if found and found.is_file() else None

        raw = Path(uproject)
        # 1. Direct file path to .uproject
        if raw.is_file() and raw.suffix.lower() == ".uproject":
            return raw.resolve()

        # 2. Direct folder path containing .uproject
        if raw.is_dir():
            found = find_uproject(raw)
            if found and found.is_file():
                return found.resolve()

        # 3. Path relative to workspace_root
        ws_cand = (self.workspace_root / raw).resolve()
        if ws_cand.is_file() and ws_cand.suffix.lower() == ".uproject":
            return ws_cand
        if ws_cand.is_dir():
            found = find_uproject(ws_cand)
            if found and found.is_file():
                return found.resolve()

        # 4. Path relative to projects_root
        pr_cand = (self.projects_root / raw).resolve()
        if pr_cand.is_file() and pr_cand.suffix.lower() == ".uproject":
            return pr_cand
        if pr_cand.is_dir():
            found = find_uproject(pr_cand)
            if found and found.is_file():
                return found.resolve()

        # 5. Project name or stem under self.projects_root or self.workspace_root
        name = raw.stem if raw.suffix.lower() == ".uproject" else str(uproject).strip()
        if (self.projects_root / name).is_dir():
            found = find_uproject(self.projects_root / name)
            if found and found.is_file():
                return found.resolve()

        if (self.workspace_root / name).is_dir():
            found = find_uproject(self.workspace_root / name)
            if found and found.is_file():
                return found.resolve()

        # Check case-insensitively in self.projects_root
        try:
            for d in self.projects_root.iterdir():
                if d.is_dir() and d.name.lower() == name.lower():
                    found = find_uproject(d)
                    if found and found.is_file():
                        return found.resolve()
        except OSError:
            pass

        # Check global candidate roots via resolve_project_dir
        pdir = resolve_project_dir(name, workspace_dir=self.workspace_root)
        if pdir:
            found = find_uproject(pdir)
            if found and found.is_file():
                return found.resolve()

        # 6. Search across all known projects across candidate roots
        all_dirs = list_all_project_dirs(self.workspace_root)
        norm_name = name.lower()
        for cand_name, cand_dir in all_dirs.items():
            if cand_name.lower() == norm_name or cand_dir.name.lower() == norm_name:
                found = find_uproject(cand_dir)
                if found and found.is_file():
                    return found.resolve()

        # 7. Fallback to workspace root if it contains a uproject
        found = find_uproject(self.workspace_root)
        if found and found.is_file():
            return found.resolve()

        return None

    def _link(self, uproject: Union[str, Path]) -> LiveEditorLink:
        up_path = self._resolve_uproject(uproject)
        if not up_path or not up_path.is_file():
            raise FileNotFoundError(f"uproject not found: {uproject}")
        key = str(up_path.resolve()).lower()
        with self._lock:
            link = self._links.get(key)
            if link is None or not link.is_running():
                link = LiveEditorLink(up_path, self.engine_root)
                link.prepare_project()
                link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
                link.connect(discovery_timeout_s=900)
                self._links[key] = link
            self._last_used[key] = self._clock()
            if self._reaper is None or not self._reaper.is_alive():
                self._reaper = threading.Thread(target=self._reap_loop, name="gf-editor-reaper", daemon=True)
                self._reaper.start()
            return link

    def close_idle_editors(self) -> List[str]:
        """Gracefully stop editors unused for editor_idle_timeout_s (frees RAM/VRAM)."""
        closed = []
        now = self._clock()
        with self._lock:
            for key in list(self._links):
                if now - self._last_used.get(key, now) >= self.editor_idle_timeout_s:
                    self._links.pop(key).stop()
                    self._last_used.pop(key, None)
                    closed.append(key)
        return closed

    def _reap_loop(self) -> None:
        while True:
            time.sleep(60)
            self.close_idle_editors()
            with self._lock:
                if not self._links:
                    return

    def unreal_editor(self, uproject: str, op: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        up_path = self._resolve_uproject(uproject)
        if not up_path or not up_path.is_file():
            return {"status": "ERROR", "error": f"uproject not found: {uproject}"}
        if op not in AGENT_EDITOR_OPS:
            # Fail closed before touching the editor: unknown (e.g. model-invented), diagnostic or legacy op.
            return {"status": "ERROR", "error": f"unknown or non-agent editor op: {op!r}",
                    "hint": "valid ops: " + op_catalog.describe_for_agent()}
        clean, errs = op_schemas.validate_args(op, args or {}, strict=True)
        if errs:  # fail before touching the editor (AD-14)
            return {"status": "ERROR", "error": "invalid args for op", "op": op, "details": errs}
        res = self._link(up_path).call(op, clean)
        return {"status": "SUCCESS" if res.get("ok") else "ERROR", "result": res}

    def close_editors(self) -> List[Optional[int]]:
        with self._lock:
            codes = [link.stop() for link in self._links.values()]
            self._links.clear()
        return codes

    def unreal_run_tests(self, uproject: str, test_filter: str = "GameForge") -> Dict[str, Any]:
        up_path = self._resolve_uproject(uproject)
        if not up_path or not up_path.is_file():
            return {"status": "ERROR", "error": f"uproject not found: {uproject}"}
        r = UnrealToolchain(self.engine_root).run_automation_tests(up_path, test_filter)
        return {"status": "SUCCESS" if r.ok else "FAILED", **r.to_dict()}

    def unreal_package(self, uproject: str) -> Dict[str, Any]:
        up_path = self._resolve_uproject(uproject)
        if not up_path or not up_path.is_file():
            return {"status": "ERROR", "error": f"uproject not found: {uproject}"}
        r = UnrealToolchain(self.engine_root).package(up_path, up_path.parent / "Packaged")
        return {"status": "SUCCESS" if r.ok else "FAILED", **r.to_dict()}

    def play_game(self, exe: str) -> Dict[str, Any]:
        from ...core.projects import find_packaged_executable, list_all_project_dirs
        raw = Path(exe)
        resolved_exe: Optional[Path] = None

        # 1. Direct path check
        if raw.is_file() and raw.suffix.lower() == ".exe":
            resolved_exe = raw.resolve()
        # 2. Check relative to projects_root
        elif (self.projects_root / raw).is_file():
            resolved_exe = (self.projects_root / raw).resolve()
        # 3. Check relative to workspace_root
        elif (self.workspace_root / raw).is_file():
            resolved_exe = (self.workspace_root / raw).resolve()
        else:
            # 4. Search across all known project directories
            all_dirs = list_all_project_dirs(self.workspace_root)
            for pdir in all_dirs.values():
                cand = pdir / raw
                if cand.is_file() and cand.suffix.lower() == ".exe":
                    resolved_exe = cand.resolve()
                    break
                # Try finding packaged executable in that project
                pkg = find_packaged_executable(pdir, project_name=raw.stem)
                if pkg and pkg.is_file() and (pkg.name.lower() == raw.name.lower() or raw.stem in ("MyGame", pdir.name)):
                    resolved_exe = pkg.resolve()
                    break

        # If the resolved path points to un-cooked Binaries/Win64/<Project>.exe, redirect to Packaged/Windows/<Project>.exe
        if resolved_exe and "Binaries" in resolved_exe.parts and "Win64" in resolved_exe.parts:
            curr = resolved_exe.parent
            while curr != curr.parent and curr.name in ("Win64", "Binaries"):
                curr = curr.parent
            packaged = find_packaged_executable(curr, project_name=resolved_exe.stem)
            if packaged and packaged.is_file():
                resolved_exe = packaged
            else:
                return {
                    "status": "ERROR",
                    "error": f"'{resolved_exe.name}' in Binaries/Win64 is an un-cooked binary, not a packaged standalone game. Please run 'unreal_package' or package the game to create {curr / 'Packaged' / 'Windows' / resolved_exe.name}.",
                }

        if not resolved_exe or not resolved_exe.is_file() or resolved_exe.suffix.lower() != ".exe":
            return {
                "status": "ERROR",
                "error": f"Not a packaged game executable: '{exe}'. The project has not been cooked and packaged into a standalone Windows executable yet. Please package the game first via Build or 'unreal_package'.",
            }

        # Allow execution only of games produced under projects_root or workspace Projects/Games subdirectories
        p_root_res = self.projects_root.resolve()
        ws_proj_res = (self.workspace_root / "Projects").resolve()
        ws_games_res = (self.workspace_root / "Games").resolve()
        in_projects = p_root_res in resolved_exe.parents
        in_subprojects = (ws_proj_res in resolved_exe.parents) or (ws_games_res in resolved_exe.parents)
        if not in_projects and not in_subprojects:
            return {"status": "BLOCKED", "error": "Only games produced under the GameForge projects root or workspace can be launched"}

        # Kept as plain subprocess.Popen (not jobs.spawn): launched for the user to keep playing, so it must not die with the IDE job.
        proc = subprocess.Popen([str(resolved_exe), "-windowed", "-ResX=1280", "-ResY=800"], cwd=str(resolved_exe.parent))
        return {"status": "SUCCESS", "pid": proc.pid, "exe": str(resolved_exe)}
