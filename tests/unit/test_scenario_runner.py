"""Unit tests for Scenario runner (WI-3.5)."""

import json
from pathlib import Path
from unittest.mock import patch

from src.gameforge_ide.qa.runner import run_packaged
from src.gameforge_ide.qa.scenario import Scenario, WaitStep, WaitArgs


def test_run_packaged_success(tmp_path: Path):
    scenario = Scenario(
        scenario_id="dummy_test",
        steps=[WaitStep(wait_s=WaitArgs(seconds=1.0))],
    )

    fake_exe = tmp_path / "FakeGame.exe"
    fake_exe.touch()

    out_dir = tmp_path / "out"

    # Simulate game binary execution writing result file
    def fake_spawn(argv, **kwargs):
        class FakeProc:
            def wait(self, timeout=None):
                result_path = out_dir / "dummy_test_result.json"
                result_path.write_text(json.dumps({
                    "schema": "scenario_result/1",
                    "scenario_id": "dummy_test",
                    "passed": True,
                    "duration_s": 1.2,
                    "steps": [],
                    "legs": [],
                    "expect": [],
                    "failures": [],
                }), encoding="utf-8")
                return 0
        return FakeProc()

    with patch("src.gameforge_ide.qa.runner.jobs.spawn", side_effect=fake_spawn):
        res = run_packaged(fake_exe, scenario, out_dir=out_dir)

    assert res.passed is True
    assert res.scenario_id == "dummy_test"


def test_run_packaged_missing_result(tmp_path: Path):
    scenario = Scenario(
        scenario_id="fail_test",
        steps=[WaitStep(wait_s=WaitArgs(seconds=1.0))],
    )

    fake_exe = tmp_path / "FakeGame.exe"
    fake_exe.touch()
    out_dir = tmp_path / "out_missing"

    def fake_spawn(argv, **kwargs):
        class FakeProc:
            def wait(self, timeout=None):
                return 0
        return FakeProc()

    with patch("src.gameforge_ide.qa.runner.jobs.spawn", side_effect=fake_spawn):
        res = run_packaged(fake_exe, scenario, out_dir=out_dir)

    assert res.passed is False
    assert "NO_RESULT" in res.failures
