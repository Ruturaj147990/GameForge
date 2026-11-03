"""Tests for Large-File and Multi-File Code Modification in GameForge IDE."""

import hashlib
import os
import tempfile
from pathlib import Path
import pytest

from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools
from src.gameforge_ide.backend.tools.gateway import ToolGateway


@pytest.fixture
def workspace_tmp(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def test_small_file_edit(workspace_tmp: Path):
    """Test standard small file propose, apply, and rollback."""
    boundary = BoundaryManager(workspace_tmp)
    edit_tools = EditTools(boundary)

    file_path = workspace_tmp / "small.txt"
    file_path.write_text("line 1\nline 2 to change\nline 3\n", encoding="utf-8")
    original_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()

    # Propose
    res = edit_tools.propose_edit(
        subpath="small.txt",
        target_content="line 2 to change",
        replacement_content="line 2 replaced",
    )
    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]
    assert "diff_patch" in res

    # Apply
    res_apply = edit_tools.apply_diff(diff_id)
    assert res_apply["status"] == "SUCCESS"
    assert "line 2 replaced" in file_path.read_text(encoding="utf-8")

    # Rollback
    res_rb = edit_tools.rollback_diff(diff_id)
    assert res_rb["status"] == "SUCCESS"
    assert hashlib.sha256(file_path.read_bytes()).hexdigest() == original_sha


def test_medium_file_edit(workspace_tmp: Path):
    """Test medium file (~1,000 lines) edit."""
    boundary = BoundaryManager(workspace_tmp)
    edit_tools = EditTools(boundary)

    file_path = workspace_tmp / "medium.py"
    lines = [f"def func_{i}():\n    return {i}\n" for i in range(1000)]
    file_path.write_text("\n".join(lines), encoding="utf-8")
    original_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()

    res = edit_tools.propose_edit(
        subpath="medium.py",
        target_content="def func_500():\n    return 500",
        replacement_content="def func_500():\n    # Optimized\n    return 500 * 2",
    )
    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]

    res_apply = edit_tools.apply_diff(diff_id)
    assert res_apply["status"] == "SUCCESS"
    assert "return 500 * 2" in file_path.read_text(encoding="utf-8")

    res_rb = edit_tools.rollback_diff(diff_id)
    assert res_rb["status"] == "SUCCESS"
    assert hashlib.sha256(file_path.read_bytes()).hexdigest() == original_sha


def test_large_and_very_large_file_edit(workspace_tmp: Path):
    """Test large (10,000 lines) and very large (50,000 lines, ~2.5 MB) files."""
    boundary = BoundaryManager(workspace_tmp)
    edit_tools = EditTools(boundary)

    file_path = workspace_tmp / "very_large.cpp"
    # Generate 50,000 lines
    content = "// GameForge Engine Core Unit\n" + "\n".join(
        [f"int32_t Variable_Index_{i} = {i * 7};" for i in range(50000)]
    ) + "\n"
    file_path.write_text(content, encoding="utf-8")
    orig_bytes = file_path.read_bytes()
    orig_sha = hashlib.sha256(orig_bytes).hexdigest()
    assert len(orig_bytes) > 1_500_000  # > 1.5 MB

    target_block = "int32_t Variable_Index_25000 = 175000;"
    repl_block = "int32_t Variable_Index_25000 = 999999; // Updated via GameForge Patch"

    res = edit_tools.propose_edit(
        subpath="very_large.cpp",
        target_content=target_block,
        replacement_content=repl_block,
    )
    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]

    res_apply = edit_tools.apply_diff(diff_id)
    assert res_apply["status"] == "SUCCESS"
    assert repl_block in file_path.read_text(encoding="utf-8")
    assert target_block not in file_path.read_text(encoding="utf-8")

    res_rb = edit_tools.rollback_diff(diff_id)
    assert res_rb["status"] == "SUCCESS"
    assert hashlib.sha256(file_path.read_bytes()).hexdigest() == orig_sha


