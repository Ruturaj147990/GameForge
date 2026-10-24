"""GameForge IDE — Application Launcher.

Default mode: native PySide6 desktop window (QMainWindow).
The browser/FastAPI mode is kept as an opt-in fallback via --serve.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
import threading
from pathlib import Path


WORKSPACE_ROOT = Path(r"E:\gameforge_step1").resolve()


def _launch_native_desktop() -> None:
    """Launch the genuine native PySide6 QMainWindow desktop application."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # High-DPI: let Qt handle scaling on Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("GameForge IDE")
    app.setApplicationDisplayName("GameForge IDE")
    app.setOrganizationName("GameForge")
    app.setApplicationVersion("1.0.0")

    # Construct all widgets from the dark source styles; MainWindow applies the
    # workspace's persisted palette after the complete widget tree exists.
    from .desktop.styles.dark_theme import apply_theme
    apply_theme(app, "dark")

    from .desktop.main_window import MainWindow
    window = MainWindow(WORKSPACE_ROOT)
    window.show()

    sys.exit(app.exec())


def _launch_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the FastAPI backend (fallback/headless mode)."""
    if not _is_loopback_host(host):
        raise ValueError("The Unreal bridge server may bind only to a loopback address.")
    import uvicorn
    from .backend.app import app
    uvicorn.run(app, host=host, port=port, log_level="info")


def _is_loopback_host(host: str) -> bool:
    """Return whether a host value resolves syntactically to loopback."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GameForge IDE — Agentic Game Development Environment"
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI backend server instead of the native desktop UI.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host (only used with --serve)")
    parser.add_argument("--port", type=int, default=8000, help="Port (only used with --serve)")
    args = parser.parse_args()

    if args.serve:
        if not _is_loopback_host(args.host):
            parser.error("--host must be localhost or a loopback IP address.")
        if not os.environ.get("GAMEFORGE_BRIDGE_TOKEN", "").strip():
            parser.error("--serve requires GAMEFORGE_BRIDGE_TOKEN; set a shared secret before launching the Unreal bridge.")
        print("=" * 52)
        # Keep console output compatible with Windows terminals using CP1252.
        print("GameForge IDE - Backend Server Mode")
        print(f"   API: http://{args.host}:{args.port}/docs")
        print("=" * 52)
        _launch_server(args.host, args.port)
    else:
        # Native desktop is the default
        _launch_native_desktop()


if __name__ == "__main__":
    main()
