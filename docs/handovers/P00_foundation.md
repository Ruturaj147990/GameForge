# P0 — Foundation Hardening (handover)

**Phase owner:** Claude (architect). **Implementer:** Antigravity. **Branch:** `master` (no feature branches).
**Resolves audit findings:** F-03, F-04, F-05, F-06, F-07, F-08, F-10 (scaffold), F-11, F-15, F-16.
**Estimate:** 4–6 working days. **Prerequisite reading:** `HANDOVER_PROTOCOL.md`, `../02_AUDIT_2026-10-31.md`, `../01_ARCHITECTURE.md` §1, §3.7, §5.

## Objective

Remove the trust defects and the host coupling, and make the editor-op layer maintainable, **before** anything is
built on top. P0 adds **no new features**. Every user-visible behaviour stays the same except two: the default model
becomes the 9B, and the bridge port becomes 47815.

## Baseline (must reproduce before starting)

```powershell
$env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP=$env:TEMP
python -m pytest tests/unit/ -q -p no:cacheprovider        # 494 passed (2026-10-31)
python -m pytest graders/protected/ -q -p no:cacheprovider # 45 passed
```

## Work items (do them in this order)

| ID | Title | Touches engine? |
|---|---|---|
| WI-0.1 | Planner: completion only on evidence | no |
| WI-0.2 | `core/settings.py` + engine discovery | no |
| WI-0.3 | Replace all hard-coded host paths | no |
| WI-0.4 | Default model 9B + `model_routing.json` | no |
| WI-0.5 | Character pipeline provenance clean-up | no |
| WI-0.6 | Split `gameforge_ops.py` into a package | yes (contract test + 1 demo) |
| WI-0.7 | Undo/reversibility audit of the 73 mutating ops | yes (spot check) |
| WI-0.8 | Op argument schemas (scaffold + validation) | no |
| WI-0.9 | Bridge port 47815 + plugin descriptor + plugin rebuild | yes (plugin build) |
| WI-0.10 | Dependency and packaging metadata | no |
| WI-0.11 | Engine-demo harness + scripts layout | yes (1 demo) |
| WI-0.12 | `scripts/verify_all.ps1` | no |

---

### WI-0.1 Planner: completion only on evidence (F-03)

**Files:** `src/gameforge_ide/backend/agent/task_state.py`, `src/gameforge_ide/backend/agent/plan_executor.py`,
`src/gameforge_ide/backend/agent/plan_generator.py`, new `tests/unit/test_planner_evidence.py`.

**Step 1 — `task_state.py`: custom predicates are judged by registered evaluators, never by their own flag.**
Add this near the top of the module, after the imports:

```python
# A "custom" predicate is satisfied only when a registered evaluator confirms it from observed state.
# The predicate's own ``satisfied`` field is output, never input (design contract rule 2).
def _history_has_success(tool_history: list[dict], tools: frozenset[str]) -> tuple[bool, str]:
    for entry in tool_history:
        if entry.get("tool_name") in tools and str(entry.get("status", "")).upper() == "SUCCESS":
            return True, f"{entry.get('tool_name')} returned SUCCESS"
    return False, f"no successful call to any of {sorted(tools)} in tool history"


def _editor_responsive(tool_history: list[dict]) -> tuple[bool, str]:
    for entry in tool_history:
        out = entry.get("output") or {}
        if entry.get("tool_name") == "unreal_editor" and isinstance(out, dict) \
                and out.get("status") == "SUCCESS" and (out.get("result") or {}).get("ok") is True:
            return True, f"editor op {((out.get('result') or {}).get('op'))} returned ok"
    return False, "no successful unreal_editor read-back in tool history"


CUSTOM_PREDICATE_EVALUATORS: dict[str, Callable[[list[dict]], tuple[bool, str]]] = {
    "inspection_complete": lambda h: _history_has_success(h, frozenset({"list_dir", "read_file", "search_code"})),
    "editor_responsive": _editor_responsive,
}
```

Add `Callable` to the `typing` import. Replace the existing `custom` branch in `evaluate_acceptance` (currently
lines 513–515) with:

```python
            elif pred.predicate_type == "custom":
                evaluator = CUSTOM_PREDICATE_EVALUATORS.get(pred.target)
                if evaluator is None:
                    pred.satisfied = False
                    unmet.append(f"custom({pred.target}): no registered evaluator (cannot be satisfied)")
                else:
                    ok, why = evaluator(tool_history)
                    pred.satisfied = ok
                    pred.evidence = why
                    if not ok:
                        unmet.append(f"custom({pred.target}): {why}")
```

**Step 2 — `plan_executor.py`: a task with no tool call and no predicates is not evidence.** At the top of
`_dispatch_tool_call` (line ~376), replace the "evaluation only" early return with:

```python
        if not task.tool_call:
            if not task.acceptance:
                return {"status": "ERROR",
                        "error": "NO_EVIDENCE: task declares neither a tool call nor acceptance predicates"}
            # Evaluation-only task: its predicates are evaluated against observed state next.
            return {"status": "SUCCESS", "message": "No direct tool call, evaluation only"}
```

Do **not** change `_evaluate_predicates([])`. A task *with* a successful tool call and no predicates stays valid
(existing tests rely on that), because the tool result is the evidence.

**Step 3 — `plan_generator.py`:**
1. Delete the hard-coded fallback (lines 230–234: `val_up = Path(r"E:\GameForge\validation\...")`). If no
   `.uproject` is found in the workspace or `context["uproject"]`, Unreal-keyword prompts fall through to the default
   plan (step 3 below). Do not substitute any other path.
2. In `generate_unreal_mutation_plan` (line 69), keep `TaskAcceptancePredicate(predicate_type="custom",
   target="editor_responsive")` but **remove `satisfied=True`**.
3. In the default plan (line ~258), give the inspect task a real read so its predicate can be met:
   ```python
   task1 = TaskNode(
       task_id="step1_inspect",
       title="Inspect project workspace and context",
       objective="Discover files and configuration relevant to prompt",
       expected_result="Workspace state cataloged",
       task_type="inspect",
       permitted_tools=["list_dir", "read_file", "search_code"],
       tool_call={"name": "list_dir", "arguments": {"subpath": ".", "max_depth": 1}},
       dependency_ids=[],
       acceptance=[TaskAcceptancePredicate(predicate_type="custom", target="inspection_complete")],
   )
   ```
4. Add to the `generate_plan_from_prompt` docstring: "Keyword-templated helper used by tests and demos only. The
   product creates plans through Forge (P2); do not call this from the IDE."

