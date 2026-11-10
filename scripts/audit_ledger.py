"""GameForge File-by-File Audit & Improvement Ledger System.

Tracks the inspection, problems, improvements, modifications, and verification
for every file in the GameForge repository.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path("docs/audit_ledger.db")
JSON_PATH = Path("docs/audit_ledger.json")
MD_PATH = Path("docs/FILE_BY_FILE_MODIFICATION_LEDGER.md")

VALID_STATUSES = [
    "NOT STARTED",
    "ANALYZED",
    "PROBLEMS IDENTIFIED",
    "IMPROVEMENTS IDENTIFIED",
    "MODIFIED",
    "VERIFIED",
    "COMPLETED",
    "NO CHANGE JUSTIFIED",
]


def init_db(db_path: Path = DB_PATH, drop: bool = False) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    if drop:
        conn.execute("DROP TABLE IF EXISTS files")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            assigned_to TEXT NOT NULL,
            status TEXT NOT NULL,
            purpose TEXT DEFAULT '',
            problems TEXT DEFAULT '',
            improvements TEXT DEFAULT '',
            modifications TEXT DEFAULT '',
            verification TEXT DEFAULT '',
            dependencies TEXT DEFAULT '',
            limitations TEXT DEFAULT '',
            justification TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def populate_inventory(conn: sqlite3.Connection) -> int:
    root = Path(".")
    count = 0
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(
            x in rel.split("/")
            for x in [
                ".git",
                "__pycache__",
                ".pytest_cache",
                ".idea",
                ".vscode",
                ".ruff_cache",
            ]
        ):
            continue

        ext = p.suffix.lower()
        cat = "other"
        assigned = "main_agent"
        status = "NOT STARTED"
        justification = ""

        if rel.startswith("src/gameforge_ide/desktop/"):
            cat = "frontend_desktop"
            assigned = "agent_1_frontend"
        elif any(
            rel.startswith(prefix)
            for prefix in [
                "src/gameforge_ide/backend/",
                "src/gameforge_ide/core/",
                "src/gameforge_ide/storage/",
                "src/gameforge_ide/index/",
                "src/gameforge_ide/config/",
                "src/gameforge_ide/models/",
            ]
        ):
            cat = "backend_core"
            assigned = "agent_2_backend"
        elif any(
            rel.startswith(prefix)
            for prefix in [
                "src/gameforge_ide/forge/",
                "src/gameforge_ide/unreal/",
                "src/gameforge_ide/composer/",
                "src/gameforge_ide/design/",
                "src/gameforge_ide/kit/",
                "src/gameforge_ide/content/",
                "src/gameforge_ide/pipeline/",
                "src/gameforge_ide/qa/",
                "src/gameforge_ide/legacy_recipes/",
                "src/gameforge_ide/evals/",
                "src/gameforge_ide/review/",
                "src/gameforge_ide/packaging/",
            ]
        ):
            cat = "pipeline_engine"
            assigned = "agent_3_pipeline"
        elif rel.startswith("src/gameforge_bench/"):
            cat = "bench"
            assigned = "main_agent"
        elif rel.startswith("tests/"):
            cat = "tests"
            assigned = "main_agent"
        elif rel.startswith("scripts/"):
            cat = "scripts"
            assigned = "main_agent"
        elif rel.startswith("configs/") or rel.startswith("schemas/"):
            cat = "configs_schemas"
            assigned = "main_agent"
        elif rel.startswith("graders/"):
            cat = "benchmark_oracles_and_ground_truth"
            assigned = "main_agent"
            status = "NO CHANGE JUSTIFIED"
            justification = (
                "Protected grading oracle and benchmark reference ground truth. Modifying oracles "
                "or ground truth solutions violates AGENTS.md §2 and invalidates benchmark integrity."
            )
        elif rel.startswith("reports/"):
            cat = "execution_reports"
            assigned = "main_agent"
            status = "NO CHANGE JUSTIFIED"
            justification = (
                "Historical run execution evidence, telemetry dumps, and playtest verification "
                "records. Mutating prior execution logs corrupts test lineage."
            )
        elif ext in [
            ".png",
            ".safetensors",
            ".obj",
            ".mtl",
            ".bin",
            ".dll",
            ".pdb",
            ".exe",
        ]:
            cat = "binary_asset"
            assigned = "main_agent"
            status = "NO CHANGE JUSTIFIED"
            justification = (
                "Binary asset, compiled binary, model weights, or 3D geometry format not "
                "safely editable via text-based AST/refactoring."
            )
        elif rel.startswith("fixtures/"):
            cat = "fixtures"
            assigned = "main_agent"
        else:
            cat = "root_docs"
            assigned = "main_agent"

        cur.execute(
            """
            INSERT OR IGNORE INTO files (
                path, category, assigned_to, status, justification, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (rel, cat, assigned, status, justification, now),
        )
        count += 1

    conn.commit()
    return count


