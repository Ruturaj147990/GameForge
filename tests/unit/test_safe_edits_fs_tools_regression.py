"""Comprehensive Regression Tests for Safe Edits, FS Tools, and Terminal Tools (DEF-114 through DEF-122)."""

import hashlib
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
import pytest

from src.gameforge_ide.backend.security.boundary import BoundaryManager, SecurityViolationError
from src.gameforge_ide.backend.tools.edit_tools import EditTools
from src.gameforge_ide.backend.tools.fs_tools import (
    tool_list_dir,
    tool_read_file,
    tool_search_code,
)
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.backend.tools.terminal_tools import TerminalTools


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# =========================================================================
# DEF-114: TerminalTools Process Runaway & Timeout Cleanup
# =========================================================================

def test_terminal_timeout_kills_child_process(workspace: Path):
    """DEF-114: When a command times out, child process must be terminated immediately."""
    terminal = TerminalTools(workspace)

    # Launch python one-liner that sleeps longer than timeout (no semicolons permitted by shell scanner)
    cmd = 'python -c "__import__(\'time\').sleep(10)"'
    t0 = time.time()
    res = terminal.run_command(cmd, timeout_seconds=1)
    duration = time.time() - t0

    assert res["status"] == "TIMEOUT"
    assert res["exit_code"] == -1
    assert "timed out after 1 seconds" in res["error"]
    assert duration < 5.0  # Must not hang for 10 seconds


# =========================================================================
# DEF-115: Windows Backslash Path Preservation
# =========================================================================

def test_terminal_preserves_windows_backslashes(workspace: Path):
    """DEF-115: Command parsing must preserve Windows backslash path separators."""
    terminal = TerminalTools(workspace)

    cmd = r"pytest tests\unit\test_edit_tools.py -k test_safe"
    args = terminal._parse_command(cmd)

    assert args[0] == "pytest"
    assert args[1] == r"tests\unit\test_edit_tools.py"
    assert args[2] == "-k"
    assert args[3] == "test_safe"


def test_terminal_unquotes_paired_quotes_without_destroying_backslashes(workspace: Path):
    """DEF-115: Quoted arguments are cleanly unquoted while keeping internal backslashes."""
    terminal = TerminalTools(workspace)

    cmd = r'git commit -m "update Source\Core\Player.cpp"'
    args = terminal._parse_command(cmd)

    assert args[0] == "git"
    assert args[1] == "commit"
    assert args[2] == "-m"
    assert args[3] == r"update Source\Core\Player.cpp"


# =========================================================================
# DEF-116: Absolute Path Bypass Rejection in Key-Value Flags
# =========================================================================

def test_terminal_rejects_absolute_path_in_flags(workspace: Path):
    """DEF-116: Rejects absolute paths passed in --flag=value format."""
    terminal = TerminalTools(workspace)

    # Windows drive absolute path
    res1 = terminal.run_command(r"git config --file=C:\Windows\System32\calc.exe")
    assert res1["status"] == "BLOCKED"
    assert "absolute path" in res1["error"].lower()

    # POSIX root path
    res2 = terminal.run_command("git config --file=/etc/shadow")
    assert res2["status"] == "BLOCKED"
    assert "absolute path" in res2["error"].lower()

    # Traversal in flag value
    res3 = terminal.run_command(r"git config --file=..\..\secret.txt")
    assert res3["status"] == "BLOCKED"
    assert "traversal" in res3["error"].lower()


# =========================================================================
# DEF-117: Batch Edit Transaction Failure Atomic Recovery
# =========================================================================

