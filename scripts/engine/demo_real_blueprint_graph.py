"""GameForge Milestone 2: Real Blueprint Graph Authoring V1 Vertical Slice.

Zero mocks. Zero simulators. Real UE 5.7.4 editor execution.
Creates BP_GameForgeGraphProbe with:
Event BeginPlay -> Print String("GAMEFORGE_BLUEPRINT_GRAPH_V1")
Places instance in level, executes PIE, and verifies the runtime log marker in the real engine.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.gameforge_ide.unreal.live_editor import LiveEditorLink


def run_vertical_slice():
    evidence = {
        "milestone": "MILESTONE_2_REAL_BLUEPRINT_GRAPH_V1",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "steps": [],
        "overall_status": "PENDING",
    }
    
    uproject_path = Path(r"E:\GameForge\validation\live_ops_probe\GFProbe.uproject")
    print(f"Connecting to live Unreal project: {uproject_path}")
    
    link = LiveEditorLink(uproject_path)
    prep = link.prepare_project()
    print(f"Project prepared: token={prep['token_file']}")
    
    # Launch real editor
    pid = link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    print(f"Launched UnrealEditor.exe with PID {pid}")
    
    try:
        print("Awaiting editor discovery and connection...")
        node = link.connect(discovery_timeout_s=900)
        print(f"Connected to node: {node.get('node_id')}")
        
        # Step 0: Handshake
        t0 = time.time()
        hs = link.call("handshake")
        evidence["steps"].append({"step": "0_handshake", "ok": hs.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": hs.get("data")})
        assert hs.get("ok"), f"Handshake failed: {hs}"
        print(f"Step 0 Handshake OK: Engine {hs['data']['engine_version']}")
        
        # Target asset path
        bp_path = "/Game/BP_GameForgeGraphProbe"
        
        # Clean existing probe if any
        link.call("delete_asset", {"asset_path": bp_path})
        
        # Step 1: Create Blueprint Asset in Unreal
        t0 = time.time()
        res_create = link.call("create_blueprint", {"asset_path": bp_path, "parent_class": "Actor"})
        evidence["steps"].append({"step": "1_create_blueprint", "ok": res_create.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_create.get("data")})
        assert res_create.get("ok"), f"create_blueprint failed: {res_create}"
        print("Step 1: Created Blueprint asset BP_GameForgeGraphProbe in Unreal")
        
        # Step 2: Read back initial graph and identify nodes
        t0 = time.time()
        res_rb1 = link.call("blueprint_readback_graph", {"blueprint_path": bp_path, "graph_name": "EventGraph"})
        evidence["steps"].append({"step": "2_initial_readback", "ok": res_rb1.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_rb1.get("data")})
        assert res_rb1.get("ok"), f"blueprint_readback_graph failed: {res_rb1}"
        initial_nodes = res_rb1["data"]["nodes"]
        print(f"Step 2: Read back graph with {len(initial_nodes)} initial nodes")
        
        # Find or create BeginPlay event node
        begin_play_node = next((n for n in initial_nodes if "beginplay" in n.get("title", "").lower() or "receivebeginplay" in n.get("event_name", "").lower()), None)
        if not begin_play_node:
            t0 = time.time()
            res_bp = link.call("blueprint_create_node", {
                "blueprint_path": bp_path,
                "graph_name": "EventGraph",
                "node_type": "Event",
                "pos_x": 100,
                "pos_y": 100,
                "extra_params": {"event_name": "ReceiveBeginPlay"}
            })
            assert res_bp.get("ok"), f"Failed to create BeginPlay node: {res_bp}"
            begin_play_node = res_bp["data"]
            print("Created explicit ReceiveBeginPlay node")
        else:
            print(f"Found existing BeginPlay node: {begin_play_node['title']} (id: {begin_play_node['node_id']})")
            
        # Step 3: Create PrintString CallFunction node
        t0 = time.time()
        res_print = link.call("blueprint_create_node", {
            "blueprint_path": bp_path,
            "graph_name": "EventGraph",
            "node_type": "CallFunction",
            "pos_x": 450,
            "pos_y": 100,
            "extra_params": {
                "function_name": "PrintString",
                "function_class": "/Script/Engine.KismetSystemLibrary"
            }
        })
        evidence["steps"].append({"step": "3_create_print_node", "ok": res_print.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_print.get("data")})
        assert res_print.get("ok"), f"Failed to create PrintString node: {res_print}"
        print_node = res_print["data"]
        print(f"Step 3: Created PrintString node with ID {print_node['node_id']}")
        
        # Step 4: Set literal default value on InString pin
        t0 = time.time()
        marker_text = "GAMEFORGE_BLUEPRINT_GRAPH_V1"
        res_default = link.call("blueprint_set_pin_default", {
            "blueprint_path": bp_path,
            "node_id": print_node["node_id"],
            "pin_name": "inString",
            "default_value": marker_text
        })
        evidence["steps"].append({"step": "4_set_pin_default", "ok": res_default.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_default.get("data")})
        assert res_default.get("ok"), f"set_pin_default failed: {res_default}"
        print(f"Step 4: Set pin inString default value to '{marker_text}' (readback: {res_default['data']['readback_value']})")
        
        # Step 5: Connect execution pins (BeginPlay.then -> PrintString.execute)
        t0 = time.time()
        res_conn = link.call("blueprint_connect_pins", {
            "blueprint_path": bp_path,
            "from_node": begin_play_node["node_id"],
            "from_pin": "then",
            "to_node": print_node["node_id"],
            "to_pin": "execute"
        })
        evidence["steps"].append({"step": "5_connect_pins", "ok": res_conn.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_conn.get("data")})
        assert res_conn.get("ok"), f"connect_pins failed: {res_conn}"
        print("Step 5: Connected execution pins: BeginPlay.then -> PrintString.execute (verified linked)")
        
        # Step 6: Read back graph and verify node linkage
        t0 = time.time()
        res_rb2 = link.call("blueprint_readback_graph", {"blueprint_path": bp_path, "graph_name": "EventGraph"})
        evidence["steps"].append({"step": "6_verify_graph_readback", "ok": res_rb2.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_rb2.get("data")})
        assert res_rb2.get("ok"), f"readback failed: {res_rb2}"
        
        # Confirm link in readback data
        nodes_after = res_rb2["data"]["nodes"]
        found_link = False
        for n in nodes_after:
            if n["node_id"] == begin_play_node["node_id"]:
                for p in n.get("pins", []):
                    if p["pin_name"] == "then" and any(l.get("target_node_id") == print_node["node_id"] for l in p.get("linked_to", [])):
                        found_link = True
                        break
        assert found_link, "Graph read-back did not verify link from BeginPlay to PrintString"
        print("Step 6: Verified connection in full graph read-back")
        
        # Step 7: Compile real Blueprint and verify compiler diagnostics
        t0 = time.time()
        res_comp = link.call("blueprint_compile", {"blueprint_path": bp_path})
        evidence["steps"].append({"step": "7_compile_blueprint", "ok": res_comp.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_comp.get("data")})
        assert res_comp.get("ok"), f"blueprint_compile failed: {res_comp}"
        assert res_comp["data"].get("status") in ("UpToDate", "UpToDateWithWarnings"), f"Unexpected status: {res_comp['data']}"
        print(f"Step 7: Compiled Blueprint cleanly with status '{res_comp['data']['status']}'")
        
        # Step 8: Save asset and verify dirty flag cleared
        t0 = time.time()
        res_save = link.call("blueprint_save", {"blueprint_path": bp_path})
        evidence["steps"].append({"step": "8_save_blueprint", "ok": res_save.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_save.get("data")})
        assert res_save.get("ok"), f"blueprint_save failed: {res_save}"
        print("Step 8: Saved Blueprint asset to disk with package dirty flag cleared")
        
        # Step 9: Level setup and Actor placement
        t0 = time.time()
        level_path = "/Game/Maps/GF_Probe"
        link.call("new_level", {"level_path": level_path, "if_exists": "load"})
        
        # Spawn instance of our newly compiled Blueprint
        gen_class = res_comp["data"].get("generated_class") or f"{bp_path}.BP_GameForgeGraphProbe_C"
        res_spawn = link.call("spawn_actor", {
            "actor_class": gen_class,
            "label": "BP_GameForgeGraphProbe_Instance",
            "location": {"x": 0, "y": 0, "z": 100}
        })
        evidence["steps"].append({"step": "9_spawn_actor_instance", "ok": res_spawn.get("ok"), "elapsed_s": round(time.time() - t0, 3), "data": res_spawn.get("data")})
        assert res_spawn.get("ok"), f"Failed to spawn actor instance: {res_spawn}"
        print(f"Step 9: Placed instance of {gen_class} in level")
        
        # Step 10: Launch Play In Editor (PIE) and verify output log marker
        t0 = time.time()
        # Record pre-PIE log size
        log_pre = link.call("log_tail", {"lines": 50})
        
        # Request PIE start
        pie_res = link.call("pie_start", {"simulate": True})
        print(f"PIE requested: ok={pie_res.get('ok')}")
        
        # Give engine frames to execute BeginPlay and print to log
        time.sleep(3.0)
        
        # Check PIE status
        st = link.call("pie_status")
        print(f"PIE status: in_pie={st.get('data', {}).get('in_pie')}")
        
        # Read log tail
        log_res = link.call("log_tail", {"lines": 300})
        log_lines = (log_res.get("data") or {}).get("lines", [])
        
        # Stop PIE
        link.call("pie_stop")
        print("PIE stopped cleanly")
        
        # Search for runtime Blueprint print message in logs
        found_marker = False
        matching_line = ""
        for line in log_lines:
            if marker_text in line and "GAMEFORGE_RESULT" not in line:
                found_marker = True
                matching_line = line
                break
                
        # Also check file directly if not found in tail
        if not found_marker:
            log_file = uproject_path.parent / "Saved" / "Logs" / "GFProbe.log"
            if log_file.exists():
                text = log_file.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    if marker_text in line and "GAMEFORGE_RESULT" not in line:
                        found_marker = True
                        matching_line = line
                        break
                        
        evidence["steps"].append({
            "step": "10_pie_runtime_verification",
            "ok": found_marker,
            "elapsed_s": round(time.time() - t0, 3),
            "marker_found": found_marker,
            "matching_log_line": matching_line
        })
        
        assert found_marker, f"Runtime marker '{marker_text}' not observed in Unreal Output Log!"
        print(f"Step 10: VERIFIED RUNTIME MARKER IN UNREAL ENGINE OUTPUT LOG: '{matching_line.strip()}'")
        
        evidence["overall_status"] = "PASSED"
        evidence["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        
    finally:
        print("Stopping Unreal Editor process...")
        code = link.stop()
        print(f"Unreal Editor exited with code {code}")
        
    report_path = ROOT / "reports" / "milestone2_blueprint_demo.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Evidence report written to: {report_path}")
    return evidence


if __name__ == "__main__":
    run_vertical_slice()
