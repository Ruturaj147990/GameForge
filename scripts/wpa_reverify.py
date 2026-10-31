"""Roadmap WP-A step 1: re-verify the two open doubts on a disposable copy of the probe project.

1. IK retarget authenticity. The synthesized Walk is retargeted fresh onto Epic's AnimatedCharacter skeleton with
   the IK Retargeter (`anim_ik_retarget`), then source and result are sampled in component space by the engine
   (`anim_sample_world_pose`). A genuine retarget keeps the motion (each limb swings through the same angles
   relative to its reference pose) while the limb lengths stay the target's own. A skeleton swap would keep the
   source's lengths and is reported as a failure.
2. PCG authenticity. `pcg_scatter` runs in a fresh level and `pcg_verify_authenticity` checks that the instances
   sit in ISM components carrying PCG's generated-component tag and that the graph holds real PCG node settings.

Evidence: reports/wpa_reverify_<date>.json. Usage: python scripts/wpa_reverify.py
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

PROBE = Path(r"E:\GameForge\validation\live_ops_probe")
DATE = time.strftime("%Y%m%d")
DISPOSABLE = Path(rf"E:\GameForge\validation\wpa_reverify_{DATE}")
REPORT = REPO / "reports" / f"wpa_reverify_{DATE}.json"

SOURCE_MESH = "/Game/Characters/GFAdventurerHero/GFAdventurerHero/SkeletalMeshes/GFAdventurerHero"
WALK = "/Game/Characters/GFAdventurerHero/Animations/Anim_Walk"
TARGET_MESH = "/Game/Audit/RetargetTarget/SK_RetargetTarget"
SOURCE_RIG = {"root": "pelvis", "chains": {
    "Spine": ["spine_01", "spine_02"], "Head": ["neck", "head"],
    "LeftArm": ["upperarm_l", "hand_l"], "RightArm": ["upperarm_r", "hand_r"],
    "LeftLeg": ["thigh_l", "foot_l"], "RightLeg": ["thigh_r", "foot_r"]}}
TARGET_RIG = {"root": "Hips1", "chains": {
    "Spine": ["AbdoBottom1", "Brachius1"], "Head": ["Neck", "HeadEnd"],
    "LeftArm": ["ShoulderLeft1", "HandLeft"], "RightArm": ["ShoulderRight1", "HandRight"],
    "LeftLeg": ["HipLeft", "FootLeft"], "RightLeg": ["HipRight", "FootRight"]}}
COMPARED_CHAINS = ("LeftLeg", "RightLeg", "LeftArm", "RightArm")
FRAMES = 9
ANGLE_TOL_DEG = 12.0      # mean |source swing - target swing| per chain
LENGTH_TOL = 0.15         # target limb length must stay within 15% of the target's own reference length
MIN_SWING_DEG = 5.0       # the source chain must actually move for the comparison to mean anything


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def _angle(a, b):
    na, nb = _norm(a), _norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(a[i] * b[i] for i in range(3)) / (na * nb)))))


def compare_chains(src: dict, tgt: dict) -> dict:
    """Per-chain swing angles (vs reference pose) and limb lengths for source and retargeted sequences."""
    out = {}
    for chain in COMPARED_CHAINS:
        s0, s1 = SOURCE_RIG["chains"][chain]
        t0, t1 = TARGET_RIG["chains"][chain]
        s_ref = _sub(src["reference"][s1], src["reference"][s0])
        t_ref = _sub(tgt["reference"][t1], tgt["reference"][t0])
        rows = []
        for fs, ft in zip(src["frames"], tgt["frames"]):
            sv = _sub(fs["positions"][s1], fs["positions"][s0])
            tv = _sub(ft["positions"][t1], ft["positions"][t0])
            rows.append({"time": fs["time"], "source_swing_deg": round(_angle(sv, s_ref), 2),
                         "target_swing_deg": round(_angle(tv, t_ref), 2),
                         "source_len_cm": round(_norm(sv), 2), "target_len_cm": round(_norm(tv), 2)})
        swing_err = sum(abs(r["source_swing_deg"] - r["target_swing_deg"]) for r in rows) / len(rows)
        src_range = max(r["source_swing_deg"] for r in rows) - min(r["source_swing_deg"] for r in rows)
        t_ref_len, s_ref_len = _norm(t_ref), _norm(s_ref)
        len_dev = max(abs(r["target_len_cm"] / t_ref_len - 1.0) for r in rows) if t_ref_len else 1.0
        # Lengths only tell a retarget from a skeleton swap where the two skeletons' limbs differ (> 5%):
        # a swap keeps the source's bone translations, a retarget keeps the target's own.
        discriminating = abs(t_ref_len - s_ref_len) > 0.05 * s_ref_len
        swap_like = discriminating and max(abs(r["target_len_cm"] - r["source_len_cm"]) for r in rows) < 0.02 * s_ref_len
        out[chain] = {
            "source_ref_len_cm": round(s_ref_len, 2), "target_ref_len_cm": round(t_ref_len, 2),
            "mean_swing_error_deg": round(swing_err, 2), "source_swing_range_deg": round(src_range, 2),
            "max_target_len_deviation": round(len_dev, 3), "length_discriminates_swap": discriminating,
            "lengths_identical_to_source": swap_like,
            "pass": swing_err <= ANGLE_TOL_DEG and len_dev <= LENGTH_TOL and not swap_like, "frames": rows,
        }
    return out


def make_disposable() -> Path:
    if DISPOSABLE.exists():
        shutil.rmtree(DISPOSABLE)
    shutil.copytree(PROBE, DISPOSABLE, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    return DISPOSABLE / "GFProbe.uproject"


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "project": str(DISPOSABLE), "checks": {}, "steps": {},
           "tolerances": {"angle_deg": ANGLE_TOL_DEG, "length_frac": LENGTH_TOL, "min_swing_deg": MIN_SWING_DEG}}
    checks, steps = rep["checks"], rep["steps"]
    link = LiveEditorLink(make_disposable())
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=DISPOSABLE / "wpa_editor.log")
    try:
        link.connect(discovery_timeout_s=900)

        # 1. Fresh IK retarget + world-space comparison
        rt = link.call("anim_ik_retarget", {"source_mesh": SOURCE_MESH, "target_mesh": TARGET_MESH,
                                            "source_rig": SOURCE_RIG, "target_rig": TARGET_RIG,
                                            "animations": [WALK + "." + WALK.rsplit("/", 1)[-1]],
                                            "destination_path": "/Game/WPA/Retarget"}, timeout_s=300)
        steps["ik_retarget"] = (rt.get("data") or {}) | {"errors": rt.get("errors")}
        on_target = (rt.get("data") or {}).get("on_target_skeleton") or []
        checks["retarget_produced_sequence_on_target_skeleton"] = bool(rt.get("ok")) and bool(on_target)
        if on_target:
            src_bones = sorted({b for c in COMPARED_CHAINS for b in SOURCE_RIG["chains"][c]})
            tgt_bones = sorted({b for c in COMPARED_CHAINS for b in TARGET_RIG["chains"][c]})
            probe = link.call("anim_sample_world_pose", {"anim_sequence_path": WALK, "bones": src_bones, "times": [0.0]})
            steps["sample_probe"] = {"ok": probe.get("ok"), "errors": probe.get("errors")}
            length = (probe.get("data") or {}).get("play_length_s") or 0.0
            # Stop short of play_length: evaluating exactly at the end returns an empty (all-zero) pose.
            times = [round(length * i / FRAMES, 4) for i in range(FRAMES)] if length else [0.0]
            src = link.call("anim_sample_world_pose", {"anim_sequence_path": WALK, "bones": src_bones, "times": times})
            tgt = link.call("anim_sample_world_pose", {"anim_sequence_path": on_target[0], "bones": tgt_bones,
                                                       "times": times})
            steps["source_sample"] = {"ok": src.get("ok"), "errors": src.get("errors"),
                                      "skeleton": (src.get("data") or {}).get("skeleton")}
            steps["target_sample"] = {"ok": tgt.get("ok"), "errors": tgt.get("errors"),
                                      "skeleton": (tgt.get("data") or {}).get("skeleton")}
            if src.get("ok") and tgt.get("ok"):
                chains = compare_chains(src["data"], tgt["data"])
                steps["chain_comparison"] = chains
                checks["target_is_a_different_skeleton"] = src["data"]["skeleton"] != tgt["data"]["skeleton"]
                checks["source_motion_present"] = all(c["source_swing_range_deg"] >= MIN_SWING_DEG
                                                      for k, c in chains.items() if "Leg" in k)
                checks["leg_tracks_match_source_motion_in_world_space"] = all(
                    chains[k]["pass"] for k in ("LeftLeg", "RightLeg"))
                checks["arm_tracks_match_source_motion_in_world_space"] = all(
                    chains[k]["pass"] for k in ("LeftArm", "RightArm"))
                disc = [c for c in chains.values() if c["length_discriminates_swap"]]
                checks["swap_test_has_discriminating_chain"] = bool(disc)
                checks["not_a_skeleton_swap"] = bool(disc) and not any(c["lengths_identical_to_source"] for c in disc)
            else:
                checks["world_space_sampling_ran"] = False

        # 2. PCG authenticity in a fresh level
        steps["new_level"] = link.call("new_level", {"level_path": "/Game/WPA/Maps/PCGReverify"}).get("ok")
        sc = link.call("pcg_scatter", {"graph_folder": "/Game/WPA/PCG", "label": "GF_WPA_PCG"}, timeout_s=180)
        steps["pcg_scatter"] = (sc.get("data") or {}) | {"errors": sc.get("errors")}
        ver = {}
        for _ in range(30):
            ver = link.call("pcg_verify_authenticity", {"label": "GF_WPA_PCG"})
            if ver.get("ok"):
                break
            time.sleep(2.0)
        data = ver.get("data") or {}
        steps["pcg_verify"] = data | {"errors": ver.get("errors")}
        nodes = data.get("node_settings", [])
        checks["pcg_graph_has_real_pcg_nodes"] = ("PCGCreatePointsGridSettings" in nodes
                                                  and "PCGStaticMeshSpawnerSettings" in nodes)
        checks["pcg_instances_in_pcg_tagged_components"] = bool(ver.get("ok"))
        checks["no_untagged_ism_on_volume"] = not data.get("untagged_ism_components")
        steps["pcg_surface_sampler_used"] = "PCGSurfaceSamplerSettings" in nodes
    finally:
        rep["editor_exit_code"] = link.stop()
        rep["ok"] = bool(checks) and all(checks.values())
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