def update_file(
    conn: sqlite3.Connection,
    path: str,
    status: str,
    purpose: str = "",
    problems: str = "",
    improvements: str = "",
    modifications: str = "",
    verification: str = "",
    dependencies: str = "",
    limitations: str = "",
    justification: str = "",
) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")
    path = path.replace("\\", "/").removeprefix("./")
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()

    # Read existing row
    cur.execute("SELECT * FROM files WHERE path = ?", (path,))
    row = cur.fetchone()
    if not row:
        # Insert new
        cat = "other"
        assigned = "main_agent"
        cur.execute(
            """
            INSERT INTO files (
                path, category, assigned_to, status, purpose, problems, improvements,
                modifications, verification, dependencies, limitations, justification, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path,
                cat,
                assigned,
                status,
                purpose,
                problems,
                improvements,
                modifications,
                verification,
                dependencies,
                limitations,
                justification,
                now,
            ),
        )
    else:
        # Update fields that were passed
        updates = ["status = ?", "updated_at = ?"]
        params = [status, now]
        if purpose:
            updates.append("purpose = ?")
            params.append(purpose)
        if problems:
            updates.append("problems = ?")
            params.append(problems)
        if improvements:
            updates.append("improvements = ?")
            params.append(improvements)
        if modifications:
            updates.append("modifications = ?")
            params.append(modifications)
        if verification:
            updates.append("verification = ?")
            params.append(verification)
        if dependencies:
            updates.append("dependencies = ?")
            params.append(dependencies)
        if limitations:
            updates.append("limitations = ?")
            params.append(limitations)
        if justification:
            updates.append("justification = ?")
            params.append(justification)
        params.append(path)
        cur.execute(f"UPDATE files SET {', '.join(updates)} WHERE path = ?", params)
    conn.commit()
    return True


def get_summary(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM files GROUP BY status")
    statuses = dict(cur.fetchall())
    cur.execute("SELECT category, count(*) FROM files GROUP BY category")
    categories = dict(cur.fetchall())
    cur.execute("SELECT assigned_to, count(*) FROM files GROUP BY assigned_to")
    assigned = dict(cur.fetchall())
    cur.execute("SELECT count(*) FROM files")
    total = cur.fetchone()[0]
    return {
        "total": total,
        "statuses": statuses,
        "categories": categories,
        "assigned": assigned,
    }


def _atomic_write_text(out_path: Path, text: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(f".{out_path.name}.tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, out_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def list_files(
    conn: sqlite3.Connection,
    category: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM files {where} ORDER BY path", params)
    cols = [col[0] for col in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def export_json(conn: sqlite3.Connection, out_path: Path = JSON_PATH) -> None:
    rows = list_files(conn)
    _atomic_write_text(out_path, json.dumps(rows, indent=2) + "\n")


def export_markdown(conn: sqlite3.Connection, out_path: Path = MD_PATH) -> None:
    summary = get_summary(conn)
    cur = conn.cursor()
    cur.execute("SELECT * FROM files ORDER BY category, path")
    cols = [col[0] for col in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    lines = [
        "# GameForge — File-by-File Audit & Modification Master Ledger",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Total Tracked Files:** {summary['total']}",
        "",
        "## Summary by Status",
        "",
        "| Status | Count | Percentage |",
        "| --- | --- | --- |",
    ]
    for st in VALID_STATUSES:
        cnt = summary["statuses"].get(st, 0)
        pct = (cnt / summary["total"] * 100) if summary["total"] else 0
        lines.append(f"| {st} | {cnt} | {pct:.1f}% |")

    lines.extend([
        "",
        "## Summary by Category",
        "",
        "| Category | Count |",
        "| --- | --- |",
    ])
    for cat, cnt in sorted(summary["categories"].items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {cnt} |")

    lines.extend([
        "",
        "## Complete File Inventory & Modification Records",
        "",
        "| Path | Category | Status | Assigned To | Improvements / Justification |",
        "| --- | --- | --- | --- | --- |",
    ])

    for r in rows:
        summary_text = (
            r["modifications"]
            or r["improvements"]
            or r["justification"]
            or r["problems"]
            or "-"
        )
        # Escape pipe in markdown table
        summary_text = summary_text.replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(
            f"| `{r['path']}` | {r['category']} | {r['status']} | {r['assigned_to']} | {summary_text} |"
        )

    _atomic_write_text(out_path, "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Ledger Management")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init")
    p_init.add_argument("--drop", action="store_true")
    sub.add_parser("summary")
    sub.add_parser("export")

    p_list = sub.add_parser("list")
    p_list.add_argument("--category", default=None)
    p_list.add_argument("--status", default=None, choices=VALID_STATUSES)
    p_list.add_argument("--assigned-to", default=None)
    p_list.add_argument("--json", action="store_true")

    up = sub.add_parser("update")
    up.add_argument("path", help="Relative file path")
    up.add_argument("--status", required=True, choices=VALID_STATUSES)
    up.add_argument("--purpose", default="")
    up.add_argument("--problems", default="")
    up.add_argument("--improvements", default="")
    up.add_argument("--modifications", default="")
    up.add_argument("--verification", default="")
    up.add_argument("--dependencies", default="")
    up.add_argument("--limitations", default="")
    up.add_argument("--justification", default="")

    args = parser.parse_args()
    drop_flag = getattr(args, "drop", False) if args.command == "init" else False
    conn = init_db(drop=drop_flag)

    try:
        if args.command == "init":
            count = populate_inventory(conn)
            print(f"Populated inventory: {count} files tracked.")
            export_json(conn)
            export_markdown(conn)
        elif args.command == "update":
            update_file(
                conn,
                args.path,
                args.status,
                args.purpose,
                args.problems,
                args.improvements,
                args.modifications,
                args.verification,
                args.dependencies,
                args.limitations,
                args.justification,
            )
            print(f"Updated {args.path} -> {args.status}")
        elif args.command == "summary":
            s = get_summary(conn)
            print(json.dumps(s, indent=2))
        elif args.command == "list":
            rows = list_files(
                conn,
                category=args.category,
                status=args.status,
                assigned_to=args.assigned_to,
            )
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for r in rows:
                    print(f"{r['status']:20} | {r['category']:20} | {r['path']}")
        elif args.command == "export":
            export_json(conn)
            export_markdown(conn)
            print("Exported JSON and Markdown ledgers.")
        else:
            parser.print_help()
        return 0
    finally:
        with contextlib.suppress(Exception):
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
