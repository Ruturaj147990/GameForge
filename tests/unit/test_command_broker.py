"""Unit tests for Central Command Execution Broker (DEF-301) and Process Lifecycle (DEF-305)."""

import os
import sys
import time
from pathlib import Path
import pytest

from src.gameforge_ide.backend.models.command_contract import (
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandStatus,
    RiskCategory,
)
from src.gameforge_ide.backend.models.modes import PermissionsMode
from src.gameforge_ide.backend.tools.command_broker import CommandExecutionBroker
from src.gameforge_ide.backend.tools.terminal_tools import TerminalTools
from src.gameforge_ide.core.process_manager import (
    ProcessLifecycleManager,
    safe_remove_file,
    safe_remove_directory,
    retry_on_sharing_violation,
)


@pytest.fixture
def broker(tmp_path: Path) -> CommandExecutionBroker:
    return CommandExecutionBroker(workspace_root=tmp_path)


def test_command_broker_mode_request_all_requires_approval(broker: CommandExecutionBroker, tmp_path: Path):
    """In REQUEST_ALL mode, every command requires user approval."""
    req = CommandExecutionRequest(
        command="python -c \"print('hello')\"",
        shell="direct",
        working_directory=str(tmp_path),
        permissions_mode=PermissionsMode.REQUEST_ALL,
    )
    res = broker.execute(req, approval_granted=False)
    assert res.status == CommandStatus.AWAITING_APPROVAL
    assert res.requires_approval is True
    assert res.approved_by_user is None

    # When approved, it runs and succeeds
    res_approved = broker.execute(req, approval_granted=True)
    assert res_approved.status == CommandStatus.SUCCEEDED
    assert res_approved.exit_code == 0
    assert "hello" in res_approved.stdout


def test_command_broker_mode_auto_safe_commands(broker: CommandExecutionBroker, tmp_path: Path):
    """In AUTO mode, safe workspace development commands execute automatically."""
    test_file = tmp_path / "sample.txt"
    test_file.write_text("sample content", encoding="utf-8")

    # Python execution
    req_py = CommandExecutionRequest(
        command="python -c \"print('auto_mode')\"",
        shell="direct",
        working_directory=str(tmp_path),
        permissions_mode=PermissionsMode.AUTO,
    )
    res_py = broker.execute(req_py, approval_granted=False)
    assert res_py.status == CommandStatus.SUCCEEDED
    assert res_py.requires_approval is False
    assert "auto_mode" in res_py.stdout

    # Read operation (cat/type alias)
    risk_cat, requires_approval, _ = broker.classify_risk(
        "cat sample.txt",
        shell="powershell",
        working_directory=tmp_path,
        permissions_mode=PermissionsMode.AUTO,
    )
    assert risk_cat == RiskCategory.ROUTINE_READ
    assert requires_approval is False


def test_command_broker_mode_auto_blocks_destructive_deletes(broker: CommandExecutionBroker, tmp_path: Path):
    """In AUTO mode, destructive/recursive delete commands require explicit approval."""
    commands = [
        "rmdir /s /q build",
        "rd /s temp",
        "Remove-Item -Recurse -Force dist",
        "rm -rf build",
    ]
    for cmd in commands:
        risk_cat, requires, _ = broker.classify_risk(
            cmd,
            shell="powershell",
            working_directory=tmp_path,
            permissions_mode=PermissionsMode.AUTO,
        )
        assert risk_cat == RiskCategory.DESTRUCTIVE_DELETE
        assert requires is True


def test_command_broker_mode_auto_detects_registry_and_admin(broker: CommandExecutionBroker, tmp_path: Path):
    """In AUTO mode, registry modification and admin elevation require approval."""
    cmd_reg = "Set-ItemProperty -Path 'HKLM:\\Software\\Test' -Name 'Val' -Value 1"
    risk_reg, requires_reg, _ = broker.classify_risk(
        cmd_reg,
        shell="powershell",
        working_directory=tmp_path,
        permissions_mode=PermissionsMode.AUTO,
    )
    assert risk_reg == RiskCategory.SYSTEM_MODIFICATION
    assert requires_reg is True

    cmd_admin = "Start-Process powershell.exe -Verb RunAs"
    risk_admin, requires_admin, _ = broker.classify_risk(
        cmd_admin,
        shell="powershell",
        working_directory=tmp_path,
        permissions_mode=PermissionsMode.AUTO,
    )
    assert risk_admin == RiskCategory.ELEVATED_ADMIN
    assert requires_admin is True


def test_command_broker_mode_unrestricted(broker: CommandExecutionBroker, tmp_path: Path):
    """In UNRESTRICTED mode, ordinary operations run without routine prompts."""
    risk, requires, _ = broker.classify_risk(
        "python -c \"print(1)\"",
        shell="direct",
        working_directory=tmp_path,
        permissions_mode=PermissionsMode.UNRESTRICTED,
    )
    assert requires is False


