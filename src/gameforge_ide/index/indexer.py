"""Project indexer (WI-8.4).

Maintains an SQLite database at <workspace>/.gameforge/index/<project_key>.db
containing indexed files, C++ symbols (UCLASS/USTRUCT/UENUM/UFUNCTION/UPROPERTY/inheritance),
INI configuration key-values, and Unreal assets with FTS5 search.
Incremental: re-indexes only files whose mtime or size changed.
"""
from __future__ import annotations

import configparser
import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Regex patterns for C++ Unreal macro declarations and symbols
RE_UCLASS = re.compile(r"UCLASS\s*\([^)]*\)", re.MULTILINE)
RE_USTRUCT = re.compile(r"USTRUCT\s*\([^)]*\)", re.MULTILINE)
RE_UENUM = re.compile(r"UENUM\s*\([^)]*\)", re.MULTILINE)
RE_UFUNCTION = re.compile(r"UFUNCTION\s*\([^)]*\)", re.MULTILINE)
RE_UPROPERTY = re.compile(r"UPROPERTY\s*\([^)]*\)", re.MULTILINE)

RE_CLASS_DECL = re.compile(r"\bclass\s+(?:[A-Za-z0-9_]+_API\s+)?([A-Z][A-Za-z0-9_]*)(?:\s*:\s*public\s+([A-Za-z0-9_]+))?", re.MULTILINE)
RE_STRUCT_DECL = re.compile(r"\bstruct\s+(?:[A-Za-z0-9_]+_API\s+)?([A-Z][A-Za-z0-9_]*)", re.MULTILINE)
RE_ENUM_DECL = re.compile(r"\benum\s+(?:class\s+)?([A-Za-z0-9_]+)", re.MULTILINE)
RE_FUNC_DECL = re.compile(r"(?:virtual\s+|static\s+)?(?:[\w:<>&*~]+\s+)+([^\W\d]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:override\s*)?(?:final\s*)?[;{]", re.MULTILINE | re.UNICODE)
RE_PROP_DECL = re.compile(r"(?:[\w:<>&*]+\s+)+([^\W\d]\w*)\s*(?:=\s*[^;]+)?;", re.MULTILINE | re.UNICODE)


