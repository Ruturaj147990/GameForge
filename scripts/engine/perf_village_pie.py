"""Roadmap M19: CSV-profiler capture of the generated forest village in PIE.

Re-opens the disposable project from `demo_m8v2_village.py`, loads Village_A, starts PIE, records
`csvprofile` for ~10 s and summarises frame / game-thread / render-thread / GPU times. Editor PIE with
-RenderOffscreen at 1280x720 is not a shipping measurement; numbers are for regression tracking only.

Evidence: reports/m19_perf_village.json. Usage: python scripts/engine/perf_village_pie.py
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gameforge_ide.backend.tools.csv_profile import parse_csv_profile  # noqa: E402
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m19_perf_village.json"


def _get_project_dir() -> Path:
    try:
        val_root = get_settings().require_dev("validation_root")
        p = Path(val_root) / f"m8v2_village_{time.strftime('%Y%m%d')}"
        if p.exists():
            return p
    except Exception:
        pass
    return REPO / "scratch" / "validation" / f"m8v2_village_{time.strftime('%Y%m%d')}"


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV-profiler capture of forest village in PIE")
    parser.add_argument("--project", default=None, help="Explicit path to village project folder")
    args = parser.parse_args()

    project_dir = Path(args.project).resolve() if args.project else _get_project_dir()
    rep: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "project": str(project_dir),
        "checks": {},
        "steps": {},
        "conditions": "editor PIE, -RenderOffscreen 1280x720, RX 7700 XT, Development editor build",
    }
    uproject_file = project_dir / "GFProbe.uproject"
    link = LiveEditorLink(uproject_file)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=project_dir / "perf_editor.log")
    try:
        link.connect(discovery_timeout_s=900)
        rep["steps"]["load_level"] = link.call("load_level", {"level_path": "/Game/Village/Maps/Village_A"}).get("ok")
        before = {
            f.get("path")
            for f in (link.call("perf_list_csv", {}).get("data") or {}).get("files", [])
            if isinstance(f, dict) and f.get("path")
        }
        pie_active = False
        try:
            rep["steps"]["pie_start"] = link.call("pie_start", {}).get("ok")
            pie_active = bool(rep["steps"]["pie_start"])
            time.sleep(6.0)
            rep["steps"]["start"] = link.call("perf_console", {"command": "csvprofile start"}).get("ok")
            time.sleep(10.0)
            rep["steps"]["stop"] = link.call("perf_console", {"command": "csvprofile stop"}).get("ok")
            new_files: List[Dict[str, Any]] = []
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                time.sleep(1.0)
                files = (link.call("perf_list_csv", {}).get("data") or {}).get("files", [])
                new_files = [
                    f for f in files
                    if isinstance(f, dict) and f.get("path") not in before and (f.get("bytes") or 0) > 0
                ]
                if new_files:
                    break
        finally:
            if pie_active:
                with contextlib.suppress(Exception):
                    link.call("pie_stop", {})

        rep["steps"]["csv_files"] = new_files
        rep["checks"]["csv_written"] = bool(new_files)
        if new_files:
            time.sleep(1.0)
            summary = parse_csv_profile(str(new_files[-1].get("path", "")))
            rep["summary"] = summary
            rep["checks"]["frames_captured"] = (summary.get("frames") or 0) > 30
            rep["checks"]["timing_columns_present"] = "FrameTime" in summary and "GameThreadTime" in summary
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["editor_exit_code"] = link.stop()
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        tmp = REPORT.with_suffix(".tmp")
        tmp.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        tmp.replace(REPORT)
    print(json.dumps({"checks": rep["checks"], "summary": rep.get("summary")}, indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
