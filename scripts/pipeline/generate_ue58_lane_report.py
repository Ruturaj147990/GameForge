"""Generate UE 5.8 compatibility lane report (WI-10.6)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_REPORTS_DIR = REPO_ROOT / "reports" / "P10"
DEFAULT_REPORT_FILE = DEFAULT_REPORTS_DIR / "ue58_lane.json"
DEFAULT_UE58_CANDIDATE = Path("E:/UE/UE_5.8")

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.unreal.mcp_bridge import verify_port_coexistence


def _write_atomic_json(target_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, target_path)


def record_ue58_lane(
    output_path: Optional[Path] = None,
    editor_port: Optional[int] = None,
    mcp_port: int = 8000,
    ue58_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Inspect UE 5.8 readiness, MCP port coexistence, and output structured compatibility report."""
    s = get_settings()
    effective_editor_port = editor_port if editor_port is not None else s.bridge_port
    out_file = output_path or DEFAULT_REPORT_FILE
    target_ue58 = ue58_path or DEFAULT_UE58_CANDIDATE

    ue58_installed = target_ue58.is_dir() and (target_ue58 / "Engine" / "Binaries").is_dir()
    port_check = verify_port_coexistence(editor_port=effective_editor_port, mcp_port=mcp_port)

    status_str = (
        "READY (UE 5.8 installed; compatibility harness ready)"
        if ue58_installed
        else "BLOCKED (needs approval: UE 5.8 installation; compatibility harness ready)"
    )

    report: Dict[str, Any] = {
        "status": status_str,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pinned_engine": {
            "version": s.engine.version if s.engine else "5.7.4",
            "root": str(s.engine.root) if s.engine else "",
            "channel": getattr(s, "engine_channel", "pinned"),
        },
        "ue58_target": {
            "channel": "next",
            "installed": ue58_installed,
            "root": str(target_ue58).replace("\\", "/"),
            "reason": "Engine present and verified." if ue58_installed else f"Requires user approval for secondary engine install on {target_ue58.as_posix()}.",
        },
        "mcp_bridge": {
            "read_only_client": "src/gameforge_ide/unreal/mcp_bridge.py",
            "port_coexistence": port_check,
            "editor_port": effective_editor_port,
            "mcp_port": mcp_port,
        },
        "cpp_compatibility": {
            "macro_guards": "#if ENGINE_MINOR_VERSION >= 8",
            "ai_callable_meta": "meta=(AICallable) on read-only UFUNCTIONs",
        },
    }

    _write_atomic_json(out_file, report)
    print(f"UE 5.8 lane report saved to {out_file}")
    print(f"Port coexistence: {port_check['status']} | Engine channel: {getattr(s, 'engine_channel', 'pinned')} | UE 5.8 installed: {ue58_installed}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate UE 5.8 compatibility lane report")
    parser.add_argument("--output", type=Path, default=None, help="Output path for JSON report")
    parser.add_argument("--editor-port", type=int, default=None, help="Editor bridge port override")
    parser.add_argument("--mcp-port", type=int, default=8000, help="MCP port override (default: 8000)")
    parser.add_argument("--ue58-root", type=Path, default=None, help="UE 5.8 root directory override")
    args = parser.parse_args()

    record_ue58_lane(
        output_path=args.output,
        editor_port=args.editor_port,
        mcp_port=args.mcp_port,
        ue58_path=args.ue58_root,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