def test_command_broker_forbidden_commands_unconditionally_blocked(broker: CommandExecutionBroker, tmp_path: Path):
    """Catastrophic commands (format, diskpart, etc.) are unconditionally BLOCKED across all modes."""
    forbidden = [
        "format c: /fs:ntfs",
        "diskpart /s script.txt",
        "del /s /q c:",
    ]
    for mode in (PermissionsMode.REQUEST_ALL, PermissionsMode.AUTO, PermissionsMode.UNRESTRICTED):
        for cmd in forbidden:
            req = CommandExecutionRequest(
                command=cmd,
                shell="cmd",
                working_directory=str(tmp_path),
                permissions_mode=mode,
            )
            res = broker.execute(req, approval_granted=True)
            assert res.status == CommandStatus.BLOCKED
            assert "forbidden" in (res.error_message or "").lower()


def test_command_broker_powershell_aliases_and_pipelines(broker: CommandExecutionBroker, tmp_path: Path):
    """PowerShell aliases (ls, dir, cat, gc, pwd) and pipelines (|) parse correctly."""
    # Aliases
    assert broker._extract_first_executable("ls -la", shell="powershell") == "Get-ChildItem"
    assert broker._extract_first_executable("dir", shell="powershell") == "Get-ChildItem"
    assert broker._extract_first_executable("cat file.txt", shell="powershell") == "Get-Content"
    assert broker._extract_first_executable("pwd", shell="powershell") == "Get-Location"
    assert broker._extract_first_executable("rm -Recurse out", shell="powershell") == "Remove-Item"

    # Pipeline
    pipeline_cmd = "Get-ChildItem | Select-String 'needle'"
    first = broker._extract_first_executable(pipeline_cmd, shell="powershell")
    assert first == "Get-ChildItem"


def test_command_broker_outside_workspace_detection(broker: CommandExecutionBroker, tmp_path: Path):
    """Outside workspace access is identified and gated."""
    outside_dir = Path("C:/Windows/System32")
    if not outside_dir.exists():
        outside_dir = tmp_path.parent.parent

    risk, requires, _ = broker.classify_risk(
        f"type {outside_dir / 'calc.exe'}",
        shell="powershell",
        working_directory=tmp_path,
        permissions_mode=PermissionsMode.AUTO,
    )
    assert risk == RiskCategory.OUTSIDE_WORKSPACE
    assert requires is True


def test_command_broker_timeout_terminates_process(broker: CommandExecutionBroker, tmp_path: Path):
    """Long-running or hanging command times out and terminates without leaking."""
    req = CommandExecutionRequest(
        command="python -c \"import time; time.sleep(10)\"",
        shell="direct",
        working_directory=str(tmp_path),
        permissions_mode=PermissionsMode.AUTO,
        timeout_seconds=1,
    )
    t0 = time.time()
    res = broker.execute(req, approval_granted=True)
    duration = time.time() - t0

    assert res.status == CommandStatus.FAILED
    assert "timed out after 1" in (res.error_message or "")
    assert duration < 5.0


def test_terminal_tools_integration_with_broker(tmp_path: Path):
    """TerminalTools delegates through CommandExecutionBroker."""
    tt = TerminalTools(tmp_path)
    assert hasattr(tt, "broker")
    assert isinstance(tt.broker, CommandExecutionBroker)

    # Allowlisted direct command
    res = tt.run_command("python -c \"print('terminal_broker')\"")
    assert res["status"] == "SUCCESS"
    assert res["exit_code"] == 0
    assert "terminal_broker" in res["stdout"]


def test_process_lifecycle_manager_windowless_and_cleanup(tmp_path: Path):
    """ProcessLifecycleManager executes windowless and cleans files lock-aware."""
    pm = ProcessLifecycleManager.get_instance()
    exit_code, stdout, stderr, dur = pm.run(["python", "-c", "print('windowless_ok')"], cwd=tmp_path)
    assert exit_code == 0
    assert "windowless_ok" in stdout

    # Test lock-aware file deletion
    sample_file = tmp_path / "deleteme.txt"
    sample_file.write_text("data", encoding="utf-8")
    assert sample_file.exists()
    ok = safe_remove_file(sample_file)
    assert ok is True
    assert not sample_file.exists()

    # Test lock-aware directory deletion
    sample_dir = tmp_path / "subfolder"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "child.txt").write_text("child data", encoding="utf-8")
    ok_dir = safe_remove_directory(sample_dir)
    assert ok_dir is True
    assert not sample_dir.exists()


def test_permissions_mode_unknown_value_fails_closed():
    """Unknown or corrupted permissions values must not silently become AUTO."""
    with pytest.raises(ValueError):
        PermissionsMode.from_str("unrestricted-ish")
    assert PermissionsMode.from_str("agentic") == PermissionsMode.AUTO
    assert PermissionsMode.from_str("manual") == PermissionsMode.REQUEST_ALL


def test_terminal_direct_parser_has_no_stale_executable_allowlist(tmp_path: Path):
    """Direct command parsing accepts ordinary executables without a hardcoded allowlist."""
    terminal = TerminalTools(tmp_path)
    parsed = terminal._parse_command("cat sample.txt")
    assert parsed[0].lower() == "cat"
