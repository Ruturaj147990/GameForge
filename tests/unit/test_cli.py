"""Unit tests for CLI commands and argument handling."""

from pathlib import Path
from gameforge_bench.cli import main


def test_cli_help(capsys):
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "gameforge-bench" in out
    assert "doctor" in out
    assert "list-tasks" in out
    assert "validate-specs" in out
    assert "run" in out
    assert "summarize" in out


def test_cli_doctor(capsys):
    code = main(["doctor"])
    assert code == 0
    out = capsys.readouterr().out
    assert "GAMEFORGE BENCHMARK DOCTOR" in out
    assert "Python Version" in out


def test_cli_list_tasks(capsys):
    code = main(["list-tasks", "--workspace", str(Path.cwd())])
    assert code == 0
    out = capsys.readouterr().out
    assert "T2-001" in out
    assert "Total Logical Tasks: 30" in out


def test_cli_validate_specs(capsys):
    code = main(["validate-specs", "--workspace", str(Path.cwd())])
    assert code == 0
    out = capsys.readouterr().out
    assert "SPECIFICATION VALIDATION REPORT: PASSED" in out


def test_cli_summarize_empty(capsys, tmp_path):
    code = main(["summarize", "--report-dir", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Total Evaluated Runs: 0" in out
