"""Regenerate the op table in GAMEFORGE_UNREAL_OPERATION_COVERAGE.md from unreal/op_catalog.py."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameforge_ide.unreal import op_catalog  # noqa: E402

BEGIN, END = "<!-- op-catalog:begin -->", "<!-- op-catalog:end -->"


def main() -> int:
    problems = op_catalog.catalog_problems()
    if problems:
        print("\n".join(problems))
        return 1
    doc = ROOT / "GAMEFORGE_UNREAL_OPERATION_COVERAGE.md"
    text = doc.read_text(encoding="utf-8")
    block = f"{BEGIN}\n{op_catalog.render_markdown()}\n{END}"
    if BEGIN in text:
        text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + f"\n\n## Generated catalogue ({len(op_catalog.CATALOG)} ops)\n\n{block}\n"
    doc.write_text(text, encoding="utf-8")
    print(f"OK {len(op_catalog.CATALOG)} ops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
