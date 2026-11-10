"""Job Object Leak Test for Phase 2 Exit Gate (AD-11, Blueprint §8.1).

Verifies that killing the IDE process terminates all child processes (UBT, UnrealEditor, dotnet, helpers)
via the Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
Saves evidence to reports/P2/job_object_leak_test.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import psutil

REPO = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO / "reports" / "P2"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_leak_test() -> Dict[str, Any]:
    print("=== Running Job Object Leak Test ===", flush=True)

    if sys.platform != "win32":
        evidence: Dict[str, Any] = {"ok": True, "skipped": "Non-Windows platform"}
        report_path = REPORTS_DIR / "job_object_leak_test.json"
        tmp_report = report_path.with_suffix(".tmp")
        tmp_report.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        os.replace(tmp_report, report_path)
        return evidence

    # Helper process simulating the IDE launching a long-running child process via jobs.spawn
    repo_escaped = str(REPO).replace("\\", "\\\\")
    helper_code = (
        "import sys, os, time\n"
        f"if '{repo_escaped}' not in sys.path: sys.path.insert(0, '{repo_escaped}')\n"
        "from src.gameforge_ide.core import jobs\n"
        "# Spawn a 120s worker process into the IDE job\n"
        "proc = jobs.spawn([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "print(f'PARENT:{sys.argv[0]} PID:{os.getpid()} CHILD:{proc.pid}', flush=True)\n"
        "time.sleep(60)\n"
    )

    creationflags = 0x08000000  # CREATE_NO_WINDOW
    helper_proc = subprocess.Popen(
        [sys.executable, "-c", helper_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )

    child_pid: int | None = None
    parent_pid: int | None = None

    try:
        line = helper_proc.stdout.readline().strip() if helper_proc.stdout else ""
        print(f"Helper output: {line}", flush=True)
        if "CHILD:" not in line:
            err_text = helper_proc.stderr.read() if helper_proc.stderr else ""
            raise RuntimeError(f"Expected CHILD: in output, got: {line!r}\nStderr: {err_text}")

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
        tmp_report = report_path.with_suffix(".tmp")
        tmp_report.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        os.replace(tmp_report, report_path)
        print(f"Saved evidence to {report_path}", flush=True)
        return evidence
    finally:
        # Guarantee cleanup in case of assertion error
        if helper_proc.poll() is None:
            try:
                helper_proc.kill()
            except Exception:
                pass
        if child_pid and psutil.pid_exists(child_pid):
            try:
                psutil.Process(child_pid).kill()
            except Exception:
                pass
