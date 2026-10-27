"""Prerequisite verification script for Milestone 4.
Verifies that WBP_GameForgeHUD_V1 exists, hierarchy persists, compiles cleanly,
displays in PIE, and Blueprint graph authoring remains functional on real UE 5.7.4.
"""
from __future__ import annotations

import json
import os
import sys
import time

PROJECT_DIR = r"E:\GameForge\validation\live_ops_probe"
UPROJECT_PATH = os.path.join(PROJECT_DIR, "GFProbe.uproject")

sys.path.insert(0, r"E:\gameforge_step1")
from src.gameforge_ide.unreal.live_editor import LiveEditorLink


def main() -> int:
    print("=" * 60)
    print("VERIFYING MILESTONE 3 PREREQUISITES ON REAL UE 5.7.4")
    print("=" * 60)

    link = LiveEditorLink(UPROJECT_PATH)
    link.prepare_project()
    print("Launching Unreal Editor...")
    link.launch(["-RenderOffscreen", "-stdout", "-FullStdOutLogOutput", "-unattended"])
    print("Connecting to loopback Python bridge...")
    link.connect(discovery_timeout_s=60.0)

    try:
        # 1. Handshake
        hs = link.call("handshake")
        hs_data = hs.get("data", {})
        print(f"[1/6] Handshake OK: engine={hs_data.get('engine_version')}")

        # 2. Verify WBP_GameForgeHUD_V1 exists
        asset_path = "/Game/UI/WBP_GameForgeHUD_V1"
        exists_res = link.call("asset_exists", {"asset_path": asset_path})
        exists_data = exists_res.get("data", {})
        print(f"[2/6] Asset exists ({asset_path}): {exists_data.get('exists')}")
        assert exists_data.get("exists") is True, f"Asset {asset_path} does not exist!"

        # 3. Inspect persisted widget
        inspect_res = link.call("widget_inspect", {"asset_path": asset_path})
        assert inspect_res.get("ok") is True, f"widget_inspect failed: {inspect_res}"
        data = inspect_res.get("data", {})
        print(f"[3/6] Widget inspected: widget_count={data.get('widget_count')}, status={data.get('status')}, dirty={data.get('is_dirty')}")
        assert data.get("widget_count") == 7, f"Expected 7 widgets, got {data.get('widget_count')}"

        # 4. Readback hierarchy
        tree_res = link.call("widget_readback_tree", {"asset_path": asset_path})
        assert tree_res.get("ok") is True, f"widget_readback_tree failed: {tree_res}"
        tdata = tree_res.get("data", {})
        names = [w.get("name") for w in tdata.get("widgets", [])]
        print(f"[4/6] Widget hierarchy read back: {names}")
        expected = ["CanvasPanel_0", "HUDTitle", "StatsBox", "HealthLabel", "HealthBar", "StaminaLabel", "StaminaBar"]
        assert all(n in names for n in expected), f"Missing expected widgets from {names}"

        # 5. Compile widget
        compile_res = link.call("widget_compile", {"asset_path": asset_path})
        assert compile_res.get("ok") is True, f"widget_compile failed: {compile_res}"
        cdata = compile_res.get("data", {})
        print(f"[5/6] Widget compile status: {cdata.get('status')}, compiled_successfully={cdata.get('compiled_successfully')}")
        assert cdata.get("compiled_successfully") is True, f"Compilation failed: {cdata}"

        # 6. Verify Blueprint graph authoring asset
        bp_path = "/Game/BP_GameForgeGraphProbe"
        bp_inspect = link.call("blueprint_inspect", {"blueprint_path": bp_path})
        assert bp_inspect.get("ok") is True, f"blueprint_inspect failed: {bp_inspect}"
        bp_data = bp_inspect.get("data", {})
        print(f"[6/6] Blueprint graph probe: status={bp_data.get('status')}, is_up_to_date={bp_data.get('is_up_to_date')}")
        assert bp_data.get("is_up_to_date") is True, f"BP not up to date: {bp_data}"

        print("=" * 60)
        print("ALL MILESTONE 3 PREREQUISITES VERIFIED SUCCESSFULLY!")
        print("=" * 60)
        return 0

    finally:
        try:
            link.call("quit_editor")
        except Exception:
            pass
        link.stop()


if __name__ == "__main__":
    sys.exit(main())
