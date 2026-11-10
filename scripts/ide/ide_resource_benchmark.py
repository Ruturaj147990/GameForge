"""Shipped-IDE efficiency benchmark (Master Blueprint v2 §8.1 release gate).

Measures the GameForge IDE process itself (not models, editors or builds it drives):
cold start to visible window, idle private memory, idle CPU, threads, child processes,
and the per-workspace metadata footprint. Writes JSON and exits non-zero on a budget miss.

    python scripts/ide/ide_resource_benchmark.py --workspace <dir> [--idle-seconds 30]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

T_PROCESS_START = time.perf_counter()
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BUDGETS: Dict[str, float] = {
    "startup_s": 2.5,
    "idle_private_mb": 300.0,
    "idle_cpu_pct_one_core": 1.0,
    "child_processes": 0.0,
}


def dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Shipped-IDE efficiency benchmark")
    ap.add_argument("--workspace", required=True, help="Path to project workspace directory")
    ap.add_argument("--idle-seconds", type=float, default=30.0, help="Duration to monitor idle resource utilization")
    ap.add_argument("--out", default=None, help="Output JSON report file path")
    a = ap.parse_args()

    import psutil
    from PySide6.QtWidgets import QApplication
    from src.gameforge_ide.desktop.main_window import MainWindow

    proc = psutil.Process()
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(Path(a.workspace))
    win.show()
    app.processEvents()
    startup_s = time.perf_counter() - T_PROCESS_START

    result: Dict[str, Any] = {}
    try:
        # settle, then measure an idle window
        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        cpu0 = proc.cpu_times()
        t0 = time.monotonic()
        while time.monotonic() - t0 < max(0.1, a.idle_seconds):
            app.processEvents()
            time.sleep(0.05)  # an idle event loop; Qt timers still fire
        cpu1 = proc.cpu_times()
        wall = max(0.001, time.monotonic() - t0)
        cpu_pct = ((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)) / wall * 100.0
        mem = proc.memory_full_info()
        children = proc.children(recursive=True)
        child_names = []
        for c in children:
            try:
                child_names.append(c.name())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        result = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "startup_s": round(startup_s, 2),
            "idle_private_mb": round(getattr(mem, "private", mem.uss) / 2**20, 1),
            "idle_working_set_mb": round(mem.rss / 2**20, 1),
            "idle_cpu_pct_one_core": round(cpu_pct, 2),
            "threads": proc.num_threads(),
            "child_processes": len(children),
            "child_names": sorted(set(child_names)),
            "workspace_metadata_mb": round(dir_size(Path(a.workspace) / ".gameforge") / 2**20, 2),
            "budgets": BUDGETS,
        }
        result["violations"] = [k for k, lim in BUDGETS.items() if result[k] > lim]
        print(json.dumps(result, indent=1))
        if a.out:
            out_p = Path(a.out)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            tmp = out_p.with_suffix(".tmp")
            tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
            tmp.replace(out_p)
    finally:
        win.confirm_on_close = False  # automation: skip the "Are you sure?" dialog
        win.close()
        app.processEvents()

    return 1 if result.get("violations") else 0


if __name__ == "__main__":
    raise SystemExit(main())
