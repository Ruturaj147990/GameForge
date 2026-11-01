"""Unit tests for agent code verification and assistant fix loop (WI-8.5)."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.gameforge_ide.backend.agent.code_verify import (
    create_code_verification_spec,
    propose_assistant_fix,
)
from src.gameforge_ide.forge.model import StepKind


def test_create_code_verification_spec(tmp_path: Path):
    proj_dir = tmp_path / "MyProject"
    proj_dir.mkdir()

    spec = create_code_verification_spec(proj_dir)
    assert spec.origin == "agent_plan"
    assert len(spec.steps) == 4

    step_ids = [s.step_id for s in spec.steps]
    assert step_ids == ["build_editor", "automation", "package", "scenarios"]

    # Verify dependencies
    assert spec.steps[0].depends_on == []
    assert spec.steps[1].depends_on == ["build_editor"]
    assert spec.steps[2].depends_on == ["automation"]
    assert spec.steps[3].depends_on == ["package"]

    # Topo order must succeed without cycle
    topo = spec.topo_order()
    assert len(topo) == 4


def test_propose_assistant_fix_diagnostics_analysis(tmp_path: Path):
    proj_dir = tmp_path / "FixTestProj"
    src_dir = proj_dir / "Source"
    src_dir.mkdir(parents=True)

    header = src_dir / "TestActor.h"
    header.write_text(
        "class ATestActor {\n    void BrokenMethod();\n};\n",
        encoding="utf-8",
    )

    diags = [
        {
            "file": "Source/TestActor.h",
            "line": 2,
            "message": "error: expected a ';' after method declaration",
            "severity": "error",
        }
    ]

    proposal = propose_assistant_fix(proj_dir, diagnostics=diags, attempt=1, max_attempts=3)
    assert proposal["status"] == "PROPOSED"
    assert proposal["attempt"] == 1
    assert proposal["target_file"] == "Source/TestActor.h"
    assert proposal["line"] == 2
    assert "diff" in proposal


def test_propose_assistant_fix_caps_at_3_attempts(tmp_path: Path):
    proj_dir = tmp_path / "FixTestProj"
    diags = [{"file": "Source/Foo.cpp", "line": 10, "message": "unresolved external symbol"}]

    # Attempts 1, 2, 3 succeed with proposals
    for att in (1, 2, 3):
        res = propose_assistant_fix(proj_dir, diagnostics=diags, attempt=att, max_attempts=3)
        assert res["status"] == "PROPOSED"

    # Attempt 4 must be EXHAUSTED
    res_exhausted = propose_assistant_fix(proj_dir, diagnostics=diags, attempt=4, max_attempts=3)
    assert res_exhausted["status"] == "EXHAUSTED"
    assert "Maximum fix attempts" in res_exhausted["error"]
