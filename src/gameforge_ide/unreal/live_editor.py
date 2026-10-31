"""Live Unreal Editor link for GameForge (real, not simulated).

Uses the engine's own ``remote_execution.py`` (shipped with the PythonScriptPlugin of
the pinned engine install) so the wire protocol always matches the engine version.

Responsibilities:
  * ``prepare_project``: enable loopback-only remote execution (TTL 0, bind 127.0.0.1)
    in the project's DefaultEngine.ini, install the in-editor operation library and
    write the per-session token to <Project>/Saved/GameForge/session.token.
  * ``launch`` / ``stop``: own the editor process lifetime (the supervisor role).
  * ``connect``: discover editors over the engine protocol and accept only the node
    whose project root matches the expected project (identity check, fail closed).
  * ``call``: run one named operation with a timeout and parse its JSON envelope.

Nothing here fabricates success. Any failure returns ``ok: False`` with the cause.
"""

from __future__ import annotations

import importlib.util
import json
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..core.settings import engine_root_or_missing

RESULT_SENTINEL = "@@GAMEFORGE_RESULT@@"
OPS_LIBRARY_SOURCE = Path(__file__).parent / "GameForge" / "Content" / "Python" / "gameforge_ops"  # package (2.1+)

_REMOTE_EXEC_SETTINGS = (
    "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]\n"
    "bRemoteExecution=True\n"
    "RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766\n"
    "RemoteExecutionMulticastBindAddress=127.0.0.1\n"
    "RemoteExecutionMulticastTtl=0\n"
)


class LiveEditorError(RuntimeError):
    pass


