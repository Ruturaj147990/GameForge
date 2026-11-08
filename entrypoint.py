"""GameForge Standalone Desktop Application Entry Point.

Used by PyInstaller and standalone binary distributions.
"""

import os
import sys
from pathlib import Path

# Ensure application root is on sys.path
# entrypoint.py lives at the repository root; under PyInstaller the bundle root
# is sys._MEIPASS. (The previous value walked two directories above the repo.)
app_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from src.gameforge_ide.launcher import main

if __name__ == "__main__":
    sys.exit(main())
