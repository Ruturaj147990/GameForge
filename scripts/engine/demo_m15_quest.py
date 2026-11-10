"""Roadmap M15 acceptance (part 2): quest giver → objective → pickups → save/load across game sessions, in PIE.

Disposable probe copy (plugin m15b). Level: a quest giver (`AGameForgeQuestGiver`) and two relic pickups
(`AGameForgePickup` with ObjectiveId=collect_relics) on a NavMesh floor. Session 1: the player's pawn walks to the
giver (dialogue + objective starts), collects both relics (progress 1/2, 2/2 → Completed), returns (turn-in line).
Every change is written to the USaveGame slot. Session 2 (new PIE = new GameInstance): the subsystem must load the
slot, report the objective Completed 2/2, and the giver must go straight to the turn-in line.

Evidence: reports/m15_quest_demo.json. Usage: python scripts/engine/demo_m15_quest.py
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ENGINE_SCRIPTS = str(REPO / "scripts" / "engine")
if ENGINE_SCRIPTS not in sys.path:
    sys.path.insert(0, ENGINE_SCRIPTS)

from src.gameforge_ide.core.settings import get_settings  # noqa: E402

REPORT = REPO / "reports" / "m15_quest_demo.json"
GIVER_CLASS = "/Script/GameForgeRuntime.GameForgeQuestGiver"
GIVER, RELICS = {"x": -700, "y": 0, "z": 100}, [{"x": 300, "y": 600, "z": 100}, {"x": 300, "y": -600, "z": 100}]
QUEST = "collect_relics"
QUEST_CONTENT = {"objective_id": QUEST, "objective_title": "Recover the relics", "objective_target": 2,
                 "intro_lines": ["Traveller! Thieves scattered our relics.", "Bring two of them back, please."],
                 "turn_in_line": "You found them all. Thank you!"}


def objective(link: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    res = link.call("gameplay_objectives", {}) or {}
    data = res.get("data") or {}
    obj = next((o for o in data.get("objectives", []) if o.get("id") == QUEST), {})
    return data, obj


def spoken(link: Any) -> List[str]:
    res = link.call("pie_actor_state", {"actor_class": GIVER_CLASS, "properties": ["spoken_lines"]}) or {}
    d = res.get("data") or {}
    actors = d.get("actors") or []
    if actors and isinstance(actors[0], dict):
        return actors[0].get("spoken_lines") or []
    return []


def walk_until(link: Any, spot: Dict[str, Any], pred: Callable[[], bool], timeout_s: float = 15.0) -> bool:
    link.call("pie_move_player_to", {"location": spot})
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if pred():
            return True
        time.sleep(0.3)
    return False


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_landscape as land

    checks, steps = rep["checks"], rep["steps"]
    try:
        val_root = get_settings().require_dev("validation_root")
    except Exception:
        val_root = REPO / "scratch" / "validation"

    land.PLUGIN_BUILD = val_root / "GameForgePlugin_neutral"
    land.PROJECT_DIR = val_root / f"m15_quest_{time.strftime('%Y%m%d')}"
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    save_file = land.PROJECT_DIR / "Saved" / "SaveGames" / "GF_Objectives.sav"
    log_path = land.PROJECT_DIR / "landscape_editor_quest.log"
    link = land.start(uproject, "quest")
    try:
        link.call("new_level", {"level_path": "/Game/M15/Maps/QuestTest"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 50, "y": 50, "z": 1}})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "mobility": "Movable", "rotation": {"pitch": -45, "yaw": 30, "roll": 0},
                                  "location": {"x": 0, "y": 0, "z": 800}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart", "location": {"x": -1600, "y": 0, "z": 120}})
        link.call("spawn_actor", {"actor_class": "NavMeshBoundsVolume", "label": "GF_NavBounds",
                                  "location": {"x": 0, "y": 0, "z": 100}, "scale": {"x": 25, "y": 25, "z": 4}})
        g = link.call("spawn_actor", {"actor_class": GIVER_CLASS, "label": "GF_QuestGiver", "location": GIVER}) or {}
        placed = [bool(g.get("ok"))]
        for prop, value in QUEST_CONTENT.items():
            r = link.call("set_actor_property", {"label": "GF_QuestGiver", "property": prop, "value": value}) or {}
            placed.append(bool(r.get("ok")))
        for i, spot in enumerate(RELICS):
            p = link.call("spawn_actor", {"actor_class": "/Script/GameForgeRuntime.GameForgePickup", "label": f"GF_Relic{i}",
                                          "location": spot}) or {}
            s = link.call("set_actor_property", {"label": f"GF_Relic{i}", "property": "objective_id", "value": QUEST}) or {}
            placed += [bool(p.get("ok")), bool(s.get("ok"))]
        checks["quest_actors_placed"] = all(placed)
        link.call("nav_rebuild", {}, timeout_s=120)
        link.call("save_all", {})

        # Session 1
        link.call("pie_start", {})
        try:
            time.sleep(4.0)
            data, obj = objective(link)
            steps["s1_start"] = data
            checks["s1_starts_without_save"] = data.get("loaded_from_slot") is False and not obj
            walk_until(link, GIVER, lambda: objective(link)[1].get("state") == "Active")
            steps["s1_after_talk"] = {"objective": objective(link)[1], "spoken": spoken(link)}
            checks["talking_starts_objective_with_dialogue"] = steps["s1_after_talk"]["objective"].get("state") == "Active" \
                and len(steps["s1_after_talk"]["spoken"]) == 2
            walk_until(link, RELICS[0], lambda: objective(link)[1].get("progress") == 1)
            steps["s1_after_relic1"] = objective(link)[1]
            walk_until(link, RELICS[1], lambda: objective(link)[1].get("state") == "Completed")
            steps["s1_after_relic2"] = objective(link)[1]
            checks["relics_advance_and_complete_objective"] = steps["s1_after_relic1"].get("progress") == 1 and \
                steps["s1_after_relic2"].get("state") == "Completed" and steps["s1_after_relic2"].get("progress") == 2
            walk_until(link, GIVER, lambda: len(spoken(link)) >= 3)
            steps["s1_turn_in"] = spoken(link)
            checks["turn_in_dialogue_after_completion"] = len(steps["s1_turn_in"]) == 3 and "found them all" in steps["s1_turn_in"][-1]
        finally:
            with contextlib.suppress(Exception):
                link.call("pie_stop", {})

        time.sleep(2.0)
        steps["save_file"] = {"exists": save_file.exists(), "bytes": save_file.stat().st_size if save_file.exists() else 0}
        checks["save_slot_written_to_disk"] = save_file.exists() and save_file.stat().st_size > 0

        # Session 2: new GameInstance must restore the quest from the slot
        link.call("pie_start", {})
        try:
            time.sleep(4.0)
            data, obj = objective(link)
            steps["s2_start"] = data
            checks["s2_restores_completed_objective_from_slot"] = data.get("loaded_from_slot") is True and \
                obj.get("state") == "Completed" and obj.get("progress") == 2
            walk_until(link, GIVER, lambda: len(spoken(link)) >= 1)
            steps["s2_spoken"] = spoken(link)
            checks["s2_giver_uses_restored_state"] = steps["s2_spoken"] == ["You found them all. Thank you!"]
        finally:
            with contextlib.suppress(Exception):
                link.call("pie_stop", {})
    finally:
        rep["editor_exit_code"] = link.stop()
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    steps["gf_events"] = re.findall(r"GF_EVENT (?:objective_\w+|dialogue) .*", text)


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["dialogue UI (lines are logged/read back, not shown on screen)", "branching dialogue", "packaged build"]}
    try:
        run(rep)
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        tmp_report = REPORT.with_suffix(".tmp")
        tmp_report.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        os.replace(tmp_report, REPORT)
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
