"""P0 WI-0.10 (audit F-15): every third-party import in the product is a declared requirement."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gameforge_ide"
MAP = {"PIL": "pillow", "yaml": "pyyaml", "PySide6": "pyside6", "shiboken6": "pyside6", "numpy": "numpy", "pydantic": "pydantic",
       "fastapi": "fastapi", "uvicorn": "uvicorn", "httpx": "httpx", "psutil": "psutil", "rich": "rich"}
OPTIONAL = {"keyring", "unreal", "torch", "torch_directml", "anyio", "starlette", "pytest"}


def _declared() -> set:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    return {re.split(r"[<>=!~\[ ]", line.strip())[0].lower() for line in text.splitlines() if line.strip()}


def test_declared_dependencies_cover_imports():
    declared, missing = _declared(), set()
    for path in SRC.rglob("*.py"):
        if "Content/Python" in path.as_posix():
            continue  # runs inside the editor's own Python
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for n in names:
                if n in sys.stdlib_module_names or n in OPTIONAL or n in ("src", "gameforge_ide", "gameforge_bench", "tests"):
                    continue
                if MAP.get(n, n).lower() not in declared:
                    missing.add(f"{n} ({path.relative_to(ROOT).as_posix()})")
    assert not missing, "undeclared third-party imports: " + ", ".join(sorted(missing))
