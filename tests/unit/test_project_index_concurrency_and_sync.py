"""Unit tests for ProjectIndex concurrency, transaction safety, and FTS5 synchronization (WI-8.4)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
import pytest

from src.gameforge_ide.index.indexer import ProjectIndex


def test_indexer_connection_pragmas_and_autocommit(tmp_path: Path):
    idx = ProjectIndex(tmp_path)
    conn = idx._get_connection()
    try:
        # Check autocommit mode (isolation_level is None)
        assert conn.isolation_level is None

        # Check PRAGMA journal_mode is WAL
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert jm.lower() == "wal"

        # Check PRAGMA busy_timeout >= 30000
        bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert bt >= 30000
    finally:
        conn.close()


def test_indexer_no_duplicate_fts_inserts_and_exact_sync(tmp_path: Path):
    proj_dir = tmp_path / "MyProject"
    src_dir = proj_dir / "Source"
    src_dir.mkdir(parents=True)

    header = src_dir / "TestActor.h"
    header.write_text(
        """#pragma once
UCLASS()
class MYPROJECT_API ATestActor : public AActor
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere)
    int32 Health = 100;

    UFUNCTION(BlueprintCallable)
    void TakeDamage();
};
""",
        encoding="utf-8",
    )

    idx = ProjectIndex(proj_dir)
    res = idx.index_project()
    assert res["indexed_files"] == 1

    conn = idx._get_connection()
    try:
        # Verify row counts between symbols and symbols_fts match exactly (no duplicate inserts)
        sym_count = conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0]
        fts_count = conn.execute("SELECT COUNT(*) FROM symbols_fts;").fetchone()[0]
        assert sym_count == fts_count
        assert sym_count >= 3  # ATestActor, Health, TakeDamage

        # Verify FTS integrity-check
        integrity = conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('integrity-check');").fetchall()
        assert integrity == [] or integrity == [(None,)]

        # Search works instantly via FTS
        search_res = idx.search_symbols("ATestActor")
        assert search_res["total"] == 1
        assert search_res["results"][0]["name"] == "ATestActor"

        # Delete the file and re-index: both symbols and symbols_fts must be cleanly cleared
        header.unlink()
        res_del = idx.index_project()
        assert res_del["deleted_files"] == 1

        sym_count_after = conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0]
        fts_count_after = conn.execute("SELECT COUNT(*) FROM symbols_fts;").fetchone()[0]
        assert sym_count_after == 0
        assert fts_count_after == 0

        # Searching for deleted symbol returns 0
        search_after = idx.search_symbols("ATestActor")
        assert search_after["total"] == 0
    finally:
        conn.close()
