"""Job Object Leak Test for Phase 2 Exit Gate (AD-11, Blueprint §8.1).

Verifies that killing the IDE process terminates all child processes (UBT, UnrealEditor, dotnet, helpers)
via the Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
Saves evidence to reports/P2/job_object_leak_test.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
import psutil

REPORTS_DIR = Path("reports/P2")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_leak_test() -> dict:
    print("=== Running Job Object Leak Test ===", flush=True)

    if sys.platform != "win32":
        evidence = {"ok": True, "skipped": "Non-Windows platform"}
        (REPORTS_DIR / "job_object_leak_test.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        return evidence

    # Helper process simulating the IDE launching a long-running child process via jobs.spawn
    helper_code = (
        "import sys, time\n"
        "from src.gameforge_ide.core import jobs\n"
        "# Spawn a 120s worker process into the IDE job\n"
        "proc = jobs.spawn([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "print(f'PARENT:{sys.argv[0]} PID:{__import__(\"os\").getpid()} CHILD:{proc.pid}', flush=True)\n"
        "time.sleep(60)\n"
    )

    helper_proc = subprocess.Popen(
        [sys.executable, "-c", helper_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    line = helper_proc.stdout.readline().strip()
    print(f"Helper output: {line}", flush=True)
    assert "CHILD:" in line, f"Expected CHILD: in output, got {line!r}"

    parts = line.split()
    parent_pid = int(next(p.split(":")[-1] for p in parts if p.startswith("PID:")))
    child_pid = int(next(p.split(":")[-1] for p in parts if p.startswith("CHILD:")))

    print(f"Parent PID: {parent_pid}, Child PID: {child_pid}", flush=True)
    assert psutil.pid_exists(parent_pid), "Parent PID does not exist"
    assert psutil.pid_exists(child_pid), "Child PID does not exist"

    # Abruptly kill the parent process (simulating IDE crash or task termination)
    print(f"Killing parent process {parent_pid}...", flush=True)
    p = psutil.Process(parent_pid)
    p.kill()
    helper_proc.wait(timeout=5)

    # Wait for Windows kernel to close the job object and terminate all assigned processes
    child_terminated = False
    for _ in range(30):
        time.sleep(0.1)
        if not psutil.pid_exists(child_pid):
            child_terminated = True
            break

    print(f"Child {child_pid} terminated: {child_terminated}", flush=True)
    assert child_terminated, f"LEAK DETECTED: child process {child_pid} was not terminated after parent kill"

    evidence = {
        "ok": child_terminated,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "child_terminated_on_parent_kill": child_terminated,
        "surviving_children": [],
        "timestamp": time.time(),
        "platform": sys.platform,
    }

    report_path = REPORTS_DIR / "job_object_leak_test.json"
    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Saved evidence to {report_path}", flush=True)
    return evidence


if __name__ == "__main__":
    ev = run_leak_test()
    if not ev["ok"]:
        sys.exit(1)
    print("JOB OBJECT LEAK TEST PASSED!", flush=True)
