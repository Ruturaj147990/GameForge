"""Tests for resilient code editing and full autonomous source engineering."""

from pathlib import Path
import pytest
from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools
from src.gameforge_ide.backend.tools.gateway import ToolGateway


def test_propose_edit_whitespace_tolerance(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "sample.cpp"
    sample_file.write_text(
        "void AGameCharacter::BeginPlay()\n"
        "{\n"
        "    Super::BeginPlay();\n"
        "    SetHealth(100.0f);\n"
        "}\n",
        encoding="utf-8"
    )

    # Indentation mismatch in target_content (2 spaces vs 4 spaces)
    res = et.propose_edit(
        subpath="sample.cpp",
        target_content="  Super::BeginPlay();\n  SetHealth(100.0f);",
        replacement_content="    Super::BeginPlay();\n    SetHealth(200.0f);\n    SetShield(50.0f);",
    )

    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]
    apply_res = et.apply_diff(diff_id)
    assert apply_res["status"] == "SUCCESS"

    updated = sample_file.read_text(encoding="utf-8")
    assert "SetHealth(200.0f);" in updated
    assert "SetShield(50.0f);" in updated


def test_propose_edit_full_file_rewrite_fallback(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "config.ini"
    sample_file.write_text("[Settings]\nSpeed=10\n", encoding="utf-8")

    # Empty target_content with replacement_content on existing file -> treated as full-file rewrite
    res = et.propose_edit(
        subpath="config.ini",
        target_content="",
        replacement_content="[Settings]\nSpeed=20\nGravity=980\n",
    )

    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"

    updated = sample_file.read_text(encoding="utf-8")
    assert "Speed=20" in updated
    assert "Gravity=980" in updated


def test_gateway_propose_edit_path_aliases(tmp_path: Path):
    gw = ToolGateway(tmp_path)

    # Calling propose_edit using 'path' instead of 'subpath'
    res = gw.execute_tool(
        "propose_edit",
        {
            "path": "new_script.py",
            "replacement_content": "print('autonomous engineering')\n",
        }
    )

    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]
    apply_res = gw.execute_tool("apply_edit", {"diff_id": diff_id}, approval_granted=True)
    assert apply_res["status"] == "SUCCESS"

    created = tmp_path / "new_script.py"
    assert created.exists()
    assert "autonomous engineering" in created.read_text(encoding="utf-8")
