"""Unreal toolchain: scaffold, build, test, package, smoke-test (Master Blueprint v2, WP2).

Everything here runs real engine executables of the pinned install and returns structured
results with exit codes, durations, parsed diagnostics and log paths. Nothing is simulated.

Executables are invoked directly (UnrealBuildTool.exe, AutomationTool.exe, UnrealEditor-Cmd.exe)
with argv lists and no shell. Builds run at below-normal priority so the IDE stays responsive.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union
from ..core.settings import engine_root_or_missing
from ..core import jobs

BELOW_NORMAL = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_IDENT = re.compile(r"^[A-Z][A-Za-z0-9]{1,30}$")
logger = logging.getLogger(__name__)


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning"
    code: str
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    source: str = "msvc"  # msvc | uht | linker | ubt | automation


@dataclass
class StepResult:
    ok: bool
    step: str
    exit_code: Optional[int]
    duration_s: float
    log_path: Optional[str] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)
    data: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["error_count"] = sum(1 for x in self.diagnostics if x.severity == "error")
        d["warning_count"] = sum(1 for x in self.diagnostics if x.severity == "warning")
        return d


# ── diagnostics ─────────────────────────────────────────────────────────────

_MSVC = re.compile(r"^\s*(?P<file>[A-Za-z]:[^()]+?)\((?P<line>\d+)(?:,\d+)?\)\s*:\s*(?P<sev>fatal error|error|warning)\s+(?P<code>[A-Z]+\d+)\s*:\s*(?P<msg>.*)$")
_UHT = re.compile(r"^\s*(?P<file>[A-Za-z]:[^()]+?)\((?P<line>\d+)\)\s*:\s*(?P<sev>Error|Warning)\s*:\s*(?P<msg>.*)$")
_LINK = re.compile(r"^\s*(?P<obj>[^:]+?)\s*:\s*(?P<sev>fatal error|error|warning)\s+(?P<code>LNK\d+)\s*:\s*(?P<msg>.*)$")
_UBT = re.compile(r"^\s*(?:ERROR|Error)\s*:\s*(?P<msg>.+)$")


ENHANCED_INPUT_INI = (
    "[/Script/Engine.InputSettings]\n"
    "DefaultPlayerInputClass=/Script/EnhancedInput.EnhancedPlayerInput\n"
    "DefaultInputComponentClass=/Script/EnhancedInput.EnhancedInputComponent\n"
)

_LEGACY_INPUT_INI = (
    "[/Script/Engine.InputSettings]\n"
    "+ActionMappings=(ActionName=\"Jump\",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=SpaceBar)\n"
    "+ActionMappings=(ActionName=\"Jump\",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=Gamepad_FaceButton_Bottom)\n"
    "+ActionMappings=(ActionName=\"Restart\",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=R)\n"
    "+ActionMappings=(ActionName=\"Attack\",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=LeftMouseButton)\n"
    "+ActionMappings=(ActionName=\"Attack\",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=SpaceBar)\n"
    "+ActionMappings=(ActionName=\"Attack\",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=Gamepad_FaceButton_Bottom)\n"
    "+AxisMappings=(AxisName=\"MoveForward\",Scale=1.000000,Key=W)\n"
    "+AxisMappings=(AxisName=\"MoveForward\",Scale=-1.000000,Key=S)\n"
    "+AxisMappings=(AxisName=\"MoveForward\",Scale=1.000000,Key=Up)\n"
    "+AxisMappings=(AxisName=\"MoveForward\",Scale=-1.000000,Key=Down)\n"
    "+AxisMappings=(AxisName=\"MoveForward\",Scale=1.000000,Key=Gamepad_LeftY)\n"
    "+AxisMappings=(AxisName=\"MoveRight\",Scale=1.000000,Key=D)\n"
    "+AxisMappings=(AxisName=\"MoveRight\",Scale=-1.000000,Key=A)\n"
    "+AxisMappings=(AxisName=\"MoveRight\",Scale=1.000000,Key=Right)\n"
    "+AxisMappings=(AxisName=\"MoveRight\",Scale=-1.000000,Key=Left)\n"
    "+AxisMappings=(AxisName=\"MoveRight\",Scale=1.000000,Key=Gamepad_LeftX)\n"
    "+AxisMappings=(AxisName=\"Turn\",Scale=1.000000,Key=MouseX)\n"
    "+AxisMappings=(AxisName=\"Turn\",Scale=1.000000,Key=Gamepad_RightX)\n"
    "+AxisMappings=(AxisName=\"LookUp\",Scale=-1.000000,Key=MouseY)\n"
    "+AxisMappings=(AxisName=\"LookUp\",Scale=-1.000000,Key=Gamepad_RightY)\n"
    "bCaptureMouseOnLaunch=True\n"
    "DefaultViewportMouseCaptureMode=CapturePermanently_IncludingInitialMouseDown\n"
)


def parse_build_diagnostics(text: str, limit: int = 200) -> List[Diagnostic]:
    """Turn UBT/MSVC/UHT/linker output into compact, de-duplicated diagnostics."""
    out: List[Diagnostic] = []
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        d = None
        m = _MSVC.match(line)
        if m:
            sev = "error" if "error" in m["sev"] else "warning"
            d = Diagnostic(sev, m["code"], m["msg"].strip(), m["file"].strip(), int(m["line"]), "msvc")
        elif (m := _UHT.match(line)):
            d = Diagnostic(m["sev"].lower(), "UHT", m["msg"].strip(), m["file"].strip(), int(m["line"]), "uht")
        elif (m := _LINK.match(line)):
            sev = "error" if "error" in m["sev"] else "warning"
            d = Diagnostic(sev, m["code"], m["msg"].strip(), m["obj"].strip(), None, "linker")
        elif (m := _UBT.match(line)):
            d = Diagnostic("error", "UBT", m["msg"].strip(), None, None, "ubt")
        if d is None:
            continue
        key = (d.severity, d.code, d.file, d.line, d.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
        if len(out) >= limit:
            break
    return out


def parse_automation_report(report_dir: Path) -> Dict:
    """Parse the JSON report written by -ReportExportPath (index.json)."""
    index = Path(report_dir) / "index.json"
    if not index.is_file():
        return {"found": False, "tests": [], "succeeded": 0, "failed": 0, "not_run": 0}
    raw = index.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")  # report is UTF-8 with BOM
    data = json.loads(text)
    tests = []
    for t in data.get("tests", []):
        errs = [e.get("event", {}).get("message", "") for e in t.get("entries", [])
                if e.get("event", {}).get("type") == "Error"]
        tests.append({"name": t.get("fullTestPath") or t.get("testDisplayName"),
                      "state": t.get("state"), "errors": errs[:5]})
    return {"found": True, "tests": tests,
            "succeeded": data.get("succeeded", sum(1 for t in tests if t["state"] == "Success")),
            "failed": data.get("failed", sum(1 for t in tests if t["state"] == "Fail")),
            "not_run": data.get("notRun", 0)}


def format_unreal_cmd(argv: List[str]) -> Union[str, List[str]]:
    """Format command arguments for Unreal Engine executables on Windows.
    
    Ensures switches like -Project=..., -ExecCmds=..., -ReportExportPath=..., -abslog=...
    have whitespace before the '-' and quotes properly enclosing the value so that
    Unreal's FCommandLine::Parse and FParse::Value extract the full path without truncating at spaces.
    """
    if sys.platform != "win32":
        return argv

    tokens: List[str] = []
    for arg in argv:
        if arg.startswith("-") and "=" in arg:
            switch, val = arg.split("=", 1)
            val_clean = val.strip('"')
            # Normalize backslashes to avoid escaping issues in Windows CLI for file paths
            val_norm = val_clean.replace("\\", "/") if ((":" in val_clean or "/" in val_clean or "\\" in val_clean) and not val_clean.startswith("Automation")) else val_clean
            if " " in val_norm or '"' in val:
                tokens.append(f'{switch}="{val_norm}"')
            else:
                tokens.append(f'{switch}={val_norm}')
        elif arg.startswith("-"):
            if " " in arg or '"' in arg:
                tokens.append(f'"{arg}"')
            else:
                tokens.append(arg)
        else:
            # Positional argument (e.g. exe path or uproject path)
            clean = arg.strip('"')
            norm = clean.replace("\\", "/") if (":" in clean or "/" in clean or "\\" in clean) else clean
            if " " in norm or '"' in clean:
                tokens.append(f'"{norm}"')
            else:
                tokens.append(norm)

    return " ".join(tokens)


# ── toolchain ───────────────────────────────────────────────────────────────

class UnrealToolchain:
    _DEPLOY_LOCK = threading.Lock()

    def __init__(self, engine_root: Optional[Path] = None, max_parallel_actions: Optional[int] = None):
        self.engine_root = Path(engine_root or engine_root_or_missing())
        e = self.engine_root / "Engine"
        ubt_candidates = [
            e / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe",
            e / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll",
            e / "Binaries" / "DotNET" / "UnrealBuildTool.exe",
            e / "Binaries" / "DotNET" / "UnrealBuildTool.dll",
        ]
        self.ubt = next((c for c in ubt_candidates if c.is_file()), ubt_candidates[0])

        uat_candidates = [
            e / "Binaries" / "DotNET" / "AutomationTool" / "AutomationTool.exe",
            e / "Binaries" / "DotNET" / "AutomationTool.exe",
            e / "Build" / "BatchFiles" / "RunUAT.bat",
        ]
        self.uat = next((c for c in uat_candidates if c.is_file()), uat_candidates[0])
        self.editor_cmd = e / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
        self.max_parallel_actions = max_parallel_actions
        self.cancel_event = None  # threading.Event set by the UI to cancel the running step

    @staticmethod
    def kill_tree(proc: subprocess.Popen) -> None:
        """Kill a process and all its descendants (UBT/UAT/packaged bootstrappers spawn children)."""
        if proc is None:
            return
        pid = getattr(proc, "pid", None)
        try:
            import psutil
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            parent.kill()
        except Exception:
            pass

        if pid and sys.platform == "win32":
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    startupinfo=si,
                )
            except Exception:
                pass

        try:
            proc.kill()
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    def _wait(self, proc: subprocess.Popen, timeout_s: float) -> Optional[int]:
        """Wait for exit, honouring cancel; returns exit code, or raises TimeoutError / InterruptedError."""
        deadline = time.monotonic() + timeout_s
        while True:
            code = proc.poll()
            if code is not None:
                return code
            if self.cancel_event is not None and self.cancel_event.is_set():
                self.kill_tree(proc)
                raise InterruptedError("CANCELLED")
            if time.monotonic() > deadline:
                self.kill_tree(proc)
                raise TimeoutError(f"TIMEOUT after {timeout_s}s")
            time.sleep(0.25)

    def check(self) -> Dict[str, bool]:
        return {"ubt": self.ubt.is_file(), "uat": self.uat.is_file(), "editor_cmd": self.editor_cmd.is_file()}

    def engine_version(self) -> str:
        v = json.loads((self.engine_root / "Engine" / "Build" / "Build.version").read_text(encoding="utf-8", errors="replace"))
        return f'{v["MajorVersion"]}.{v["MinorVersion"]}.{v["PatchVersion"]}'

    # ── process helper ─────────────────────────────────────────────────────
    def _run(self, step: str, argv: List[str], log_path: Path, timeout_s: float,
             cwd: Optional[Path] = None) -> StepResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        print(f"[Unreal Toolchain] Running step '{step}' (timeout: {timeout_s}s)...", flush=True)
        cmd = format_unreal_cmd(argv)
        try:
            with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                log.write("ARGV: " + json.dumps(argv) + "\n")
                if isinstance(cmd, str):
                    log.write("CMD: " + cmd + "\n")
                log.flush()
                proc = jobs.spawn(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None,
                                  creationflags=BELOW_NORMAL | NO_WINDOW)
                try:
                    code = self._wait(proc, timeout_s)
                except (TimeoutError, InterruptedError) as exc:
                    print(f"[Unreal Toolchain] Step '{step}' TIMEOUT/INTERRUPTED: {exc}", flush=True)
                    return StepResult(False, step, None, round(time.monotonic() - started, 1), str(log_path),
                                      errors=[str(exc)])
        except OSError as exc:
            print(f"[Unreal Toolchain] Step '{step}' LAUNCH FAILED: {exc}", flush=True)
            return StepResult(False, step, None, 0.0, str(log_path), errors=[f"launch failed: {exc}"])
        dur = round(time.monotonic() - started, 1)
        status_tag = "OK" if code == 0 else f"FAILED (code {code})"
        try:
            print(f"[Unreal Toolchain] Step '{step}' {status_tag} in {dur}s (log: {log_path.name})", flush=True)
        except Exception:
            pass
        text = log_path.read_text(encoding="utf-8", errors="replace")
        diags = parse_build_diagnostics(text)
        return StepResult(code == 0, step, code, dur, str(log_path), diags)

    # ── scaffold ───────────────────────────────────────────────────────────
    def scaffold_cpp_project(self, project_dir: Path, name: str, extra_files: Optional[Dict[str, str]] = None,
                             default_map: Optional[str] = None, game_mode: Optional[str] = None,
                             module_deps: Optional[List[str]] = None, overwrite_source: bool = True,
                             display_title: Optional[str] = None,
                             plugins: Optional[List[str]] = None) -> Dict:
        """Write a minimal, valid UE C++ project. Returns the files written."""
        if not _IDENT.match(name):
            raise ValueError(f"project name must be PascalCase alphanumeric (got {name!r})")
        title = "".join(c for c in (display_title or name) if c not in '"\\\r\n')[:60]
        project_dir = Path(project_dir)
        base_deps = ["Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "GameplayAbilities", "GameplayTags"]
        deps = base_deps + [d for d in (module_deps or []) if d not in base_deps]
        plugin_list = [{"Name": "PythonScriptPlugin", "Enabled": True},
                       {"Name": "EditorScriptingUtilities", "Enabled": True}]
        for req_plugin in ("EnhancedInput", "GameplayAbilities", "Niagara"):
            if not any(p.get("Name") == req_plugin for p in plugin_list):
                plugin_list.append({"Name": req_plugin, "Enabled": True})
        if plugins:
            for p_item in plugins:
                p_name = p_item if isinstance(p_item, str) else p_item.get("Name", "")
                if p_name and not any(p.get("Name") == p_name for p in plugin_list):
                    plugin_list.append({"Name": p_name, "Enabled": True})

        # Plugin trimming for package size optimization (WI-10.2)
        trimmed = ["AlembicImporter", "GeometryCache", "SpeedTreeImporter", "DatasmithContent"]
        for t_p in trimmed:
            if not any(p.get("Name") == t_p for p in plugin_list):
                plugin_list.append({"Name": t_p, "Enabled": False})

        input_ini = ENHANCED_INPUT_INI if (module_deps and "EnhancedInput" in module_deps) else _LEGACY_INPUT_INI

        files: Dict[str, str] = {
            f"{name}.uproject": json.dumps({
                "FileVersion": 3, "EngineAssociation": self.engine_version().rsplit(".", 1)[0],
                "Category": "", "Description": f"{name} - generated by GameForge",
                "Modules": [{"Name": name, "Type": "Runtime", "LoadingPhase": "Default"}],
                "Plugins": plugin_list,
            }, indent="\t"),
            f"Source/{name}.Target.cs": _TARGET_CS.format(name=name, cls=f"{name}Target", type="Game", extra=""),
            f"Source/{name}Editor.Target.cs": _TARGET_CS.format(name=name, cls=f"{name}EditorTarget", type="Editor", extra=""),
            f"Source/{name}/{name}.Build.cs": _BUILD_CS.format(name=name, deps=", ".join(f'"{d}"' for d in deps)),
            f"Source/{name}/{name}.h": "#pragma once\n\n#include \"CoreMinimal.h\"\n",
            f"Source/{name}/{name}.cpp": (f"#include \"{name}.h\"\n#include \"Modules/ModuleManager.h\"\n\n"
                                          f"IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, {name}, \"{name}\");\n"),
            "Config/DefaultGame.ini": (f"[/Script/EngineSettings.GeneralProjectSettings]\nProjectName={name}\n"
                                       f"ProjectDisplayedTitle=NSLOCTEXT(\"[/Script/EngineSettings]\", "
                                       f"\"GameForgeTitle\", \"{title}\")\n\n"
                                       f"[/Script/GameForgeRuntime.GameForgeRuntimeSettings]\n"
                                       f"GameDefinition=/Game/GameForge/GD_Main.GD_Main\n\n"
                                       f"[/Script/UnrealEd.ProjectPackagingSettings]\n"
                                       f"+DirectoriesToAlwaysCook=(Path=\"/Game/Maps\")\n"
                                       f"+DirectoriesToAlwaysCook=(Path=\"/Game/Characters\")\n"
                                       f"+DirectoriesToAlwaysCook=(Path=\"/Game/LevelPrototyping\")\n"
                                       f"+DirectoriesToAlwaysCook=(Path=\"/Game/GameForge\")\n"),
            "Config/DefaultInput.ini": input_ini,
        }
        effective_map = default_map or "/Game/Maps/Level_1"
        engine_ini = ["[/Script/EngineSettings.GameMapsSettings]"]
        engine_ini += [f"GameDefaultMap={effective_map}", f"EditorStartupMap={effective_map}"]
        if game_mode:
            engine_ini.append(f"GlobalDefaultGameMode={game_mode}")
        engine_ini += ["", "[/Script/Engine.RendererSettings]",
                       "r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange=True",
                       "r.AllowStaticLighting=False",
                       "", "[/Script/WindowsTargetPlatform.WindowsTargetSettings]",
                       "DefaultGraphicsRHI=DefaultGraphicsRHI_DX12", ""]
        files["Config/DefaultEngine.ini"] = "\n".join(engine_ini)
        files.update(extra_files or {})
        written = []
        for rel, content in files.items():
            path = project_dir / rel
            if path.exists() and not overwrite_source and rel.startswith("Source/"):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(rel)

        # Deploy GameForge plugin if referenced in plugin_list
        if any(p.get("Name") == "GameForge" for p in plugin_list):
            self.deploy_gameforge_plugin(project_dir)

        return {"uproject": str(project_dir / f"{name}.uproject"), "files": written}

    def deploy_gameforge_plugin(self, project_dir: Path) -> Path:
        """Ensure GameForge plugin is deployed and synchronized into <project_dir>/Plugins/GameForge."""
        with self._DEPLOY_LOCK:
            project_dir = Path(project_dir)
            target = project_dir / "Plugins" / "GameForge"
            repo_plugin = Path(__file__).resolve().parent / "GameForge"

            # Candidates for full plugin with precompiled binaries
            candidates = [
                repo_plugin,
                Path(r"E:\GameForge\validation\P3_kittest_20261031\Plugins\GameForge"),
            ]
            try:
                from ..core.settings import get_settings
                s = get_settings()
                if s.plugin_build and s.plugin_build.is_dir() and s.plugin_build != repo_plugin:
                    candidates.append(s.plugin_build)
                if s.validation_root:
                    candidates.append(s.validation_root / "P3_kittest_20261031" / "Plugins" / "GameForge")
            except Exception:
                pass

            best_source = next((c for c in candidates if c.is_dir() and (c / "GameForge.uplugin").is_file()), None)

            # If target does not exist, do full initial deployment
            if not target.is_dir():
                if not best_source:
                    logger.warning("Could not find GameForge plugin source to deploy into %s", project_dir)
                    return target
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(best_source, target, dirs_exist_ok=True)
                logger.info("Deployed GameForge plugin from %s to %s", best_source, target)
                return target

            # Target exists: synchronize latest Python ops, C++ sources, config, uplugin, and binaries
            if repo_plugin.is_dir():
                # 1. Sync Python ops and scripts
                repo_python = repo_plugin / "Content" / "Python"
                if repo_python.is_dir():
                    target_python = target / "Content" / "Python"
                    target_python.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copytree(repo_python, target_python, dirs_exist_ok=True)
                    except Exception as exc:
                        logger.warning("Could not sync Python ops to %s: %s", target, exc)

                # 2. Sync C++ sources
                repo_source = repo_plugin / "Source"
                if repo_source.is_dir():
                    try:
                        shutil.copytree(repo_source, target / "Source", dirs_exist_ok=True)
                    except Exception as exc:
                        logger.warning("Could not sync C++ source to %s: %s", target, exc)

                # 3. Sync GameForge.uplugin descriptor
                repo_uplugin = repo_plugin / "GameForge.uplugin"
                if repo_uplugin.is_file():
                    try:
                        shutil.copy2(repo_uplugin, target / "GameForge.uplugin")
                    except Exception as exc:
                        logger.warning("Could not sync GameForge.uplugin to %s: %s", target, exc)

                # 4. Sync Config
                repo_cfg = repo_plugin / "Config"
                if repo_cfg.is_dir():
                    try:
                        shutil.copytree(repo_cfg, target / "Config", dirs_exist_ok=True)
                    except Exception as exc:
                        logger.warning("Could not sync plugin Config to %s: %s", target, exc)

            # 5. Sync Binaries from binary_source into target
            binary_source = next((c for c in candidates if c.is_dir() and (c / "Binaries" / "Win64").is_dir() and any((c / "Binaries" / "Win64").glob("*.dll"))), None)
            if not binary_source and best_source and (best_source / "Binaries" / "Win64").is_dir():
                binary_source = best_source

            if binary_source and (binary_source / "Binaries" / "Win64").is_dir():
                target_bin = target / "Binaries" / "Win64"
                target_bin.mkdir(parents=True, exist_ok=True)
                try:
                    src_bin = binary_source / "Binaries" / "Win64"
                    for src_item in src_bin.iterdir():
                        dst_item = target_bin / src_item.name
                        if not dst_item.exists() or src_item.stat().st_mtime > dst_item.stat().st_mtime:
                            if src_item.is_file():
                                shutil.copy2(src_item, dst_item)
                            elif src_item.is_dir():
                                shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                except Exception as exc:
                    logger.warning("Could not sync plugin Binaries to %s: %s", target, exc)

            return target

    # ── build ──────────────────────────────────────────────────────────────
    def build(self, uproject: Path, target: str, configuration: str = "Development", platform: str = "Win64",
              timeout_s: float = 3600, log_dir: Optional[Path] = None) -> StepResult:
        uproject = Path(uproject)
        # Ensure GameForge plugin exists if referenced in .uproject
        try:
            if uproject.is_file():
                uproj_data = json.loads(uproject.read_text(encoding="utf-8", errors="replace"))
                plugins = uproj_data.get("Plugins", [])
                if any(p.get("Name") == "GameForge" for p in plugins):
                    self.deploy_gameforge_plugin(uproject.parent)
        except Exception as exc:
            logger.warning("Could not check/deploy plugin before build: %s", exc)

        log = (log_dir or uproject.parent / "Saved" / "GameForge" / "logs") / f"build_{target}_{configuration}.log"
        argv = [str(self.ubt), target, platform, configuration, f"-Project={uproject}", "-WaitMutex",
                "-NoHotReloadFromIDE", "-FromMsBuild", "-NoUBA"]
        if self.max_parallel_actions:
            argv.append(f"-MaxParallelActions={self.max_parallel_actions}")
        res = self._run("build", argv, log, timeout_s)
        res.data = {"target": target, "configuration": configuration, "platform": platform}
        if not res.ok and not any(d.severity == "error" for d in res.diagnostics):
            res.errors.append("build failed without parseable diagnostics; see log")
        return res

    # ── automation tests ───────────────────────────────────────────────────
    def run_automation_tests(self, uproject: Path, test_filter: str, timeout_s: float = 1800,
                             report_dir: Optional[Path] = None) -> StepResult:
        uproject = Path(uproject)
        report_dir = Path(report_dir or uproject.parent / "Saved" / "GameForge" / "automation")
        if report_dir.exists():
            for f in report_dir.glob("*"):
                if f.is_file():
                    f.unlink()
        log = report_dir.parent / "logs" / "automation.log"
        argv = [str(self.editor_cmd), str(uproject), f"-ExecCmds=Automation RunTests {test_filter};Quit",
                "-unattended", "-nopause", "-nosplash", "-NullRHI", "-NoSound", "-stdout", "-FullStdOutLogOutput",
                f"-ReportExportPath={report_dir}", "-TestExit=Automation Test Queue Empty"]
        res = self._run("automation", argv, log, timeout_s)
        report = parse_automation_report(report_dir)
        res.data = {"filter": test_filter, "report_dir": str(report_dir), **report}
        res.diagnostics = [Diagnostic("error", "TEST", "; ".join(t["errors"]) or "failed", t["name"], None, "automation")
                           for t in report["tests"] if t["state"] != "Success"]
        res.ok = report["found"] and report["failed"] == 0 and report["succeeded"] > 0
        if not report["found"]:
            res.errors.append("no automation report written (tests did not run)")
        return res

    # ── package ────────────────────────────────────────────────────────────
    def package(self, uproject: Path, archive_dir: Path, configuration: str = "Development",
                platform: str = "Win64", timeout_s: float = 7200, profile: str = "default") -> StepResult:
        uproject = Path(uproject)
        # Ensure GameForge plugin exists and is synchronized before packaging
        try:
            if uproject.is_file():
                uproj_data = json.loads(uproject.read_text(encoding="utf-8", errors="replace"))
                plugins = uproj_data.get("Plugins", [])
                if any(p.get("Name") == "GameForge" for p in plugins):
                    self.deploy_gameforge_plugin(uproject.parent)
        except Exception as exc:
            logger.warning("Could not check/deploy plugin before package: %s", exc)

        # Ensure cooker always cooks map paths (+DirectoriesToAlwaysCook=(Path="/Game/Maps"))
        try:
            from ..content.epic_packs import update_default_game_ini_cook_dirs
            update_default_game_ini_cook_dirs(
                uproject.parent,
                ["/Game/Maps", "/Game/Characters", "/Game/LevelPrototyping", "/Game/GameForge"],
            )
        except Exception as exc:
            logger.warning("Could not update cook dirs in DefaultGame.ini: %s", exc)

        if profile == "release" or configuration == "Shipping":
            game_ini = uproject.parent / "Config" / "DefaultGame.ini"
            if game_ini.exists():
                text = game_ini.read_text(encoding="utf-8", errors="replace")
                if "PakFileCompressionFormats=Oodle" not in text:
                    oodle_lines = (
                        "BuildConfiguration=PPBC_Shipping\n"
                        "bCompressed=True\n"
                        "PakFileCompressionFormats=Oodle\n"
                        "bShareMaterialShaderCode=True\n"
                        "bSharedMaterialNativeLibraries=True\n"
                        "IncludePrerequisites=False\n"
                        "+DirectoriesToNeverCook=(Path=\"/Game/GameForge/Debug\")\n"
                    )
                    header = "[/Script/UnrealEd.ProjectPackagingSettings]"
                    if header in text:
                        text = text.replace(header, f"{header}\n{oodle_lines}")
                    else:
                        text = f"{text}\n\n{header}\n{oodle_lines}"
                    game_ini.write_text(text, encoding="utf-8")

        log = uproject.parent / "Saved" / "GameForge" / "logs" / f"package_{platform}_{configuration}.log"
        argv = [str(self.uat), "BuildCookRun", f"-project={uproject}", "-noP4", f"-platform={platform}",
                f"-clientconfig={configuration}", "-build", "-cook", "-stage", "-pak", "-archive",
                f"-archivedirectory={archive_dir}", "-unattended", "-utf8output", "-nocompileeditor",
                "-skipbuildeditor"]
        res = self._run("package", argv, log, timeout_s, cwd=self.engine_root / "Engine")
        name = uproject.stem
        exe = Path(archive_dir) / "Windows" / f"{name}.exe"
        res.data = {"archive_dir": str(archive_dir), "exe": str(exe), "exe_exists": exe.is_file()}
        if exe.is_file():
            res.data["archive_bytes"] = sum(f.stat().st_size for f in (Path(archive_dir) / "Windows").rglob("*") if f.is_file())
        res.ok = res.ok and exe.is_file()
        return res

    # ── world partition hlod builder ───────────────────────────────────────
    def build_world_partition_hlod(self, uproject: Path, timeout_s: float = 1800) -> StepResult:
        """Run World Partition HLOD builder commandlet."""
        uproject = Path(uproject)
        log = uproject.parent / "Saved" / "GameForge" / "logs" / "hlod_builder.log"
        argv = [
            str(self.editor_cmd),
            str(uproject),
            "-run=WorldPartitionBuilderCommandlet",
            "-Builder=WorldPartitionHLODsBuilder",
            "-AllowCommandletRendering",
            "-unattended",
            "-nopause",
            "-nosplash",
            "-NullRHI",
            "-stdout",
        ]
        return self._run("hlod_builder", argv, log, timeout_s)

    # ── packaged smoke test ────────────────────────────────────────────────
    def smoke_test_packaged(self, exe: Path, args: List[str], expect_log: str, timeout_s: float = 300,
                            log_path: Optional[Path] = None) -> StepResult:
        """Launch a packaged game, wait for it to exit, require exit 0 and an expected log line."""
        exe = Path(exe)
        log_path = Path(log_path or exe.parent / "GameForgeSmoke.log")
        argv = [str(exe)] + list(args) + [f"-abslog={log_path}", "-unattended", "-nosplash", "-NoSound"]
        cmd = format_unreal_cmd(argv)
        started = time.monotonic()
        try:
            proc = jobs.spawn(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=NO_WINDOW)
            code = self._wait(proc, timeout_s)
        except TimeoutError:
            return StepResult(False, "smoke", None, round(time.monotonic() - started, 1), str(log_path),
                              errors=[f"packaged game did not exit within {timeout_s}s"])
        except InterruptedError:
            return StepResult(False, "smoke", None, round(time.monotonic() - started, 1), str(log_path),
                              errors=["CANCELLED"])
        except OSError as exc:
            return StepResult(False, "smoke", None, 0.0, str(log_path), errors=[f"launch failed: {exc}"])
        text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        found = [l.strip() for l in text.splitlines() if expect_log in l]
        res = StepResult(code == 0 and bool(found), "smoke", code, round(time.monotonic() - started, 1), str(log_path))
        res.data = {"expect": expect_log, "matched_lines": found[-5:]}
        if not found:
            res.errors.append(f"expected log line not found: {expect_log}")
        return res


_TARGET_CS = """using UnrealBuildTool;
using System.Collections.Generic;

public class {cls} : TargetRules
{{
	public {cls}(TargetInfo Target) : base(Target)
	{{
		Type = TargetType.{type};
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		bUseAdaptiveUnityBuild = false;
		ExtraModuleNames.Add("{name}");{extra}
	}}
}}
"""

_BUILD_CS = """using UnrealBuildTool;

public class {name} : ModuleRules
{{
	public {name}(ReadOnlyTargetRules Target) : base(Target)
	{{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] {{ {deps} }});
	}}
}}
"""
