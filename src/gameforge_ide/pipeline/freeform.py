"""Free-form game pipeline: any game request, no recipe required (Master Blueprint v2 §3, §7).

Stages (fail closed, each with evidence):
  design -> scaffold -> framework -> author -> build_repair -> assemble_level
         -> package -> packaged_smoke (with self-test repair) -> report

Repair ladder (bounded): compiler diagnostics -> model fixes the files (<= BUILD_REPAIRS);
packaged self-test failure / runtime errors -> model fixes the files, rebuild, repackage
(<= RUNTIME_REPAIRS). Exhaustion ends FAILED with the last diagnostics; never a fake success.

Resumable: a stage whose inputs hash is unchanged and whose evidence still exists is skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..legacy_recipes.freeform_host.framework import api_doc, framework_sources, reference_impl
from ..unreal.toolchain import UnrealToolchain
from . import stages
from .authoring import ModelAuthor, parse_files, safety_scan
from .autofix import autofix, hints_for
from .vision_review import review_screenshot
from ..core.settings import engine_root_or_missing

BUILD_REPAIRS = 5
RUNTIME_REPAIRS = 3
FREEFORM_STAGES = ["design", "scaffold", "framework", "author", "build_repair", "assemble_level", "package",
                   "packaged_smoke", "quality_review"]
QUALITY_ROUNDS = 1

_STOP = {"in", "with", "for", "using", "on", "that", "where", "which", "unreal", "engine", "ue5", "ue"}


def derive_title(prompt: str) -> str:
    m = re.search(r"\b(?:called|named|titled)\s+[\"']?([A-Za-z][A-Za-z0-9 \-]{1,40}?)[\"']?(?:\s+(?:with|in|for|that|where)\b|[.,!]|$)", prompt, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(?:create|make|build|generate|develop|design|write)\s+(?:me\s+)?(?:an?\s+|the\s+)?(.+?)\s+game\b", prompt, re.I)
    words = []
    if m:
        for w in re.findall(r"[A-Za-z0-9\-]+", m.group(1)):
            if w.lower() in _STOP:
                break
            words.append(w)
    title = " ".join(words[:5]).replace("-", " ").title() or "My Game"
    return title


def pascal(title: str) -> str:
    out = "".join(p[:1].upper() + p[1:] for p in re.findall(r"[A-Za-z0-9]+", title))
    if not out or not out[0].isalpha():
        out = "Game" + out
    return out[:30]


@dataclass
class FFStage:
    stage: str
    ok: bool
    duration_s: float = 0.0
    data: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    skipped: bool = False


SYSTEM = ("You are an expert Unreal Engine 5.7 C++ gameplay programmer. You write complete, compilable code "
          "against the exact API you are given. You never invent engine functions.")


class FreeformGamePipeline:
    def __init__(self, workspace_root: Path, projects_root: Path, engine_root: Optional[Path] = None,
                 on_event: Optional[Callable[[str, Dict], None]] = None, use_reference_impl: bool = False,
                 local_model: Optional[str] = None, resume: bool = False, cancel_event=None):
        self.workspace_root = Path(workspace_root)
        self.projects_root = Path(projects_root)
        self.engine_root = Path(engine_root or engine_root_or_missing())
        self.toolchain = UnrealToolchain(self.engine_root, max_parallel_actions=max(2, (os.cpu_count() or 4) - 2))
        self.on_event = on_event or (lambda k, d: None)
        self.use_reference_impl = use_reference_impl
        self.local_model = local_model
        self.cancel_event = cancel_event
        self.toolchain.cancel_event = cancel_event
        self.resume = resume  # keep existing model-written files that still pass the safety scan

    def _emit(self, kind: str, **data) -> None:
        try:
            self.on_event(kind, data)
        except Exception:
            pass

    # ── helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _files_block(files: Dict[str, str]) -> str:
        return "\n".join(f"=== FILE: {k} ===\n{v.rstrip()}\n=== END FILE ===" for k, v in files.items())

    def _write_impl(self, src_dir: Path, files: Dict[str, str]) -> None:
        for name, content in files.items():
            dest = src_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")

    def _read_impl(self, src_dir: Path) -> Dict[str, str]:
        files = {n: (src_dir / n).read_text(encoding="utf-8") for n in ("GFGameImpl.h", "GFGameImpl.cpp")
                 if (src_dir / n).exists()}
        if src_dir.is_dir():
            for p in src_dir.rglob("*"):
                if p.is_file() and p.suffix in (".h", ".cpp"):
                    rel = p.relative_to(src_dir).as_posix()
                    if rel not in files:
                        try:
                            files[rel] = p.read_text(encoding="utf-8")
                        except Exception:
                            pass
        return files

    @staticmethod
    def _diag_context(src_dir: Path, diags: List[Dict], limit: int = 12) -> str:
        lines = []
        for d in diags[:limit]:
            loc = Path(d.get("file") or "").name
            lines.append(f"- {d['severity']} {d['code']} {loc}:{d.get('line')}: {d['message']}")
            f = Path(d.get("file") or "")
            if f.name.startswith("GFGameImpl") and f.exists() and d.get("line"):
                src = f.read_text(encoding="utf-8", errors="replace").splitlines()
                i = int(d["line"]) - 1
                for j in range(max(0, i - 2), min(len(src), i + 3)):
                    lines.append(f"    {j + 1:4d}{'>' if j == i else ' '} {src[j]}")
        return "\n".join(lines)

    # ── run ────────────────────────────────────────────────────────────────
    def run(self, prompt: str, title: Optional[str] = None) -> Dict:
        title = title or derive_title(prompt)
        name = pascal(title)
        project_dir = self.projects_root / name
        uproject = project_dir / f"{name}.uproject"
        src_dir = project_dir / "Source" / name
        evidence = project_dir / "Saved" / "GameForge"
        evidence.mkdir(parents=True, exist_ok=True)
        author = None if self.use_reference_impl else ModelAuthor(
            self.workspace_root, evidence / "authoring", local_model=self.local_model or "gameforge-qwen3.5-9b:latest")
        results: List[FFStage] = []
        ctx: Dict = {"design": ""}
        state_file = evidence / "freeform_state.json"
        prev = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}

        def run_stage(stage: str, fn: Callable[[], FFStage]) -> bool:
            if self.cancel_event is not None and self.cancel_event.is_set():
                results.append(FFStage(stage, False, errors=["CANCELLED by user"]))
                self._emit("stage_finished", stage=stage, ok=False, duration_s=0.0, errors=["CANCELLED by user"])
                return False
            self._emit("stage_started", stage=stage)
            t0 = time.monotonic()
            try:
                rec = fn()
            except Exception as exc:
                rec = FFStage(stage, False, errors=[f"{type(exc).__name__}: {exc}"])
            rec.duration_s = round(time.monotonic() - t0, 1)
            results.append(rec)
            self._emit("stage_finished", stage=stage, ok=rec.ok, duration_s=rec.duration_s, errors=rec.errors[:3],
                       skipped=rec.skipped)
            return rec.ok

        def finish(failed: Optional[str]) -> Dict:
            payload = {"ok": failed is None, "failed_stage": failed, "prompt": prompt, "title": title,
                       "project_dir": str(project_dir), "author": author.describe() if author else "reference_impl",
                       "model_calls": author.calls if author else 0,
                       "engine_version": self.toolchain.engine_version(),
                       "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "stages": [r.__dict__ for r in results]}
            md = [f"# GameForge free-form report — {title}", "", f"- Prompt: {prompt}",
                  f"- Result: **{'PASS' if failed is None else 'FAIL at ' + failed}**",
                  f"- Author: {payload['author']} ({payload['model_calls']} model calls)", "",
                  "| Stage | Result | Time (s) | Notes |", "|---|---|---|---|"]
            for r in results:
                note = "; ".join(r.errors)[:200] if r.errors else ("skipped (evidence unchanged)" if r.skipped else "")
                if r.stage == "build_repair":
                    note = f"attempts {r.data.get('attempts')}; " + note
                md.append(f"| {r.stage} | {'PASS' if r.ok else 'FAIL'} | {r.duration_s} | {note} |")
            report = stages.write_report(evidence, payload, "\n".join(md) + "\n")
            impl = self._read_impl(src_dir)
            state_file.write_text(json.dumps({"impl_hash": hashlib.sha256(json.dumps(impl, sort_keys=True).encode()).hexdigest(),
                                              "passed": [r.stage for r in results if r.ok]}), encoding="utf-8")
            out = {"status": "SUCCESS" if failed is None else "FAILED", **payload, "report_path": str(report)}
            exe = project_dir / "Packaged" / "Windows" / f"{name}.exe"
            if failed is None and exe.exists():
                out["exe"] = str(exe)
            self._emit("pipeline_finished", ok=failed is None, report=str(report), failed_stage=failed)
            return out

        # design
        def s_design():
            if self.resume and len(self._read_impl(src_dir)) == 2:
                return FFStage("design", True, data={"reused": True}, skipped=True)
            if author is None:
                ctx["design"] = "Reference game: click all nine cubes."
                return FFStage("design", True, data={"design": ctx["design"]})
            text = author.complete(SYSTEM, [{"role": "user", "content": (
                f"Game request: {prompt}\n\nThe game will be built with this framework:\n{api_doc(name)}\n"
                "Write a structured game design (max 250 words): core mechanics and state machine, controls "
                "(mouse clicks and/or keyboard input), visual scene layout using SpawnShape/SpawnProp/SpawnText, "
                "camera perspective (GetCameraFocus/Distance/Pitch/Yaw), primary and secondary HUD readouts, "
                "score/win/lose conditions, and the exact assertions RunSelfTest will verify.")}], "design", 1024)
            ctx["design"] = text.strip()
            return FFStage("design", bool(ctx["design"]), data={"design": ctx["design"][:2000]})

        def s_scaffold():
            info = self.toolchain.scaffold_cpp_project(project_dir, name, default_map=f"/Game/Maps/{name}Map",
                                                       game_mode=f"/Script/{name}.GFHostGameMode",
                                                       overwrite_source=False, display_title=title)
            return FFStage("scaffold", uproject.is_file(), data=info)

        def s_framework():
            for rel, content in framework_sources(name, title).items():
                p = project_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8", newline="\n")
            return FFStage("framework", True, data={"files": sorted(framework_sources(name, title))})

        def s_author():
            if author is None:
                files = {Path(k).name: v for k, v in reference_impl(name).items()}
            else:
                existing = self._read_impl(src_dir)
                if self.resume and len(existing) == 2 and not safety_scan(existing):
                    return FFStage("author", True, data={"reused": True, "reason": "resume"}, skipped=True)
                if prev.get("impl_hash") and existing and "author" in prev.get("passed", []) and \
                        hashlib.sha256(json.dumps(existing, sort_keys=True).encode()).hexdigest() == prev["impl_hash"]:
                    return FFStage("author", True, data={"reused": True}, skipped=True)
                files = {}
                issues: List[str] = []
                for attempt in range(3):
                    msg = (f"Game request: {prompt}\n\nDesign:\n{ctx['design']}\n\nFramework contract:\n{api_doc(name)}\n"
                           "Now write the complete GFGameImpl.h and GFGameImpl.cpp. Output ONLY the two files in this "
                           "exact format, with no other text:\n=== FILE: GFGameImpl.h ===\n<code>\n=== END FILE ===\n"
                           "=== FILE: GFGameImpl.cpp ===\n<code>\n=== END FILE ===")
                    if issues:
                        msg += "\n\nYour previous answer was rejected:\n- " + "\n- ".join(issues)
                    files = parse_files(author.complete(SYSTEM, [{"role": "user", "content": msg}], f"author_{attempt}"))
                    issues = [] if len(files) == 2 else ["output must contain both files in the required format"]
                    issues += safety_scan(files) if files else []
                    if not issues:
                        break
                if issues:
                    return FFStage("author", False, errors=issues)
            self._write_impl(src_dir, files)
            return FFStage("author", True, data={"files": sorted(files), "lines": sum(v.count("\n") for v in files.values())})

        def build_ladder(label: str, budget: int):
            """Compile; on errors apply rung 1 (deterministic autofix) then rung 2 (model + hints)."""
            attempts = []
            r = None
            diags: List[Dict] = []
            for attempt in range(budget + 1):
                if self.cancel_event is not None and self.cancel_event.is_set():
                    break
                r = self.toolchain.build(uproject, f"{name}Editor")
                diags = [d.__dict__ for d in r.diagnostics if d.severity == "error"]
                attempts.append({"attempt": attempt, "ok": r.ok, "errors": len(diags), "seconds": r.duration_s})
                self._emit("build_attempt", attempt=attempt, ok=r.ok, errors=len(diags))
                if r.ok:
                    return True, attempts, r, []
                if author is None or attempt == budget:
                    break
                current = self._read_impl(src_dir)
                fixed_files, notes = autofix(current, diags=diags)
                if notes and fixed_files != current and not safety_scan(fixed_files):
                    self._write_impl(src_dir, fixed_files)
                    attempts[-1]["repair"] = "autofix: " + "; ".join(notes)
                    self._emit("autofix", notes=notes)
                    continue
                hints = hints_for(diags)
                fixed = self._repair(author, src_dir, name, ctx, "The build failed. Compiler diagnostics:\n"
                                     + self._diag_context(src_dir, diags)
                                     + (f"\n\nHow to fix these error codes:\n{hints}" if hints else ""),
                                     f"{label}_{attempt}")
                attempts[-1]["repair"] = "model" if fixed else "model returned no usable files"
            return False, attempts, r, diags

        def s_build_repair():
            ok, attempts, r, diags = build_ladder("build_fix", BUILD_REPAIRS)
            data = {"attempts": len(attempts), "history": attempts, "log": r.log_path if r else None}
            if ok:
                return FFStage("build_repair", True, data=data)
            data["diagnostics"] = diags[:15]
            return FFStage("build_repair", False, data=data,
                           errors=[f"{d['code']} {Path(d.get('file') or '').name}:{d.get('line')} {d['message']}"
                                   for d in diags[:5]] or (r.errors if r else ["build failed"]))

        def s_assemble():
            # One heavy GPU workload at a time: free local-LLM VRAM before the editor renders.
            from ..backend.tools.game_tools import GameTools
            freed = GameTools.release_llm_vram()
            ok, data, errors = stages.assemble_level(self.engine_root, uproject, evidence, name, 1200.0)
            data["unloaded_models"] = freed
            return FFStage("assemble_level", ok, data=data, errors=errors)

        def s_package_and_smoke():
            history = []
            for attempt in range(RUNTIME_REPAIRS + 1):
                pok, pdata, perr = stages.package(self.toolchain, uproject)
                if not pok:
                    history.append({"attempt": attempt, "stage": "package", "errors": perr[:3]})
                    return FFStage("package", False, data={"history": history, **pdata}, errors=perr or ["package failed"])
                results.append(FFStage("package", True, data=pdata))
                sok, sdata, serr = stages.packaged_smoke(self.toolchain, Path(pdata["exe"]), evidence, name)
                lines = sdata.get("selftest_lines") or []
                logic_passed = any("GF_SELFTEST PASS" in l for l in lines)
                history.append({"attempt": attempt, "stage": "smoke", "ok": sok, "logic_passed": logic_passed,
                                "selftest": lines, "screenshot": sdata.get("screenshot_content")})
                if sok:
                    return FFStage("packaged_smoke", True, data={"history": history, **sdata})
                if author is None or attempt == RUNTIME_REPAIRS:
                    return FFStage("packaged_smoke", False, data={"history": history, **sdata}, errors=serr)
                if logic_passed:
                    feedback = (
                        "The game's self-test PASSED, but the gameplay screenshot shows nothing (black or empty "
                        f"frame; stats {sdata.get('screenshot_content')}). Keep the game logic and RunSelfTest as they "
                        "are; fix only what the player sees: StartGame() must spawn visible shapes near the floor "
                        "(Z between 0 and 300) inside the camera view; SpawnShape scale is a multiplier where "
                        "FVector(1.f) is 100 cm; GetCameraFocus() must be the centre of the play area, "
                        "GetCameraDistance() about 1.5x the play-area width (800-2500), GetCameraPitch() between "
                        "-80 and -40 (negative looks down).")
                else:
                    feedback = (
                        "The packaged game ran its self-test and it did not pass.\n"
                        f"Self-test log: {lines}\nRuntime errors: {sdata.get('game_errors')}\n"
                        "Fix the game logic or the self-test so the rules are genuinely correct and RunSelfTest "
                        "verifies them. Do not make RunSelfTest return true unconditionally.\n"
                        "Read the failing check literally and change the code it points at. Common causes: "
                        "StartGame() does not first Empty() every member array/map and reset every counter "
                        "(RestartGame destroys all shapes and calls StartGame); state is read before it is set; "
                        "the self-test expects timing - drive time with OnTick(0.1f) loops instead.")
                if len(history) >= 2 and history[-1].get("selftest") == history[-2].get("selftest") \
                        and history[-1].get("logic_passed") == history[-2].get("logic_passed"):
                    feedback += "\nYour previous fix did not change the result. Make a different, concrete change."
                self._repair(author, src_dir, name, ctx, feedback, f"runtime_fix_{attempt}")
                ok, att, r, diags = build_ladder(f"runtime{attempt}_build_fix", 3)
                history[-1]["rebuild"] = {"ok": ok, "attempts": len(att)}
                if not ok:
                    return FFStage("packaged_smoke", False, data={"history": history},
                                   errors=["runtime repair left the build broken: " + "; ".join(
                                       d["message"] for d in diags[:3])[:300]])
            return FFStage("packaged_smoke", False, errors=["unreachable"])

        def s_quality():
            """Advisory vision review; may run QUALITY_ROUNDS improvement rounds that must keep every gate green."""
            last = next((r for r in reversed(results) if r.stage == "packaged_smoke" and r.ok), None)
            shot = (last.data.get("screenshot") if last else None)
            if author is None or not shot:
                return FFStage("quality_review", True, data={"skipped": "no model author or no screenshot"}, skipped=True)
            facts = f"shapes alive={last.data.get('scene_shapes')}; self-test: {(last.data.get('selftest_lines') or [''])[-1][-200:]}"
            rounds = []
            verdict = review_screenshot(Path(shot), prompt, ctx.get("design", ""), facts)
            rounds.append({"round": 0, "verdict": verdict})
            for q in range(QUALITY_ROUNDS):
                if not verdict.get("available") or verdict.get("matches_request") is not False:
                    break
                snapshot = self._read_impl(src_dir)
                feedback = ("The game builds, passes its self-test and runs, but a QA reviewer looked at the gameplay "
                            f"screenshot and reported: problems={verdict['problems']} suggestions={verdict['suggestions']}. "
                            f"Objective scene facts at capture time: {facts}. Improve what the player sees and the "
                            "pacing (sensible number, size and placement of objects; clear feedback) while keeping the "
                            "rules correct and RunSelfTest passing. Add a self-test check for the issue you fix.")
                self._repair(author, src_dir, name, ctx, feedback, f"quality_fix_{q}")
                ok, att, _r, _d = build_ladder(f"quality{q}_build_fix", 3)
                kept = False
                if ok:
                    pok, pdata, _ = stages.package(self.toolchain, uproject)
                    if pok:
                        sok, sdata, _ = stages.packaged_smoke(self.toolchain, Path(pdata["exe"]), evidence, name)
                        if sok:
                            kept = True
                            shot = sdata.get("screenshot")
                            facts = f"shapes alive={sdata.get('scene_shapes')}; self-test: {(sdata.get('selftest_lines') or [''])[-1][-200:]}"
                            verdict = review_screenshot(Path(shot), prompt, ctx.get("design", ""), facts)
                if not kept:
                    # Improvement broke a hard gate: restore the last passing version and rebuild it.
                    self._write_impl(src_dir, snapshot)
                    ok2, _a, _r2, _d2 = build_ladder(f"quality{q}_restore", 0)
                    pok2, pdata2, _ = stages.package(self.toolchain, uproject) if ok2 else (False, {}, [])
                    sok2 = stages.packaged_smoke(self.toolchain, Path(pdata2["exe"]), evidence, name)[0] if pok2 else False
                    rounds.append({"round": q + 1, "kept": False, "restored_passing_build": bool(sok2)})
                    if not sok2:
                        return FFStage("quality_review", False, data={"rounds": rounds},
                                       errors=["could not restore the last passing build after a quality round"])
                    break
                rounds.append({"round": q + 1, "kept": True, "verdict": verdict})
            final = verdict.get("matches_request")
            return FFStage("quality_review", True, data={"rounds": rounds, "final_verdict": final,
                                                         "advisory": True, "screenshot": shot},
                           errors=[] if final is not False else
                           ["advisory: reviewer still reports issues: " + "; ".join(verdict.get("problems", [])[:3])])

        plan = [("design", s_design), ("scaffold", s_scaffold), ("framework", s_framework), ("author", s_author),
                ("build_repair", s_build_repair), ("assemble_level", s_assemble)]
        for stage_name, fn in plan:
            if not run_stage(stage_name, fn):
                return finish(stage_name)
        if not run_stage("packaged_smoke", s_package_and_smoke):
            return finish("packaged_smoke")
        if not run_stage("quality_review", s_quality):
            return finish("quality_review")
        return finish(None)

    def _repair(self, author: ModelAuthor, src_dir: Path, name: str, ctx: Dict, problem: str, label: str) -> bool:
        current = self._read_impl(src_dir)
        msg = (f"{problem}\n\nCurrent files:\n{self._files_block(current)}\n\nFramework contract (unchanged, do not "
               f"redefine it):\n{api_doc(name)}\nReturn the COMPLETE corrected GFGameImpl.h and GFGameImpl.cpp in the "
               "exact '=== FILE: name === ... === END FILE ===' format and nothing else.")
        files = parse_files(author.complete(SYSTEM, [{"role": "user", "content": msg}], label))
        if len(files) != 2 or safety_scan(files):
            return False
        self._write_impl(src_dir, files)
        return True
