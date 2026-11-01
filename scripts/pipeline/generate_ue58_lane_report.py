"""Generate UE 5.8 compatibility lane report (WI-10.6)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = REPO_ROOT / "reports" / "P10"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.unreal.mcp_bridge import verify_port_coexistence


def record_ue58_lane() -> dict:
    s = get_settings()
    port_check = verify_port_coexistence(editor_port=s.bridge_port, mcp_port=8000)

    report = {
        "status": "BLOCKED (needs approval: UE 5.8 installation; compatibility harness ready)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pinned_engine": {
            "version": s.engine.version if s.engine else "5.7.4",
            "root": str(s.engine.root) if s.engine else "",
            "channel": getattr(s, "engine_channel", "pinned"),
        },
        "ue58_target": {
            "channel": "next",
            "installed": False,
            "reason": "Requires user approval for secondary engine install on E:/UE/UE_5.8.",
        },
        "mcp_bridge": {
            "read_only_client": "src/gameforge_ide/unreal/mcp_bridge.py",
            "port_coexistence": port_check,
            "editor_port": s.bridge_port,
            "mcp_port": 8000,
        },
        "cpp_compatibility": {
            "macro_guards": "#if ENGINE_MINOR_VERSION >= 8",
            "ai_callable_meta": "meta=(AICallable) on read-only UFUNCTIONs",
        },
    }

    out_file = REPORTS_DIR / "ue58_lane.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"UE 5.8 lane report saved to {out_file}")
    print(f"Port coexistence: {port_check['status']} | Engine channel: {getattr(s, 'engine_channel', 'pinned')}")
    return report


if __name__ == "__main__":
    record_ue58_lane()
