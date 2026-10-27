"""Shipped-IDE efficiency benchmark (Master Blueprint v2 §8.1 release gate).

Measures the GameForge IDE process itself (not models, editors or builds it drives):
cold start to visible window, idle private memory, idle CPU, threads, child processes,
and the per-workspace metadata footprint. Writes JSON and exits non-zero on a budget miss.

    python scripts/ide_resource_benchmark.py --workspace <dir> [--idle-seconds 30]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

T_PROCESS_START = time.perf_counter()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BUDGETS = {"startup_s": 2.5, "idle_private_mb": 300.0, "idle_cpu_pct_one_core": 1.0, "child_processes": 0}


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--idle-seconds", type=float, default=30.0)
    ap.add_argument("--out", default=None)
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

    # settle, then measure an idle window
    end = time.monotonic() + 5
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    cpu0 = proc.cpu_times()
    t0 = time.monotonic()
    while time.monotonic() - t0 < a.idle_seconds:
        app.processEvents()
        time.sleep(0.05)  # an idle event loop; Qt timers still fire
    cpu1 = proc.cpu_times()
    wall = time.monotonic() - t0
    cpu_pct = ((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)) / wall * 100.0
    mem = proc.memory_full_info()
    children = proc.children(recursive=True)
    result = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "startup_s": round(startup_s, 2),
        "idle_private_mb": round(getattr(mem, "private", mem.uss) / 2**20, 1),
        "idle_working_set_mb": round(mem.rss / 2**20, 1),
        "idle_cpu_pct_one_core": round(cpu_pct, 2),
        "threads": proc.num_threads(),
        "child_processes": len(children),
        "child_names": sorted({c.name() for c in children}),
        "workspace_metadata_mb": round(dir_size(Path(a.workspace) / ".gameforge") / 2**20, 2),
        "budgets": BUDGETS,
    }
    result["violations"] = [k for k, lim in BUDGETS.items() if result[k] > lim]
    print(json.dumps(result, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    win.confirm_on_close = False  # automation: skip the "Are you sure?" dialog
    win.close()
    app.processEvents()
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
