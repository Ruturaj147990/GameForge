"""GameForge IDE — Application Launcher.

Default mode: native PySide6 desktop window (QMainWindow).
The browser/FastAPI mode is kept as an opt-in fallback via --serve.
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .core.settings import get_settings


def _configure_terminal_logging(verbose: bool = False) -> None:
    """Configure terminal logging so all engine, model, forge and UI events are visible."""
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    # Explicitly ensure all gameforge package loggers inherit the correct level
    for name in ("src", "src.gameforge_ide", "gameforge_ide", "gameforge"):
        logging.getLogger(name).setLevel(level)

    # Format with clean timestamps and module names
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for h in root.handlers:
            h.setLevel(level)
            h.setFormatter(formatter)

    # Suppress verbose noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def _safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            # Fall back to replacing unencodable characters
            ascii_msg = msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
            print(ascii_msg, flush=True)
        except Exception:
            pass


def _install_exception_hook() -> None:
    """Ensures unhandled exceptions in Qt slots and background threads print detailed tracebacks to the terminal."""
    def _excepthook(exc_type, exc_value, exc_traceback):
        import traceback
        lines = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        _safe_print(f"\n[GameForge Unhandled Error] Uncaught exception in runtime:\n{lines}")
        try:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        except Exception:
            pass

    sys.excepthook = _excepthook


def _setup_terminal_event_listener() -> None:
    """Subscribe to EventBus to print real-time Forge, pipeline, and job execution logs in the terminal."""
    try:
        from .core.events import default_bus
        bus = default_bus()

        def _on_event(topic: str, ev: Dict[str, Any]) -> None:
            if topic == "forge":
                kind = ev.get("kind")
                run_id = ev.get("run_id", "")
                if kind == "run_started":
                    title = ev.get("title", "")
                    count = ev.get("steps_count", "")
                    _safe_print(f"\n[Forge Run] ═══════════════════════════════════════════════════════")
                    _safe_print(f"[Forge Run] STARTING RUN: {run_id} ({title}) [{count} steps]")
                    _safe_print(f"[Forge Run] ═══════════════════════════════════════════════════════")
                elif kind == "step_started":
                    step_id = ev.get("step_id", "")
                    k_type = ev.get("kind_type", "")
                    _safe_print(f"[Forge Step] ▶ [{step_id}] ({k_type}) Starting...")
                elif kind == "step_finished":
                    step_id = ev.get("step_id", "")
                    ok = ev.get("ok", False)
                    dur = ev.get("duration_s", 0)
                    status_str = "✓ OK" if ok else "✗ FAILED"
                    errs = ev.get("errors") or []
                    err_str = f" | Errors: {errs}" if errs else ""
                    _safe_print(f"[Forge Step] {status_str} [{step_id}] in {dur}s{err_str}")
                elif kind == "run_finished":
                    st = ev.get("status", "")
                    _safe_print(f"[Forge Run] ═══════════════════════════════════════════════════════")
                    _safe_print(f"[Forge Run] RUN {run_id} FINISHED: {st}")
                    _safe_print(f"[Forge Run] ═══════════════════════════════════════════════════════\n")
            elif topic == "pipeline":
                stage = ev.get("stage", "")
                status = ev.get("status", "")
                _safe_print(f"[GameForge Pipeline] {stage}: {status}")
            elif topic in ("job.failed", "job_failed"):
                _safe_print(f"[GameForge Job FAILED] Job '{ev.get('job_name')}' failed: {ev.get('error')} ({ev.get('type')})")

        bus.subscribe("*", _on_event)
    except Exception as exc:
        _safe_print(f"[GameForge Warning] Failed to attach terminal event listener: {exc}")


def _is_portable_mode() -> bool:
    """Check if GameForge is running in portable / isolated mode."""
    if os.environ.get("GAMEFORGE_PORTABLE", "").strip().lower() in ("1", "true", "yes"):
        return True
    marker_candidates = [
        Path(__file__).resolve().parent / ".portable",
        Path(__file__).resolve().parents[1] / ".portable",
        Path(__file__).resolve().parents[2] / ".portable",
        Path.cwd() / ".portable",
    ]
    return any(p.is_file() for p in marker_candidates)


def _resolve_workspace(workspace_arg: Optional[Path | str] = None, portable: bool = False) -> Path:
    """Resolve active workspace directory with resilient portable and repo-free fallbacks."""
    if workspace_arg:
        ws = Path(workspace_arg).resolve()
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    if portable or _is_portable_mode():
        # In portable mode, use a self-contained local workspace folder
        if getattr(sys, "frozen", False):
            app_root = Path(sys.executable).resolve().parent
        else:
            app_root = Path(__file__).resolve().parents[2]
        portable_ws = app_root / "workspace"
        try:
            portable_ws.mkdir(parents=True, exist_ok=True)
            return portable_ws.resolve()
        except Exception:
            pass

    try:
        ws = get_settings().default_workspace
        ws.mkdir(parents=True, exist_ok=True)
        return ws.resolve()
    except Exception:
        local_ws = Path.cwd() / "workspace"
        local_ws.mkdir(parents=True, exist_ok=True)
        return local_ws.resolve()


def _launch_native_desktop(workspace_path: Optional[Path | str] = None, verbose: bool = False, portable: bool = False) -> None:
    """Launch the genuine native PySide6 QMainWindow desktop application."""
    _configure_terminal_logging(verbose=verbose)
    _install_exception_hook()
    _setup_terminal_event_listener()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # Set explicit Windows application user model ID for taskbar grouping & icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GameForge.Studio.IDE.1.0")
        except Exception:
            pass

    # High-DPI: let Qt handle scaling on Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("GameForge IDE")
    try:
        from .desktop.diagnostics.stall_monitor import setup_stall_monitor
        setup_stall_monitor()
    except Exception as exc:
        logging.getLogger(__name__).debug("Stall monitor setup skipped: %s", exc)
    app.setApplicationDisplayName("GameForge IDE")
    app.setOrganizationName("GameForge")
    app.setApplicationVersion("1.0.0")

    # Construct all widgets from the dark source styles; MainWindow applies the
    # workspace's persisted palette after the complete widget tree exists.
    from .desktop.styles.dark_theme import apply_theme
    apply_theme(app, "dark")

    target_ws = _resolve_workspace(workspace_path, portable=portable)

    print(f"[GameForge] Launching GameForge IDE desktop [workspace: {target_ws}]...", flush=True)
    from .desktop.main_window import MainWindow
    window = MainWindow(target_ws)
    window.show()
    window.raise_()
    window.activateWindow()
    print("[GameForge] GameForge IDE window opened and active.", flush=True)

    sys.exit(app.exec())


def _launch_server(host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    """Start the FastAPI backend (fallback/headless mode)."""
    if not _is_loopback_host(host):
        raise ValueError("The Unreal bridge server may bind only to a loopback address.")
    import uvicorn
    from .backend.app import app
    uvicorn.run(app, host=host, port=port or get_settings().bridge_port, log_level="info")


def _is_loopback_host(host: str) -> bool:
    """Return whether a host value resolves syntactically to loopback."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    from . import __version__
    parser = argparse.ArgumentParser(
        description="GameForge IDE - Agentic Game Development Environment"
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=None,
        help="Optional workspace folder to open (default: configured default_workspace or local workspace).",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="Run in self-contained portable mode (storing workspace and data locally in the application folder).",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI backend server instead of the native desktop UI.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host (only used with --serve)")
    parser.add_argument("--port", type=int, default=None,
                        help="Port (only used with --serve; default: settings bridge_port, 47815)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose debug logging to the terminal.")
    args = parser.parse_args()

    if args.serve:
        if not _is_loopback_host(args.host):
            parser.error("--host must be localhost or a loopback IP address.")
        if not os.environ.get("GAMEFORGE_BRIDGE_TOKEN", "").strip():
            parser.error("--serve requires GAMEFORGE_BRIDGE_TOKEN; set a shared secret before launching the Unreal bridge.")
        print("=" * 52)
        # Keep console output compatible with Windows terminals using CP1252.
        effective_port = args.port or get_settings().bridge_port
        print("GameForge IDE - Backend Server Mode")
        print(f"   API: http://{args.host}:{effective_port}/docs")
        print("=" * 52)
        _launch_server(args.host, effective_port)
    else:
        # Native desktop is the default
        _launch_native_desktop(args.workspace, verbose=args.verbose, portable=args.portable)


if __name__ == "__main__":
    main()
