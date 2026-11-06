"""Tests for Desktop IDE Lifecycle Safety, Unreal Command Formulation, and BoundaryManager Security.

Conforms to GameForge 1.0 Master Transformation Directive:
- Verifies MainWindow lifecycle safety (confirm_on_close = False cleanly closes without blocking modal dialogs).
- Verifies Unreal toolchain command formulation (format_unreal_cmd) with space handling,
  quotation, and forward-slash normalization.
- Verifies ToolGateway allowlist containment for dev commands vs high-risk ops.
- Verifies BoundaryManager security policies:
  * Path traversal rejection (../ escapes, drive jumps, UNC shares)
  * Windows NTFS Alternate Data Streams rejection (file:stream)
  * Windows reserved device names rejection (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
  * Windows 8.3 short name canonicalization
  * Protected folder immunity (graders/protected, .git internal objects, Ollama blobs)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from src.gameforge_ide.backend.models.modes import AutonomyProfile
from src.gameforge_ide.backend.security.boundary import (
    BoundaryManager,
    SecurityViolationError,
    expand_8_3_short_names,
)
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.desktop.main_window import MainWindow
from src.gameforge_ide.unreal.toolchain import format_unreal_cmd


# ==============================================================================
# 1. MainWindow Lifecycle Safety: `confirm_on_close = False`
# ==============================================================================

def test_main_window_confirm_on_close_false_clean_exit(qapp: QApplication, temp_workspace: Path):
    """Verify that setting confirm_on_close = False allows MainWindow to exit cleanly
    even when background tasks are active, without blocking on QMessageBox modal dialogs.
    """
    win = MainWindow(temp_workspace)
    # Explicitly set the automation safety flag
    win.confirm_on_close = False

    try:
        # Simulate active busy agent state
        mock_agent = getattr(win, "_agent", None)
        if mock_agent is not None:
            setattr(mock_agent, "is_busy", True)

        # Dispatch a QCloseEvent directly
        event = QCloseEvent()
        win.closeEvent(event)

        # Event must be accepted cleanly, not ignored
        assert event.isAccepted() is True, "Close event must be accepted when confirm_on_close = False"
    finally:
        win.close()


def test_main_window_confirm_on_close_true_prompts_when_busy(qapp: QApplication, temp_workspace: Path):
    """Verify that when confirm_on_close = True and the application is busy,
    the closeEvent prompts the user and respects rejection.
    """
    win = MainWindow(temp_workspace)
    win.confirm_on_close = True

    try:
        # Simulate active busy agent state
        if hasattr(win, "_agent"):
            setattr(win._agent, "is_busy", True)

        # Patch QMessageBox.question to simulate user clicking "No" (do not exit)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mock_dialog:
            event = QCloseEvent()
            win.closeEvent(event)

            # Dialog should have been displayed
            assert mock_dialog.called, "QMessageBox.question must be called when confirm_on_close is True and busy"
            # Event should be ignored (window stays open)
            assert event.isAccepted() is False, "Close event must be ignored when user rejects quit prompt"

        # Patch QMessageBox.question to simulate user clicking "Yes" (exit)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mock_dialog_yes:
            event_yes = QCloseEvent()
            win.closeEvent(event_yes)

            assert mock_dialog_yes.called
            assert event_yes.isAccepted() is True, "Close event must be accepted when user confirms quit"
    finally:
        win.confirm_on_close = False
        win.close()


def test_main_window_top_bar_chat_panel_integration(qapp: QApplication, temp_workspace: Path):
    """Verify MainWindow initializes with TopBar and ChatPanel properly wired together."""
    win = MainWindow(temp_workspace)
    win.confirm_on_close = False

    try:
        assert hasattr(win, "_top_bar")
        assert hasattr(win, "_chat_panel")

        top_bar: TopBar = win._top_bar
        chat_panel = win._chat_panel

        assert hasattr(top_bar, "task_mode_combo")
        assert hasattr(top_bar, "autonomy_combo")
        assert hasattr(chat_panel, "task_mode_combo")
        assert hasattr(chat_panel, "autonomy_combo")

        # Verify initial states match
        assert top_bar.task_mode_combo.currentText() == "Planning"
        assert chat_panel.task_mode_combo.currentText() == "Planning"
        assert top_bar.autonomy_combo.currentText() == "Agentic"
        assert chat_panel.autonomy_combo.currentText() == "Agentic"

        # Verify changing top_bar cascades to chat_panel
        top_bar.task_mode_combo.setCurrentText("Fast")
        assert chat_panel.task_mode_combo.currentText() == "Fast"

        # Verify changing chat_panel cascades to top_bar
        chat_panel.autonomy_combo.setCurrentText("Manual")
        assert top_bar.autonomy_combo.currentText() == "Manual"
    finally:
        win.close()



# ==============================================================================
# 2. Toolchain & Unreal Command Formulation
# ==============================================================================

def test_format_unreal_cmd_paths_with_spaces_and_quotes():
    """Verify format_unreal_cmd handles Windows paths with spaces, switch quotation,
    and slash normalization for Unreal's FCommandLine::Parse.
    """
    argv = [
        "E:\\Epic Games\\UE_5.7\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe",
        "-project=E:\\My Game Projects\\ActionRPG\\ActionRPG.uproject",
        "-ExecCmds=Automation RunTests GameForge.Core; Quit",
        "-ReportExportPath=E:\\My Game Projects\\ActionRPG\\Saved\\Reports",
        "-noP4",
        "-build",
        "-cook",
    ]

    cmd = format_unreal_cmd(argv)

    if sys.platform == "win32":
        assert isinstance(cmd, str)
        # Positional executable with space should be enclosed in quotes
        assert '"E:/Epic Games/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe"' in cmd
        # Switch with space in value should have value enclosed in quotes: -switch="val"
        assert '-project="E:/My Game Projects/ActionRPG/ActionRPG.uproject"' in cmd
        assert '-ExecCmds="Automation RunTests GameForge.Core; Quit"' in cmd
        assert '-ReportExportPath="E:/My Game Projects/ActionRPG/Saved/Reports"' in cmd
        # Backslashes normalized to forward slashes in path arguments
        assert "\\" not in cmd.split("-project=")[1].split()[0]
        # Switches without spaces should remain plain
        assert "-noP4" in cmd
        assert "-build" in cmd
        assert "-cook" in cmd
    else:
        # Non-Windows platforms preserve argv list
        assert cmd == argv


def test_toolchain_command_allowlist_containment(temp_workspace: Path):
    """Verify ToolGateway strictly enforces the command allowlist under AGENTIC profile."""
    gateway = ToolGateway(temp_workspace)

    # 1. Permitted allowlisted commands
    allowlisted = [
        "pytest",
        "pytest tests/unit/ -v",
        "python -m pytest",
        "python -m pytest tests/gameforge_1_0/",
        "git status",
        "git status --short",
        "git diff HEAD",
        "cargo test",
        "ctest -C Release",
    ]
    for cmd in allowlisted:
        req = gateway.tool_requires_approval("run_command", {"command": cmd}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert req is False, f"Command '{cmd}' is allowlisted and should not require approval in AGENTIC mode"

    # 2. Blocked unallowlisted commands
    blocked = [
        "rmdir /s /q .",
        "cmd.exe /c del *",
        "powershell -c Get-Process",
        "curl http://169.254.169.254",
        "bash -c 'rm -rf /'",
        "echo malicious >> config.ini",
    ]
    for cmd in blocked:
        req = gateway.tool_requires_approval("run_command", {"command": cmd}, autonomy_profile=AutonomyProfile.AGENTIC)
        assert req is True, f"Command '{cmd}' is NOT allowlisted and MUST require approval in AGENTIC mode"


# ==============================================================================
# 3. BoundaryManager Security Policies
# ==============================================================================

def test_boundary_manager_path_traversal_rejection(temp_workspace: Path):
    """Verify BoundaryManager detects and rejects directory traversal attempts."""
    bm = BoundaryManager(temp_workspace)

    traversal_attacks = [
        "../../outside.txt",
        "..\\..\\outside.txt",
        "subdir/../../../windows/system32/calc.exe",
        "Content/../../../../secret.key",
    ]

    for attack in traversal_attacks:
        with pytest.raises(SecurityViolationError):
            bm.validate_path(attack)

        assert bm.is_safe(attack) is False


def test_boundary_manager_unc_network_share_rejection(temp_workspace: Path):
    """Verify BoundaryManager rejects UNC network paths."""
    bm = BoundaryManager(temp_workspace)

    unc_paths = [
        "\\\\server\\share\\malware.exe",
        "//192.168.1.100/data/config.ini",
        "\\\\?\\UNC\\server\\share\\test",
    ]

    for unc in unc_paths:
        with pytest.raises(SecurityViolationError):
            bm.validate_path(unc)

        assert bm.is_safe(unc) is False


def test_boundary_manager_alternate_data_streams_rejection(temp_workspace: Path):
    """Verify BoundaryManager rejects Windows NTFS Alternate Data Streams (ADS)."""
    bm = BoundaryManager(temp_workspace)

    ads_attacks = [
        "Source/Game/Player.cpp:hidden_stream",
        "Content/Maps/Level1.umap:zone_identifier",
        "test.txt:stream:$DATA",
    ]

    for ads in ads_attacks:
        with pytest.raises(SecurityViolationError):
            bm.validate_path(ads)

        assert bm.is_safe(ads) is False


def test_boundary_manager_reserved_device_names_rejection(temp_workspace: Path):
    """Verify BoundaryManager rejects Windows reserved DOS device names."""
    bm = BoundaryManager(temp_workspace)

    reserved_names = [
        "CON", "con.txt", "PRN", "prn.log",
        "AUX", "aux.cpp", "NUL", "nul.dat",
        "COM1", "com2.h", "LPT1", "lpt3.ini",
        "Source/Game/CON.cpp",
    ]

    for dev in reserved_names:
        with pytest.raises(SecurityViolationError):
            bm.validate_path(dev)

        assert bm.is_safe(dev) is False


def test_boundary_manager_windows_8_3_short_names_expansion(temp_workspace: Path):
    """Verify expand_8_3_short_names canonicalizes paths without failing."""
    res = expand_8_3_short_names(temp_workspace)
    assert isinstance(res, Path)
    assert res.exists()


def test_boundary_manager_protected_folder_immunity(temp_workspace: Path):
    """Verify BoundaryManager blocks writes to protected system and oracle directories."""
    bm = BoundaryManager(temp_workspace)

    # 1. Protected directories for writes
    protected_write_targets = [
        "graders/protected/test_oracle.py",
        "graders/protected/deep/nested/gate.py",
        ".git/HEAD",
        ".git/config",
        ".git/objects/4b/825dc642cb6eb9a060e54bf8d69288fbee4904",
        "models/ollama/models/blobs/sha256-abcdef",
        "",  # Workspace root directory itself
        ".",
    ]

    for target in protected_write_targets:
        with pytest.raises(SecurityViolationError):
            bm.validate_path(target, allow_write=True)

        assert bm.is_safe(target, allow_write=True) is False

    # 2. Permitted file writes inside workspace
    permitted_writes = [
        "Source/Game/NewCharacter.cpp",
        "Source/Game/NewCharacter.h",
        "Config/DefaultEngine.ini",
        "Content/Maps/Level_01.umap",
        ".gitignore",      # git config file, but not .git internal repo structure
        ".gitattributes",
    ]

    for target in permitted_writes:
        resolved = bm.validate_path(target, allow_write=True)
        assert resolved.is_relative_to(bm.workspace_root)
        assert bm.is_safe(target, allow_write=True) is True
