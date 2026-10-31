"""Packaged-build check of the gameplay kit (pickup + objectives/save + quest giver + guard AI), roadmap §5 item 6(d).

Scaffolds a C++ project GFKitTest (E:\\GameForge\\validation\\kit_packaged_<date>), copies the GameForge plugin
(source included), builds the editor target, builds the level through editor ops (quest giver, two relic pickups,
patrolling guard, NavMesh, AGameForgeKitSelfTest with waypoints), packages Win64 Development, then runs the real game
binary twice:
  1. -GFKitSelfTest: the player's pawn walks the waypoints (NavMesh moves) → expects the quest Completed with three
     dialogue lines and the guard to have patrolled and chased the pawn;
  2. -GFKitSelfTestRestore: a NEW process must load the completed quest from the game's own save slot.
Each run must exit 0 and log "GF_KIT_SELFTEST PASS".

Evidence: reports/kit_packaged_selftest.json. Usage: python scripts/package_kit_selftest.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402
from src.gameforge_ide.unreal.toolchain import UnrealToolchain  # noqa: E402

REPORT = REPO / "reports" / "kit_packaged_selftest.json"
NAME = "GFKitTest"
ROOT = Path(rf"E:\GameForge\validation\kit_packaged_{time.strftime('%Y%m%d')}")
MAP = "/Game/Maps/KitTest"
PLUGIN_SRC = REPO / "src" / "gameforge_ide" / "unreal" / "GameForge"
GIVER, RELICS = {"x": -700, "y": 0, "z": 100}, [{"x": 300, "y": 600, "z": 100}, {"x": 300, "y": -600, "z": 100}]
GUARD_ROUTE = [{"x": 1200, "y": -1400, "z": 100}, {"x": 1200, "y": -600, "z": 100}]
WAYPOINTS = [GIVER, RELICS[0], RELICS[1], GIVER, {"x": 1200, "y": 200, "z": 100}]


def build_level(uproject: Path, steps: dict) -> bool:
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=ROOT / "level_editor.log")
    ok = []
    try:
        link.connect(discovery_timeout_s=900)
        ok.append(link.call("new_level", {"level_path": MAP}).get("ok"))
        for a in [
            {"actor_class": "StaticMeshActor", "label": "GF_Floor", "static_mesh": "/Engine/BasicShapes/Cube.Cube",
             "location": {"x": 0, "y": 0, "z": -50}, "scale": {"x": 60, "y": 60, "z": 1}},
            {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0, "mobility": "Movable",
             "rotation": {"pitch": -45, "yaw": 30, "roll": 0}, "location": {"x": 0, "y": 0, "z": 800}},
            {"actor_class": "SkyLight", "label": "GF_Sky", "mobility": "Movable", "location": {"x": 0, "y": 0, "z": 900}},
            {"actor_class": "PlayerStart", "label": "GF_PlayerStart", "location": {"x": -1600, "y": 0, "z": 120}},
            {"actor_class": "NavMeshBoundsVolume", "label": "GF_NavBounds", "location": {"x": 0, "y": 0, "z": 100},
             "scale": {"x": 30, "y": 30, "z": 4}},
            {"actor_class": "/Script/GameForgeRuntime.GameForgeQuestGiver", "label": "GF_QuestGiver", "location": GIVER},
            {"actor_class": "/Script/GameForgeRuntime.GameForgeGuard", "label": "GF_Guard",
             "location": {"x": 1200, "y": -1400, "z": 120}},
            {"actor_class": "/Script/GameForgeRuntime.GameForgeKitSelfTest", "label": "GF_SelfTest",
             "location": {"x": 0, "y": 0, "z": 300}},
        ]:
            ok.append(link.call("spawn_actor", a).get("ok"))
        for i, spot in enumerate(RELICS):
            ok.append(link.call("spawn_actor", {"actor_class": "/Script/GameForgeRuntime.GameForgePickup",
                                                "label": f"GF_Relic{i}", "location": spot}).get("ok"))
            ok.append(link.call("set_actor_property", {"label": f"GF_Relic{i}", "property": "objective_id",
                                                       "value": "collect_relics"}).get("ok"))
        ok.append(link.call("set_actor_property", {"label": "GF_Guard", "property": "patrol_points", "value": GUARD_ROUTE}).get("ok"))
        ok.append(link.call("set_actor_property", {"label": "GF_SelfTest", "property": "waypoints", "value": WAYPOINTS}).get("ok"))
        ok.append(link.call("nav_rebuild", {}, timeout_s=120).get("ok"))
        ok.append(link.call("save_all", {}).get("ok"))
    finally:
        steps["level_editor_exit"] = link.stop()
    steps["level_ops_ok"] = ok
    return all(ok)


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    tc = UnrealToolchain()
    if ROOT.exists():
        shutil.rmtree(ROOT)
    scaffold = tc.scaffold_cpp_project(ROOT, NAME, default_map=MAP, module_deps=[])
    uproject = Path(scaffold["uproject"])
    shutil.copytree(PLUGIN_SRC, ROOT / "Plugins" / "GameForge",
                    ignore=shutil.ignore_patterns("Binaries", "Intermediate", "__pycache__"))
    data = json.loads(uproject.read_text(encoding="utf-8"))
    for plugin in ("GameForge", "Niagara"):
        if not any(p.get("Name") == plugin for p in data["Plugins"]):
            data["Plugins"].append({"Name": plugin, "Enabled": True})
    uproject.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

    b = tc.build(uproject, f"{NAME}Editor", log_dir=ROOT / "logs")
    steps["editor_build"] = b.to_dict() if hasattr(b, "to_dict") else {"ok": b.ok}
    checks["editor_target_builds"] = bool(b.ok)
    if not b.ok:
        return
    checks["level_built_by_ops"] = build_level(uproject, steps)
    if not checks["level_built_by_ops"]:
        return

    archive = ROOT / "Packaged"
    p = tc.package(uproject, archive)
    steps["package"] = {"ok": p.ok, "data": p.data, "errors": p.errors, "log": p.log_path if hasattr(p, "log_path") else None}
    checks["packages"] = bool(p.ok)
    if not p.ok:
        return
    game_exe = archive / "Windows" / NAME / "Binaries" / "Win64" / f"{NAME}.exe"  # the launcher spawns this binary
    save_dir = archive / "Windows" / NAME / "Saved" / "SaveGames"
    if save_dir.exists():
        shutil.rmtree(save_dir)
    for tag, flag in (("fresh", "-GFKitSelfTest"), ("restore", "-GFKitSelfTestRestore")):
        s = tc.smoke_test_packaged(game_exe, [flag, "-RenderOffscreen", "-ResX=1280", "-ResY=720"],
                                   expect_log="GF_KIT_SELFTEST PASS", timeout_s=240,
                                   log_path=ROOT / f"packaged_{tag}.log")
        text = Path(s.log_path).read_text(encoding="utf-8", errors="replace") if Path(s.log_path).exists() else ""
        steps[f"run_{tag}"] = {"ok": s.ok, "exit": s.exit_code if hasattr(s, "exit_code") else None,
                               "errors": s.errors, "selftest_lines": [l.strip() for l in text.splitlines() if "GF_KIT_SELFTEST" in l][-8:],
                               "gf_events": [l.strip()[:200] for l in text.splitlines() if "GF_EVENT" in l][-20:]}
        checks[f"packaged_{tag}_selftest_pass"] = bool(s.ok)
        if tag == "fresh":
            # Run 1 reported every waypoint "reached" within ~30 ms of wall time; require physically plausible legs
            # (DefaultPawn max speed 1200 cm/s) before accepting the walk as real movement.
            import re as _re
            legs, prev = [], None
            for l in text.splitlines():
                m = _re.search(r"waypoint=(\d+) reached=(\d) leg_s=([\d.]+) world_t=([\d.]+) pawn=(-?\d+),(-?\d+),", l)
                if m:
                    pos, t = (float(m.group(5)), float(m.group(6))), float(m.group(4))
                    if prev:
                        d = ((pos[0] - prev[0][0]) ** 2 + (pos[1] - prev[0][1]) ** 2) ** 0.5
                        legs.append({"to": int(m.group(1)), "reached": m.group(2) == "1", "dist_cm": round(d),
                                     "dt_s": round(t - prev[1], 2), "speed": round(d / max(t - prev[1], 1e-3))})
                    prev = (pos, t)
            steps["legs"] = legs
            checks["walk_physically_plausible"] = bool(legs) and all(g["speed"] <= 1500 for g in legs) and \
                all(g["reached"] for g in legs)
    steps["save_file"] = [str(f) for f in save_dir.glob("*.sav")] if save_dir.exists() else []


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "project": str(ROOT), "checks": {}, "steps": {}}
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
