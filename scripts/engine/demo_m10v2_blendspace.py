"""Roadmap M10 v2 WP-10.1 (asset half): a BlendSpace1D over the synthesized Idle/Walk/Run clips.

Builds BS_GFLocomotion (axis Speed 0–600, samples Idle 0 / Walk 150 / Run 450) on the GFAdventurerHero skeleton
in a disposable probe copy, reads it back, restarts the editor and requires an identical read-back.
Not covered (stays PLANNED): driving the BlendSpace from GameForgeLocomotionAnimInstance (C++), start/stop and
turn-in-place clips.

Evidence: reports/m10v2_blendspace_demo.json. Usage: python scripts/engine/demo_m10v2_blendspace.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ENGINE_SCRIPTS = str(REPO / "scripts" / "engine")
if ENGINE_SCRIPTS not in sys.path:
    sys.path.insert(0, ENGINE_SCRIPTS)

from src.gameforge_ide.core.settings import get_settings  # noqa: E402

REPORT = REPO / "reports" / "m10v2_blendspace_demo.json"
ANIMS = "/Game/Characters/GFAdventurerHero/Animations"
SKELETON = "/Game/Characters/GFAdventurerHero/GFAdventurerHero/SkeletalMeshes/GFAdventurerHero_Skeleton"
BS = "/Game/Characters/GFAdventurerHero/Animations/BS_GFLocomotion"
SAMPLES = [{"animation": f"{ANIMS}/Anim_Idle", "value": 0.0}, {"animation": f"{ANIMS}/Anim_Walk", "value": 150.0},
           {"animation": f"{ANIMS}/Anim_Run", "value": 450.0}]


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_landscape as land

    checks, steps = rep["checks"], rep["steps"]
    val_root = get_settings().require_dev("validation_root")
    land.PROJECT_DIR = val_root / f"m10v2_blendspace_{time.strftime('%Y%m%d')}"
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = land.start(uproject, "bs_a")
    try:
        r = link.call("anim_create_blendspace_1d", {"asset_path": BS, "skeleton_path": SKELETON, "axis_name": "Speed",
                                                    "min": 0, "max": 600, "grid": 4, "samples": SAMPLES}, timeout_s=120) or {}
        r_data = r.get("data") if isinstance(r.get("data"), dict) else {}
        steps["create"] = r_data | {"ok": r.get("ok"), "errors": r.get("errors")}
        before_resp = link.call("anim_inspect_blendspace", {"blendspace_path": BS}) or {}
        before = before_resp.get("data") if isinstance(before_resp.get("data"), dict) else {}
        steps["before_restart"] = before
        checks["blendspace_created"] = bool(r.get("ok"))
        checks["axis_read_back"] = (before.get("axes") or [{}])[0] == {"name": "Speed", "min": 0.0, "max": 600.0, "grid": 4}
        checks["samples_read_back"] = [(str(s.get("animation", "")).split(".")[0], s.get("value")) for s in before.get("samples", [])] == \
            [(s["animation"], s["value"]) for s in SAMPLES]
        link.call("save_all", {})
    finally:
        rep["editor_exit_code_a"] = link.stop()
    link = land.start(uproject, "bs_b")
    try:
        after_resp = link.call("anim_inspect_blendspace", {"blendspace_path": BS}) or {}
        after = after_resp.get("data") if isinstance(after_resp.get("data"), dict) else {}
        steps["after_restart"] = after
        checks["identical_after_restart"] = bool(after) and after == before
    finally:
        rep["editor_exit_code_b"] = link.stop()


def main() -> int:
    rep: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "checks": {},
        "steps": {},
        "not_covered": ["AnimInstance driving the BlendSpace", "start/stop + turn-in-place clips"],
    }
    try:
        run(rep)
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        tmp = REPORT.with_name(f".{REPORT.name}.tmp.{os.getpid()}")
        try:
            tmp.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, REPORT)
        finally:
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