def test_apply_batch_rollback_restores_pending_state(workspace: Path):
    """DEF-117: On mid-batch write failure, rolled back diffs are restored to PENDING_APPROVAL."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    # Create file 1
    f1 = workspace / "file1.txt"
    f1.write_text("initial f1\n", encoding="utf-8")

    # File 2 will be simulated to fail during write
    f2 = workspace / "file2.txt"
    f2.write_text("initial f2\n", encoding="utf-8")

    res1 = edit_tools.propose_edit("file1.txt", "initial f1", "modified f1")
    res2 = edit_tools.propose_edit("file2.txt", "initial f2", "modified f2")

    d1 = res1["diff_id"]
    d2 = res2["diff_id"]

    # Sabotage f2 write by replacing atomic_write with an exception for f2
    orig_atomic = edit_tools._atomic_write

    def mock_atomic_write(target: Path, content: bytes):
        if target.name == "file2.txt":
            raise PermissionError("Simulated locked file on NTFS")
        orig_atomic(target, content)

    edit_tools._atomic_write = mock_atomic_write

    # Apply batch containing both diffs
    batch_res = edit_tools.apply_batch([d1, d2])

    assert batch_res["status"] == "ERROR"
    assert "Batch application failed during write" in batch_res["error"]

    # File 1 must have been rolled back to initial state
    assert f1.read_text(encoding="utf-8") == "initial f1\n"

    # CRITICAL: diff 1 must have been restored to PENDING_APPROVAL in memory and on disk!
    assert d1 in edit_tools.pending_diffs
    assert edit_tools.pending_diffs[d1]["status"] == "PENDING_APPROVAL"
    disk_d1 = edit_tools._load_diff_from_disk(d1)
    assert disk_d1 is not None
    assert disk_d1["status"] == "PENDING_APPROVAL"


# =========================================================================
# DEF-118: Mixed Line Ending Replacement Resilience
# =========================================================================

def test_mixed_line_endings_replacement(workspace: Path):
    """DEF-118: Propose and apply edits on files with mixed CRLF and LF line endings."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    # File with mixed CRLF at top, LF in code block
    mixed_content = "/* Header */\r\n// Info\r\n\nvoid Run()\n{\n    return;\n}\n"
    f = workspace / "mixed.cpp"
    f.write_bytes(mixed_content.encode("utf-8"))

    # Target content specified with CRLF
    target = "void Run()\r\n{\r\n    return;\r\n}"
    replacement = "void Run()\r\n{\r\n    Execute();\r\n}"

    prop = edit_tools.propose_edit("mixed.cpp", target, replacement)
    assert prop["status"] == "PENDING_APPROVAL"
    assert prop["diff_patch"] != ""  # Must not be an empty diff!

    app = edit_tools.apply_diff(prop["diff_id"])
    assert app["status"] == "SUCCESS"

    result_bytes = f.read_bytes()
    assert b"Execute();" in result_bytes
    assert b"/* Header */\r\n" in result_bytes

    # Roll back
    rb = edit_tools.rollback_diff(prop["diff_id"])
    assert rb["status"] == "SUCCESS"
    assert f.read_bytes() == mixed_content.encode("utf-8")


def test_noop_replacement_detection_and_rejection(workspace: Path):
    """DEF-118: Identical replacement returns NOOP; failed replacement returns ERROR."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    f = workspace / "noop.txt"
    f.write_text("alpha beta gamma\n", encoding="utf-8")

    # Identical target and replacement
    res = edit_tools.propose_edit("noop.txt", "beta", "beta")
    assert res["status"] == "NOOP"

    # Non-existent target block
    res_err = edit_tools.propose_edit("noop.txt", "delta", "omega")
    assert res_err["status"] == "ERROR"
    assert "not found" in res_err["error"].lower()


# =========================================================================
# DEF-119: UTF-16, UTF-8-BOM, and Non-UTF-8 Encoding Preservation
# =========================================================================

def test_utf16_le_file_edit_and_search(workspace: Path):
    """DEF-119: UTF-16 LE files are correctly edited, rolled back, and searched without corruption."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    # Create UTF-16 LE file with BOM
    f = workspace / "DefaultEngine.ini"
    orig_text = "[Core.Log]\r\nLogTemp=All\r\n"
    f.write_bytes(b"\xff\xfe" + orig_text.encode("utf-16-le"))

    # Search code must find text in UTF-16 LE file
    search_res = tool_search_code(boundary, "LogTemp")
    assert search_res["status"] == "SUCCESS"
    assert len(search_res["matches"]) >= 1
    assert "DefaultEngine.ini" in search_res["matches"][0]["file"]

    # Read file must decode UTF-16 cleanly without null bytes
    read_res = tool_read_file(boundary, "DefaultEngine.ini")
    assert read_res["status"] == "SUCCESS"
    assert "\x00" not in read_res["content"]
    assert "LogTemp=All" in read_res["content"]

    # Propose and apply edit
    prop = edit_tools.propose_edit("DefaultEngine.ini", "LogTemp=All", "LogTemp=VeryVerbose")
    assert prop["status"] == "PENDING_APPROVAL"

    app = edit_tools.apply_diff(prop["diff_id"])
    assert app["status"] == "SUCCESS"

    new_bytes = f.read_bytes()
    assert new_bytes.startswith(b"\xff\xfe")  # Preserves UTF-16 LE BOM!
    assert "LogTemp=VeryVerbose".encode("utf-16-le") in new_bytes

    # Rollback must restore original bytes exactly
    rb = edit_tools.rollback_diff(prop["diff_id"])
    assert rb["status"] == "SUCCESS"
    assert f.read_bytes() == b"\xff\xfe" + orig_text.encode("utf-16-le")


