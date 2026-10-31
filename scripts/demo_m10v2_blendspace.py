"""Roadmap M10 v2 WP-10.1 (asset half): a BlendSpace1D over the synthesized Idle/Walk/Run clips.

Builds BS_GFLocomotion (axis Speed 0–600, samples Idle 0 / Walk 150 / Run 450) on the GFAdventurerHero skeleton
in a disposable probe copy, reads it back, restarts the editor and requires an identical read-back.
Not covered (stays PLANNED): driving the BlendSpace from GameForgeLocomotionAnimInstance (C++), start/stop and
turn-in-place clips.

Evidence: reports/m10v2_blendspace_demo.json. Usage: python scripts/demo_m10v2_blendspace.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import demo_m11_landscape as land  # noqa: E402

REPORT = REPO / "reports" / "m10v2_blendspace_demo.json"
ANIMS = "/Game/Characters/GFAdventurerHero/Animations"
SKELETON = "/Game/Characters/GFAdventurerHero/GFAdventurerHero/SkeletalMeshes/GFAdventurerHero_Skeleton"
BS = "/Game/Characters/GFAdventurerHero/Animations/BS_GFLocomotion"
SAMPLES = [{"animation": f"{ANIMS}/Anim_Idle", "value": 0.0}, {"animation": f"{ANIMS}/Anim_Walk", "value": 150.0},
           {"animation": f"{ANIMS}/Anim_Run", "value": 450.0}]


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m10v2_blendspace_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = land.start(uproject, "bs_a")
    try:
        r = link.call("anim_create_blendspace_1d", {"asset_path": BS, "skeleton_path": SKELETON, "axis_name": "Speed",
                                                    "min": 0, "max": 600, "grid": 4, "samples": SAMPLES}, timeout_s=120)
        steps["create"] = (r.get("data") or {}) | {"ok": r.get("ok"), "errors": r.get("errors")}
        before = link.call("anim_inspect_blendspace", {"blendspace_path": BS}).get("data") or {}
        steps["before_restart"] = before
        checks["blendspace_created"] = bool(r.get("ok"))
        checks["axis_read_back"] = (before.get("axes") or [{}])[0] == {"name": "Speed", "min": 0.0, "max": 600.0, "grid": 4}
        checks["samples_read_back"] = [(s["animation"].split(".")[0], s["value"]) for s in before.get("samples", [])] == \
            [(s["animation"], s["value"]) for s in SAMPLES]
        link.call("save_all", {})
    finally:
        rep["editor_exit_code_a"] = link.stop()
    link = land.start(uproject, "bs_b")
    try:
        after = link.call("anim_inspect_blendspace", {"blendspace_path": BS}).get("data") or {}
        steps["after_restart"] = after
        checks["identical_after_restart"] = bool(after) and after == before
    finally:
        rep["editor_exit_code_b"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["AnimInstance driving the BlendSpace", "start/stop + turn-in-place clips"]}
    try:
        run(rep)
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