def test_conflict_detection_stale_sha(workspace_tmp: Path):
    """Verify stale SHA conflict detection when file is externally modified."""
    boundary = BoundaryManager(workspace_tmp)
    edit_tools = EditTools(boundary)

    file_path = workspace_tmp / "conflict.txt"
    file_path.write_text("original content\n", encoding="utf-8")

    res = edit_tools.propose_edit(
        subpath="conflict.txt",
        target_content="original content",
        replacement_content="agent content",
    )
    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]

    # External modification
    file_path.write_text("external conflict edit\n", encoding="utf-8")

    # Apply must fail with STALE
    res_apply = edit_tools.apply_diff(diff_id)
    assert res_apply["status"] == "STALE"
    assert "File changed after this diff was proposed" in res_apply["error"]
    assert file_path.read_text(encoding="utf-8") == "external conflict edit\n"


def test_rollback_stale_detection(workspace_tmp: Path):
    """Verify rollback detects if file was externally modified after diff was applied."""
    boundary = BoundaryManager(workspace_tmp)
    edit_tools = EditTools(boundary)

    file_path = workspace_tmp / "rollback_conflict.txt"
    file_path.write_text("initial state\n", encoding="utf-8")

    res = edit_tools.propose_edit(
        subpath="rollback_conflict.txt",
        target_content="initial state",
        replacement_content="modified state",
    )
    diff_id = res["diff_id"]
    edit_tools.apply_diff(diff_id)
    assert file_path.read_text(encoding="utf-8") == "modified state\n"

    # External edit after apply
    file_path.write_text("third-party edit after apply\n", encoding="utf-8")

    res_rb = edit_tools.rollback_diff(diff_id)
    assert res_rb["status"] == "STALE"
    assert "File changed after this diff was applied" in res_rb["error"]
    assert file_path.read_text(encoding="utf-8") == "third-party edit after apply\n"


def test_multi_file_coordinated_edits(workspace_tmp: Path):
    """Test coordinated changes across multiple interrelated files."""
    gateway = ToolGateway(workspace_tmp)

    files = {
        "header.h": "class Player { public: int health = 100; };",
        "player.cpp": "void Player::Heal() { health += 10; }",
        "game.cpp": "void Game::Start() { Player p; p.Heal(); }",
    }
    for name, content in files.items():
        (workspace_tmp / name).write_text(content, encoding="utf-8")

    diff_ids = []
    # Propose edit across header and cpp
    res1 = gateway.edit_tools.propose_edit("header.h", "int health = 100;", "int health = 200;")
    res2 = gateway.edit_tools.propose_edit("player.cpp", "health += 10;", "health += 25;")
    res3 = gateway.edit_tools.propose_edit("game.cpp", "p.Heal();", "p.Heal(); // Initial boost")

    for r in [res1, res2, res3]:
        assert r["status"] == "PENDING_APPROVAL"
        diff_ids.append(r["diff_id"])

    # Apply all in coordinated batch
    for d_id in diff_ids:
        r_app = gateway.edit_tools.apply_diff(d_id)
        assert r_app["status"] == "SUCCESS"

    assert (workspace_tmp / "header.h").read_text(encoding="utf-8") == "class Player { public: int health = 200; };"
    assert (workspace_tmp / "player.cpp").read_text(encoding="utf-8") == "void Player::Heal() { health += 25; }"
    assert "// Initial boost" in (workspace_tmp / "game.cpp").read_text(encoding="utf-8")

    # Coordinated rollback
    for d_id in reversed(diff_ids):
        r_rb = gateway.edit_tools.rollback_diff(d_id)
        assert r_rb["status"] == "SUCCESS"

    for name, orig in files.items():
        assert (workspace_tmp / name).read_text(encoding="utf-8") == orig


def test_reject_diff(workspace_tmp: Path):
    """Verify rejecting a diff leaves filesystem completely unchanged."""
    boundary = BoundaryManager(workspace_tmp)
    edit_tools = EditTools(boundary)

    file_path = workspace_tmp / "reject.txt"
    file_path.write_text("keep this line\n", encoding="utf-8")

    res = edit_tools.propose_edit(
        subpath="reject.txt",
        target_content="keep this line",
        replacement_content="discard this change",
    )
    diff_id = res["diff_id"]

    res_rej = edit_tools.reject_diff(diff_id, reason="Needs more review")
    assert res_rej["status"] == "REJECTED"
    assert res_rej["reason"] == "Needs more review"

    assert file_path.read_text(encoding="utf-8") == "keep this line\n"

    # Attempting to apply rejected diff fails
    res_apply = edit_tools.apply_diff(diff_id)
    assert res_apply["status"] == "ERROR"