def test_utf8_bom_preservation(workspace: Path):
    """DEF-119: UTF-8 with BOM files maintain BOM across edit and rollback."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    f = workspace / "Config.ini"
    f.write_bytes(b"\xef\xbb\xbf" + "Setting=1\r\n".encode("utf-8"))

    prop = edit_tools.propose_edit("Config.ini", "Setting=1", "Setting=2")
    assert prop["status"] == "PENDING_APPROVAL"

    app = edit_tools.apply_diff(prop["diff_id"])
    assert app["status"] == "SUCCESS"

    new_bytes = f.read_bytes()
    assert new_bytes.startswith(b"\xef\xbb\xbf")  # Preserves UTF-8 BOM!
    assert b"Setting=2" in new_bytes

    rb = edit_tools.rollback_diff(prop["diff_id"])
    assert rb["status"] == "SUCCESS"
    assert f.read_bytes() == b"\xef\xbb\xbf" + "Setting=1\r\n".encode("utf-8")


# =========================================================================
# DEF-120: Rollback of Read-Only Files & Existing 0-Byte Preservation
# =========================================================================

def test_rollback_read_only_newly_created_file(workspace: Path):
    """DEF-120: Rolling back newly created file succeeds even if file was marked read-only."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    new_file = "NewFolder/SubFolder/Created.txt"
    prop = edit_tools.propose_edit(new_file, "", "fresh content\n")
    assert prop["status"] == "PENDING_APPROVAL"

    app = edit_tools.apply_diff(prop["diff_id"])
    assert app["status"] == "SUCCESS"

    target_path = workspace / "NewFolder" / "SubFolder" / "Created.txt"
    assert target_path.exists()

    # Mark file read-only on NTFS
    os.chmod(target_path, stat.S_IREAD)

    # Rollback must clear read-only attribute and delete file, and prune empty parent folders
    rb = edit_tools.rollback_diff(prop["diff_id"])
    assert rb["status"] == "SUCCESS"
    assert not target_path.exists()
    assert not (workspace / "NewFolder").exists()  # Cleaned empty parent dirs!