def load_engine_remote_execution(engine_root: Path):
    """Import remote_execution.py from the pinned engine install."""
    path = Path(engine_root) / "Engine" / "Plugins" / "Experimental" / "PythonScriptPlugin" / "Content" / "Python" / "remote_execution.py"
    if not path.is_file():
        raise LiveEditorError(f"engine remote_execution.py not found at {path}")
    spec = importlib.util.spec_from_file_location("ue_remote_execution", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_result(command_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the GameForge envelope from a remote_execution command result."""
    outputs = command_result.get("output") or []
    for entry in reversed(outputs):
        text = entry.get("output", "") if isinstance(entry, dict) else str(entry)
        for line in reversed(text.splitlines()):
            if line.startswith(RESULT_SENTINEL):
                try:
                    return json.loads(line[len(RESULT_SENTINEL):])
                except json.JSONDecodeError as exc:
                    return {"ok": False, "errors": [f"malformed result envelope: {exc}"]}
    result = command_result.get("result")
    return {
        "ok": False,
        "errors": ["no GameForge result envelope in editor output"],
        "data": {"python_success": command_result.get("success"), "python_result": result,
                 "output": [o.get("output") if isinstance(o, dict) else o for o in outputs][-5:]},
    }


def build_command(op_name: str, args: Dict[str, Any], token: str) -> str:
    """Build the Python snippet sent to the editor. Arguments travel as a JSON string literal."""
    payload = json.dumps({"op": op_name, "args": args, "token": token})
    return "import gameforge_ops\ngameforge_ops.dispatch(%r)\n" % payload


class LiveEditorLink:
    def __init__(self, uproject: Path, engine_root: Optional[Path] = None,
                 call_timeout_s: float = 60.0):
        self.uproject = Path(uproject).resolve()
        self.project_dir = self.uproject.parent
        self.engine_root = Path(engine_root or engine_root_or_missing())
        self.call_timeout_s = call_timeout_s
        self._rx_module = None
        self._rx = None
        self._process: Optional[subprocess.Popen] = None
        self._token: Optional[str] = None
        self._lock = threading.Lock()  # one call in flight (Blueprint rule 6)
        self.node: Optional[Dict[str, Any]] = None
        self.last_stop_graceful = False

    # ── project preparation ────────────────────────────────────────────────
    @property
    def token_file(self) -> Path:
        return self.project_dir / "Saved" / "GameForge" / "session.token"

    def prepare_project(self) -> Dict[str, Any]:
        cfg = self.project_dir / "Config" / "DefaultEngine.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        if "bRemoteExecution=True" not in text:
            cfg.write_text(text.rstrip() + "\n\n" + _REMOTE_EXEC_SETTINGS, encoding="utf-8")
        self._ensure_python_plugin_enabled()
        py_dir = self.project_dir / "Content" / "Python"
        py_dir.mkdir(parents=True, exist_ok=True)
        stale = py_dir / "gameforge_ops.py"  # pre-2.1 single-file copy
        if stale.exists():
            stale.unlink()
        dest = py_dir / "gameforge_ops"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(OPS_LIBRARY_SOURCE, dest, ignore=shutil.ignore_patterns("__pycache__"))

        # Deploy GameForge native plugin if binaries exist
        plugin_src = Path(__file__).parent / "GameForge"
        plugin_bin = plugin_src / "Binaries" / "Win64"
        plugin_dest = self.project_dir / "Plugins" / "GameForge"
        if plugin_bin.is_dir() and not (plugin_dest / "Binaries" / "Win64").is_dir():
            plugin_dest.parent.mkdir(parents=True, exist_ok=True)
            if plugin_dest.exists():
                shutil.rmtree(plugin_dest)
            shutil.copytree(plugin_src, plugin_dest)

        self._token = secrets.token_hex(32)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(self._token, encoding="utf-8")
        return {"config": str(cfg), "ops_library": str(dest), "token_file": str(self.token_file)}

    def _ensure_python_plugin_enabled(self) -> None:
        data = json.loads(self.uproject.read_text(encoding="utf-8"))
        plugins = data.setdefault("Plugins", [])
        names = {p.get("Name") for p in plugins}
        changed = False
        for name in ("PythonScriptPlugin", "EditorScriptingUtilities", "GameForge"):
            if name not in names:
                plugins.append({"Name": name, "Enabled": True})
                changed = True
        if changed:
            self.uproject.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

    # ── process lifetime ───────────────────────────────────────────────────
    def launch(self, extra_args: Optional[List[str]] = None, log_path: Optional[Path] = None,
               no_sound: bool = True) -> int:
        exe = self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
        if not exe.is_file():
            raise LiveEditorError(f"UnrealEditor.exe not found at {exe}")
        argv = [str(exe), str(self.uproject), "-nosplash", "-nopause", "-unattended"]
        if no_sound:  # audio checks (M14) need the real audio device
            argv.append("-NoSound")
        if log_path:
            argv.append(f"-abslog={log_path}")
        argv += list(extra_args or [])
        self._process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return self._process.pid

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self, timeout_s: float = 30.0, graceful_timeout_s: float = 90.0) -> Optional[int]:
        """Ask the editor to quit; force-terminate only if it does not exit in time."""
        self.last_stop_graceful = False
        if self._process is not None and self._process.poll() is None and self._rx is not None:
            if self.call("quit_editor", {}, timeout_s=15).get("ok"):
                try:
                    self._process.wait(timeout=graceful_timeout_s)
                    self.last_stop_graceful = True
                except subprocess.TimeoutExpired:
                    pass
        self.disconnect()
        if self._process is None:
            return None
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
        return self._process.returncode

    # ── connection ─────────────────────────────────────────────────────────
    def connect(self, discovery_timeout_s: float = 300.0) -> Dict[str, Any]:
        if self._token is None and self.token_file.exists():
            self._token = self.token_file.read_text(encoding="utf-8").strip()
        if not self._token:
            raise LiveEditorError("no session token: call prepare_project() before launching the editor")
        self._rx_module = self._rx_module or load_engine_remote_execution(self.engine_root)
        cfg = self._rx_module.RemoteExecutionConfig()  # defaults: 239.0.0.1:6766, bind 127.0.0.1, TTL 0
        self._rx = self._rx_module.RemoteExecution(cfg)
        self._rx.start()
        deadline = time.monotonic() + discovery_timeout_s
        expected = self.project_dir.resolve()
        rejected: List[str] = []
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                self.disconnect()
                raise LiveEditorError(f"editor exited during discovery (code {self._process.returncode})")
            for node in self._rx.remote_nodes:
                root = node.get("project_root") or ""
                try:
                    same = Path(root).resolve() == expected
                except OSError:
                    same = False
                if same:
                    self._rx.open_command_connection(node["node_id"])
                    self.node = node
                    return node
                if root and root not in rejected:
                    rejected.append(root)
            time.sleep(1.0)
        self.disconnect()
        raise LiveEditorError(f"no editor for {expected} answered discovery within {discovery_timeout_s}s; "
                              f"rejected nodes: {rejected}")

    def disconnect(self) -> None:
        if self._rx is not None:
            try:
                self._rx.stop()
            except Exception:
                pass
        self._rx = None

    def capture_screenshot(self, output_path: Path, resolution=(1280, 720), wait_s: float = 30.0,
                           show_ui: bool = False) -> Dict[str, Any]:
        """Request a viewport capture and block until the file is written.

        The engine renders the capture on a later frame, so no further mutation may be
        sent until the file exists, or the image would show a later scene state.
        ``show_ui`` captures the game viewport including UMG; the default camera-only
        capture never shows widgets, so UI evidence must pass ``show_ui=True``.
        """
        output_path = Path(output_path)
        if output_path.exists():
            output_path.unlink()
        args = {"output_path": output_path.as_posix(), "resolution": list(resolution)}
        if show_ui:
            args["show_ui"] = True
        res = self.call("viewport_screenshot", args)
        if not res.get("ok"):
            return res
        deadline = time.monotonic() + wait_s
        last_size = -1
        while time.monotonic() < deadline:
            if output_path.exists():
                size = output_path.stat().st_size
                if size > 0 and size == last_size:  # stable size => write finished
                    res["data"].update({"path": str(output_path), "bytes": size, "async": False})
                    return res
                last_size = size
            time.sleep(0.5)
        return {"ok": False, "op": "viewport_screenshot", "errors": ["SCREENSHOT_TIMEOUT"],
                "data": {"path": str(output_path)}}

    # ── operations ─────────────────────────────────────────────────────────
    def call(self, op_name: str, args: Optional[Dict[str, Any]] = None,
             timeout_s: Optional[float] = None) -> Dict[str, Any]:
        if self._rx is None or not self._rx.has_command_connection():
            return {"ok": False, "op": op_name, "errors": ["EDITOR_NOT_CONNECTED"]}
        command = build_command(op_name, args or {}, self._token or "")
        box: Dict[str, Any] = {}

        def _run():
            try:
                box["result"] = self._rx.run_command(command, unattended=True,
                                                     exec_mode=self._rx_module.MODE_EXEC_FILE)
            except Exception as exc:  # socket errors, editor crash
                box["error"] = f"{type(exc).__name__}: {exc}"

        with self._lock:
            started = time.monotonic()
            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(timeout_s or self.call_timeout_s)
            elapsed = round(time.monotonic() - started, 3)
        if worker.is_alive():
            return {"ok": False, "op": op_name, "errors": ["EDITOR_CALL_TIMEOUT"], "elapsed_s": elapsed}
        if "error" in box:
            # A dropped socket is either a crash or a lost link; either way the channel is dead.
            self.disconnect()
            crashed = False
            if self._process is not None:
                try:
                    self._process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                crashed = self._process.poll() is not None
            return {"ok": False, "op": op_name,
                    "errors": ["EDITOR_CRASHED" if crashed else "EDITOR_LINK_LOST", box["error"]],
                    "elapsed_s": elapsed}
        envelope = parse_result(box["result"])
        envelope.setdefault("op", op_name)
        envelope["elapsed_s"] = elapsed
        return envelope
