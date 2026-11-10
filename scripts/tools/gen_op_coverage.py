"""Regenerate the op table in docs/generated/GAMEFORGE_UNREAL_OPERATION_COVERAGE.md from unreal/op_catalog.py.

    python scripts/tools/gen_op_coverage.py           # rewrite the table
    python scripts/tools/gen_op_coverage.py --check   # exit 1 if the catalogue is invalid or the table is stale
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from gameforge_ide.unreal import op_catalog  # noqa: E402

BEGIN, END = "<!-- op-catalog:begin -->", "<!-- op-catalog:end -->"
DOC = ROOT / "docs" / "generated" / "GAMEFORGE_UNREAL_OPERATION_COVERAGE.md"


def render(text: str) -> str:
    block = f"{BEGIN}\n{op_catalog.render_markdown()}\n{END}"
    if BEGIN in text and END in text:
        start_idx = text.index(BEGIN)
        end_idx = text.index(END) + len(END)
        return text[:start_idx] + block + text[end_idx:]
    return text.rstrip() + f"\n\n## Generated catalogue ({len(op_catalog.CATALOG)} ops)\n\n{block}\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Unreal operation coverage markdown documentation")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if catalogue is invalid or table is stale")
    args = parser.parse_args(argv)

    problems = op_catalog.catalog_problems()
    if problems:
        print("\n".join(problems))
        return 1

    text = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""
    new = render(text)

    if args.check:
        if new != text:
            print(f"DRIFT: {DOC.name} is stale; run scripts/tools/gen_op_coverage.py")
            return 1
        print(f"OK {len(op_catalog.CATALOG)} ops (table current)")
        return 0

    DOC.parent.mkdir(parents=True, exist_ok=True)
    tmp_doc = DOC.with_suffix(".tmp")
    tmp_doc.write_text(new, encoding="utf-8")
    tmp_doc.replace(DOC)
    print(f"OK {len(op_catalog.CATALOG)} ops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
