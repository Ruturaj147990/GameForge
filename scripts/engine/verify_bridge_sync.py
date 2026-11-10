"""Editor GameForge.SyncContext -> Bridge on port 47815 verification (P0 WI-0.9).

Launches the bridge with --serve and GAMEFORGE_BRIDGE_TOKEN on port 47815,
starts offscreen editor on a disposable probe, triggers GameForge.SyncContext,
confirms 200 OK received context, and writes reports/P0/bridge_47815.json.

Usage:
    python scripts/engine/verify_bridge_sync.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.request
import urllib.error

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

BRIDGE_PORT = 47815
TOKEN = "gameforge_p0_bridge_token_test_47815"


def wait_for_bridge(timeout_s: float = 30.0) -> bool:
    url = f"http://127.0.0.1:{BRIDGE_PORT}/api/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def get_synced_context(timeout_s: float = 10.0) -> Dict[str, Any]:
    url = f"http://127.0.0.1:{BRIDGE_PORT}/api/unreal/context"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    deadline = time.monotonic() + timeout_s
    last_err: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and isinstance(data, dict) and data.get("project_name"):
                    return data
        except Exception as exc:
            last_err = exc
        time.sleep(0.5)
    if last_err:
        raise last_err
    return {}


def main() -> int:
    print(f"Starting bridge on port {BRIDGE_PORT} with token...")
    bridge_env = dict(os.environ)
    bridge_env["GAMEFORGE_BRIDGE_TOKEN"] = TOKEN
    os.environ["GAMEFORGE_BRIDGE_TOKEN"] = TOKEN

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW

    bridge_proc = subprocess.Popen(
        [sys.executable, "-m", "src.gameforge_ide.launcher", "--serve"],
        env=bridge_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creation_flags,
    )

    evidence: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "bridge_port": BRIDGE_PORT,
        "token_configured": bool(TOKEN),
        "steps": [],
        "verdict": "UNKNOWN",
    }

    link = None
    try:
        # Step 1: Health check on 47815
        bridge_alive = wait_for_bridge(20.0)
        print(f"Bridge healthy on {BRIDGE_PORT}: {bridge_alive}")
        assert bridge_alive, f"Bridge did not become healthy on port {BRIDGE_PORT}"
        evidence["steps"].append({"step": "bridge_health", "ok": bridge_alive, "port": BRIDGE_PORT})

        # Step 2: Disposable probe & offscreen editor
        uproject = disposable_probe("bridge_47815")
        print(f"Probe created at {uproject}")
        evidence["steps"].append({"step": "probe_created", "uproject": str(uproject)})

        link = start_editor(uproject, "bridge_47815")
        hs = link.call("handshake", {})
        print(f"Handshake: {hs.get('ok')}")
        assert hs.get("ok"), "Editor handshake failed"
        engine_ver = (hs.get("data") or {}).get("engine_version")
        evidence["steps"].append({"step": "editor_connected", "engine_version": engine_ver})

        # Step 3: Trigger console command GameForge.SyncContext
        sync_cmd = """
import unreal
unreal.SystemLibrary.execute_console_command(None, "GameForge.SyncContext")
print("@@SYNC_SENT@@DONE")
"""
        rx = getattr(link, "_rx", None)
        rx_mod = getattr(link, "_rx_module", None)
        if rx and rx_mod:
            res = rx.run_command(sync_cmd, unattended=True, exec_mode=rx_mod.MODE_EXEC_FILE)
            evidence["steps"].append({"step": "execute_sync_command", "output": res.get("output")})
        else:
            evidence["steps"].append({"step": "execute_sync_command", "output": "rx unavailable"})
        print("GameForge.SyncContext console command executed in editor")

        # Step 4: Wait and read back context from the bridge
        ctx = get_synced_context(timeout_s=10.0)
        print(f"Context received by bridge: {ctx}")
        assert ctx.get("project_name") == "GFProbe", f"Unexpected project_name in context: {ctx}"
        assert str(ctx.get("engine_version", "")).startswith("5.7"), f"Unexpected engine_version in context: {ctx}"
        evidence["steps"].append({"step": "received_context", "context": ctx})

        evidence["verdict"] = "PASS"
        print("Verification PASS: Editor successfully synced context with bridge on 47815")
        return 0

    except Exception as exc:
        evidence["verdict"] = "FAIL"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        print(f"Verification FAIL: {exc}")
        return 1
    finally:
        if link:
            link.stop()
        bridge_proc.terminate()
        try:
            stdout, _ = bridge_proc.communicate(timeout=5)
            evidence["bridge_log"] = stdout
        except Exception:
            bridge_proc.kill()
            stdout, _ = bridge_proc.communicate()
            evidence["bridge_log"] = stdout

        out_path = write_report("bridge_47815", evidence, "P0")
        print(f"Wrote report to {out_path}")


if __name__ == "__main__":
    sys.exit(main())
