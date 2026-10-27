"""Unreal toolchain: scaffold, build, test, package, smoke-test (Master Blueprint v2, WP2).

Everything here runs real engine executables of the pinned install and returns structured
results with exit codes, durations, parsed diagnostics and log paths. Nothing is simulated.

Executables are invoked directly (UnrealBuildTool.exe, AutomationTool.exe, UnrealEditor-Cmd.exe)
with argv lists and no shell. Builds run at below-normal priority so the IDE stays responsive.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

BELOW_NORMAL = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_IDENT = re.compile(r"^[A-Z][A-Za-z0-9]{1,30}$")


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


# ── toolchain ───────────────────────────────────────────────────────────────

class UnrealToolchain:
    def __init__(self, engine_root: Path = Path(r"E:\UE\UE_5.7"), max_parallel_actions: Optional[int] = None):
        self.engine_root = Path(engine_root)
        e = self.engine_root / "Engine"
        self.ubt = e / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
        self.uat = e / "Binaries" / "DotNET" / "AutomationTool" / "AutomationTool.exe"
        self.editor_cmd = e / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
        self.max_parallel_actions = max_parallel_actions
        self.cancel_event = None  # threading.Event set by the UI to cancel the running step

    @staticmethod
    def kill_tree(proc: subprocess.Popen) -> None:
        """Kill a process and all its descendants (UBT/UAT/packaged bootstrappers spawn children)."""
        try:
            import psutil
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            parent.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=30)
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
        v = json.loads((self.engine_root / "Engine" / "Build" / "Build.version").read_text(encoding="utf-8"))
        return f'{v["MajorVersion"]}.{v["MinorVersion"]}.{v["PatchVersion"]}'

    # ── process helper ─────────────────────────────────────────────────────
    def _run(self, step: str, argv: List[str], log_path: Path, timeout_s: float,
             cwd: Optional[Path] = None) -> StepResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                log.write("ARGV: " + json.dumps(argv) + "\n")
                log.flush()
                proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None,
                                        creationflags=BELOW_NORMAL | NO_WINDOW)
                try:
                    code = self._wait(proc, timeout_s)
                except (TimeoutError, InterruptedError) as exc:
                    return StepResult(False, step, None, round(time.monotonic() - started, 1), str(log_path),
                                      errors=[str(exc)])
        except OSError as exc:
            return StepResult(False, step, None, 0.0, str(log_path), errors=[f"launch failed: {exc}"])
        text = log_path.read_text(encoding="utf-8", errors="replace")
        diags = parse_build_diagnostics(text)
        return StepResult(code == 0, step, code, round(time.monotonic() - started, 1), str(log_path), diags)

    # ── scaffold ───────────────────────────────────────────────────────────
    def scaffold_cpp_project(self, project_dir: Path, name: str, extra_files: Optional[Dict[str, str]] = None,
                             default_map: Optional[str] = None, game_mode: Optional[str] = None,
                             module_deps: Optional[List[str]] = None, overwrite_source: bool = True,
                             display_title: Optional[str] = None) -> Dict:
        """Write a minimal, valid UE C++ project. Returns the files written."""
        if not _IDENT.match(name):
            raise ValueError(f"project name must be PascalCase alphanumeric (got {name!r})")
        title = "".join(c for c in (display_title or name) if c not in '"\\\r\n')[:60]
        project_dir = Path(project_dir)
        deps = ["Core", "CoreUObject", "Engine", "InputCore"] + [d for d in (module_deps or []) if d not in
                                                                  ("Core", "CoreUObject", "Engine", "InputCore")]
        files: Dict[str, str] = {
            f"{name}.uproject": json.dumps({
                "FileVersion": 3, "EngineAssociation": self.engine_version().rsplit(".", 1)[0],
                "Category": "", "Description": f"{name} - generated by GameForge",
                "Modules": [{"Name": name, "Type": "Runtime", "LoadingPhase": "Default"}],
                "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True},
                            {"Name": "EditorScriptingUtilities", "Enabled": True}],
            }, indent="\t"),
            f"Source/{name}.Target.cs": _TARGET_CS.format(name=name, cls=f"{name}Target", type="Game", extra=""),
            f"Source/{name}Editor.Target.cs": _TARGET_CS.format(name=name, cls=f"{name}EditorTarget", type="Editor", extra=""),
            f"Source/{name}/{name}.Build.cs": _BUILD_CS.format(name=name, deps=", ".join(f'"{d}"' for d in deps)),
            f"Source/{name}/{name}.h": "#pragma once\n\n#include \"CoreMinimal.h\"\n",
            f"Source/{name}/{name}.cpp": (f"#include \"{name}.h\"\n#include \"Modules/ModuleManager.h\"\n\n"
                                          f"IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, {name}, \"{name}\");\n"),
            "Config/DefaultGame.ini": (f"[/Script/EngineSettings.GeneralProjectSettings]\nProjectName={name}\n"
                                       f"ProjectDisplayedTitle=NSLOCTEXT(\"[/Script/EngineSettings]\", "
                                       f"\"GameForgeTitle\", \"{title}\")\n"),
        }
        engine_ini = ["[/Script/EngineSettings.GameMapsSettings]"]
        if default_map:
            engine_ini += [f"GameDefaultMap={default_map}", f"EditorStartupMap={default_map}"]
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
        return {"uproject": str(project_dir / f"{name}.uproject"), "files": written}

    # ── build ──────────────────────────────────────────────────────────────
    def build(self, uproject: Path, target: str, configuration: str = "Development", platform: str = "Win64",
              timeout_s: float = 3600, log_dir: Optional[Path] = None) -> StepResult:
        uproject = Path(uproject)
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
                platform: str = "Win64", timeout_s: float = 7200) -> StepResult:
        uproject = Path(uproject)
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

    # ── packaged smoke test ────────────────────────────────────────────────
    def smoke_test_packaged(self, exe: Path, args: List[str], expect_log: str, timeout_s: float = 300,
                            log_path: Optional[Path] = None) -> StepResult:
        """Launch a packaged game, wait for it to exit, require exit 0 and an expected log line."""
        exe = Path(exe)
        log_path = Path(log_path or exe.parent / "GameForgeSmoke.log")
        argv = [str(exe)] + list(args) + [f"-abslog={log_path}", "-unattended", "-nosplash", "-NoSound"]
        started = time.monotonic()
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