class ProjectIndex:
    """Manages SQLite symbol, config, and asset index for an Unreal project."""

    def __init__(self, project_dir: Path, workspace_dir: Optional[Path] = None):
        self.project_dir = project_dir.resolve()
        self.workspace_dir = (workspace_dir or self.project_dir.parent).resolve()
        self.project_key = hashlib.sha1(str(self.project_dir).encode("utf-8")).hexdigest()

        index_dir = self.workspace_dir / ".gameforge" / "index"
        index_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = index_dir / f"{self.project_key}.db"
        self._has_fts_triggers = False
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    size INTEGER,
                    mtime REAL,
                    sha1 TEXT
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT,
                    name TEXT,
                    file TEXT,
                    line INTEGER,
                    parent TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file);
                CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);

                CREATE TABLE IF NOT EXISTS config (
                    file TEXT,
                    section TEXT,
                    key TEXT,
                    value TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_config_key ON config(key);

                CREATE TABLE IF NOT EXISTS assets (
                    path TEXT PRIMARY KEY,
                    class TEXT,
                    deps_json TEXT
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            # Create FTS5 virtual table for symbols with sync triggers
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
                        name,
                        file,
                        content=symbols,
                        content_rowid=id
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS symbols_ai AFTER INSERT ON symbols BEGIN
                        INSERT INTO symbols_fts(rowid, name, file) VALUES (new.id, new.name, new.file);
                    END;
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS symbols_ad AFTER DELETE ON symbols BEGIN
                        INSERT INTO symbols_fts(symbols_fts, rowid, name, file) VALUES('delete', old.id, old.name, old.file);
                    END;
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS symbols_au AFTER UPDATE ON symbols BEGIN
                        INSERT INTO symbols_fts(symbols_fts, rowid, name, file) VALUES('delete', old.id, old.name, old.file);
                        INSERT INTO symbols_fts(rowid, name, file) VALUES (new.id, new.name, new.file);
                    END;
                    """
                )
                self._has_fts_triggers = True
            except sqlite3.OperationalError:
                self._has_fts_triggers = False

    def index_project(self, force: bool = False) -> Dict[str, Any]:
        """Scan project tree and update database incrementally."""
        t0 = time.time()
        conn = self._get_connection()
        try:
            # 1. Load cached files
            cached = {
                row[0]: (row[1], row[2], row[3])
                for row in conn.execute("SELECT path, size, mtime, sha1 FROM files").fetchall()
            }

            # 2. Fast Discover files via os.scandir
            found_paths = set()
            files_to_index: List[Path] = []
            scan_dirs = [
                self.project_dir / "Source",
                self.project_dir / "Config",
                self.project_dir / "Plugins",
            ]

            valid_exts = {".h", ".hpp", ".cpp", ".cxx", ".inl", ".ini", ".uproject"}
            proj_str = str(self.project_dir)
            proj_len = len(proj_str) + 1

            def _fast_scan(dir_path: str) -> None:
                try:
                    with os.scandir(dir_path) as it:
                        for entry in it:
                            name = entry.name
                            if entry.is_dir(follow_symlinks=False):
                                if name not in ("Intermediate", "Binaries", ".git", ".gameforge", "Saved"):
                                    _fast_scan(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                dot_idx = name.rfind(".")
                                if dot_idx != -1 and name[dot_idx:].lower() in valid_exts:
                                    rel_str = entry.path[proj_len:].replace("\\", "/")
                                    found_paths.add(rel_str)
                                    try:
                                        st = entry.stat(follow_symlinks=False)
                                        sz, mt = st.st_size, st.st_mtime
                                        if force or rel_str not in cached or cached[rel_str][0] != sz or cached[rel_str][1] != mt:
                                            files_to_index.append(Path(entry.path))
                                    except OSError:
                                        pass
                except OSError:
                    pass

            for base_dir in scan_dirs:
                if base_dir.is_dir():
                    _fast_scan(str(base_dir))

            # 3. Detect deleted files
            deleted = set(cached.keys()) - found_paths
            if deleted:
                conn.execute("BEGIN TRANSACTION;")
                for rel_str in deleted:
                    conn.execute("DELETE FROM files WHERE path = ?", (rel_str,))
                    conn.execute("DELETE FROM symbols WHERE file = ?", (rel_str,))
                    conn.execute("DELETE FROM config WHERE file = ?", (rel_str,))
                conn.commit()

            # 4. Index new / modified files
            indexed_count = len(files_to_index)
            if files_to_index:
                conn.execute("BEGIN TRANSACTION;")
                for p in files_to_index:
                    rel_str = str(p.relative_to(self.project_dir)).replace("\\", "/")
                    try:
                        st = p.stat()
                        content_bytes = p.read_bytes()
                        sha1_hash = hashlib.sha1(content_bytes).hexdigest()
                        conn.execute(
                            "INSERT OR REPLACE INTO files (path, size, mtime, sha1) VALUES (?, ?, ?, ?)",
                            (rel_str, st.st_size, st.st_mtime, sha1_hash),
                        )

                        # Delete old symbols / config for this file
                        conn.execute("DELETE FROM symbols WHERE file = ?", (rel_str,))
                        conn.execute("DELETE FROM config WHERE file = ?", (rel_str,))

                        ext = p.suffix.lower()
                        if ext in (".h", ".hpp", ".cpp", ".cxx", ".inl"):
                            symbols = self._parse_cpp_file(p, rel_str, content_bytes)
                            for sym in symbols:
                                cur = conn.execute(
                                    "INSERT INTO symbols (kind, name, file, line, parent) VALUES (?, ?, ?, ?, ?)",
                                    (sym["kind"], sym["name"], sym["file"], sym["line"], sym["parent"]),
                                )
                                try:
                                    conn.execute(
                                        "INSERT INTO symbols_fts (rowid, name, file) VALUES (?, ?, ?)",
                                        (cur.lastrowid, sym["name"], sym["file"]),
                                    )
                                except Exception:
                                    pass

                        elif ext == ".ini":
                            config_items = self._parse_ini_file(p, rel_str, content_bytes)
                            for cfg in config_items:
                                conn.execute(
                                    "INSERT INTO config (file, section, key, value) VALUES (?, ?, ?, ?)",
                                    (cfg["file"], cfg["section"], cfg["key"], cfg["value"]),
                                )
                    except Exception:
                        pass
                conn.commit()

            duration = round(time.time() - t0, 3)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_indexed_at', ?)",
                (time.strftime("%Y-%m-%dT%H:%M:%SZ"),),
            )
            conn.commit()

            return {
                "total_files": len(found_paths),
                "indexed_files": indexed_count,
                "deleted_files": len(deleted),
                "duration_seconds": duration,
            }
        finally:
            conn.close()

    def _parse_cpp_file(self, path: Path, rel_str: str, content_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract C++ symbols with Unreal metadata."""
        text = content_bytes.decode("utf-8", errors="replace")
        lines = text.splitlines()
        symbols: List[Dict[str, Any]] = []

        def has_macro(name: str, start_idx: int, end_idx: int) -> bool:
            return any(name in lines[k] for k in range(max(0, start_idx), min(len(lines), end_idx)))

        current_class: Optional[str] = None
        for i, line in enumerate(lines, 1):
            sline = line.strip()

            # Enum declaration (check before class because of `enum class`)
            m_enum = RE_ENUM_DECL.search(line)
            if m_enum and (has_macro("UENUM", i - 3, i) or sline.startswith("enum")):
                en_name = m_enum.group(1)
                symbols.append(
                    {
                        "kind": "enum",
                        "name": en_name,
                        "file": rel_str,
                        "line": i,
                        "parent": current_class,
                    }
                )
                continue

            # Class declaration (skip if enum class)
            if not sline.startswith("enum"):
                m_class = RE_CLASS_DECL.search(line)
                if m_class and (has_macro("UCLASS", i - 3, i) or "class" in sline):
                    cls_name = m_class.group(1)
                    parent_cls = m_class.group(2)
                    current_class = cls_name
                    symbols.append(
                        {
                            "kind": "class",
                            "name": cls_name,
                            "file": rel_str,
                            "line": i,
                            "parent": parent_cls,
                        }
                    )
                    continue

            # Struct declaration
            m_struct = RE_STRUCT_DECL.search(line)
            if m_struct and (has_macro("USTRUCT", i - 3, i) or "struct" in sline):
                st_name = m_struct.group(1)
                symbols.append(
                    {
                        "kind": "struct",
                        "name": st_name,
                        "file": rel_str,
                        "line": i,
                        "parent": current_class,
                    }
                )
                continue

            # UFUNCTION declaration
            if has_macro("UFUNCTION", i - 6, i):
                m_fn = RE_FUNC_DECL.search(line)
                if m_fn:
                    fn_name = m_fn.group(1)
                    symbols.append(
                        {
                            "kind": "function",
                            "name": fn_name,
                            "file": rel_str,
                            "line": i,
                            "parent": current_class,
                        }
                    )
                    continue

            # UPROPERTY declaration
            if has_macro("UPROPERTY", i - 6, i):
                m_prop = RE_PROP_DECL.search(line)
                if m_prop:
                    prop_name = m_prop.group(1)
                    symbols.append(
                        {
                            "kind": "property",
                            "name": prop_name,
                            "file": rel_str,
                            "line": i,
                            "parent": current_class,
                        }
                    )
                    continue

        return symbols

    def _parse_ini_file(self, path: Path, rel_str: str, content_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract config sections and key/values from INI files."""
        text = content_bytes.decode("utf-8", errors="replace")
        items: List[Dict[str, Any]] = []
        current_section = "General"

        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith(";") or s.startswith("#"):
                continue
            if s.startswith("[") and s.endswith("]"):
                current_section = s[1:-1].strip()
            elif "=" in s:
                k, _, v = s.partition("=")
                items.append(
                    {
                        "file": rel_str,
                        "section": current_section,
                        "key": k.strip().lstrip("+-"),
                        "value": v.strip(),
                    }
                )
        return items

    def index_assets(self, assets_list: List[Dict[str, Any]]) -> int:
        """Populate assets table from list_assets output."""
        conn = self._get_connection()
        try:
            conn.execute("BEGIN TRANSACTION;")
            conn.execute("DELETE FROM assets;")
            for a in assets_list:
                path = a.get("path") or a.get("asset_path", "")
                cls_name = a.get("class") or a.get("asset_class", "")
                deps = a.get("dependencies", [])
                conn.execute(
                    "INSERT OR REPLACE INTO assets (path, class, deps_json) VALUES (?, ?, ?)",
                    (path, cls_name, str(deps)),
                )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('assets_indexed_at', ?)",
                (time.strftime("%Y-%m-%dT%H:%M:%SZ"),),
            )
            conn.commit()
            return len(assets_list)
        finally:
            conn.close()

    def search_symbols(
        self,
        query: str,
        kind: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search indexed C++ symbols with pagination and total count (< 50ms)."""
        limit = min(50, max(1, limit))
        offset = max(0, offset)

        conn = self._get_connection()
        try:
            clean_q = re.sub(r"[^A-Za-z0-9_*]", "", query).strip()
            use_fts = bool(re.search(r"[A-Za-z0-9]", clean_q))

            results = []
            total = 0
            fts_worked = False

            if use_fts:
                try:
                    q_fts = f"{clean_q}*" if not clean_q.endswith("*") else clean_q
                    where_clauses = ["symbols_fts MATCH ?"]
                    params: List[Any] = [q_fts]
                    if kind:
                        where_clauses.append("s.kind = ?")
                        params.append(kind)
                    where_str = f"WHERE {' AND '.join(where_clauses)}"

                    count_sql = f"SELECT COUNT(*) FROM symbols_fts fts JOIN symbols s ON s.id = fts.rowid {where_str}"
                    total = conn.execute(count_sql, params).fetchone()[0]

                    select_sql = (
                        f"SELECT s.kind, s.name, s.file, s.line, s.parent "
                        f"FROM symbols_fts fts JOIN symbols s ON s.id = fts.rowid "
                        f"{where_str} ORDER BY s.name ASC LIMIT ? OFFSET ?"
                    )
                    params.extend([limit, offset])
                    rows = conn.execute(select_sql, params).fetchall()
                    results = [
                        {
                            "kind": r[0],
                            "name": r[1],
                            "file": r[2],
                            "line": r[3],
                            "parent": r[4],
                        }
                        for r in rows
                    ]
                    fts_worked = True
                except Exception:
                    fts_worked = False

            if not fts_worked:
                where_clauses = ["name LIKE ?"]
                params = [f"%{query}%"]
                if kind:
                    where_clauses.append("kind = ?")
                    params.append(kind)
                where_str = f"WHERE {' AND '.join(where_clauses)}"

                count_sql = f"SELECT COUNT(*) FROM symbols {where_str}"
                total = conn.execute(count_sql, params).fetchone()[0]

                select_sql = f"SELECT kind, name, file, line, parent FROM symbols {where_str} ORDER BY name ASC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                rows = conn.execute(select_sql, params).fetchall()
                results = [
                    {
                        "kind": r[0],
                        "name": r[1],
                        "file": r[2],
                        "line": r[3],
                        "parent": r[4],
                    }
                    for r in rows
                ]

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "results": results,
            }
        finally:
            conn.close()
