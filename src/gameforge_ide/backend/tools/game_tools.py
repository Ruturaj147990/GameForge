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
from typing import Any, Callable, Dict, List, Optional

from ...pipeline.game_pipeline import GamePipeline
from ...pipeline.spec_from_prompt import is_game_creation_request, match_prompt
from ...recipes.grid_board_game.recipe import GridBoardParams
from ...unreal.live_editor import LiveEditorLink
from ...unreal import op_catalog, op_schemas
from ...unreal.toolchain import UnrealToolchain
from ...core.settings import engine_root_or_missing

# Generated from the op catalogue (single source of truth). The hand-kept list this replaced covered 13 of ~40
# read ops, so harmless reads of animation/PCG/material/audio state needed an approval card.
READ_ONLY_EDITOR_OPS = op_catalog.read_only_ops()
AGENT_EDITOR_OPS = frozenset(op_catalog.agent_ops())


class ApprovalStore:
    """Persisted pending actions. Only the UI's approve path may execute them."""

    def __init__(self, workspace_root: Path):
        self.root = Path(workspace_root) / ".gameforge" / "approvals"

    def create(self, tool: str, args: Dict[str, Any], summary: str, consequence: str,
               session_id: Optional[str] = None, plan_id: Optional[str] = None) -> Dict[str, Any]:
        """``plan_id`` marks a plan-task approval: approving it unblocks the plan, which runs the tool."""
        self.root.mkdir(parents=True, exist_ok=True)
        rec = {"approval_id": "apr_" + secrets.token_hex(6), "tool": tool, "args": args, "summary": summary,
               "consequence": consequence, "session_id": session_id, "status": "PENDING",
               "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if plan_id:
            rec["plan_id"] = plan_id
        self._write(rec)
        return rec

    def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        path = self.root / f"{approval_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_pending(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out = []
        for p in sorted(self.root.glob("apr_*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if rec.get("status") == "PENDING":
                out.append(rec)
        return out

    def transition(self, approval_id: str, status: str, result: Optional[Dict] = None) -> Optional[Dict]:
        """PENDING -> APPROVED/REJECTED -> DONE/FAILED. Returns None if the transition is not allowed."""
        rec = self.get(approval_id)
        allowed = {"PENDING": {"APPROVED", "REJECTED"}, "APPROVED": {"DONE", "FAILED"}}
        if rec is None or status not in allowed.get(rec["status"], set()):
            return None
        rec["status"] = status
        rec[f"{status.lower()}_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if result is not None:
            rec["result"] = result
        self._write(rec)
        return rec

    def _write(self, rec: Dict) -> None:
        path = self.root / f"{rec['approval_id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, path)  # atomic


class GameTools:
    def __init__(self, workspace_root: Path, projects_root: Optional[Path] = None,
                 engine_root: Optional[Path] = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.projects_root = Path(projects_root or self._configured_projects_root())
        self.engine_root = Path(engine_root or engine_root_or_missing())
        self.approvals = ApprovalStore(self.workspace_root)
        self._links: Dict[str, LiveEditorLink] = {}
        self._last_used: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.editor_idle_timeout_s = 600.0
        self._reaper: Optional[threading.Thread] = None
        self._clock = time.monotonic

    def _configured_projects_root(self) -> Path:
        """Workspace setting > GAMEFORGE_PROJECTS_ROOT > <workspace>/Games."""
        settings = self.workspace_root / ".gameforge" / "settings.json"
        if settings.is_file():
            try:
                val = json.loads(settings.read_text(encoding="utf-8")).get("projects_root")
                if val:
                    return Path(val)
            except (OSError, json.JSONDecodeError):
                pass
        env = os.environ.get("GAMEFORGE_PROJECTS_ROOT")
        return Path(env) if env else self.workspace_root / "Games"

    # ── T1 ─────────────────────────────────────────────────────────────────
    def plan_game(self, prompt: str) -> Dict[str, Any]:
        spec = match_prompt(prompt)
        res = {"status": "SUCCESS" if spec.matched else "NO_RECIPE", "spec": spec.to_dict(),
               "projects_root": str(self.projects_root)}
        if spec.matched:
            res["project_dir"] = str(self.projects_root / spec.params.project_name)
        return res

    def propose_create_game(self, prompt: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """For a game-creation prompt with a matching recipe, persist a pending create_game action."""
        if not is_game_creation_request(prompt):
            return None
        spec = match_prompt(prompt)
        if not spec.matched:
            return self._propose_freeform(prompt, session_id)
        project_dir = self.projects_root / spec.params.project_name
        rec = self.approvals.create(
            "create_game", {"params": spec.params.to_dict(), "package": True}, spec.summary(),
            consequence=(f"Writes a new Unreal C++ project to {project_dir}, compiles it, launches Unreal Editor "
                         "to build the level, runs automation tests, then cooks and packages a Windows build. "
                         "Typical time 5-20 minutes; uses CPU/GPU heavily while building."),
            session_id=session_id)
        rec["spec"] = spec.to_dict()
        rec["stages"] = ["spec", "scaffold", "sources", "build_editor", "assemble_level", "automation_tests",
                         "package", "packaged_smoke"]
        rec["plan_text"] = (
            f"**Game plan — {spec.recipe_title}** (verified recipe `{spec.recipe_id}`)\n\n{spec.summary()}\n\n"
            "**Acceptance criteria (checked against the real engine):**\n"
            + "\n".join(f"- `{a}`" for a in spec.acceptance)
            + "\n\nApprove below to build it. Nothing runs until you approve.")
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
                             on_event: Optional[Callable[[str, Dict], None]] = None, cancel_event=None) -> Dict[str, Any]:
        from ...pipeline.freeform import FreeformGamePipeline
        self.release_llm_vram()
        return FreeformGamePipeline(self.workspace_root, self.projects_root, self.engine_root,
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

    def create_game(self, params: Dict[str, Any], package: bool = True,
                    on_event: Optional[Callable[[str, Dict], None]] = None, cancel_event=None) -> Dict[str, Any]:
        p = GridBoardParams(**{k: tuple(v) if isinstance(v, list) else v for k, v in params.items()})
        freed = self.release_llm_vram()
        if on_event and freed:
            on_event("gpu_released", {"unloaded_models": freed})
        pipe = GamePipeline(self.projects_root, self.engine_root, on_event=on_event,
                            max_parallel_actions=max(2, (os.cpu_count() or 4) - 2), cancel_event=cancel_event)
        res = pipe.run(p, skip_package=not package)
        out = {"status": "SUCCESS" if res.ok else "FAILED", **res.to_dict()}
        smoke = next((s for s in res.stages if s.stage == "packaged_smoke"), None)
        if smoke and smoke.ok:
            exe = Path(res.project_dir) / "Packaged" / "Windows" / f"{p.project_name}.exe"
            out["exe"] = str(exe)
            out["screenshot"] = smoke.data.get("screenshot")
        return out

    # ── live editor ────────────────────────────────────────────────────────
    def _link(self, uproject: str) -> LiveEditorLink:
        key = str(Path(uproject).resolve()).lower()
        with self._lock:
            link = self._links.get(key)
            if link is None or not link.is_running():
                link = LiveEditorLink(Path(uproject), self.engine_root)
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
        if not Path(uproject).is_file():
            return {"status": "ERROR", "error": f"uproject not found: {uproject}"}
        if op not in AGENT_EDITOR_OPS:
            # Fail closed before touching the editor: unknown (e.g. model-invented), diagnostic or legacy op.
            return {"status": "ERROR", "error": f"unknown or non-agent editor op: {op!r}",
                    "hint": "valid ops: " + op_catalog.describe_for_agent()}
        clean, errs = op_schemas.validate_args(op, args or {})
        if errs:  # fail before touching the editor (AD-14)
            return {"status": "ERROR", "error": "invalid args for op", "op": op, "details": errs}
        res = self._link(uproject).call(op, clean)
        return {"status": "SUCCESS" if res.get("ok") else "ERROR", "result": res}

    def close_editors(self) -> List[Optional[int]]:
        with self._lock:
            codes = [link.stop() for link in self._links.values()]
            self._links.clear()
        return codes

    def unreal_run_tests(self, uproject: str, test_filter: str = "GameForge") -> Dict[str, Any]:
        r = UnrealToolchain(self.engine_root).run_automation_tests(Path(uproject), test_filter)
        return {"status": "SUCCESS" if r.ok else "FAILED", **r.to_dict()}

    def unreal_package(self, uproject: str) -> Dict[str, Any]:
        up = Path(uproject)
        r = UnrealToolchain(self.engine_root).package(up, up.parent / "Packaged")
        return {"status": "SUCCESS" if r.ok else "FAILED", **r.to_dict()}

    def play_game(self, exe: str) -> Dict[str, Any]:
        path = Path(exe)
        if not path.is_file() or path.suffix.lower() != ".exe":
            return {"status": "ERROR", "error": f"not a packaged game executable: {exe}"}
        if self.projects_root.resolve() not in path.resolve().parents:
            return {"status": "BLOCKED", "error": "only games produced under the GameForge projects root can be launched"}
        proc = subprocess.Popen([str(path), "-windowed", "-ResX=1280", "-ResY=800"], cwd=str(path.parent))
        return {"status": "SUCCESS", "pid": proc.pid, "exe": str(path)}
