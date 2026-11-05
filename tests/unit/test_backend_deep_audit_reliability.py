"""Comprehensive tests for Backend Architecture, Tools, Data Integrity, Storage & Core Services.

Audits:
1. Multi-chunk diffs with cumulative line/char offset adjustment.
2. CRLF vs LF line ending preservation across edits and rewrites.
3. Multi-file batch edit application & rollback (new file + existing file).
4. Boundary security: Windows case-insensitivity, 8.3 short filename expansion, ADS colon rejection.
5. SQLite FTS5 query sanitization & database locked retries.
6. Core systems: EventBus subscriber exception isolation & read-only atomic writes.
"""

from __future__ import annotations

import os
import stat
import sqlite3
import time
from pathlib import Path
import pytest

from src.gameforge_ide.backend.security.boundary import BoundaryManager, SecurityViolationError, expand_8_3_short_names
from src.gameforge_ide.backend.tools.edit_tools import EditTools, apply_unified_diff
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.core.events import EventBus
from src.gameforge_ide.index.indexer import ProjectIndex
from src.gameforge_ide.storage.atomic import atomic_write, atomic_write_text, safe_read_text


# =========================================================================
# 1. Multi-Chunk Diffs & Cumulative Offset Adjustment
# =========================================================================

def test_multi_chunk_edits_cumulative_offset_adjustment(tmp_path: Path):
    """When chunk 1 adds lines, chunk 2 must apply at the shifted line offset without corrupting lines."""
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample = tmp_path / "MultiChunk.cpp"
    original_code = (
        "void AHero::Init()\n"
        "{\n"
        "    SetupStats();\n"
        "    SetupInventory();\n"
        "    SetupAbilities();\n"
        "    SetupHUD();\n"
        "}\n"
    )
    sample.write_text(original_code, encoding="utf-8")

    # Chunk 1 replaces SetupStats() with 3 lines (+2 lines delta)
    # Chunk 2 replaces SetupHUD() which was at line 6 in original, now shifted to line 8
    chunks = [
        {
            "target": "    SetupStats();",
            "replacement": "    SetupStats();\n    SetupHealth();\n    SetupMana();",
        },
        {
            "target": "    SetupHUD();",
            "replacement": "    SetupAdvancedHUD();",
        },
    ]

    res = et.propose_edit(subpath="MultiChunk.cpp", chunks=chunks)
    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]

    apply_res = et.apply_diff(diff_id)
    assert apply_res["status"] == "SUCCESS"

    result_code = sample.read_text(encoding="utf-8")
    expected_lines = [
        "void AHero::Init()",
        "{",
        "    SetupStats();",
        "    SetupHealth();",
        "    SetupMana();",
        "    SetupInventory();",
        "    SetupAbilities();",
        "    SetupAdvancedHUD();",
        "}",
    ]
    actual_lines = [l.strip("\r") for l in result_code.splitlines()]
    assert actual_lines == expected_lines


def test_apply_unified_diff_multi_hunk_cumulative_offsets():
    """Unified diff with multiple hunks correctly updates cumulative line deltas without corrupting lines."""
    original = (
        "Line 1\n"
        "Line 2\n"
        "Line 3\n"
        "Line 4\n"
        "Line 5\n"
        "Line 6\n"
        "Line 7\n"
        "Line 8\n"
        "Line 9\n"
        "Line 10\n"
    )
    # Hunk 1 adds 2 lines at line 2. Hunk 2 modifies line 8.
    diff_patch = (
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -2,3 +2,5 @@\n"
        " Line 2\n"
        "-Line 3\n"
        "+Line 3_A\n"
        "+Line 3_B\n"
        "+Line 3_C\n"
        " Line 4\n"
        "@@ -7,3 +9,3 @@\n"
        " Line 7\n"
        "-Line 8\n"
        "+Line 8_MOD\n"
        " Line 9\n"
    )

    ok, patched, err = apply_unified_diff(original, diff_patch)
    assert ok is True
    assert err is None
    assert "Line 3_A\nLine 3_B\nLine 3_C" in patched
    assert "Line 8_MOD" in patched
    assert "Line 5\nLine 6\nLine 7" in patched


# =========================================================================
# 2. CRLF vs LF Consistency
# =========================================================================

