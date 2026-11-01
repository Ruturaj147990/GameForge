"""Unit tests for Local Fine-tune Flywheel capture (WI-9.4)."""
from pathlib import Path
import json
import pytest

from src.gameforge_ide.models.flywheel import FlywheelCapture


def test_flywheel_disabled_by_default(tmp_path: Path):
    fw = FlywheelCapture(datasets_root=tmp_path, enabled=False)
    p = fw.record_accepted_design("make platformer", {"title": "Platformer"}, "ws_1")
    assert p is None
    assert not list(tmp_path.glob("*"))


def test_flywheel_captures_when_enabled(tmp_path: Path):
    fw = FlywheelCapture(datasets_root=tmp_path, enabled=True)
    
    # 1. Accepted design
    f1 = fw.record_accepted_design("make 3d platformer", {"title": "Platformer", "genre": "platformer"}, "ws_test")
    assert f1 is not None
    assert f1.is_file()

    # 2. Accepted patch
    f2 = fw.record_accepted_patch("make guards faster", [{"op": "replace", "path": "/speed", "value": 350}], 2, "ws_test")
    assert f2 == f1

    # 3. Passed compile repair
    f3 = fw.record_compile_repair(["error C2143: missing ';'"], {"Source/Test.cpp": "int x = 5;\n"}, "ws_test")
    assert f3 == f1

    # Verify content
    lines = [json.loads(line) for line in f1.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 3
    assert lines[0]["type"] == "design_draft"
    assert lines[0]["prompt"] == "make 3d platformer"
    assert lines[1]["type"] == "gds_patch"
    assert lines[2]["type"] == "cpp_repair"
