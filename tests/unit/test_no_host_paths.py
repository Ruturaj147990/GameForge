r"""AD-15: product code must not contain host path literals (e.g. E:\..., C:\Users\...)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "gameforge_ide"
DRIVE = re.compile(r"^[A-Za-z]:[\/]")


def test_no_drive_letter_string_literals_in_product_code():
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("recipes/") and rel.endswith("templates.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and DRIVE.match(node.value):
                offenders.append(f"{rel}:{node.lineno}: {node.value[:60]}")
    assert not offenders, "host paths in product code:\n" + "\n".join(offenders)