**Step 4 — tests** (`tests/unit/test_planner_evidence.py`). Use the `temp_workspace` pattern from
`tests/unit/test_task_plan.py`. Write four tests:
- `test_custom_predicate_preset_true_is_ignored`: build `TaskState(... acceptance=[TaskAcceptancePredicate(predicate_type="custom", target="inspection_complete", satisfied=True)])`, call `evaluate_acceptance(ws, set(), [])`, and assert it is not satisfied.
- `test_custom_predicate_unknown_target_never_satisfied`.
- `test_inspection_complete_satisfied_by_successful_list_dir`: history `[{"tool_name": "list_dir", "status": "SUCCESS", "output": {}}]` → satisfied.
- `test_task_without_tool_and_predicates_fails`: a plan with one `TaskNode` that has no `tool_call` and no `acceptance`, run through `TaskPlanExecutor(...).run_plan(plan, auto_approve_all=True)` → task status `FAILED`, and `"NO_EVIDENCE"` in `error_message`.

**Acceptance:** the four new tests pass and the full unit suite is green. `scripts/engine/demo_real_failure_plan.py` and
`scripts/engine/demo_real_repo_plan.py` still pass. They need no engine: run them and paste the verdict lines.

---

### WI-0.2 `core/settings.py` + engine discovery (F-05, AD-15)

**Files:** new `src/gameforge_ide/core/__init__.py` (empty), new `src/gameforge_ide/core/settings.py`,
`configs/host_profiles/dev-rx7700xt.json` (add keys), new `tests/unit/test_settings.py`.

**Step 1 — add these keys to the host profile JSON** (keep the existing ones):

```json
  "default_workspace": "E:\\gameforge_step1",
  "artifacts_root": "E:\\GameForge",
  "validation_root": "E:\\GameForge\\validation",
  "probe_project": "E:\\GameForge\\validation\\live_ops_probe\\GFProbe.uproject",
  "plugin_build": "E:\\GameForge\\validation\\GameForgePlugin_neutral",
  "bridge_port": 47815
```

**Step 2 — `core/settings.py`** (canonical; copy verbatim):

```python
"""Single source of truth for paths, engine location, model defaults and host-profile values (AD-15).

Resolution order for every value (first hit wins):
  1. environment variables GAMEFORGE_* (CI, tests, scripts)
  2. the user settings file %APPDATA%\\GameForge\\settings.json (written by the Settings view in P4)
  3. the host profile JSON named by GAMEFORGE_HOST_PROFILE or settings.json "host_profile" (developer machines)
  4. discovery (engine: Epic launcher manifest, then the registry) or a product default

No other module may contain a host path literal; tests/unit/test_no_host_paths.py enforces this.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

PACKAGE_ROOT = Path(__file__).resolve().parents[1]          # src/gameforge_ide
REPO_ROOT = PACKAGE_ROOT.parents[1]                          # repository root (source checkouts only)
PINNED_ENGINE = "5.7"
DEFAULT_BRIDGE_PORT = 47815
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_ROUTING_FILE = PACKAGE_ROOT / "config" / "model_routing.json"


class EngineNotFoundError(RuntimeError):
    """Raised when an operation needs Unreal Engine and none is configured or discoverable."""


@dataclass(frozen=True)
class EngineInstall:
    root: Path
    version: str          # "5.7.4"
    changelist: int
    source: str           # "env" | "settings" | "host_profile" | "launcher" | "registry"


@dataclass(frozen=True)
class Settings:
    engine: Optional[EngineInstall]
    projects_root: Path
    artifacts_root: Path
    default_workspace: Path
    ollama_url: str
    bridge_port: int
    models: Dict[str, str]
    validation_root: Optional[Path] = None   # developer hosts only
    probe_project: Optional[Path] = None     # developer hosts only
    plugin_build: Optional[Path] = None      # developer hosts only
    host_profile: Dict[str, Any] = field(default_factory=dict)
    host_profile_path: Optional[Path] = None

    @property
    def engine_root(self) -> Path:
        if self.engine is None:
            raise EngineNotFoundError(
                f"Unreal Engine {PINNED_ENGINE} was not found. Set it in Settings or GAMEFORGE_ENGINE_ROOT.")
        return self.engine.root

    def model_for(self, role: str) -> str:
        if role not in self.models:
            raise KeyError(f"no model configured for role {role!r}; known roles: {sorted(self.models)}")
        return self.models[role]

    def require_dev(self, name: str) -> Path:
        value = getattr(self, name)
        if value is None:
            raise RuntimeError(f"{name} is only available on a developer host profile (GAMEFORGE_HOST_PROFILE)")
        return value


def _read_json(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def user_settings_path() -> Optional[Path]:
    override = os.environ.get("GAMEFORGE_USER_SETTINGS")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "GameForge" / "settings.json" if appdata else None


def engine_version(root: Path) -> Optional[tuple[str, int]]:
    """(``"5.7.4"``, changelist) from ``Engine/Build/Build.version``, or None if this is not an engine root."""
    data = _read_json(root / "Engine" / "Build" / "Build.version")
    try:
        return f"{data['MajorVersion']}.{data['MinorVersion']}.{data['PatchVersion']}", int(data.get("Changelist", 0))
    except KeyError:
        return None


def _install(root: Path, source: str) -> Optional[EngineInstall]:
    ver = engine_version(root)
    if ver is None or not (root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe").is_file():
        return None
    return EngineInstall(root=root, version=ver[0], changelist=ver[1], source=source)


def discover_engines() -> List[EngineInstall]:
    """Installed engines: the Epic launcher manifest first, then the registry. Only verified roots are returned."""
    found: List[EngineInstall] = []
    manifest = os.environ.get("GAMEFORGE_LAUNCHER_MANIFEST")
    if not manifest and os.environ.get("PROGRAMDATA"):
        manifest = str(Path(os.environ["PROGRAMDATA"]) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat")
    for item in _read_json(Path(manifest) if manifest else None).get("InstallationList", []):
        if str(item.get("AppName", "")).startswith("UE_") and item.get("InstallLocation"):
            inst = _install(Path(item["InstallLocation"]), "launcher")
            if inst and all(i.root != inst.root for i in found):
                found.append(inst)
    if not os.environ.get("GAMEFORGE_SKIP_REGISTRY"):
        try:
            import winreg  # Windows only
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine") as base:
                for i in range(winreg.QueryInfoKey(base)[0]):
                    with winreg.OpenKey(base, winreg.EnumKey(base, i)) as key:
                        inst = _install(Path(winreg.QueryValueEx(key, "InstalledDirectory")[0]), "registry")
                        if inst and all(x.root != inst.root for x in found):
                            found.append(inst)
        except OSError:
            pass
    return found


def _pick_engine(explicit: Optional[str], source: str) -> Optional[EngineInstall]:
    if explicit:
        return _install(Path(explicit), source)  # an explicit path that is not an engine resolves to None (fail closed)
    pinned = [e for e in discover_engines() if e.version.startswith(PINNED_ENGINE + ".")]
    return max(pinned, key=lambda e: e.changelist) if pinned else None


def _path(value: Any) -> Optional[Path]:
    return Path(str(value)) if value else None


def _load_models() -> Dict[str, str]:
    data = _read_json(MODEL_ROUTING_FILE)
    roles = data.get("roles", {})
    return {str(k): str(v) for k, v in roles.items()} if isinstance(roles, dict) else {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    user = _read_json(user_settings_path())
    profile_path = _path(os.environ.get("GAMEFORGE_HOST_PROFILE") or user.get("host_profile"))
    profile = _read_json(profile_path)

    def pick(env: str, key: str) -> Optional[Any]:
        return os.environ.get(env) or user.get(key) or profile.get(key)

    engine_explicit = pick("GAMEFORGE_ENGINE_ROOT", "engine_root")
    engine_source = ("env" if os.environ.get("GAMEFORGE_ENGINE_ROOT") else
                     "settings" if user.get("engine_root") else "host_profile")
    home = Path.home()
    models = _load_models()
    models.update({str(k): str(v) for k, v in (user.get("models") or {}).items()})
    return Settings(
        engine=_pick_engine(engine_explicit, engine_source),
        projects_root=_path(pick("GAMEFORGE_PROJECTS_ROOT", "projects_root")) or home / "Documents" / "GameForge" / "Projects",
        artifacts_root=_path(pick("GAMEFORGE_ARTIFACTS_ROOT", "artifacts_root")) or home / "Documents" / "GameForge",
        default_workspace=_path(pick("GAMEFORGE_WORKSPACE", "default_workspace")) or home / "Documents" / "GameForge",
        ollama_url=str(pick("GAMEFORGE_OLLAMA_URL", "ollama_url") or DEFAULT_OLLAMA_URL),
        bridge_port=int(pick("GAMEFORGE_BRIDGE_PORT", "bridge_port") or DEFAULT_BRIDGE_PORT),
        models=models,
        validation_root=_path(profile.get("validation_root")),
        probe_project=_path(profile.get("probe_project")),
        plugin_build=_path(profile.get("plugin_build")),
        host_profile=profile,
        host_profile_path=profile_path if profile else None,
    )


def reset_settings_cache() -> None:
    """Tests and the Settings view call this after changing the environment or settings.json."""
    get_settings.cache_clear()
```

