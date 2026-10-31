"""Render IDE view snapshots at various DPI scale factors (WI-4.12).

Usage:
  python scripts/ide/ide_snapshot.py --scale 1.0 --view home
  python scripts/ide/ide_snapshot.py --all
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Add repo to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VIEWS = ["home", "games", "design", "build", "play", "evidence", "assets", "code", "settings"]


def snapshot_view(scale: float, view_id: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"dpi_{scale}_{view_id}.png"

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = str(scale)

    from PySide6.QtWidgets import QApplication
    from src.gameforge_ide.desktop.main_window import MainWindow

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    bench_ws = Path(r"E:\GameForge\ide_bench_ws")
    if not bench_ws.is_dir():
        bench_ws = REPO_ROOT / "scratch" / "bench_ws"
        bench_ws.mkdir(parents=True, exist_ok=True)

    win = MainWindow(bench_ws)
    win.resize(1440, 900)
    win.show()

    # Switch to view
    if hasattr(win, "_switch_studio_view"):
        win._switch_studio_view(view_id)

    # Allow layout passes
    end = time.time() + 0.3
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)

    win.grab().save(str(out_file))
    print(f"Captured {out_file} (scale={scale}, view={view_id})")

    win.confirm_on_close = False
    win.close()
    return out_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture DPI snapshots of Studio views")
    parser.add_argument("--scale", type=float, default=1.0, help="DPI scale factor (e.g. 1.0, 1.25, 1.5)")
    parser.add_argument("--view", type=str, default="home", help="View ID to capture (or 'all')")
    parser.add_argument("--all", action="store_true", help="Capture all 9 views at 1.0, 1.25, and 1.5 scale")
    args = parser.parse_args()

    out_dir = REPO_ROOT / "reports" / "P4"

    if args.all:
        scales = [1.0, 1.25, 1.5]
        for s in scales:
            for v in VIEWS:
                snapshot_view(s, v, out_dir)
        print("All DPI snapshots captured successfully.")
        return 0

    if args.view == "all":
        for v in VIEWS:
            snapshot_view(args.scale, v, out_dir)
    else:
        snapshot_view(args.scale, args.view, out_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
