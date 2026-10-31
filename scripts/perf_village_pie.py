"""Roadmap M19: CSV-profiler capture of the generated forest village in PIE.

Re-opens the disposable project from `demo_m8v2_village.py`, loads Village_A, starts PIE, records
`csvprofile` for ~10 s and summarises frame / game-thread / render-thread / GPU times. Editor PIE with
-RenderOffscreen at 1280x720 is not a shipping measurement; numbers are for regression tracking only.

Evidence: reports/m19_perf_village.json. Usage: python scripts/perf_village_pie.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.gameforge_ide.backend.tools.csv_profile import parse_csv_profile  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

PROJECT = Path(rf"E:\GameForge\validation\m8v2_village_{time.strftime('%Y%m%d')}")
REPORT = REPO / "reports" / "m19_perf_village.json"


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "project": str(PROJECT), "checks": {}, "steps": {},
           "conditions": "editor PIE, -RenderOffscreen 1280x720, RX 7700 XT, Development editor build"}
    link = LiveEditorLink(PROJECT / "GFProbe.uproject")
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=PROJECT / "perf_editor.log")
    try:
        link.connect(discovery_timeout_s=900)
        rep["steps"]["load_level"] = link.call("load_level", {"level_path": "/Game/Village/Maps/Village_A"}).get("ok")
        before = {f["path"] for f in (link.call("perf_list_csv", {}).get("data") or {}).get("files", [])}
        rep["steps"]["pie_start"] = link.call("pie_start", {}).get("ok")
        time.sleep(6.0)
        rep["steps"]["start"] = link.call("perf_console", {"command": "csvprofile start"}).get("ok")
        time.sleep(10.0)
        rep["steps"]["stop"] = link.call("perf_console", {"command": "csvprofile stop"}).get("ok")
        new = []
        for _ in range(20):
            time.sleep(1.0)
            files = (link.call("perf_list_csv", {}).get("data") or {}).get("files", [])
            new = [f for f in files if f["path"] not in before and f["bytes"] > 0]
            if new:
                break
        link.call("pie_stop", {})
        rep["steps"]["csv_files"] = new
        rep["checks"]["csv_written"] = bool(new)
        if new:
            time.sleep(1.0)
            summary = parse_csv_profile(new[-1]["path"])
            rep["summary"] = summary
            rep["checks"]["frames_captured"] = summary["frames"] > 30
            rep["checks"]["timing_columns_present"] = "FrameTime" in summary and "GameThreadTime" in summary
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["editor_exit_code"] = link.stop()
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"checks": rep["checks"], "summary": rep.get("summary")}, indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