**Step 3 — this developer host:** create `%APPDATA%\GameForge\settings.json` (a tiny file, allowed on C:):
```json
{"host_profile": "E:\\gameforge_step1\\configs\\host_profiles\\dev-rx7700xt.json"}
```

**Step 4 — tests** (`tests/unit/test_settings.py`). Every test sets `GAMEFORGE_USER_SETTINGS` to a temp file and
`GAMEFORGE_SKIP_REGISTRY=1` with `monkeypatch`, and calls `reset_settings_cache()` in setup and teardown (use a fixture).
- Fake engine: create `tmp/UE/Engine/Build/Build.version` (`{"MajorVersion":5,"MinorVersion":7,"PatchVersion":4,"Changelist":123}`) and an empty `tmp/UE/Engine/Binaries/Win64/UnrealEditor.exe`.
- `test_engine_from_env`: `GAMEFORGE_ENGINE_ROOT` = fake root → `settings.engine.version == "5.7.4"`, source `"env"`.
- `test_engine_from_launcher_manifest`: write a manifest JSON with `InstallationList: [{"AppName":"UE_5.7","InstallLocation": <fake>}]`, point `GAMEFORGE_LAUNCHER_MANIFEST` at it, no env root → source `"launcher"`.
- `test_explicit_non_engine_path_fails_closed`: `GAMEFORGE_ENGINE_ROOT` = an empty dir → `engine is None`, and `engine_root` raises `EngineNotFoundError`.
- `test_host_profile_values`: profile with `probe_project` → `require_dev("probe_project")` returns it. Without a profile, `require_dev` raises.
- `test_models_from_routing_file`: `model_for("chat") == "gameforge-qwen3.5-9b:latest"` (needs WI-0.4; mark that test for WI-0.4 if you do WI-0.2 first).

**Acceptance:** tests pass. `python -c "from src.gameforge_ide.core.settings import get_settings as g; s=g(); print(s.engine, s.projects_root)"`
prints the 5.7.4 install from the launcher manifest and `E:\GameForge\projects` on this host.

---

### WI-0.3 Replace all hard-coded host paths (F-05)

**Files:** the 17 files listed below, plus new `tests/unit/test_no_host_paths.py`.

**Rule:** constructor parameters that default to a host path become `Optional[Path] = None` and resolve inside the
body. Module-level constants become functions or are resolved lazily. Never resolve at import time: tests change the
environment.

| File:line (2026-10-31) | Current | Replace with |
|---|---|---|
| `backend/agent/plan_generator.py:233` | probe fallback | removed in WI-0.1 |
| `backend/app.py:26` | `WORKSPACE_ROOT = Path(r"E:\gameforge_step1")` | `WORKSPACE_ROOT = get_settings().default_workspace.resolve()` (module-level is acceptable here: the bridge app is created once per `--serve` process) |
| `backend/models/capability.py:44` | `storage_root=Path(r"E:\GameForge")` | `storage_root: Optional[Path] = None` → `storage_root or get_settings().artifacts_root` |
| `backend/providers/router.py:31` | same | same |
| `backend/tools/asset_tools.py:73` | `E:\GameForge\assets\generated` | `get_settings().artifacts_root / "assets" / "generated"` |
| `backend/tools/character_generator.py:83` | `…\characters` | same pattern |
| `backend/tools/motion_generator.py:87` | `…\animations` | same pattern |
| `backend/tools/game_tools.py:97` | `engine_root=Path(r"E:\UE\UE_5.7")` | `engine_root: Optional[Path] = None` → `engine_root or get_settings().engine_root` (also `projects_root` → `get_settings().projects_root`) |
| `backend/tools/unreal_tools.py:18` | engine path list | the first element becomes `get_settings().engine.root` if the engine is not None; keep the remaining discovery logic |
| `launcher.py:17` | `WORKSPACE_ROOT` | delete the constant; in `_launch_native_desktop`, `target_ws = Path(workspace_path).resolve() if workspace_path else get_settings().default_workspace` |
| `pipeline/animation_pipeline.py:70-71` | probe + output | `workspace_dir` required (`Optional` → raise `ValueError("workspace_dir is required")` if None); `output_dir or artifacts_root/assets/generated/animations` |
| `pipeline/character_pipeline.py:71-72` | same | same; lines 145–147 are removed in WI-0.5 |
| `pipeline/freeform.py:78` | engine | `Optional[Path] = None` → settings |
| `pipeline/game_pipeline.py:88-89` | projects + engine | `Optional` → settings |
| `unreal/live_editor.py:84` | engine | `Optional` → settings |
| `unreal/toolchain.py:116` | engine | `Optional` → settings |