def test_crlf_file_preserves_crlf_on_partial_edit(tmp_path: Path):
    """Modifying a CRLF file never converts untouched lines or replacement to LF."""
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample = tmp_path / "WindowsScript.py"
    # Pure CRLF file
    sample.write_bytes(b"def start():\r\n    x = 1\r\n    y = 2\r\n    return x + y\r\n")

    # Replacement supplied with LF newlines
    res = et.propose_edit(
        subpath="WindowsScript.py",
        target_content="    x = 1\r\n    y = 2",
        replacement_content="    x = 10\n    y = 20",
    )
    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"

    content = sample.read_bytes()
    # Must contain CRLF throughout, never pure LF
    assert b"\r\n" in content
    assert b"x = 10\r\n    y = 20\r\n" in content
    # Verify no stray lone LF without CR
    assert b"\r\n" * 4 == content.replace(b"def start():", b"").replace(b"    x = 10", b"").replace(b"    y = 20", b"").replace(b"    return x + y", b"")


def test_lf_file_preserves_lf_on_crlf_input(tmp_path: Path):
    """Modifying an LF file with CRLF replacement never introduces CRLF into the file."""
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample = tmp_path / "LinuxScript.sh"
    # Pure LF file
    sample.write_bytes(b"#!/usr/bin/env bash\necho 'hello'\nexit 0\n")

    # Replacement supplied with Windows CRLF
    res = et.propose_edit(
        subpath="LinuxScript.sh",
        target_content="echo 'hello'",
        replacement_content="echo 'hello'\r\necho 'world'",
    )
    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"

    content = sample.read_bytes()
    # Must NOT contain CRLF
    assert b"\r\n" not in content
    assert b"echo 'hello'\necho 'world'\n" in content


# =========================================================================
# 3. Rollback of Multi-File Batch Edits (New File + Existing File)
# =========================================================================

def test_rollback_batch_new_file_and_modified_file(tmp_path: Path):
    """Rolling back a batch containing a new file and an existing file deletes the new file and restores original."""
    gw = ToolGateway(tmp_path)

    # File 1: Existing file
    f1 = tmp_path / "Existing.txt"
    f1_original = "Original Content\nLine 2\n"
    f1.write_text(f1_original, encoding="utf-8")

    # File 2: Newly created file in subfolder
    new_subpath = "Sub/NewFile.txt"

    # Propose diff 1 (modify existing)
    p1 = gw.execute_tool(
        "propose_edit",
        {
            "subpath": "Existing.txt",
            "target": "Line 2",
            "replacement": "Line 2 MODIFIED",
        },
    )
    # Propose diff 2 (create new file)
    p2 = gw.execute_tool(
        "propose_edit",
        {
            "subpath": new_subpath,
            "target": "",
            "replacement": "New file content in batch\n",
        },
    )

    d1, d2 = p1["diff_id"], p2["diff_id"]

    # Apply batch
    apply_res = gw.execute_tool("apply_batch", {"diff_ids": [d1, d2]}, approval_granted=True)
    assert apply_res["status"] == "SUCCESS"
    assert "Line 2 MODIFIED" in f1.read_text(encoding="utf-8")
    f2 = tmp_path / "Sub" / "NewFile.txt"
    assert f2.is_file()
    assert "New file content in batch" in f2.read_text(encoding="utf-8")

    # Rollback batch
    rb_res = gw.execute_tool("rollback_batch", {"diff_ids": [d1, d2]}, approval_granted=True)
    assert rb_res["status"] == "SUCCESS"

    # Existing file must be restored to exact original bytes
    assert f1.read_text(encoding="utf-8") == f1_original
    # New file must be deleted
    assert not f2.exists()

    # Attempting to rollback again must be rejected cleanly (already rolled back)
    rb_repeat = gw.execute_tool("rollback_edit", {"diff_id": d1}, approval_granted=True)
    assert rb_repeat["status"] == "ERROR"
    assert "not in APPLIED state" in rb_repeat["error"]


# =========================================================================
# 4. Boundary Security: Case-Insensitivity, 8.3 Expansion, ADS Colons
# =========================================================================

def test_boundary_drive_casing_and_case_insensitivity(tmp_path: Path):
    """Drive casing variations (e:\\ vs E:\\) and folder casing do not cause false boundary violations."""
    bm = BoundaryManager(tmp_path)

    # Existing file
    test_file = tmp_path / "Source" / "Actor.cpp"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("class AActor;", encoding="utf-8")

    # Access via exact path
    v1 = bm.validate_path("Source/Actor.cpp")
    assert v1.is_file()

    # Access via case-varied path
    v2 = bm.validate_path("source/actor.cpp")
    assert v2.is_file()

    # Absolute path with flipped drive casing
    abs_str = str(test_file)
    if len(abs_str) >= 2 and abs_str[1] == ":":
        drive = abs_str[0]
        flipped_drive = drive.lower() if drive.isupper() else drive.upper()
        flipped_path = flipped_drive + abs_str[1:]
        v3 = bm.validate_path(flipped_path)
        assert v3.is_file()


