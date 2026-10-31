"""Roadmap M13 + M14 acceptance: VFX and spatialized SFX triggered by a real gameplay event in PIE.

Disposable probe copy (plugin build m14v2), editor with sound enabled. Level: floor + NavMesh + PlayerStart and an
`AGameForgePickup` (GameForgeRuntime kit actor) with CollectVFX = NS_GFExplosion, CollectSound = a procedurally
synthesized pickup chime (imported as a SoundWave) and CollectAttenuation = ATT_GFPickup (inner 300 / falloff 2500).
In PIE the player's own pawn walks a NavMesh path into the pickup; nothing calls the VFX or audio directly.
Checks: nothing plays before the event; the overlap logs `GF_EVENT pickup` naming the player pawn with VFX and
sound spawned; the live actor reads back collected=True, its audio component playing right after the event and
finished ~1.5 s later (0.35 s one-shot), the effect has live particles, and the sound uses the attenuation asset.

Evidence: reports/gameplay_feedback_demo.json (+ PIE capture). Supersedes scripts/demo_m13_gameplay_vfx.py
(whose evidence, reports/m13_gameplay_vfx_demo.json, used the earlier AGameForgeVFXPickup class).
Usage: python scripts/demo_gameplay_feedback.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import demo_m11_landscape as land  # noqa: E402
from src.gameforge_ide.backend.tools.sfx_synth import SFXSpec, generate_sfx  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "gameplay_feedback_demo.json"
SYSTEM = "/Game/Feedback/VFX/NS_GFExplosion"
SOUND = "/Game/Feedback/Audio/SFX_Pickup"
ATT = "/Game/Feedback/Audio/ATT_GFPickup"
PICKUP_CLASS = "/Script/GameForgeRuntime.GameForgePickup"
PICKUP_AT = {"x": 300, "y": 0, "z": 100}
STATE_PROPS = ["collected", "collected_by", "spawned_vfx", "spawned_sound", "collect_attenuation"]


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PLUGIN_BUILD = Path(r"E:\GameForge\validation\GameForgePlugin_m14v2")
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "gameplay_feedback_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    chime = generate_sfx(SFXSpec(name="Pickup", kind="pickup", seed=4), land.PROJECT_DIR / "SourceAudio")
    steps["sfx"] = {"path": chime["path"], "sha256": chime["sha256"], "analysis": chime["analysis"]}
    log_path = land.PROJECT_DIR / "feedback_editor.log"
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=log_path, no_sound=False)
    try:
        link.connect(discovery_timeout_s=900)
        link.call("new_level", {"level_path": "/Game/Feedback/Maps/PickupTest"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 30, "y": 30, "z": 1}})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "mobility": "Movable", "rotation": {"pitch": -45, "yaw": 30, "roll": 0},
                                  "location": {"x": 0, "y": 0, "z": 800}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart",
                                  "location": {"x": -600, "y": 0, "z": 120}})
        link.call("spawn_actor", {"actor_class": "NavMeshBoundsVolume", "label": "GF_NavBounds",
                                  "location": {"x": 0, "y": 0, "z": 100}, "scale": {"x": 15, "y": 15, "z": 4}})
        sysr = link.call("vfx_create_system", {"asset_path": SYSTEM, "template_system": "SimpleExplosion"}, timeout_s=120)
        att = link.call("audio_create_attenuation", {"asset_path": ATT, "inner_radius": 300, "falloff_distance": 2500})
        imp = link.call("audio_import", {"source_file": chime["path"], "destination_path": SOUND.rsplit("/", 1)[0],
                                         "destination_name": SOUND.rsplit("/", 1)[1], "looping": False}, timeout_s=120)
        checks["assets_created"] = all(bool(r.get("ok")) for r in (sysr, att, imp))
        steps["assets"] = {"vfx": sysr.get("errors"), "attenuation": att.get("errors"), "sound": imp.get("errors")}
        pick = link.call("spawn_actor", {"actor_class": PICKUP_CLASS, "label": "GF_Pickup", "location": PICKUP_AT})
        sets = {prop: link.call("set_actor_property", {"label": "GF_Pickup", "property": prop, "value": value, "asset": True})
                for prop, value in (("collect_vfx", SYSTEM), ("collect_sound", SOUND), ("collect_attenuation", ATT))}
        steps["pickup"] = {"spawn": pick.get("ok"), "errors": pick.get("errors"),
                           "set": {k: (v.get("data") or {}).get("value") for k, v in sets.items()}}
        checks["pickup_configured"] = bool(pick.get("ok")) and all(v.get("ok") for v in sets.values())
        steps["nav_rebuild"] = link.call("nav_rebuild", {}, timeout_s=120).get("data")
        link.call("save_all", {})

        link.call("pie_start", {})
        time.sleep(6.0)
        before = link.call("pie_actor_state", {"actor_class": PICKUP_CLASS, "properties": STATE_PROPS}).get("data") or {}
        steps["state_before"] = before
        b = (before.get("actors") or [{}])[0]
        checks["nothing_before_event"] = b.get("collected") is False and b.get("spawned_sound") is None \
            and b.get("spawned_vfx") is None

        move = link.call("pie_move_player_to", {"location": PICKUP_AT})
        steps["move"] = {"ok": move.get("ok"), "data": move.get("data"), "errors": move.get("errors")}
        after, peak, series, shot = {}, 0, [], None
        # Run 1 missed the 0.35 s chime: a slow screenshot sat between polls. Poll the actor tightly until the
        # event happens, so the sound's playing state is read while it is still playing.
        t0 = time.time()
        while time.time() - t0 < 10.0 and not after:
            s = link.call("pie_actor_state", {"actor_class": PICKUP_CLASS, "properties": STATE_PROPS}).get("data") or {}
            a = (s.get("actors") or [{}])[0]
            if a.get("collected"):
                after = a
                series.append({"t": round(time.time() - t0, 2), "sound_playing": (a.get("spawned_sound") or {}).get("playing")})
        t0 = time.time()
        while time.time() - t0 < 10.0:
            s = link.call("pie_actor_state", {"actor_class": PICKUP_CLASS, "properties": STATE_PROPS}).get("data") or {}
            a = (s.get("actors") or [{}])[0]
            c = link.call("vfx_particle_counts", {"world": "pie", "label": "Pickup"})
            n = int((c.get("data") or {}).get("total_particles", 0) or 0)
            peak = max(peak, n)
            series.append({"t": round(time.time() - t0, 2), "particles": n,
                           "sound_playing": (a.get("spawned_sound") or {}).get("playing")})
            if n > 0 and shot is None:
                link.call("pie_view_from", {"location": {"x": -300, "y": 0, "z": 300},
                                            "rotation": {"pitch": -20, "yaw": 0, "roll": 0}})
                shot = link.capture_screenshot(land.PROJECT_DIR / "Saved" / "Screenshots" / "gameplay_feedback.png",
                                               wait_s=20.0, show_ui=True)
            if after and time.time() - t0 > 4.0:
                break
            time.sleep(0.2)
        time.sleep(1.5)
        final = link.call("pie_actor_state", {"actor_class": PICKUP_CLASS, "properties": STATE_PROPS}).get("data") or {}
        steps.update(state_first_collected=after, state_final=final, series=series, particle_peak=peak,
                     screenshot=(shot or {}).get("data"))
        link.call("pie_stop", {})
    finally:
        rep["editor_exit_code"] = link.stop()

    f = (steps.get("state_final", {}).get("actors") or [{}])[0]
    first = steps.get("state_first_collected") or {}
    checks["collected_by_player_pawn"] = bool(first.get("collected")) and "Pawn" in str(first.get("collected_by"))
    checks["sound_playing_right_after_event"] = any(s.get("sound_playing") for s in steps.get("series", []))
    checks["one_shot_sound_finished_later"] = (f.get("spawned_sound") or {}).get("playing") is False
    checks["sound_is_the_pickup_chime"] = SOUND in str((first.get("spawned_sound") or {}).get("sound"))
    checks["attenuation_asset_bound"] = ATT in str(first.get("collect_attenuation"))
    checks["effect_has_live_particles"] = steps.get("particle_peak", 0) > 0
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    events = re.findall(r"GF_EVENT pickup .*", text)
    steps["gf_events"] = events
    checks["gf_event_logged_with_vfx_and_sound"] = any("spawned=1" in e and "sound=SFX_Pickup" in e and
                                                       "sound_playing=1" in e for e in events)


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["packaged build", "stat Niagara cost", "audible output measurement (no loopback capture)"]}
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