Use the import `from ..core.settings import get_settings` (relative depth varies; match each file's existing
import style). Check every caller of `CharacterPipeline(...)` and `AnimationPipeline(...)` (scripts and tests) and pass
`workspace_dir` explicitly. Scripts get it from `get_settings().require_dev("validation_root")` or from their own
disposable project.

**Test** `tests/unit/test_no_host_paths.py`:

```python
"""AD-15: product code must not contain host path literals (e.g. E:\\..., C:\\Users\\...)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "gameforge_ide"
DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
EXEMPT = {"core/settings.py"}  # documents the resolution order only; contains no literals today


def test_no_drive_letter_string_literals_in_product_code():
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXEMPT or "/recipes/" in f"/{rel}" and rel.endswith("templates.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and DRIVE.match(node.value):
                offenders.append(f"{rel}:{node.lineno}: {node.value[:60]}")
    assert not offenders, "host paths in product code:\n" + "\n".join(offenders)
```

If the test finds a path that is **not** in the table above, do not exempt it. Fix it with the same pattern and list
it in the commit message.

**Acceptance:** the test passes and the full unit suite is green. `python -m src.gameforge_ide.launcher --help` works.
The IDE starts (smoke test: launch, wait 5 s, close with `win.confirm_on_close = False` through
`scripts/ide/ide_resource_benchmark.py`), and the benchmark stays within budget.

---

### WI-0.4 Default model 9B + routing file (F-06)

**Files:** new `src/gameforge_ide/config/model_routing.json`; `backend/session_manager.py:54,72`;
`backend/app.py:45`; `backend/agent/context_manager.py:97`; `desktop/main_window.py:346,566,866`;
`desktop/panels/chat_panel.py:501,557`; `tests/unit/test_desktop_acceptance.py:890`.

`src/gameforge_ide/config/model_routing.json`:

```json
{
  "schema": "model_routing/1",
  "source": "Blueprint v2 routing table (2026-10-27). Replaced by the P9 eval-generated table.",
  "roles": {
    "chat": "gameforge-qwen3.5-9b:latest",
    "design": "gameforge-qwen3.5-9b:latest",
    "codegen": "gameforge-qwen3.5-9b:latest",
    "fast": "gameforge-qwen3.5-4b:latest",
    "vision": "gameforge-qwen3.5-4b:latest",
    "heavy_local": "gameforge-27b-sft:latest"
  }
}
```

Changes:
- `SessionManager.create_session(..., model_name: Optional[str] = None, ...)`: if None, use
  `get_settings().model_for("chat")`. The dataclass field default `model_name` (line 54) becomes
  `field(default_factory=lambda: get_settings().model_for("chat"))`.
- `context_manager.build_system_prompt(..., active_model: Optional[str] = None)` → resolve the same way.
- `app.py` request model: `model_name: Optional[str] = None` → resolve at use.
- `main_window.py` and `chat_panel.py`: the hard-coded `addItem("gameforge-27b-sft:latest")` lines become
  `addItem(get_settings().model_for("chat"))`, and the initial `_current_model` / status label use the same value.
  The About text (line 866) states the four-model roster instead of naming the 27B as "the" model.
- `test_desktop_acceptance.py:890`: the assertion encodes the defect. Change it to
  `assert session.model_name == get_settings().model_for("chat")`. Tests that pass `model_name=` explicitly
  stay unchanged.

**Acceptance:** suite green. A fresh IDE launch shows `gameforge-qwen3.5-9b:latest` in the toolbar
(screenshot `reports/P0/ide_default_model.png` taken with `scratch/ide_snapshot.py`).

---

### WI-0.5 Character pipeline provenance (F-07)