def test_rollback_preserves_existing_empty_file(workspace: Path):
    """DEF-120: Editing an existing 0-byte file and rolling back does NOT delete the file."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    empty_file = workspace / "__init__.py"
    empty_file.write_bytes(b"")
    assert empty_file.exists()
    assert empty_file.stat().st_size == 0

    prop = edit_tools.propose_edit("__init__.py", "", "# Package init\n")
    assert prop["status"] == "PENDING_APPROVAL"

    app = edit_tools.apply_diff(prop["diff_id"])
    assert app["status"] == "SUCCESS"
    assert empty_file.read_text(encoding="utf-8") == "# Package init\n"

    # Rollback must restore the 0-byte file, NOT delete it
    rb = edit_tools.rollback_diff(prop["diff_id"])
    assert rb["status"] == "SUCCESS"
    assert empty_file.exists()
    assert empty_file.stat().st_size == 0


# =========================================================================
# DEF-121: Binary Asset Skipping & Redundant Project Prefix in Search
# =========================================================================

def test_search_code_skips_binary_assets(workspace: Path):
    """DEF-121: search_code skips Unreal .uasset/.umap and textures rather than parsing as text."""
    boundary = BoundaryManager(workspace)

    # Create binary file with pattern
    uasset = workspace / "HeroMesh.uasset"
    uasset.write_bytes(b"\x00\x01\x02SearchTarget\x03\x04")

    # Create text file with pattern
    cpp = workspace / "Hero.cpp"
    cpp.write_text("// SearchTarget implementation\n", encoding="utf-8")

    res = tool_search_code(boundary, "SearchTarget")
    assert res["status"] == "SUCCESS"
    matches = res["matches"]
    assert len(matches) == 1
    assert matches[0]["file"] == "Hero.cpp"


def test_search_code_handles_redundant_project_prefix(workspace: Path):
    """DEF-121: search_code strips redundant project prefix from subpath."""
    boundary = BoundaryManager(workspace)

    src = workspace / "Source"
    src.mkdir(parents=True)
    (src / "Game.cpp").write_text("void StartGame() {}\n", encoding="utf-8")

    # Pass redundant workspace folder name as prefix
    redundant_subpath = f"{workspace.name}/Source"
    res = tool_search_code(boundary, "StartGame", subpath=redundant_subpath)
    assert res["status"] == "SUCCESS"
    assert len(res["matches"]) == 1


# =========================================================================
# DEF-122: Security Boundary Traversal Exception Safety
# =========================================================================

def test_fs_and_edit_tools_handle_security_violations_gracefully(workspace: Path):
    """DEF-122: Tools catch SecurityViolationError and return structured error response."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    # Directory traversal in propose_edit
    res_prop = edit_tools.propose_edit("../../evil.txt", "a", "b")
    assert res_prop["status"] == "BLOCKED"
    assert "Security boundary violation" in res_prop["error"]

    # Traversal in tool_list_dir
    res_list = tool_list_dir(boundary, subpath="../../")
    assert "error" in res_list
    assert "Security violation" in res_list["error"]

    # Traversal in tool_read_file
    res_read = tool_read_file(boundary, subpath="../../evil.txt")
    assert "error" in res_read
    assert "Security violation" in res_read["error"]

    # Traversal in tool_search_code
    res_search = tool_search_code(boundary, "query", subpath="../../")
    assert "error" in res_search
    assert "Security violation" in res_search["error"]


# =========================================================================
# Large File (>50,000 Lines) Safe Batch Edit and Rollback
# =========================================================================

def test_large_file_50k_lines_batch_and_rollback(workspace: Path):
    """Verify 50,000-line safe atomic editing and rollback operates within budget."""
    boundary = BoundaryManager(workspace)
    edit_tools = EditTools(boundary)

    f1 = workspace / "Large1.cpp"
    lines1 = [f"int32_t Var_A_{i} = {i};\n" for i in range(50000)]
    f1.write_text("".join(lines1), encoding="utf-8")
    sha1 = hashlib.sha256(f1.read_bytes()).hexdigest()

    f2 = workspace / "Large2.cpp"
    lines2 = [f"int32_t Var_B_{i} = {i * 2};\n" for i in range(50000)]
    f2.write_text("".join(lines2), encoding="utf-8")
    sha2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    t0 = time.time()
    p1 = edit_tools.propose_edit("Large1.cpp", "int32_t Var_A_25000 = 25000;", "int32_t Var_A_25000 = 99999;")
    p2 = edit_tools.propose_edit("Large2.cpp", "int32_t Var_B_25000 = 50000;", "int32_t Var_B_25000 = 88888;")

    d1 = p1["diff_id"]
    d2 = p2["diff_id"]

    # Batch apply
    batch_res = edit_tools.apply_batch([d1, d2])
    assert batch_res["status"] == "SUCCESS"
    assert "Var_A_25000 = 99999;" in f1.read_text(encoding="utf-8")
    assert "Var_B_25000 = 88888;" in f2.read_text(encoding="utf-8")

    # Batch rollback
    rb_res = edit_tools.rollback_batch([d1, d2])
    assert rb_res["status"] == "SUCCESS"
    t_total = time.time() - t0

    assert hashlib.sha256(f1.read_bytes()).hexdigest() == sha1
    assert hashlib.sha256(f2.read_bytes()).hexdigest() == sha2
    assert t_total < 2.0  # Must finish within 2.0s budget
