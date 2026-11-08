"""Terminal Command Execution for GameForge IDE.

Wired through the central CommandExecutionBroker (DEF-301) and ProcessLifecycleManager (DEF-305).
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..security.boundary import BoundaryManager, SecurityViolationError
from ..models.command_contract import (
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandStatus,
    RiskCategory,
)
from ..models.modes import PermissionsMode
from .command_broker import CommandExecutionBroker


class TerminalTools:
    """Executes commands within the workspace governed by CommandExecutionBroker."""

    FORBIDDEN_COMMANDS: List[str] = [
        "format",
        "diskpart",
        "bcdedit",
        "del /s /q c:",
        "rmdir /s /q c:",
    ]

    SHELL_SYNTAX = re.compile(r"(?:[;&|`%*?]|\r|\n|\$\(|[<>]|\$env:|\$\{)")
    MAX_TIMEOUT_SECONDS = 300

    def __init__(self, workspace_root: Path):
        self.boundary = BoundaryManager(workspace_root)
        self.workspace_root = self.boundary.workspace_root
        self.broker = CommandExecutionBroker(self.workspace_root)

    def _blocked(self, message: str) -> Dict[str, Any]:
        return {
            "status": "BLOCKED",
            "exit_code": -1,
            "error": f"Security boundary violation: {message}",
            "stdout": "",
            "stderr": "",
        }

    def _parse_command(self, command: str) -> List[str]:
        """Return safe argv or raise ValueError without ever interpreting a shell.
        
        Preserves Windows backslash path separators while cleanly removing paired outer quotes.
        """
        if not command or not command.strip():
            raise ValueError("Command is empty.")
        if self.SHELL_SYNTAX.search(command):
            raise ValueError("Shell operators, redirection, interpolation, and multiline commands are not permitted.")
        try:
            # posix=False preserves Windows backslashes in paths like tests\unit\test_foo.py
            raw_tokens = shlex.split(command, posix=False)
            args = []
            for t in raw_tokens:
                if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
                    args.append(t[1:-1])
                else:
                    args.append(t)
        except ValueError as exc:
            raise ValueError(f"Unable to parse command: {exc}") from exc
        if not args:
            raise ValueError("Command is empty.")
        if len(Path(args[0]).parts) > 1:
            raise ValueError(f"Path-qualified executable '{args[0]}' is not permitted.")
        executable = Path(args[0]).name.lower()
        if executable in (
            "del", "erase", "format", "diskpart", "bcdedit",
            "powershell", "powershell.exe", "pwsh", "pwsh.exe",
            "cmd", "cmd.exe", "bash", "bash.exe", "sh", "sh.exe",
        ):
            raise ValueError(f"Executable '{args[0]}' is not in the approved agent command allowlist.")
        for arg in args[1:]:
            if ".." in arg or "%" in arg or "$env:" in arg or "${" in arg:
                raise ValueError(f"Argument '{arg}' contains prohibited interpolation or traversal.")
            if arg.startswith(("/", "\\")) or (len(arg) > 1 and arg[1] == ":"):
                raise ValueError(f"Argument '{arg}' refers to an absolute path outside workspace.")

            # Check key-value separated arguments (e.g. --path=C:\..., -o=/etc/...)
            val = ""
            if "=" in arg:
                val = arg.split("=", 1)[1].strip("\"'")
            elif arg.startswith(("-o", "-I", "-L")) and len(arg) > 2:
                val = arg[2:].strip("\"'")

            if val and (val.startswith(("/", "\\")) or (len(val) > 1 and val[1] == ":")):
                raise ValueError(f"Argument '{arg}' refers to an absolute path outside workspace.")

        return args

    def run_command(
        self,
        command: str,
        subpath: str = ".",
        timeout_seconds: int = 60,
        permissions_mode: Optional[Union[PermissionsMode, str]] = None,
        approval_granted: bool = False,
        shell: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Executes a command within the workspace directory via CommandExecutionBroker."""
        cmd_lower = command.lower().strip()
        for forbidden in self.FORBIDDEN_COMMANDS:
            if forbidden in cmd_lower:
                return self._blocked(f"Command contains forbidden operation '{forbidden}'")

        try:
            if isinstance(timeout_seconds, bool):
                raise ValueError()
            timeout_val = int(timeout_seconds)
        except (ValueError, TypeError):
            return self._blocked("timeout_seconds must be an integer.")

        if not 1 <= timeout_val <= self.MAX_TIMEOUT_SECONDS:
            return self._blocked(
                f"timeout_seconds must be between 1 and {self.MAX_TIMEOUT_SECONDS}."
            )
        timeout_seconds = timeout_val

        # Resolve working directory
        try:
            working_dir = self.boundary.validate_path(subpath, allow_write=False)
        except (ValueError, SecurityViolationError) as exc:
            return self._blocked(str(exc))

        if not working_dir.exists() or not working_dir.is_dir():
            return self._blocked(f"Working directory is not an existing directory: '{subpath}'.")

        # Resolve permissions mode
        pm = PermissionsMode.from_str(permissions_mode) if permissions_mode else PermissionsMode.AUTO

        # Default to direct shell-free execution for agent security (REQ-051).
        # Explicit shell choices (powershell, cmd, bash) can be passed when needed.
        target_shell = shell or "direct"
        if target_shell == "direct":
            try:
                args = self._parse_command(command)
            except (ValueError, SecurityViolationError) as exc:
                return self._blocked(str(exc))
        elif target_shell not in ("powershell", "cmd", "bash"):
            return self._blocked(f"Unsupported shell: {target_shell!r}")

        request = CommandExecutionRequest(
            command=command,
            shell=target_shell,
            working_directory=str(working_dir),
            permissions_mode=pm,
            reason=reason,
            timeout_seconds=timeout_seconds,
        )

        res = self.broker.execute(request, approval_granted=approval_granted)

        # Map to dict format expected by callers
        status_label = "SUCCESS" if res.status == CommandStatus.SUCCEEDED else (
            "BLOCKED" if res.status == CommandStatus.BLOCKED else (
                "TIMEOUT" if "timed out after" in (res.error_message or "").lower() else (
                    "PENDING_APPROVAL" if res.status == CommandStatus.AWAITING_APPROVAL else (
                        "FAILED" if res.status == CommandStatus.FAILED else str(res.status.value)
                    )
                )
            )
        )

        return {
            "status": status_label,
            "exit_code": res.exit_code if res.exit_code is not None else -1,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "output": res.stdout,
            "error": res.error_message or (res.stderr if res.status == CommandStatus.FAILED else ""),
            "duration_seconds": res.duration_s,
            "command": res.command,
            "argv": args if "args" in locals() else [command],
            "requires_approval": res.requires_approval,
            "risk_category": res.risk_category.value,
            "execution_id": res.execution_id,
        }
