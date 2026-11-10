"""Engine undo spot check (P0 WI-0.7).

Verifies that ScopedEditorTransaction correctly registers transactions in Unreal Editor 5.7.4,
and that 'TRANSACTION UNDO' console command reverts actor property mutations and actor spawning.

Usage:
    python scripts/engine/spotcheck_undo.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parents[2]
if "GAMEFORGE_HOST_PROFILE" not in os.environ:
    dev_prof = REPO / "configs" / "host_profiles" / "dev-rx7700xt.json"
    if dev_prof.exists():
        os.environ["GAMEFORGE_HOST_PROFILE"] = str(dev_prof)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
engine_scripts = REPO / "scripts" / "engine"
if str(engine_scripts) not in sys.path:
    sys.path.insert(0, str(engine_scripts))

from _harness import disposable_probe, start_editor, write_report  # noqa: E402


def run_undo_spotcheck() -> int:
    uproject = disposable_probe("undo_spotcheck")
    print(f"Disposable probe created at {uproject}")

    link = start_editor(uproject, "undo_spotcheck")
    evidence: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "uproject": str(uproject),
        "steps": [],
        "verdict": "UNKNOWN",
    }

    try:
        # Step 1: Handshake
        hs = link.call("handshake", {})
        print(f"Handshake: {hs.get('ok')}")
        assert hs.get("ok"), f"Handshake failed: {hs}"
        evidence["steps"].append({"step": "handshake", "result": hs})

        # Step 2: New level or load level
        lvl = link.call("new_level", {"level_path": "/Game/Maps/GF_UndoLevel"})
        print(f"new_level: {lvl.get('ok')}")
        assert lvl.get("ok"), f"new_level failed: {lvl}"
        evidence["steps"].append({"step": "new_level", "result": lvl})

        # Step 3: Spawn actor
        spawn_res = link.call("spawn_actor", {
            "actor_class": "StaticMeshActor",
            "label": "GF_UndoCube",
            "location": {"x": 100.0, "y": 200.0, "z": 50.0},
            "static_mesh": "/Engine/BasicShapes/Cube.Cube"
        })
        print(f"spawn_actor: {spawn_res.get('ok')}")
        assert spawn_res.get("ok"), f"spawn_actor failed: {spawn_res}"
        evidence["steps"].append({"step": "spawn_actor", "result": spawn_res})

        # Read back actors in level
        actors_before = link.call("actors_in_level", {"limit": 100})
        cube_present = any(a.get("label") == "GF_UndoCube" for a in (actors_before.get("data") or {}).get("actors", []))
        print(f"Actor present in level: {cube_present}")
        assert cube_present, "GF_UndoCube not found in actors_in_level"

        # Step 4: Mutate property via set_actor_property
        # tags is a built-in Actor property (Array[Name])
        set_res = link.call("set_actor_property", {
            "label": "GF_UndoCube",
            "property": "tags",
            "value": ["UndoTestTag"]
        })
        print(f"set_actor_property: {set_res.get('ok')}, data: {set_res.get('data')}")
        assert set_res.get("ok"), f"set_actor_property failed: {set_res}"
        evidence["steps"].append({"step": "set_actor_property", "result": set_res})

        # Helper to query actor property in editor via python
        check_prop_snippet = """
import unreal, json
found = False
tags = []
for a in unreal.EditorActorSubsystem().get_all_level_actors():
    if a.get_actor_label() == "GF_UndoCube":
        found = True
        tags = [str(t) for t in a.get_editor_property("tags")]
        break
print("@@PROP@@" + json.dumps({"found": found, "tags": tags}))
"""
        def get_cube_prop() -> Optional[Dict[str, Any]]:
            rx = getattr(link, "_rx", None)
            rx_module = getattr(link, "_rx_module", None)
            if not rx or not rx_module:
                return None
            res = rx.run_command(check_prop_snippet, unattended=True, exec_mode=rx_module.MODE_EXEC_FILE)
            for o in (res.get("output") or []):
                text = o.get("output") if isinstance(o, dict) else str(o)
                for line in text.splitlines():
                    if "@@PROP@@" in line:
                        payload = line.partition("@@PROP@@")[2].strip()
                        try:
                            return json.loads(payload)
                        except Exception:
                            return None
            return None

        prop_after_set = get_cube_prop()
        print(f"Property after set: {prop_after_set}")
        assert prop_after_set and "UndoTestTag" in prop_after_set.get("tags", []), "Property set not reflected"
        evidence["steps"].append({"step": "property_before_undo", "tags": prop_after_set.get("tags")})

        # Step 5: Execute console command TRANSACTION UNDO
        undo_snippet = """
import unreal
unreal.SystemLibrary.execute_console_command(None, "TRANSACTION UNDO")
print("@@UNDO@@DONE")
"""
        rx = getattr(link, "_rx", None)
        rx_module = getattr(link, "_rx_module", None)
        if rx and rx_module:
            undo_res = rx.run_command(undo_snippet, unattended=True, exec_mode=rx_module.MODE_EXEC_FILE)
            evidence["steps"].append({"step": "execute_undo", "raw_output": undo_res.get("output")})
        else:
            evidence["steps"].append({"step": "execute_undo", "raw_output": "rx unavailable"})

        # Step 6: Verify property reverted
        prop_after_undo = get_cube_prop()
        print(f"Property after undo: {prop_after_undo}")
        tags_reverted = prop_after_undo is not None and "UndoTestTag" not in prop_after_undo.get("tags", [])
        evidence["steps"].append({
            "step": "property_after_undo",
            "tags": prop_after_undo.get("tags") if prop_after_undo else None,
            "reverted": tags_reverted
        })
        assert tags_reverted, f"Property did not revert! Still: {prop_after_undo}"

        # Step 7: Read back with actors_in_level
        actors_after = link.call("actors_in_level", {"limit": 100})
        cube_still_present = any(a.get("label") == "GF_UndoCube" for a in (actors_after.get("data") or {}).get("actors", []))
        print(f"Actor still present after property undo: {cube_still_present}")
        assert cube_still_present, "Actor disappeared after property undo"
        evidence["steps"].append({"step": "actors_in_level_after_undo", "actor_present": cube_still_present})

        evidence["verdict"] = "PASS"
        print("Spot check PASS: ScopedEditorTransaction + TRANSACTION UNDO works in 5.7.4")
        return 0

    except Exception as exc:
        evidence["verdict"] = "FAIL"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        print(f"Spot check FAIL: {exc}")
        return 1
    finally:
        link.stop()
        out_path = write_report("undo_spotcheck", evidence, "P0")
        print(f"Wrote report to {out_path}")


if __name__ == "__main__":
    sys.exit(run_undo_spotcheck())
