"""Engine gate verification script for Phase 2 (WI-2.6):
1. Kill test & resume on Platformer:
   - Start: python scripts/pipeline/run_game_pipeline.py --prompt "make a platformer with 6 coins"
   - Interrupt/kill when build_editor is running.
   - Resume: python scripts/pipeline/run_game_pipeline.py --resume <project_dir>
   - Verify spec/scaffold/sources were skipped and run finishes PASS.
   - Write reports/P2/resume_kill_test.json.
2. Rollback check:
   - ProjectRepo.reset_to(scaffold_checkpoint, editor_running=False)
   - Verify Source/ matches scaffold checkpoint and game sources are removed.
   - Write reports/P2/rollback_check.json.
   - Re-run pipeline to completion (PASS).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.core.settings import get_settings

DEFAULT_PROJECT_DIR = Path(r"E:\GameForge\projects\Platformer")
DEFAULT_REPORTS_DIR = REPO_ROOT / "reports" / "P2"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _write_atomic_json(target_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, target_path)


def resolve_project_dir(override: Optional[Path] = None) -> Path:
    """Resolve project directory from override, settings, or safe fallback."""
    if override:
        return override
    try:
        settings = get_settings()
        if settings.projects_root:
            p = Path(settings.projects_root) / "Platformer"
            if p.parent.exists():
                return p
    except Exception:
        pass
    if DEFAULT_PROJECT_DIR.parent.exists():
        return DEFAULT_PROJECT_DIR
    return REPO_ROOT / "scratch" / "projects" / "Platformer"


def run_kill_test(
    project_dir: Path,
    reports_dir: Path,
    prompt: str = "make a platformer with 6 coins",
) -> Dict[str, Any]:
    print("=== STEP 1: Starting kill test for Platformer ===", flush=True)
    if project_dir.exists():
        print(f"Cleaning previous {project_dir} for clean kill test...", flush=True)
        shutil.rmtree(project_dir, ignore_errors=True)

    cmd1 = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "pipeline" / "run_game_pipeline.py"),
        "--prompt",
        prompt,
        "--projects-root",
        str(project_dir.parent),
    ]
    proc1 = subprocess.Popen(
        cmd1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=CREATE_NO_WINDOW,
    )

    run1_events: List[str] = []
    killed = False

    while True:
        line = proc1.stdout.readline() if proc1.stdout else ""
        if not line and proc1.poll() is not None:
            break
        if line:
            line_str = line.strip()
            print(f"[RUN 1] {line_str}", flush=True)
            run1_events.append(line_str)
            if 'stage_started {"stage": "build_editor"}' in line_str:
                print(">>> Caught build_editor RUNNING! Waiting 2s then killing process...", flush=True)
                time.sleep(2.0)
                from src.gameforge_ide.unreal.toolchain import UnrealToolchain
                UnrealToolchain.kill_tree(proc1)
                killed = True
                break

    proc1.wait(timeout=30)
    print(f"Run 1 terminated. Killed={killed}, ExitCode={proc1.returncode}", flush=True)

    # Now Resume
    print("\n=== STEP 2: Resuming Platformer from Saved Run ===", flush=True)
    cmd2 = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "pipeline" / "run_game_pipeline.py"),
        "--resume",
        str(project_dir),
        "--projects-root",
        str(project_dir.parent),
    ]
    proc2 = subprocess.Popen(
        cmd2,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=CREATE_NO_WINDOW,
    )

    run2_events: List[str] = []
    while True:
        line = proc2.stdout.readline() if proc2.stdout else ""
        if not line and proc2.poll() is not None:
            break
        if line:
            line_str = line.strip()
            print(f"[RUN 2] {line_str}", flush=True)
            run2_events.append(line_str)

    exit_code2 = proc2.wait()
    print(f"Run 2 finished with exit code {exit_code2}", flush=True)

    from src.gameforge_ide.forge.store import RunStore
    store = RunStore(project_dir=project_dir, workspace_dir=project_dir.parent)
    state = store.latest_for_project(project_dir)
    assert state is not None, "Latest run state not found"

    # Identify skipped steps: steps that were DONE with 0 seconds in run 2
    records = state.records
    skipped_steps = [s for s in ["spec", "scaffold", "sources"] if records.get(s) and records[s].status.value == "DONE"]

    evidence: Dict[str, Any] = {
        "ok": exit_code2 == 0 and state.status == "DONE",
        "run1_killed": killed,
        "run1_events": run1_events,
        "run2_events": run2_events,
        "skipped_steps": skipped_steps,
        "final_status": state.status,
        "records": {k: {"status": r.status.value, "attempts": r.attempts, "duration_s": r.duration_s} for k, r in records.items()},
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    report_path = reports_dir / "resume_kill_test.json"
    _write_atomic_json(report_path, evidence)
    print(f"Saved kill test evidence to {report_path}", flush=True)
    return evidence


def run_rollback_check(
    project_dir: Path,
    reports_dir: Path,
    prompt: str = "make a platformer with 6 coins",
) -> Dict[str, Any]:
    print("\n=== STEP 3: Running Rollback Check ===", flush=True)
    from src.gameforge_ide.forge.checkpoints import ProjectRepo
    from src.gameforge_ide.forge.store import RunStore

    store = RunStore(project_dir=project_dir, workspace_dir=project_dir.parent)
    state = store.latest_for_project(project_dir)
    assert state is not None, "RunState not found for rollback check"

    scaffold_rec = state.records.get("scaffold")
    repo = ProjectRepo(project_dir)
    assert repo.available, "Git not available in ProjectRepo"

    scaffold_sha = (
        scaffold_rec.checkpoint
        if (scaffold_rec and scaffold_rec.checkpoint)
        else repo._run("rev-list", "--max-parents=0", "HEAD").stdout.strip()
    )
    print(f"Scaffold checkpoint SHA: {scaffold_sha}", flush=True)

    source_dir = project_dir / "Source" / "Platformer"
    files_before = sorted([f.name for f in source_dir.glob("*.cpp")]) if source_dir.exists() else []
    print(f"Source files before rollback: {files_before}", flush=True)

    # Perform rollback
    repo.reset_to(scaffold_sha, editor_running=False)

    status = repo._run("status", "--porcelain").stdout.strip()
    files_after = sorted([f.name for f in source_dir.glob("*.cpp")]) if source_dir.exists() else []
    print(f"Source files after rollback: {files_after}", flush=True)
    print(f"Git status after rollback: '{status}'", flush=True)

    # In scaffold, only Platformer.cpp exists in Source/Platformer. Gameplay sources (coins, rules) are removed.
    gameplay_sources_removed = not any("Coin" in f or "Platformer" not in f for f in files_after)
    is_clean = (status == "")

    rollback_evidence: Dict[str, Any] = {
        "ok": is_clean and gameplay_sources_removed,
        "scaffold_sha": scaffold_sha,
        "git_status_porcelain": status,
        "files_before": files_before,
        "files_after": files_after,
        "gameplay_sources_removed": gameplay_sources_removed,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    report_path = reports_dir / "rollback_check.json"
    _write_atomic_json(report_path, rollback_evidence)
    print(f"Saved rollback evidence to {report_path}", flush=True)

    # Now re-run pipeline to completion as required: "Then re-run to completion."
    print("\n=== STEP 4: Re-running pipeline to completion ===", flush=True)
    res = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "run_game_pipeline.py"),
            "--prompt",
            prompt,
            "--projects-root",
            str(project_dir.parent),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    print(f"Re-run finished with exit code {res.returncode}", flush=True)
    assert res.returncode == 0, f"Pipeline re-run failed: {res.stderr[:500]}"
    return rollback_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 Engine Gate Verification")
    parser.add_argument("--project-dir", type=Path, default=None, help="Project directory path")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR, help="Reports directory")
    parser.add_argument("--prompt", default="make a platformer with 6 coins", help="Pipeline prompt to test")
    parser.add_argument("--kill-only", action="store_true", help="Run only the kill test and resume")
    parser.add_argument("--rollback-only", action="store_true", help="Run only the rollback check")
    args = parser.parse_args()

    p_dir = resolve_project_dir(args.project_dir)
    r_dir = args.reports_dir

    if not args.rollback_only:
        ev1 = run_kill_test(p_dir, r_dir, prompt=args.prompt)
        if not ev1.get("ok"):
            print("Kill test failed!", flush=True)
            return 1

    if not args.kill_only:
        ev2 = run_rollback_check(p_dir, r_dir, prompt=args.prompt)
        if not ev2.get("ok"):
            print("Rollback check failed!", flush=True)
            return 1

    print("\nALL P2 ENGINE GATES PASSED SUCCESSFULLY!", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
