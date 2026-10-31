"""Roadmap M10 v2 WP-10.1 (drive half): the locomotion AnimInstance evaluates Idle/Walk/Run through a BlendSpace1D.

On a disposable probe copy (plugin build m10v2): build BS_GFLocomotion (Idle 0 / Walk 150 / Run 450), create an
AnimBP whose class defaults hold the six clips plus the blend space (read back after recompile), then run the PIE
locomotion script (stand → walk at 35% input → run → jump). Checks: the live anim instance reports the blend space,
the sample weights follow ground speed (Idle at rest, Walk dominant while walking, Run dominant while running, and
at least one frame with two samples blended), the movement-driven state transitions still happen in order, and the
mesh is posed.

Evidence: reports/m10v2_blend_drive_demo.json. Usage: python scripts/demo_m10v2_blend_drive.py
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

REPORT = REPO / "reports" / "m10v2_blend_drive_demo.json"
HERO = "/Game/Characters/GFAdventurerHero"
ANIMS = f"{HERO}/Animations"
MESH = f"{HERO}/GFAdventurerHero/SkeletalMeshes/GFAdventurerHero"
SKELETON = f"{MESH}_Skeleton"
BS = f"{ANIMS}/BS_GFLocomotion"
ABP = "ABP_LocomotionBlend"
CLIPS = {name: f"{ANIMS}/Anim_{name}" for name in ("Idle", "Walk", "Run", "Jump", "Fall", "Land")}
SAMPLES = [{"animation": CLIPS["Idle"], "value": 0.0}, {"animation": CLIPS["Walk"], "value": 150.0},
           {"animation": CLIPS["Run"], "value": 450.0}]
EXPECTED_TRANSITIONS = ["Idle->Walk", "Walk->Run", "Run->Jump", "Jump->Fall", "Fall->Land", "Land->Idle"]


def parse_weights(text: str) -> dict[str, float]:
    out = {}
    for part in filter(None, (text or "").split(";")):
        name, _, value = part.partition("=")
        out[name.replace("Anim_", "")] = out.get(name.replace("Anim_", ""), 0.0) + float(value)
    return out


def dominant(weights: dict[str, float]) -> str | None:
    return max(weights, key=weights.get) if weights else None


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PLUGIN_BUILD = Path(r"E:\GameForge\validation\GameForgePlugin_m10v2")
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m10v2_blenddrive_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = land.start(uproject, "drive")
    try:
        r = link.call("anim_create_blendspace_1d", {"asset_path": BS, "skeleton_path": SKELETON, "axis_name": "Speed",
                                                    "min": 0, "max": 600, "grid": 4, "samples": SAMPLES}, timeout_s=120)
        checks["blendspace_created"] = bool(r.get("ok"))
        abp = link.call("anim_create_locomotion_blueprint", {"blueprint_name": ABP, "destination_path": HERO,
                                                             "skeleton_path": SKELETON, "clips": CLIPS, "blend_space": BS})
        data = abp.get("data") or {}
        steps["anim_blueprint"] = data | {"errors": abp.get("errors")}
        assigned = data.get("assigned_clips", {})
        checks["abp_holds_blend_space_after_recompile"] = bool(abp.get("ok")) and \
            assigned.get("blend_space_after_recompile", "").split(".")[0] == BS
        link.call("save_all", {})

        link.call("pie_start", {})
        time.sleep(4.0)
        start = link.call("anim_start_locomotion_test", {"skeletal_mesh_path": MESH, "anim_blueprint_path": f"{HERO}/{ABP}",
                                                         "location": {"x": -900, "y": 900, "z": 150}})
        steps["pie_start_test"] = (start.get("data") or {}) | {"errors": start.get("errors")}
        samples, result = [], {}
        deadline = time.time() + 30
        while time.time() < deadline:
            result = link.call("anim_locomotion_test_result", {}).get("data") or {}
            w = parse_weights(result.get("blend_space_weights", ""))
            samples.append({"t": result.get("elapsed_s"), "state": result.get("current_state"),
                            "speed": round(result.get("ground_speed") or 0.0, 1), "weights": w,
                            "thigh_dev": result.get("thigh_l_deviation_deg")})
            if result.get("finished"):
                break
            time.sleep(0.25)
        link.call("pie_stop", {})
        steps["pie_samples"] = samples
        steps["pie_transitions"] = result.get("transitions", [])
        steps["pie_phases"] = result.get("phases", [])

        checks["live_instance_uses_blend_space"] = result.get("blend_space", "").split(".")[0] == BS
        rest = [s for s in samples if s["state"] == "Idle" and s["speed"] < 5 and s["weights"]]
        walk = [s for s in samples if s["state"] == "Walk" and s["weights"]]
        runs = [s for s in samples if s["state"] == "Run" and s["weights"]]
        checks["idle_weight_at_rest"] = bool(rest) and all(s["weights"].get("Idle", 0) > 0.95 for s in rest)
        checks["walk_dominant_while_walking"] = bool(walk) and \
            sum(dominant(s["weights"]) == "Walk" for s in walk) >= 0.8 * len(walk)
        checks["run_dominant_while_running"] = bool(runs) and \
            sum(dominant(s["weights"]) == "Run" for s in runs) >= 0.8 * len(runs)
        checks["weights_blend_two_samples"] = any(sum(v > 0.05 for v in s["weights"].values()) >= 2 for s in samples)
        checks["weights_sum_to_one"] = all(abs(sum(s["weights"].values()) - 1.0) < 0.02 for s in samples if s["weights"])
        transitions = [t.split()[0] for t in result.get("transitions", [])]
        it = iter(transitions)
        checks["movement_driven_transitions_in_order"] = all(any(t == want for t in it) for want in EXPECTED_TRANSITIONS)
        checks["mesh_posed"] = max((s["thigh_dev"] or 0) for s in samples) > 5.0
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {}}
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
