"""GameForge Standalone Desktop Application Entry Point.

Used by PyInstaller and standalone binary distributions.
"""

import os
import sys
from pathlib import Path

# Ensure application root is on sys.path
app_root = Path(__file__).resolve().parent.parent.parent
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from src.gameforge_ide.launcher import main

if __name__ == "__main__":
    sys.exit(main())
