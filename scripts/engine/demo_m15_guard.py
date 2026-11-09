"""Roadmap M15 (first increment): perception-driven guard NPC in PIE, on a disposable probe copy (plugin m15).

Level: floor + NavMesh + sun, an `AGameForgeGuard` (GameForgeRuntime kit: ACharacter + AAIController with engine AI
Perception sight, NavMesh movement) patrolling two points, and a far PlayerStart. In PIE: the guard patrols; the
player's own pawn walks (NavMesh path) into its view → the guard must SEE it and chase; the pawn then runs far away
(it is faster) → the guard must lose sight, search the last known location, return and resume patrol. Nothing calls
the guard's state directly; read-back is `pie_actor_state` on the live actor plus GF_EVENT lines in the log.

Evidence: reports/m15_guard_demo.json (+ PIE capture). Usage: python scripts/engine/demo_m15_guard.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
sys.path.insert(0, str(REPO / "scripts" / "engine"))

import demo_m11_landscape as land  # noqa: E402

REPORT = REPO / "reports" / "m15_guard_demo.json"
GUARD_CLASS = "/Script/GameForgeRuntime.GameForgeGuard"
PROPS = ["current_state_name", "target_name", "patrol_index", "state_log", "patrol_log", "last_move_request",
         "last_move_result", "move_requests"]
ROUTE = [{"x": -800, "y": -800, "z": 100}, {"x": 800, "y": -800, "z": 100}]
EXPECTED = ["Patrol->Chase", "Chase->Search", "Search->Return", "Return->Patrol"]


def guard_state(link) -> dict:
    data = link.call("pie_actor_state", {"actor_class": GUARD_CLASS, "properties": PROPS}).get("data") or {}
    return (data.get("actors") or [{}])[0]


def wait_for(link, pred, timeout_s: float, series: list, tag: str) -> dict:
    t0, g = time.time(), {}
    while time.time() - t0 < timeout_s:
        g = guard_state(link)
        series.append({"phase": tag, "t": round(time.time() - t0, 1), "state": g.get("current_state_name"),
                       "target": g.get("target_name"), "patrol_index": g.get("patrol_index"),
                       "req": g.get("last_move_request"), "res": g.get("last_move_result"), "n": g.get("move_requests")})
        if pred(g):
            return g
        time.sleep(0.5)
    return g


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PLUGIN_BUILD = (get_settings().require_dev("validation_root") / r"GameForgePlugin_m15")
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m15_guard_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    log_path = land.PROJECT_DIR / "landscape_editor_guard.log"
    link = land.start(uproject, "guard")
    series = []
    try:
        link.call("new_level", {"level_path": "/Game/M15/Maps/GuardTest"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 80, "y": 80, "z": 1}})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "mobility": "Movable", "rotation": {"pitch": -45, "yaw": 30, "roll": 0},
                                  "location": {"x": 0, "y": 0, "z": 800}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart",
                                  "location": {"x": 3000, "y": 3000, "z": 120}})
        link.call("spawn_actor", {"actor_class": "NavMeshBoundsVolume", "label": "GF_NavBounds",
                                  "location": {"x": 0, "y": 0, "z": 100}, "scale": {"x": 40, "y": 40, "z": 4}})
        g = link.call("spawn_actor", {"actor_class": GUARD_CLASS, "label": "GF_Guard", "location": {"x": -800, "y": -800, "z": 120}})
        r = link.call("set_actor_property", {"label": "GF_Guard", "property": "patrol_points", "value": ROUTE})
        steps["guard"] = {"spawn": g.get("ok"), "errors": g.get("errors"), "route": (r.get("data") or {}).get("value")}
        checks["guard_placed_with_route"] = bool(g.get("ok")) and bool(r.get("ok"))
        steps["nav"] = link.call("nav_rebuild", {}, timeout_s=120).get("ok")
        link.call("save_all", {})

        link.call("pie_start", {})
        time.sleep(3.0)
        first = wait_for(link, lambda s: len(s.get("patrol_log") or []) >= 2, 25.0, series, "patrol")
        steps["patrol_before_contact"] = first.get("patrol_log")
        checks["patrols_between_points_unprovoked"] = len(first.get("patrol_log") or []) >= 2 and \
            first.get("current_state_name") == "Patrol"

        # Walk the player's pawn onto the route, ahead of the guard, until it is seen.
        chased = {}
        for spot in ({"x": 1300, "y": -800, "z": 120}, {"x": -1300, "y": -800, "z": 120}, {"x": 0, "y": -300, "z": 120}):
            link.call("pie_move_player_to", {"location": spot})
            chased = wait_for(link, lambda s: s.get("current_state_name") == "Chase", 10.0, series, f"approach {spot['x']}")
            if chased.get("current_state_name") == "Chase":
                break
        steps["chase_state"] = {k: chased.get(k) for k in ("current_state_name", "target_name")}
        checks["sees_and_chases_player_pawn"] = chased.get("current_state_name") == "Chase" and \
            "Pawn" in str(chased.get("target_name"))
        link.call("pie_view_from", {"location": {"x": -2200, "y": -2200, "z": 1200}, "rotation": {"pitch": -25, "yaw": 45, "roll": 0}})
        shot = link.capture_screenshot(land.PROJECT_DIR / "Saved" / "Screenshots" / "m15_guard_chase.png", wait_s=20.0, show_ui=True)
        steps["screenshot"] = (shot.get("data") or {}).get("path")

        # Escape: the default pawn is faster than the guard's chase speed.
        link.call("pie_move_player_to", {"location": {"x": 3500, "y": 3500, "z": 120}})
        searched = wait_for(link, lambda s: s.get("current_state_name") in ("Search", "Return", "Patrol") and
                            any("Chase->Search" in e for e in (s.get("state_log") or [])), 20.0, series, "escape")
        back = wait_for(link, lambda s: any("Return->Patrol" in e for e in (s.get("state_log") or [])), 30.0, series, "return")
        steps["state_log"] = back.get("state_log")
        steps["patrol_log_final"] = back.get("patrol_log")
        transitions = [e.split()[0] for e in (back.get("state_log") or [])]
        it = iter(transitions)
        checks["loses_sight_searches_returns_patrols_in_order"] = all(any(t == want for t in it) for want in EXPECTED)
        # Run 2 passed this with an empty patrol log on both sides; require real arrivals after the return.
        n_back = len(back.get("patrol_log") or [])
        resumed = wait_for(link, lambda s: len(s.get("patrol_log") or []) >= n_back + 1, 20.0, series, "resume")
        steps["patrol_log_after_resume"] = resumed.get("patrol_log")
        checks["patrol_resumed_after_return"] = len(resumed.get("patrol_log") or []) >= n_back + 1 and \
            len(resumed.get("patrol_log") or []) > len(steps["patrol_before_contact"] or [])
        steps["searched"] = searched.get("current_state_name")
        link.call("pie_stop", {})
    finally:
        rep["editor_exit_code"] = link.stop()
        steps["series"] = series
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    steps["gf_events"] = re.findall(r"GF_EVENT guard_state .*", text)
    checks["gf_events_logged"] = len(steps["gf_events"]) >= 4


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["Behavior Tree / StateTree assets (logic is native C++ for now)", "hearing sense", "packaged build"]}
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
