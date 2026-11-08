"""Regression tests for the 2026-11-07 source hardening pass.

Covers:
- product code no longer depends on the ``tests`` package (PyInstaller excludes it);
- command broker classifies every segment of a chained command;
- catastrophic-payload detection is position aware (no false positives on --format etc.);
- git network operations and dynamic evaluation require approval in Auto mode;
- TerminalTools fails closed on an unknown permissions mode;
- UnrealToolchain.engine_version() is non-fatal for reporting callers.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.gameforge_ide.backend.models.command_contract import RiskCategory
from src.gameforge_ide.backend.models.modes import PermissionsMode
from src.gameforge_ide.backend.tools.command_broker import (
    CommandExecutionBroker,
    find_forbidden_payload,
    split_command_segments,
)
from src.gameforge_ide.backend.tools.terminal_tools import TerminalTools

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


# ── packaging: product must not import the tests package ────────────────────

def _imported_modules(py_file: Path):
    tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def test_product_code_never_imports_tests_package():
    offenders = []
    for py in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        for mod in _imported_modules(py):
            if mod == "tests" or mod.startswith("tests."):
                offenders.append(f"{py.relative_to(REPO_ROOT)} -> {mod}")
    assert not offenders, "Product code imports the tests package (excluded from the frozen build):\n" + "\n".join(offenders)


def test_legacy_recipe_fixture_alias_is_same_module():
    from src.gameforge_ide.legacy_recipes.grid_board_game import recipe as product_mod
    from tests.fixtures.legacy_recipes.grid_board_game import recipe as fixture_mod

    assert fixture_mod is product_mod


def test_pyinstaller_spec_still_excludes_tests_and_graders():
    spec = (REPO_ROOT / "GameForge.spec").read_text(encoding="utf-8")
    assert "'tests'" in spec and "'graders'" in spec


# ── command broker ───────────────────────────────────────────────────────────

@pytest.fixture()
def broker(tmp_path):
    return CommandExecutionBroker(tmp_path)


def test_split_command_segments_respects_quotes():
    assert split_command_segments("a 'x;y' ; b && c || d | e") == ["a 'x;y'", "b", "c", "d", "e"]
    assert split_command_segments('echo "a|b"') == ['echo "a|b"']


@pytest.mark.parametrize(
    "cmd",
    ["git log --format=%H", "dotnet format", "clang-format -i a.cpp", "rm -rf build/out", "python fmt.py --format json"],
)
def test_forbidden_detection_has_no_false_positives(cmd):
    assert find_forbidden_payload(cmd) is None


@pytest.mark.parametrize(
    "cmd",
    ["format c:", "diskpart /s wipe.txt", "rm -rf /", "rm -rf ~", "del /s /q c:\\", "Format-Volume -DriveLetter D", "bcdedit /set x"],
)
def test_forbidden_detection_catches_catastrophic_payloads(cmd):
    assert find_forbidden_payload(cmd) is not None


def test_chained_command_is_classified_by_its_riskiest_segment(broker):
    risk, requires, _ = broker.classify_risk(
        "git status; Remove-Item -Recurse Source", shell="powershell", permissions_mode=PermissionsMode.AUTO
    )
    assert requires is True
    assert risk == RiskCategory.DESTRUCTIVE_DELETE


def test_pipeline_of_routine_reads_stays_automatic(broker):
    risk, requires, _ = broker.classify_risk("ls | select-string foo", shell="powershell", permissions_mode=PermissionsMode.AUTO)
    assert risk == RiskCategory.ROUTINE_READ and requires is False


@pytest.mark.parametrize("cmd", ["git push origin main", "git clone https://example.invalid/x.git", "git fetch"])
def test_git_network_operations_need_approval_in_auto(broker, cmd):
    _, requires, _ = broker.classify_risk(cmd, shell="powershell", permissions_mode=PermissionsMode.AUTO)
    assert requires is True


def test_git_read_operations_stay_automatic(broker):
    _, requires, _ = broker.classify_risk("git status", shell="powershell", permissions_mode=PermissionsMode.AUTO)
    assert requires is False


@pytest.mark.parametrize("cmd", ["echo $(whoami)", "iex 'x'", "Write-Output `whoami`"])
def test_dynamic_code_needs_approval_in_auto(broker, cmd):
    _, requires, _ = broker.classify_risk(cmd, shell="powershell", permissions_mode=PermissionsMode.AUTO)
    assert requires is True


def test_substring_ubt_is_not_treated_as_build_tool(broker):
    risk, requires, _ = broker.classify_risk("mytool --doubt", shell="powershell", permissions_mode=PermissionsMode.AUTO)
    assert risk != RiskCategory.PROJECT_BUILD
    assert requires is True


def test_forbidden_payload_is_blocked_even_when_approved(broker, tmp_path):
    from src.gameforge_ide.backend.models.command_contract import CommandExecutionRequest, CommandStatus

    req = CommandExecutionRequest(
        command="git status; rm -rf /", shell="bash", working_directory=str(tmp_path),
        permissions_mode=PermissionsMode.UNRESTRICTED, timeout_seconds=5,
    )
    res = broker.execute(req, approval_granted=True)
    assert res.status == CommandStatus.BLOCKED


def test_terminal_tools_unknown_permissions_mode_fails_closed(tmp_path):
    tt = TerminalTools(tmp_path)
    res = tt.run_command("git status", permissions_mode="definitely-not-a-mode")
    assert res["status"] == "BLOCKED"


def test_terminal_tools_rejects_empty_command(tmp_path):
    tt = TerminalTools(tmp_path)
    assert tt.run_command("   ")["status"] == "BLOCKED"


# ── unreal toolchain ─────────────────────────────────────────────────────────

def test_engine_version_is_non_fatal_for_reporting(tmp_path):
    from src.gameforge_ide.unreal.toolchain import UnrealToolchain

    tc = UnrealToolchain.__new__(UnrealToolchain)
    tc.engine_root = tmp_path  # no Engine/Build/Build.version
    assert tc.engine_version() == "unknown"
    with pytest.raises(OSError):
        tc.engine_version(strict=True)


def test_engine_version_reads_bom_prefixed_build_version(tmp_path):
    from src.gameforge_ide.unreal.toolchain import UnrealToolchain

    build = tmp_path / "Engine" / "Build"
    build.mkdir(parents=True)
    (build / "Build.version").write_text(
        '{"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4}', encoding="utf-8-sig"
    )
    tc = UnrealToolchain.__new__(UnrealToolchain)
    tc.engine_root = tmp_path
    assert tc.engine_version(strict=True) == "5.7.4"


def test_product_modules_import_without_tests_package():
    """Simulate the frozen build: with ``tests`` unimportable, the formerly broken modules must load."""
    import subprocess
    import sys

    code = (
        "import sys; sys.modules['tests'] = None\n"
        "import src.gameforge_ide.backend.tools.game_tools\n"
        "import src.gameforge_ide.forge.handlers\n"
        "import src.gameforge_ide.design.legacy\n"
        "import src.gameforge_ide.pipeline.game_pipeline\n"
        "import src.gameforge_ide.pipeline.freeform\n"
        "import src.gameforge_ide.pipeline.spec_from_prompt\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert proc.returncode == 0 and "OK" in proc.stdout, proc.stderr[-2000:]