def test_boundary_rejects_alternate_data_streams(tmp_path: Path):
    """Filenames containing colon ADS stream specifiers (secret.txt:hidden) are rejected."""
    bm = BoundaryManager(tmp_path)

    with pytest.raises(SecurityViolationError) as exc1:
        bm.validate_path("secret.txt:hidden")
    assert "Alternate data stream violation" in str(exc1.value)

    with pytest.raises(SecurityViolationError) as exc2:
        bm.validate_path("Sub/file.cpp::$DATA")
    assert "Alternate data stream violation" in str(exc2.value)


def test_boundary_8_3_short_names_expand_properly(tmp_path: Path):
    """Short 8.3 style path names expand properly without bypassing boundaries."""
    bm = BoundaryManager(tmp_path)

    # Valid relative subpath
    expanded = expand_8_3_short_names(tmp_path)
    assert expanded.exists()

    # Protected path attempt with 8.3 style evasion
    with pytest.raises(SecurityViolationError):
        bm.validate_path("graders/protected/oracle.py", allow_write=True)


# =========================================================================
# 5. SQLite FTS5 Query Sanitization & Database Locked Retries
# =========================================================================

def test_fts5_query_sanitization_no_crashes(tmp_path: Path):
    """Queries with lone *, unbalanced quotes, boolean keywords (NOT, AND, OR) never crash search."""
    src_dir = tmp_path / "Source"
    src_dir.mkdir(parents=True)
    (src_dir / "TestSymbols.h").write_text(
        "class APlayerCharacter : public AActor {};\n"
        "struct FPlayerData {};\n"
        "void ResetMovementState();\n",
        encoding="utf-8",
    )

    idx = ProjectIndex(tmp_path)
    idx.index_project()

    # Problematic queries that previously crashed FTS5
    dangerous_queries = [
        "*",
        '"',
        'foo "',
        'NOT',
        'AND',
        'OR',
        'foo NOT',
        'NOT foo',
        '()',
        '(',
        ')',
        'x:',
        '***',
        '""',
        '   ',
    ]
    for q in dangerous_queries:
        res = idx.search_symbols(q)
        assert isinstance(res, dict)
        assert "results" in res
        assert "total" in res
        assert isinstance(res["total"], int)


# =========================================================================
# 6. Core Systems: EventBus Isolation & Read-Only Atomic Writes
# =========================================================================

def test_event_bus_subscriber_exception_isolation():
    """An exception in one subscriber callback never prevents remaining subscribers from receiving event."""
    bus = EventBus()
    received = []

    def failing_sub(topic: str, event: dict):
        raise RuntimeError("Subscriber explosion!")

    def good_sub_1(topic: str, event: dict):
        received.append("sub_1")

    def good_sub_2(event: dict):
        # Also tests 1-argument callback support
        received.append("sub_2")

    bus.subscribe("game.event", good_sub_1)
    bus.subscribe("game.event", failing_sub)
    bus.subscribe("game.event", good_sub_2)

    bus.publish("game.event", {"action": "jump"})

    # Both good subscribers must have executed despite the middle subscriber raising an exception
    assert "sub_1" in received
    assert "sub_2" in received
    assert len(bus.errors) >= 1
    assert "Subscriber explosion!" in str(bus.errors[0][1])


def test_atomic_write_overwrites_read_only_ntfs_file(tmp_path: Path):
    """Files with S_IREAD (Read-only) on Windows NTFS are overwritten cleanly without error."""
    ro_file = tmp_path / "ReadOnlyFile.json"
    ro_file.write_text('{"version": 1}', encoding="utf-8")

    # Set read-only attribute
    os.chmod(ro_file, stat.S_IREAD)
    assert not (ro_file.stat().st_mode & stat.S_IWRITE)

    # atomic_write must clear read-only attribute and overwrite successfully
    new_content = '{"version": 2, "status": "updated"}'
    atomic_write_text(ro_file, new_content, backup=True)

    text, recovered = safe_read_text(ro_file)
    assert text == new_content
    assert recovered is False
