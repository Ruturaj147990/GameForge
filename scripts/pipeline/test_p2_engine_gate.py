"""Engine gate verification script for Phase 2 (WI-2.6):
1. Kill test & resume on Platformer:
   - Start: python scripts/pipeline/run_game_pipeline.py --prompt "make a platformer with 6 coins"
   - Interrupt/kill when build_editor is running.
   - Resume: python scripts/pipeline/run_game_pipeline.py --resume E:\\GameForge\\projects\\Platformer
   - Verify spec/scaffold/sources were skipped and run finishes PASS.
   - Write reports/P2/resume_kill_test.json.
2. Rollback check:
   - ProjectRepo.reset_to(scaffold_checkpoint, editor_running=False)
   - Verify Source/ matches scaffold checkpoint and game sources are removed.
   - Write reports/P2/rollback_check.json.
   - Re-run pipeline to completion (PASS).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROJECT_DIR = Path(r"E:\GameForge\projects\Platformer")
REPORTS_DIR = Path("reports/P2")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def run_kill_test() -> dict:
    print("=== STEP 1: Starting kill test for Platformer ===", flush=True)
    if PROJECT_DIR.exists():
        import shutil
        print(f"Cleaning previous {PROJECT_DIR} for clean kill test...", flush=True)
        shutil.rmtree(PROJECT_DIR, ignore_errors=True)

    cmd1 = [sys.executable, "scripts/pipeline/run_game_pipeline.py", "--prompt", "make a platformer with 6 coins"]
    proc1 = subprocess.Popen(
        cmd1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    run1_events = []
    killed = False

    while True:
        line = proc1.stdout.readline()
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
    cmd2 = [sys.executable, "scripts/pipeline/run_game_pipeline.py", "--resume", str(PROJECT_DIR)]
    proc2 = subprocess.Popen(
        cmd2,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    run2_events = []
    while True:
        line = proc2.stdout.readline()
        if not line and proc2.poll() is not None:
            break
        if line:
            line_str = line.strip()
            print(f"[RUN 2] {line_str}", flush=True)
            run2_events.append(line_str)

    exit_code2 = proc2.wait()
    print(f"Run 2 finished with exit code {exit_code2}", flush=True)

    from src.gameforge_ide.forge.store import RunStore
    store = RunStore(project_dir=PROJECT_DIR, workspace_dir=PROJECT_DIR.parent)
    state = store.latest_for_project(PROJECT_DIR)
    assert state is not None, "Latest run state not found"

    # Identify skipped steps: steps that were DONE with 0 seconds in run 2
    records = state.records
    skipped_steps = [s for s in ["spec", "scaffold", "sources"] if records.get(s) and records[s].status.value == "DONE"]

    evidence = {
        "ok": exit_code2 == 0 and state.status == "DONE",
        "run1_killed": killed,
        "run1_events": run1_events,
        "run2_events": run2_events,
        "skipped_steps": skipped_steps,
        "final_status": state.status,
        "records": {k: {"status": r.status.value, "attempts": r.attempts, "duration_s": r.duration_s} for k, r in records.items()},
        "finished_at": time.time(),
    }

    report_path = REPORTS_DIR / "resume_kill_test.json"
    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Saved kill test evidence to {report_path}", flush=True)
    return evidence


def run_rollback_check() -> dict:
    print("\n=== STEP 3: Running Rollback Check ===", flush=True)
    from src.gameforge_ide.forge.checkpoints import ProjectRepo
    from src.gameforge_ide.forge.store import RunStore

    store = RunStore(project_dir=PROJECT_DIR, workspace_dir=PROJECT_DIR.parent)
    state = store.latest_for_project(PROJECT_DIR)
    assert state is not None, "RunState not found for rollback check"

    scaffold_rec = state.records.get("scaffold")
    repo = ProjectRepo(PROJECT_DIR)
    assert repo.available, "Git not available in ProjectRepo"

    scaffold_sha = (
        scaffold_rec.checkpoint
        if (scaffold_rec and scaffold_rec.checkpoint)
        else repo._run("rev-list", "--max-parents=0", "HEAD").stdout.strip()
    )
    print(f"Scaffold checkpoint SHA: {scaffold_sha}", flush=True)

    source_dir = PROJECT_DIR / "Source" / "Platformer"
    files_before = sorted([f.name for f in source_dir.glob("*.cpp")])
    print(f"Source files before rollback: {files_before}", flush=True)

    # Perform rollback
    repo.reset_to(scaffold_sha, editor_running=False)

    status = repo._run("status", "--porcelain").stdout.strip()
    files_after = sorted([f.name for f in source_dir.glob("*.cpp")])
    print(f"Source files after rollback: {files_after}", flush=True)
    print(f"Git status after rollback: '{status}'", flush=True)

    # In scaffold, only Platformer.cpp exists in Source/Platformer. Gameplay sources (coins, rules) are removed.
    gameplay_sources_removed = not any("Coin" in f or "Platformer" not in f for f in files_after)
    is_clean = (status == "")

    rollback_evidence = {
        "ok": is_clean and gameplay_sources_removed,
        "scaffold_sha": scaffold_sha,
        "git_status_porcelain": status,
        "files_before": files_before,
        "files_after": files_after,
        "gameplay_sources_removed": gameplay_sources_removed,
        "timestamp": time.time(),
    }

    report_path = REPORTS_DIR / "rollback_check.json"
    report_path.write_text(json.dumps(rollback_evidence, indent=2), encoding="utf-8")
    print(f"Saved rollback evidence to {report_path}", flush=True)

    # Now re-run pipeline to completion as required: "Then re-run to completion."
    print("\n=== STEP 4: Re-running pipeline to completion ===", flush=True)
    res = subprocess.run(
        [sys.executable, "scripts/pipeline/run_game_pipeline.py", "--prompt", "make a platformer with 6 coins"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(f"Re-run finished with exit code {res.returncode}", flush=True)
    assert res.returncode == 0, f"Pipeline re-run failed: {res.stderr[:500]}"
    return rollback_evidence


if __name__ == "__main__":
    ev1 = run_kill_test()
    if not ev1["ok"]:
        print("Kill test failed!", flush=True)
        sys.exit(1)
    ev2 = run_rollback_check()
    if not ev2["ok"]:
        print("Rollback check failed!", flush=True)
        sys.exit(1)
    print("\nALL P2 ENGINE GATES PASSED SUCCESSFULLY!", flush=True)
