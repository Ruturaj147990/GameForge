"""Regenerate the op table in docs/generated/GAMEFORGE_UNREAL_OPERATION_COVERAGE.md from unreal/op_catalog.py.

    python scripts/tools/gen_op_coverage.py           # rewrite the table
    python scripts/tools/gen_op_coverage.py --check   # exit 1 if the catalogue is invalid or the table is stale
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from gameforge_ide.unreal import op_catalog  # noqa: E402

BEGIN, END = "<!-- op-catalog:begin -->", "<!-- op-catalog:end -->"
DOC = ROOT / "docs" / "generated" / "GAMEFORGE_UNREAL_OPERATION_COVERAGE.md"


def render(text: str) -> str:
    block = f"{BEGIN}\n{op_catalog.render_markdown()}\n{END}"
    if BEGIN in text:
        return text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    return text.rstrip() + f"\n\n## Generated catalogue ({len(op_catalog.CATALOG)} ops)\n\n{block}\n"


def main() -> int:
    problems = op_catalog.catalog_problems()
    if problems:
        print("\n".join(problems))
        return 1
    text = DOC.read_text(encoding="utf-8")
    new = render(text)
    if "--check" in sys.argv[1:]:
        if new != text:
            print(f"DRIFT: {DOC.name} is stale; run scripts/tools/gen_op_coverage.py")
            return 1
        print(f"OK {len(op_catalog.CATALOG)} ops (table current)")
        return 0
    DOC.write_text(new, encoding="utf-8")
    print(f"OK {len(op_catalog.CATALOG)} ops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
