"""GameForge Standalone Desktop Application Entry Point.

Used by PyInstaller and standalone binary distributions.
Ensures safe UTF-8 stream handling even in windowed (noconsole) builds.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path


def _ensure_standard_streams() -> None:
    """Guarantee valid UTF-8 stdout/stderr/stdin streams in windowed or console builds."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    elif hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    elif hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stdin is None:
        sys.stdin = io.StringIO("")


_ensure_standard_streams()

# Ensure application root and frozen directory are on sys.path
app_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent
    if str(exe_dir) not in sys.path:
        sys.path.insert(0, str(exe_dir))

from src.gameforge_ide.launcher import main  # noqa: E402

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code or 0)
