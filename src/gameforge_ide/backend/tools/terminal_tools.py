"""Terminal Command Execution for GameForge IDE."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..security.boundary import BoundaryManager, SecurityViolationError


class TerminalTools:
    """Executes a deliberately small set of non-shell workspace commands.

    This is the agent tool, not the user-controlled interactive terminal.  It
    never invokes a command shell: compound PowerShell/cmd expressions and
    redirection are rejected before process creation.
    """

    FORBIDDEN_COMMANDS: List[str] = [
        "format",
        "diskpart",
        "bcdedit",
        "del /s /q c:",
        "rmdir /s /q c:",
    ]

    # These commands are useful for inspected project work and have predictable
    # argument parsing when launched without a shell.  Adding a command is a
    # security review decision, not a model prompt change.
    ALLOWED_EXECUTABLES = {
        "python", "python.exe", "py", "py.exe", "pytest", "pytest.exe",
        "git", "git.exe", "cmake", "cmake.exe", "dotnet", "dotnet.exe",
        "msbuild", "msbuild.exe",
    }
    SHELL_SYNTAX = re.compile(r"(?:[;&|`%*?]|\r|\n|\$\(|[<>]|\$env:|\$\{)")
    MAX_TIMEOUT_SECONDS = 300

    def __init__(self, workspace_root: Path):
        self.boundary = BoundaryManager(workspace_root)
        self.workspace_root = self.boundary.workspace_root

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
        if executable not in self.ALLOWED_EXECUTABLES:
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
    ) -> Dict[str, Any]:
        """Executes a command within the workspace directory."""
        cmd_lower = command.lower().strip()
        for forbidden in self.FORBIDDEN_COMMANDS:
            if forbidden in cmd_lower:
                return self._blocked(f"Command contains forbidden operation '{forbidden}'")

        if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
            return self._blocked("timeout_seconds must be an integer.")
        if not 1 <= timeout_seconds <= self.MAX_TIMEOUT_SECONDS:
            return self._blocked(
                f"timeout_seconds must be between 1 and {self.MAX_TIMEOUT_SECONDS}."
            )

        try:
            args = self._parse_command(command)
            working_dir = self.boundary.validate_path(subpath, allow_write=False)
        except (ValueError, SecurityViolationError) as exc:
            return self._blocked(str(exc))

        if not working_dir.exists() or not working_dir.is_dir():
            return self._blocked(f"Working directory is not an existing directory: '{subpath}'.")

        t0 = time.time()
        proc: Optional[subprocess.Popen] = None
        try:
            from ...core import jobs
            proc = jobs.spawn(
                args,
                cwd=str(working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            # Explicitly guarantee process joins the IDE Windows Job Object
            jobs.adopt(proc)

            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            duration = round(time.time() - t0, 3)
            return {
                "status": "SUCCESS" if proc.returncode == 0 else "FAILED",
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "output": stdout,
                "duration_seconds": duration,
                "command": command,
                "argv": args,
            }
        except subprocess.TimeoutExpired as exc:
            stdout_str = ""
            stderr_str = ""
            if proc is not None:
                try:
                    proc.kill()
                    if sys.platform == "win32":
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                capture_output=True,
                                timeout=5,
                            )
                        except Exception:
                            pass
                    rem_out, rem_err = proc.communicate(timeout=2)
                    stdout_str = exc.stdout or rem_out or ""
                    stderr_str = exc.stderr or rem_err or ""
                except Exception:
                    stdout_str = exc.stdout or ""
                    stderr_str = exc.stderr or ""

            return {
                "status": "TIMEOUT",
                "exit_code": -1,
                "error": f"Command timed out after {timeout_seconds} seconds.",
                "stdout": stdout_str if isinstance(stdout_str, str) else stdout_str.decode("utf-8", errors="replace"),
                "stderr": stderr_str if isinstance(stderr_str, str) else stderr_str.decode("utf-8", errors="replace"),
                "command": command,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "exit_code": -1,
                "error": f"Execution failed: {str(e)}",
                "stdout": "",
                "stderr": "",
                "command": command,
            }
        finally:
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