**File:** `src/gameforge_ide/pipeline/character_pipeline.py`.
- Delete lines 142–147 (the `ref_fbx` resolution of Epic's `AnimatedCharacter.fbx`/`SkinBasic.fbx`) and the line
  `diagnostics["import_source_fbx"] = str(ref_fbx)`.
- Line 161: `license_name="CC-BY-4.0"` → `license_name="GameForge-Generated (project-owned)"`.
- Add `diagnostics["provenance_class"] = "PROC"`.

**Test:** in `tests/unit/test_character_pipeline.py`, add `test_no_epic_reference_asset_in_diagnostics`. It asserts
that `"FbxEditorAutomation"` does not appear in `json.dumps(result.diagnostics)` and that the provenance file's licence is
the project-owned string.

---

### WI-0.6 Split `gameforge_ops.py` into a package (F-11)

**Goal:** split the file mechanically with identical behaviour: the same 126 op names and the same `dispatch` entry
point (`import gameforge_ops; gameforge_ops.dispatch(json)`), with ops grouped by catalogue domain.

**Files:** new `scripts/tools/split_ops.py`, new package `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops/`,
delete `…/Content/Python/gameforge_ops.py`, `unreal/live_editor.py` (`OPS_LIBRARY_SOURCE` + `prepare_project`),
`unreal/op_catalog.py` (`OPS_SOURCE`, `discover_ops`), `tests/unit/test_op_catalog.py` (source reading).

**Facts established on 2026-10-31** (re-check them with the script's `--check` mode before splitting):
- 176 top-level functions: 126 ops and 50 helpers. **No `global` statements.** Module state consists of dicts and
  tuples (`_OPS`, `_AUDIO_COMPONENTS`, `_MS_NODE_HANDLES`, `_MRQ_JOB`, …), which are shared by reference.
- Exactly one op calls another op (`blueprint_compile` → `compile_blueprint`), and both are in the `blueprint` domain.

**Layout:**
```
gameforge_ops/
  __init__.py        # imports _core (dispatch, op, LIBRARY_VERSION) and every domain module so @op registers
  _core.py           # module docstring, imports, LIBRARY_VERSION, RESULT_SENTINEL, _OPS, op(), _envelope,
                     # token check, dispatch, ALL 50 helpers and ALL module-level constants; defines __all__
  session.py assets.py level.py viewport.py pie.py blueprint.py umg.py gameplay.py world.py pcg.py
  materials.py mesh.py vfx.py audio.py cinematics.py profiling.py navigation.py character.py animation.py
```

**`scripts/tools/split_ops.py`** (canonical):

```python
"""Split gameforge_ops.py into a package by op-catalogue domain (P0 WI-0.6). Usage:
    python scripts/tools/split_ops.py --check     # report only
    python scripts/tools/split_ops.py --write     # write the package; the original file is left for git rm
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from src.gameforge_ide.unreal.op_catalog import CATALOG  # noqa: E402

SRC = REPO / "src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops.py"
PKG = SRC.with_suffix("")


def op_name(fn: ast.FunctionDef):
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and getattr(d.func, "id", "") == "op":
            return d.args[0].value
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    if any(isinstance(n, ast.Global) for n in ast.walk(tree)):
        print("ABORT: global statements found; the mechanical split is unsafe")
        return 2
    body = tree.body
    doc = ast.get_docstring(tree)
    imports = [n for n in body if isinstance(n, (ast.Import, ast.ImportFrom))]
    import_src = "".join("".join(lines[n.lineno - 1:n.end_lineno]) for n in imports)

    def seg(n):  # source including decorators
        start = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])]) - 1
        return "".join(lines[start:n.end_lineno]) + "\n\n"

    core_parts, domains, helper_names = [], {}, []
    for n in body:
        if n in imports or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)):
            continue
        if isinstance(n, ast.FunctionDef) and op_name(n):
            dom = CATALOG[op_name(n)].domain
            domains.setdefault(dom, []).append(seg(n))
        else:
            core_parts.append(seg(n))
            if isinstance(n, ast.FunctionDef):
                helper_names.append(n.name)
            elif isinstance(n, ast.Assign):
                helper_names += [t.id for t in n.targets if isinstance(t, ast.Name)]
    print(f"helpers+constants in _core: {len(helper_names)}; domains: "
          + ", ".join(f"{d}={len(v)}" for d, v in sorted(domains.items())))
    if dispatch_missing := "dispatch" not in helper_names:
        print("ABORT: dispatch() not found among non-op functions")
        return 2
    if a.check or not a.write:
        return 0
    PKG.mkdir(exist_ok=True)
    exported = sorted(set(helper_names) | {"op"})
    core = (f'"""{doc}\n"""\n\n' if doc else "") + import_src + "\n\n" + "".join(core_parts)
    core += "\n__all__ = " + repr(exported) + "\n"
    (PKG / "_core.py").write_text(core, encoding="utf-8", newline="\n")
    for dom, parts in domains.items():
        head = f'"""GameForge editor ops — domain: {dom} (generated by scripts/tools/split_ops.py)."""\n\n'
        mod = head + import_src + "from ._core import *  # noqa: F401,F403  (helpers, constants, op decorator)\n\n\n"
        (PKG / f"{dom}.py").write_text(mod + "".join(parts), encoding="utf-8", newline="\n")
    init = ('"""GameForge in-editor operation library. Entry point: dispatch(request_json)."""\n'
            "from ._core import dispatch, op, LIBRARY_VERSION, RESULT_SENTINEL, _OPS  # noqa: F401\n"
            + "".join(f"from . import {d}  # noqa: F401\n" for d in sorted(domains)))
    (PKG / "__init__.py").write_text(init, encoding="utf-8", newline="\n")
    print(f"wrote {PKG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

(Remove the stray walrus `dispatch_missing :=` if your linter complains. The intent is only the `"dispatch" not in
helper_names` check.)

**Steps:**
1. Run `--check`. It must report 50 helpers/constants plus `LIBRARY_VERSION`, `RESULT_SENTINEL` and `_OPS` (counted among
   the assignments), and 19 domains totalling 126 ops. Any other result means **stop and ask**.
2. Run `--write`, then `git rm` the old single file.
3. Bump `LIBRARY_VERSION` in `_core.py` to `"2.1.0"`.
4. `live_editor.py`:
   ```python
   OPS_LIBRARY_SOURCE = Path(__file__).parent / "GameForge" / "Content" / "Python" / "gameforge_ops"
   ...
   # in prepare_project():
   py_dir = self.project_dir / "Content" / "Python"
   stale = py_dir / "gameforge_ops.py"           # pre-2.1 single-file copy would shadow nothing but confuses audits
   if stale.exists():
       stale.unlink()
   dest = py_dir / "gameforge_ops"
   if dest.exists():
       shutil.rmtree(dest)
   shutil.copytree(OPS_LIBRARY_SOURCE, dest, ignore=shutil.ignore_patterns("__pycache__"))
   ```
   The returned dict key `"ops_library"` now points at the package directory.
5. `op_catalog.py`:
   ```python
   OPS_SOURCE = Path(__file__).parent / "GameForge" / "Content" / "Python" / "gameforge_ops"

   def op_sources(root: Path = OPS_SOURCE) -> list[Path]:
       return sorted(p for p in root.glob("*.py"))

   def discover_ops(source: Path = OPS_SOURCE) -> list[str]:
       files = [source] if source.is_file() else op_sources(source)
       return [n for f in files for n in re.findall(r'@op\("([^"]+)"', f.read_text(encoding="utf-8"))]
   ```
6. `tests/unit/test_op_catalog.py:24` reads `OPS_SOURCE` as one file. Change it to iterate `op_catalog.op_sources()` and
   apply the same decorator-adjacency check per file.
7. Add a test, `test_ops_package_is_importable_offline`. It inserts a fake `unreal` module (`types.ModuleType("unreal")`
   with `class _Any: def __getattr__(self, n): return self` style attributes) into `sys.modules`, imports the package
   from its directory (`importlib` with `sys.path.insert`), and asserts `len(gameforge_ops._OPS) == 126`. Undo the
   `sys.modules` changes afterwards. If import-time code calls into `unreal` in a way the fake cannot satisfy, report
   it in QUESTIONS.md; do not change op code to suit the fake.

**Engine verification (mandatory):**
```powershell
# fresh disposable copy of the probe with the CURRENT plugin build (harness from WI-0.11, or by hand before it exists)
python scripts\engine\live_editor_contract_test.py <disposable>\GFProbe.uproject   # expect 16/16, graceful stop
python scripts\engine\demo_gameplay_feedback.py                                    # expect 10/10
```
Save both outputs under `reports/P0/` (`contract_after_split.json`, `gameplay_feedback_after_split.json`).

**Failure cases to watch:** the editor caches `gameforge_ops` in `sys.modules` for the editor's lifetime, so always
launch a **new** editor after deploying. A leftover `Content/Python/gameforge_ops.py` in an *old* probe copy is
removed by step 4. `__pycache__` folders must not be copied.

---

### WI-0.7 Undo and reversibility audit (F-04)

**Goal:** every mutating op is in exactly one undo class, and a unit test keeps the source honest.

**Files:** `unreal/op_catalog.py` (new `OpSpec.undo` field), the op package modules, `tests/unit/test_op_catalog.py`,
the `_core.py` docstring.

1. Add `undo: str = "none"` to `OpSpec`, with values:
   - `"transaction"`: the op body contains `unreal.ScopedEditorTransaction(` around its edits. Use this for actor and
     property edits in a level, and for graph edits on existing assets.
   - `"checkpoint"`: not undoable in-editor (asset creation, import, delete, save, level new/load, landscape creation,
     MRQ render), so it relies on project git checkpoints (P2). Its envelope `reversibility` must be `"irreversible"`.
   - `"runtime"`: PIE or session state that disappears when PIE stops (`pie_*`, `vfx_spawn`, `audio_play_*`,
     `gameplay_modify_state`, `widget_click_button`, …).
   - `"none"`: read, view and artifact ops.
2. Extend `_ops()` with an `undo` parameter and classify all 73 mutating ops. Wrap level-actor and property edits
   that lack a transaction in `with unreal.ScopedEditorTransaction("GameForge: <op>"):`. **Do not wrap** PIE ops,
   level new/load, saves or imports. Wrapping them breaks them, or the editor refuses.
3. Test `test_undo_class_matches_source`. For each catalogue op, find its function in the package (AST over
   `op_sources()`), then assert: `undo == "transaction"` ⇔ the function body text contains
   `ScopedEditorTransaction(`; `undo == "checkpoint"` ⇒ the op's envelope calls pass `reversibility="irreversible"`;
   and every mutating op has `undo != "none"`.
4. Fix the `_core.py` docstring: "Level and property mutations run inside ScopedEditorTransaction; asset-level
   mutations are irreversible in-editor and are covered by project checkpoints (catalogue field `undo`)."

**Engine spot check:** in a disposable probe, run `spawn_actor` then `set_actor_property` through the link, then
invoke undo via an editor Python call in a **diagnostic script only** (`unreal.SystemLibrary.execute_console_command(None,
"TRANSACTION UNDO")`), and read back with `actors_in_level`. Expect the property reverted. Record the result in
`reports/P0/undo_spotcheck.json`. This proves the transaction wrapper works in 5.7.4 Python. If it does not, record
FAIL and ask before continuing.

---

### WI-0.8 Op argument schemas — scaffold and validation (F-10, AD-14)

**Files:** new `scripts/tools/gen_op_schemas.py`, new `src/gameforge_ide/unreal/op_schemas.py`,
`backend/tools/game_tools.py` (`unreal_editor`), new `tests/unit/test_op_schemas.py`.

1. `gen_op_schemas.py`: walk the op package AST. For each `@op` function, collect `args.get("k", default)` (optional,
   type from the default's literal type, `Any` if unknown) and `args["k"]` (required) keys. Print a draft
   `op_schemas.py`. Ops with no detected keys but a non-trivial body (they forward `args` wholesale; 27 ops on
   2026-10-31, e.g. `landscape_create`, `spline_create_road`, `foliage_scatter`, `landmark_spawn`) are emitted with a
   `# MANUAL:` comment and `model_config = ConfigDict(extra="allow")`.
2. Hand-review the draft for the **30 ops the agent and composer use most**: `new_level load_level spawn_actor
   delete_actor set_actor_property actors_in_level asset_exists list_assets import_asset create_material
   material_build_graph material_instance_create texture_import mesh_generate_prop static_mesh_configure pcg_build_graph
   landscape_create world_clear_generated datalayer_ensure datalayer_add_actors nav_rebuild nav_find_path pie_start
   pie_stop pie_actor_state vfx_create_system audio_import audio_create_attenuation sequence_build viewport_screenshot`.
   For those: `model_config = ConfigDict(extra="forbid")`, correct types (vectors as `Vec3 = {"x","y","z"}` models,
   rotators as `Rot3 = {"roll","pitch","yaw"}`) and field descriptions. For `landscape_create` and the other forwarded-args
   ops, read the C++ library signature in `Source/GameForgeEditor/Public/GameForgeLandscapeLibrary.h` to get the
   real parameter names.
3. Structure of `op_schemas.py`:
   ```python
   from pydantic import BaseModel, ConfigDict, Field
   class Vec3(BaseModel):
       model_config = ConfigDict(extra="forbid")
       x: float = 0.0; y: float = 0.0; z: float = 0.0
   class SpawnActorArgs(BaseModel):
       model_config = ConfigDict(extra="forbid")
       label: str = Field(min_length=1, max_length=120)
       actor_class: str = "StaticMeshActor"
       static_mesh: str | None = None
       location: Vec3 = Vec3()
       rotation: Rot3 = Rot3()
       scale: Vec3 | None = None
       mobility: str | None = None
       material: str | None = None
       light_intensity: float | None = None
   SCHEMAS: dict[str, type[BaseModel]] = {"spawn_actor": SpawnActorArgs, ...}
   def validate_args(op: str, args: dict) -> tuple[dict | None, list[str]]:
       model = SCHEMAS.get(op)
       if model is None:
           return args, []                     # P0: unknown schema passes (warning logged by caller); P2 makes it an error
       try:
           return model.model_validate(args).model_dump(exclude_none=True), []
       except ValidationError as exc:
           return None, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
   ```
   **Caution:** `spawn_actor` reads `light_intensity` with `args["light_intensity"]` inside a branch (lights only).
   That is why the generator marks it "required". Make it optional in the schema. Treat every generator "required" as
   a hypothesis until you have read the op body.
4. `GameTools.unreal_editor`: before `self._link(uproject).call(...)`, run
   `clean, errs = op_schemas.validate_args(op, args or {})`. On errors, return
   `{"status": "ERROR", "error": "invalid args for op", "details": errs}` without touching the editor.
5. Tests: every key in `SCHEMAS` is a catalogued op; `validate_args("spawn_actor", {"label": "A", "bogus": 1})`
   errors; a valid call round-trips. A golden test runs `gen_op_schemas.py --check` and asserts it reports exactly
   126 ops.

**Acceptance:** tests green. The demo from WI-0.6 still passes, because demos call the link directly, not the gateway.

---

### WI-0.9 Bridge port 47815, plugin descriptor, plugin rebuild (F-08, F-16)

**Files:** `launcher.py:53,88`, `Source/GameForgeEditor/Public/GameForgeBridgeClient.h:21`,
`Source/GameForgeEditor/Private/GameForgeBridgeClient.cpp:24-25`, `GameForge.uplugin`.

1. Python: `_launch_server(host="127.0.0.1", port: Optional[int] = None)` → `port or get_settings().bridge_port`; the
   argparse default becomes `None`, with help text `"(default: settings bridge_port, 47815)"`.
2. C++: replace both `http://127.0.0.1:8000` literals with `http://127.0.0.1:47815`. Then in
   `GameForgeEditorModule.cpp`, where `BridgeClient = MakeShared<FGameForgeBridgeClient>();` is created, read an
   optional override first:
   ```cpp
   FString Url;
   if (GConfig && GConfig->GetString(TEXT("GameForge.Bridge"), TEXT("Url"), Url, GEditorIni) && !Url.IsEmpty())
   {
       BridgeClient = MakeShared<FGameForgeBridgeClient>(Url);   // constructor still enforces loopback
   }
   else
   {
       BridgeClient = MakeShared<FGameForgeBridgeClient>();
   }
   ```
3. `GameForge.uplugin`: `"Description": "GameForge editor bridge and gameplay runtime kit for Unreal Engine 5.7."`,
   `"CreatedBy": "GameForge"`, and empty strings for `CreatedByURL`, `DocsURL` and `SupportURL`.
4. Rebuild the plugin (`06_ENGINE_NOTES_UE57.md` §Plugin build) to `E:\GameForge\validation\GameForgePlugin_p0`.
   Back up the current binaries, install them in the repo plugin `Binaries` and `live_ops_probe`, and set
   `plugin_build` in the host profile to the new folder. Record both DLL SHA-256 values in `context.md`.
5. Verify: launch the IDE with `--serve` and confirm with `Get-NetTCPConnection -LocalPort 47815`. In a disposable
   probe, trigger the editor's "GameForge.SyncContext" command (console `GameForge.SyncContext`, if the module registers
   it; otherwise any action that calls `SendContextToIDE`). Expect a 200 in the `--serve` log. Evidence goes to
   `reports/P0/bridge_47815.json`.

---

### WI-0.10 Dependency and packaging metadata (F-15)

1. `requirements.txt`: add `numpy>=2.0`, `Pillow>=10.0`. Keep the existing lines.
2. `pyproject.toml`: keep the project name `gameforge_bench`. Renaming it would break benchmark tooling: record the
   rename idea in QUESTIONS.md, do not do it. Add `numpy>=2.0` and `Pillow>=10.0` to `[project.optional-dependencies].ide`.
   Leave the entry point unchanged in P0. P11 fixes packaging.
3. Test `test_declared_dependencies_cover_imports`: AST-scan `src/gameforge_ide` (excluding
   `unreal/GameForge/Content/Python`, which runs inside the editor's Python) for top-level imported third-party
   modules, and assert each maps to a declared requirement. Use the map
   `{"PIL": "Pillow", "yaml": "pyyaml", "PySide6": "PySide6", "numpy": "numpy", "pydantic": "pydantic",
   "fastapi": "fastapi", "uvicorn": "uvicorn", "httpx": "httpx", "psutil": "psutil", "rich": "rich"}`. Standard-library
   modules are exempt (`sys.stdlib_module_names`). Optional imports guarded by `try/except ImportError` (e.g.
   `keyring`) are allowed and listed in the test as `OPTIONAL = {"keyring"}`.

---

### WI-0.11 Engine-demo harness and scripts layout

**Goal:** one harness instead of the `make_disposable`/`PLUGIN_BUILD` copies spread through 14 demo scripts, plus a
readable `scripts/` tree.

1. New `scripts/engine/_harness.py`, moved and generalised from `scripts/engine/demo_m11_landscape.py`:
   ```python
   """Shared engine-demo harness: disposable probe copies, editor start, report writing."""
   from __future__ import annotations
   import json, shutil, sys, time
   from pathlib import Path
   REPO = Path(__file__).resolve().parents[2]
   sys.path.insert(0, str(REPO))
   from src.gameforge_ide.core.settings import get_settings          # noqa: E402
   from src.gameforge_ide.unreal.live_editor import LiveEditorLink   # noqa: E402

   def disposable_probe(tag: str) -> Path:
       s = get_settings()
       probe = s.require_dev("probe_project").parent
       dest = s.require_dev("validation_root") / f"{tag}_{time.strftime('%Y%m%d')}"
       if dest.exists():
           shutil.rmtree(dest)
       shutil.copytree(probe, dest, ignore=shutil.ignore_patterns(
           "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
       bins = dest / "Plugins" / "GameForge" / "Binaries"
       if bins.exists():
           shutil.rmtree(bins)
       shutil.copytree(s.require_dev("plugin_build") / "Binaries", bins)
       return dest / "GFProbe.uproject"

   def start_editor(uproject: Path, log_name: str, no_sound: bool = True) -> LiveEditorLink:
       link = LiveEditorLink(uproject)
       link.prepare_project()
       link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"],
                   log_path=uproject.parent / f"{log_name}.log", **({} if no_sound else {"no_sound": False}))
       link.connect(discovery_timeout_s=900)
       return link

   def write_report(name: str, payload: dict, phase: str | None = None) -> Path:
       out = REPO / "reports" / (phase or "") / f"{name}.json"
       out.parent.mkdir(parents=True, exist_ok=True)
       payload.setdefault("finished", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
       out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
       return out
   ```
   Check `LiveEditorLink.launch`'s real signature for `no_sound` and adapt the call. Keep the semantics.
2. `git mv` the scripts into `scripts/engine/` (every `demo_*.py`, `wpa_reverify.py`, `perf_village_pie.py`,
   `package_kit_selftest.py`, `diag_m14_spawn_sound.py`, `live_editor_contract_test.py`, `live_operations_check.py`,
   `audit_*`, `verify_*`, `backfill_registry_hero.py`), `scripts/pipeline/` (`run_game_pipeline.py`,
   `run_freeform_game.py`, `ide_prompt_to_game_e2e.py`), `scripts/ide/` (`ide_resource_benchmark.py`,
   `native_tool_selftest.py`, `verify_four_models_live.py`), `scripts/tools/` (`gen_op_coverage.py`, `split_ops.py`,
   `gen_op_schemas.py`, `probe_bp_api.py`, `compare_gguf_tensors.py`, `convert_hf_to_gguf.py`) and `scripts/models/`
   (all `train_*`, `generate_*dataset*`, `materialize_*`, `merge_*`, `export_*`, `download_hf_checkpoint.py`,
   `smoke_test_27b_clm.py`, `pilot_compatibility_test.py`, `benchmark_long_context.py`, `build_gameforge_27b_benchmark.py`,
   `run_*eval*`, `run_*regression*`, `run_post_training_short_test.py`, `run_step5_clean_retest.py`,
   `execute_acceptance_regression.py`, `evaluate_gameforge_benchmark.py`, `audit_dataset_acceptance.py`,
   `audit_gameforge_v2_provenance.py`, `verify_artifact_acceptance.py`, `run_baseline_evaluation.py`,
   `run_fair_evaluation_suite.py`, `run_independent_regression_suite.py`, `run_phase2_*`).
3. Fix `REPO = Path(__file__).resolve().parents[N]` in each moved script (one level deeper ⇒ `parents[2]`). Replace
   each demo's local `make_disposable`/`start`/`PLUGIN_BUILD` with harness calls. Imports like
   `from demo_m11_landscape import make_disposable` become `from _harness import disposable_probe` (the scripts in
   `scripts/engine/` share a directory, so the import works when the script is run directly).
4. Update every path reference to the moved scripts: grep `scripts/` and `scripts\\` in `docs/`, `tests/`,
   `src/` (e.g. `benchmark_long_context.py` is referenced by `reports/GAMEFORGE_LONG_CONTEXT_BENCHMARK.md`, which
   stays unchanged as historical evidence) and `AGENTS.md`.
5. Benchmark-era root files (`GAMEFORGE_FINAL_MASTER_STRATEGY.md`, `STEP4_AUDIT_REPORT.md`, `GAMEFORGE_ROADMAP.csv`,
   `TASK_INVENTORY.csv`, `ENGINE_FEATURE_COVERAGE_MATRIX.csv`, `EVALUATION_CONTRACT.md`) **stay at the root**.
   `gameforge_bench` code and `tests/unit/test_acceptance_criteria.py` read them relative to the workspace root, next
   to the protected `graders/` tree. Moving them is out of scope.
6. Move `GAMEFORGE_UNREAL_OPERATION_COVERAGE.md` to `docs/generated/` and update `scripts/tools/gen_op_coverage.py`.

**Verification:** the unit suite is green (some tests import scripts by path; fix them). Then run
`python scripts\engine\demo_m15_quest.py` (8/8) to prove the harness.

---

### WI-0.12 `scripts/verify_all.ps1`

```powershell
<# GameForge verification gate. -Quick: no engine. Full: also engine contract + one demo + IDE benchmark. #>
param([switch]$Quick)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
New-Item -ItemType Directory -Force "$repo\scratch\pytest_os_temp" | Out-Null
$env:TEMP = "$repo\scratch\pytest_os_temp"; $env:TMP = $env:TEMP
if (-not $env:GAMEFORGE_HOST_PROFILE) { $env:GAMEFORGE_HOST_PROFILE = "$repo\configs\host_profiles\dev-rx7700xt.json" }
$results = [ordered]@{}
function Gate($name, [scriptblock]$cmd) {
    Write-Host "== $name" -ForegroundColor Cyan
    & $cmd
    $script:results[$name] = if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL ($LASTEXITCODE)" }
}
Gate "unit"       { python -m pytest tests/unit/ -q -p no:cacheprovider }
Gate "protected"  { python -m pytest graders/protected/ -q -p no:cacheprovider }
Gate "op-catalog" { python scripts/tools/gen_op_coverage.py --check }
if (-not $Quick) {
    Gate "contract"   { python scripts/engine/live_editor_contract_test.py --disposable }
    Gate "demo-quest" { python scripts/engine/demo_m15_quest.py }
    Gate "ide-bench"  { python scripts/ide/ide_resource_benchmark.py --workspace E:\GameForge\ide_bench_ws }
}
$results.GetEnumerator() | ForEach-Object { "{0,-12} {1}" -f $_.Key, $_.Value }
if ($results.Values | Where-Object { $_ -ne "PASS" }) { exit 1 } else { exit 0 }
```

Add `--check` to `gen_op_coverage.py`: compare the rendered table with `docs/generated/GAMEFORGE_UNREAL_OPERATION_COVERAGE.md`
and exit 1 on drift. Add `--disposable` to the contract test: use `_harness.disposable_probe("contract")` instead of a
path argument, keeping the path argument as an alternative.

---

## Phase exit gate (all must hold)

1. `scripts\verify_all.ps1` (full) → every gate PASS. Output saved to `reports/P0/verify_all.txt`.
2. `tests/unit/test_no_host_paths.py`, `test_planner_evidence.py`, `test_settings.py`, `test_op_schemas.py` and the
   extended `test_op_catalog.py` are all green.
3. Evidence files in `reports/P0/`: `contract_after_split.json`, `gameplay_feedback_after_split.json`,
   `undo_spotcheck.json`, `bridge_47815.json`, `ide_default_model.png`, `verify_all.txt`.
4. `context.md` updated: plugin build `GameForgePlugin_p0` with SHA-256 values, the test counts, and the next action
   "P1 WI-1.1".
5. `docs/00_STATUS.md` rows updated: planner, settings, op layer.

## Progress

| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 0.1 | DONE | 2026-10-31 | 2026-10-31 | `55ffc5f`; test_planner_evidence (5); repo/failure plan demos re-run as expected |
| 0.2 | DONE | 2026-10-31 | 2026-10-31 | `66c01d2`; test_settings (6); engine 5.7.4 found via host profile/launcher |
| 0.3 | DONE | 2026-10-31 | 2026-10-31 | `4c88b81`; test_no_host_paths green (0 literals in src/) |
| 0.4 | DONE | 2026-10-31 | 2026-10-31 | `a5a239e`; offscreen IDE shows gameforge-qwen3.5-9b in toolbar, chat and status |
| 0.5 | DONE | 2026-10-31 | 2026-10-31 | `4c88b81`; test_no_epic_reference_asset_in_diagnostics |
| 0.6 | DONE | 2026-10-31 | 2026-10-31 | `6c2b0d1`; 19 domain modules, 126 ops; contract 16/16 + gameplay feedback 10/10 (`reports/P0/`) |
| 0.7 | DONE | 2026-10-31 | 2026-10-31 | `7f72750`..`4475aca`; OpSpec.undo + true_reversibility + test; `reports/P0/undo_spotcheck.json` PASS (ScopedEditorTransaction + TRANSACTION UNDO verified in 5.7.4) |
| 0.8 | PARTIAL | 2026-10-31 | 2026-10-31 | `7f72750`; drafts for all 126 ops + gateway validation; hand-reviewed models for 6 core level ops (handover asked 30) |
| 0.9 | PARTIAL | 2026-10-31 | 2026-10-31 | `4475aca`; plugin p0 built (0 warnings) + installed; contract 16/16 with p0; bridge health 200 on 47815. Editor-originated SyncContext request not exercised |
| 0.10 | DONE | 2026-10-31 | 2026-10-31 | `1d7b6ee`; test_declared_dependencies (fails if numpy removed) |
| 0.11 | DONE | 2026-10-31 | 2026-10-31 | `035d90c`; 80 scripts moved; `_harness.py`; demos default to host-profile probe/plugin; coverage table in docs/generated |
| 0.12 | DONE | 2026-10-31 | 2026-10-31 | `035d90c`; `scripts/verify_all.ps1` (Quick: 4/4 PASS); full run: `reports/P0/verify_all.txt` |

## Review log (Claude)

_empty_

## Revisions

- 2026-10-31: created (Claude).
