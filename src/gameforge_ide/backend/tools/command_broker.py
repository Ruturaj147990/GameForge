"""Central Command Execution Broker and Permissions Engine for GameForge IDE.

Authoritative implementation conforming to DEF-301:
- Implements CommandExecutionBroker governing all terminal command execution.
- Enforces the three Permissions Modes: REQUEST_ALL, AUTO, UNRESTRICTED.
  - REQUEST_ALL: Every command requires explicit user approval.
  - AUTO: Automatically executes routine safe workspace development operations
    (cat, type, Get-Content, dir, ls, pwd, git status, git diff, python, pytest, cmake,
    dotnet, msbuild, UBT, UAT). Prompts before destructive deletes, registry/system edits,
    outside-workspace paths, or elevated admin commands.
  - UNRESTRICTED: Maximum application autonomy without routine approval prompts
    (OS/platform boundaries still apply).
- Shell-aware syntax parsing for Windows PowerShell, Command Prompt, Git Bash, and direct.
  Correctly handles PowerShell aliases, pipelines (|), redirection (>, >>), and quoted paths.
- Central state machine:
  CREATED -> VALIDATING -> AWAITING_APPROVAL / APPROVED -> RUNNING -> VERIFYING -> SUCCEEDED / FAILED / BLOCKED / CANCELLED.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from ...core.process_manager import ProcessLifecycleManager, default_process_manager
from ..models.command_contract import (
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandStatus,
    RiskCategory,
)
from ..models.modes import PermissionsMode
from ..security.boundary import BoundaryManager, SecurityViolationError

logger = logging.getLogger(__name__)

# Forbidden system destruction commands that are unconditionally BLOCKED in all modes
FORBIDDEN_COMMANDS: List[str] = [
    "format",
    "diskpart",
    "bcdedit",
    "del /s /q c:",
    "rmdir /s /q c:",
    "rm -rf /",
    "rm -rf c:",
]

# Token/position-aware patterns for the catastrophic payloads above. Plain substring
# matching blocked legitimate commands such as ``git log --format=%H``,
# ``dotnet format`` or ``clang-format`` and also ``rm -rf /<anything>`` inside the
# workspace, while missing variants such as ``Format-Volume`` or ``rm -rf ~``.
_CMD_START = r"(?:^|[\s;&|(`])"
_FORBIDDEN_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("format", re.compile(_CMD_START + r"format(?:\.com|\.exe)?\s+[a-z]:", re.IGNORECASE)),
    ("diskpart", re.compile(_CMD_START + r"diskpart(?:\.exe)?(?:\s|$)", re.IGNORECASE)),
    ("bcdedit", re.compile(_CMD_START + r"bcdedit(?:\.exe)?(?:\s|$)", re.IGNORECASE)),
    ("format-volume", re.compile(r"\b(?:format-volume|clear-disk|initialize-disk|remove-partition)\b", re.IGNORECASE)),
    ("del /s /q c:", re.compile(_CMD_START + r"(?:del|erase|rmdir|rd)(?:\s+/[a-z])*\s+[a-z]:[\\/]?\*?(?:\s|$|[;&|])", re.IGNORECASE)),
    ("rm -rf /", re.compile(_CMD_START + r"rm\s+(?:-[a-z]+\s+)*-[a-z]*r[a-z]*\s+(?:-[a-z]+\s+)*(?:/|/\*|~|~/|\$home|[a-z]:[\\/]?\*?)(?:\s|$|[;&|])", re.IGNORECASE)),
    ("remove-item drive root", re.compile(r"\bremove-item\b[^;&|]*\s[\"']?[a-z]:[\\/]?\*?[\"']?(?:\s|$|[;&|])", re.IGNORECASE)),
]


def find_forbidden_payload(command: str) -> Optional[str]:
    """Return the label of a catastrophic payload contained in *command*, or None."""
    for label, pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(command or ""):
            return label
    return None


def split_command_segments(command: str) -> List[str]:
    """Split a shell command line on unquoted ``;``, ``&&``, ``||``, ``|``, ``&`` and newlines.

    Used so that risk classification covers *every* command in a chain, not only the
    first executable (``git status; Remove-Item ...`` was previously classified as a
    routine read and auto-executed in Auto mode).
    """
    segments: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    i = 0
    text = command or ""
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch in (";", "\n", "\r", "|", "&"):
            seg = "".join(buf).strip()
            if seg:
                segments.append(seg)
            buf = []
            # swallow doubled operators (&&, ||)
            if i + 1 < len(text) and text[i + 1] == ch and ch in ("|", "&"):
                i += 1
        else:
            buf.append(ch)
        i += 1
    seg = "".join(buf).strip()
    if seg:
        segments.append(seg)
    return segments


# Relative severity used to aggregate the classification of chained commands.
_RISK_SEVERITY: Dict[RiskCategory, int] = {
    RiskCategory.ROUTINE_READ: 0,
    RiskCategory.DEVELOPMENT_TEST: 1,
    RiskCategory.PROJECT_BUILD: 2,
    RiskCategory.WORKSPACE_EDIT: 3,
    RiskCategory.UNCERTAIN_SCRIPT: 4,
    RiskCategory.DESTRUCTIVE_DELETE: 5,
    RiskCategory.OUTSIDE_WORKSPACE: 6,
    RiskCategory.SYSTEM_MODIFICATION: 7,
    RiskCategory.ELEVATED_ADMIN: 8,
}

# Git subcommands that transfer data over the network (egress needs approval, AD/egress rule).
_GIT_NETWORK_SUBCOMMANDS = {"push", "pull", "fetch", "clone", "submodule", "ls-remote", "archive", "send-email"}

# Known safe development commands that AUTO mode permits without routine approval
SAFE_DEVELOPMENT_EXECUTABLES: Set[str] = {
    "python", "python.exe", "py", "py.exe",
    "pytest", "pytest.exe",
    "git", "git.exe",
    "cmake", "cmake.exe",
    "dotnet", "dotnet.exe",
    "msbuild", "msbuild.exe",
    "ctest", "ctest.exe",
    "cargo", "cargo.exe",
    "unrealbuildtool", "unrealbuildtool.exe", "ubt",
    "runuat", "runuat.bat", "uat",
}

# PowerShell alias mappings to canonical cmdlets
POWERSHELL_ALIASES: Dict[str, str] = {
    "cat": "Get-Content",
    "type": "Get-Content",
    "gc": "Get-Content",
    "ls": "Get-ChildItem",
    "dir": "Get-ChildItem",
    "gci": "Get-ChildItem",
    "pwd": "Get-Location",
    "gl": "Get-Location",
    "cd": "Set-Location",
    "chdir": "Set-Location",
    "sl": "Set-Location",
    "cp": "Copy-Item",
    "copy": "Copy-Item",
    "cpi": "Copy-Item",
    "mv": "Move-Item",
    "move": "Move-Item",
    "mi": "Move-Item",
    "rm": "Remove-Item",
    "rmdir": "Remove-Item",
    "del": "Remove-Item",
    "erase": "Remove-Item",
    "rd": "Remove-Item",
    "ri": "Remove-Item",
    "echo": "Write-Output",
    "cls": "Clear-Host",
    "clear": "Clear-Host",
    "man": "Get-Help",
    "help": "Get-Help",
    "select-string": "Select-String",
}


class CommandExecutionBroker:
    """Governs validation, permission checks, shell-aware dispatch, and auditing for all agent commands."""

    def __init__(
        self,
        workspace_root: Union[str, Path],
        default_mode: PermissionsMode = PermissionsMode.AUTO,
        process_manager: Optional[ProcessLifecycleManager] = None,
    ) -> None:
        try:
            p = Path(workspace_root).resolve()
            if not p.exists() or not p.is_dir():
                p = Path.cwd().resolve()
            self.workspace_root = p
        except Exception:
            self.workspace_root = Path.cwd().resolve()
        self.boundary = BoundaryManager(self.workspace_root)
        self.default_mode = default_mode
        self.process_manager = process_manager or default_process_manager

    def classify_risk(
        self,
        command: str,
        shell: str = "powershell",
        working_directory: Optional[Union[str, Path]] = None,
        permissions_mode: Optional[PermissionsMode] = None,
    ) -> Tuple[RiskCategory, bool, str]:
        """Classifies command risk and determines whether user approval is required.
        
        Returns:
            Tuple of (RiskCategory, requires_approval, rationale_string)
        """
        mode = permissions_mode or self.default_mode
        cmd_raw = command.strip()
        cmd_lower = cmd_raw.lower()

        # 1. Check for unconditionally forbidden payloads (execute() blocks these outright)
        forbidden = find_forbidden_payload(cmd_raw)
        if forbidden:
            return (
                RiskCategory.SYSTEM_MODIFICATION,
                True,
                f"Command contains forbidden catastrophic payload '{forbidden}'.",
            )

        # 1b. Check for raw unmanaged subshell invocations or network egress
        subshell_patterns = [
            r"\bcmd(?:\.exe)?\s+/[ck]\b",
            r"\bpowershell(?:\.exe)?\s+-[ce]\b",
            r"\bpwsh(?:\.exe)?\s+-[ce]\b",
            r"\bbash\s+-c\b",
            r"\b(?:curl|wget)\b",
            r"\b(?:invoke-webrequest|iwr|invoke-restmethod|irm)\b",
        ]
        for pat in subshell_patterns:
            if re.search(pat, cmd_lower):
                return (
                    RiskCategory.SYSTEM_MODIFICATION,
                    True,
                    "Command invokes raw unmanaged subshell or network transfer.",
                )

        # 1c. Check for file redirection (writing or appending to files)
        if re.search(r"(?:>>?|[|]\s*(?:out-file|tee|set-content|add-content))", cmd_raw, re.IGNORECASE):
            return (
                RiskCategory.WORKSPACE_EDIT,
                True,
                "Command redirects output to mutate workspace files.",
            )

        # 2. Check for elevated administrator actions
        admin_patterns = [
            r"\b(?:runas|takeown)\b",
            r"-verb\s+runas",
            r"\bnet\s+(?:user|localgroup|group)\b",
            r"\bsudo\b",
        ]
        for pat in admin_patterns:
            if re.search(pat, cmd_lower):
                return (
                    RiskCategory.ELEVATED_ADMIN,
                    True,
                    "Command requests elevated administrator privileges.",
                )

        # 3. Check for system / registry modification
        sys_mod_patterns = [
            r"\b(?:reg|regedit)\b",
            r"hklm:",
            r"hkey_local_machine",
            r"\b(?:sc|netsh|bcdedit|setx|wmic)\b",
            r"(?:set|new|remove)-itemproperty.*hklm",
            r"\b(?:start|stop|restart)-service\b",
        ]
        for pat in sys_mod_patterns:
            if re.search(pat, cmd_lower):
                return (
                    RiskCategory.SYSTEM_MODIFICATION,
                    True,
                    "Command modifies Windows registry or system services.",
                )

        # 4. Check for outside-workspace directory access
        try:
            wd = Path(working_directory).resolve() if working_directory else self.workspace_root
        except Exception:
            wd = self.workspace_root
        try:
            self.boundary.validate_path(wd, allow_write=False)
        except (SecurityViolationError, ValueError):
            return (
                RiskCategory.OUTSIDE_WORKSPACE,
                True,
                f"Working directory '{wd}' is outside the authorized workspace.",
            )

        # Look for absolute path literals pointing outside workspace
        # Matches patterns like C:\Windows, D:\..., or /etc
        # Detect both Windows drive-qualified paths and POSIX absolute paths.
        # Requiring a nested POSIX path avoids mistaking common command flags
        # such as /s or /q for filesystem paths.
        abs_path_matches = re.findall(
            r"""(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/][^ \t\r\n\"']*|/(?:[^/ \t\r\n\"']+/)+[^ \t\r\n\"']+)""",
            cmd_raw,
        )
        for abs_p in abs_path_matches:
            try:
                self.boundary.validate_path(abs_p, allow_write=False)
            except (SecurityViolationError, ValueError):
                return (
                    RiskCategory.OUTSIDE_WORKSPACE,
                    True,
                    f"Command references path '{abs_p}' outside the authorized workspace.",
                )

        # 5. Check for destructive deletions
        # PowerShell: Remove-Item -Recurse, rm -r, rm -rf, rmdir /s, rd /s
        is_delete = False
        is_recursive = False

        if shell in ("powershell", "cmd", "bash", "direct"):
            # Check for cmd style recursive deletes: rmdir /s, rd /s, del /s
            if re.search(r"\b(?:rmdir|rd)\s+.*(?:/s|/q)", cmd_lower) or re.search(r"\bdel\s+.*(?:/s)", cmd_lower):
                is_delete = True
                is_recursive = True

            # Check for PowerShell and Unix delete commands with recursive flags (-r, -rf, -recurse, /s)
            if re.search(r"\b(?:remove-item|rm|rmdir|del|erase|ri)\b", cmd_lower):
                is_delete = True
                if re.search(r"(?:-recurse|-[a-zA-Z]*r[a-zA-Z]*\b|/s\b)", cmd_lower):
                    is_recursive = True

        if is_delete and is_recursive:
            return (
                RiskCategory.DESTRUCTIVE_DELETE,
                True,
                "Command performs recursive or destructive file deletion.",
            )

        # 5b. Chained commands: every segment must be classified, not only the first one.
        #     Subexpression/eval constructs cannot be statically classified at all.
        if shell != "direct":
            if re.search(r"\$\(|`|\b(?:invoke-expression|iex)\b", cmd_raw, re.IGNORECASE):
                return (
                    RiskCategory.UNCERTAIN_SCRIPT,
                    mode != PermissionsMode.UNRESTRICTED,
                    "Command uses dynamic evaluation or subexpressions that cannot be classified statically.",
                )
            segments = split_command_segments(cmd_raw)
            if len(segments) > 1:
                worst: Optional[Tuple[RiskCategory, bool, str]] = None
                for seg in segments:
                    seg_result = self.classify_risk(
                        seg, shell=shell, working_directory=wd, permissions_mode=mode
                    )
                    if worst is None or (
                        (seg_result[1], _RISK_SEVERITY.get(seg_result[0], 4))
                        > (worst[1], _RISK_SEVERITY.get(worst[0], 4))
                    ):
                        worst = seg_result
                assert worst is not None
                return (worst[0], worst[1], f"Chained command ({len(segments)} parts): {worst[2]}")

        # 6. Parse first executable token to identify safe development commands
        first_token = self._extract_first_executable(cmd_raw, shell=shell)
        first_lower = first_token.lower()

        # Check for routine read operations
        routine_reads = {
            "cat", "type", "gc", "get-content",
            "ls", "dir", "gci", "get-childitem",
            "pwd", "gl", "get-location",
            "echo", "write-output", "cls", "clear-host",
            "head", "tail", "more", "findstr", "select-string",
            "grep", "which", "where", "where.exe",
        }
        if first_lower in routine_reads:
            requires = (mode == PermissionsMode.REQUEST_ALL)
            return (
                RiskCategory.ROUTINE_READ,
                requires,
                "Routine workspace read or inspection.",
            )

        # Git read vs write
        if first_lower in ("git", "git.exe"):
            subcmd = self._extract_git_subcommand(cmd_raw)
            if subcmd in ("status", "diff", "log", "branch", "show", "rev-parse", "tag", "remote"):
                requires = (mode == PermissionsMode.REQUEST_ALL)
                return (
                    RiskCategory.ROUTINE_READ,
                    requires,
                    f"Routine git read operation ('git {subcmd}').",
                )
            if subcmd in _GIT_NETWORK_SUBCOMMANDS:
                return (
                    RiskCategory.UNCERTAIN_SCRIPT,
                    mode != PermissionsMode.UNRESTRICTED,
                    f"git {subcmd} transfers data over the network; egress requires approval.",
                )
            # Other git operations (commit, checkout, stash) are workspace edits
            requires = (mode == PermissionsMode.REQUEST_ALL)
            return (
                RiskCategory.WORKSPACE_EDIT,
                requires,
                f"Workspace version-control operation ('git {subcmd}').",
            )

        # Development tests (pytest, ctest, cargo test, dotnet test)
        if first_lower in ("pytest", "pytest.exe") or ("python" in first_lower and "pytest" in cmd_lower):
            requires = (mode == PermissionsMode.REQUEST_ALL)
            return (
                RiskCategory.DEVELOPMENT_TEST,
                requires,
                "Development test execution.",
            )

        # Builds (cmake, dotnet build, msbuild, UBT, UAT)
        if first_lower in ("cmake", "cmake.exe", "dotnet", "dotnet.exe", "msbuild", "msbuild.exe"):
            requires = (mode == PermissionsMode.REQUEST_ALL)
            return (
                RiskCategory.PROJECT_BUILD,
                requires,
                f"Project build tool invocation ({first_lower}).",
            )
        if first_lower in ("unrealbuildtool", "unrealbuildtool.exe", "ubt", "runuat", "runuat.bat", "runuat.sh", "uat", "automationtool", "automationtool.exe"):
            requires = (mode == PermissionsMode.REQUEST_ALL)
            return (
                RiskCategory.PROJECT_BUILD,
                requires,
                "Unreal Engine build toolchain invocation.",
            )

        # Python scripts or other safe tools
        if first_lower in SAFE_DEVELOPMENT_EXECUTABLES:
            requires = (mode == PermissionsMode.REQUEST_ALL)
            return (
                RiskCategory.WORKSPACE_EDIT,
                requires,
                f"Workspace development tool invocation ({first_lower}).",
            )

        # In UNRESTRICTED mode, ordinary commands execute without routine prompts
        if mode == PermissionsMode.UNRESTRICTED:
            return (
                RiskCategory.WORKSPACE_EDIT,
                False,
                "Command allowed under Unrestricted permissions mode.",
            )

        # Default fallback in AUTO mode: ask when uncertain
        if mode == PermissionsMode.REQUEST_ALL:
            return (
                RiskCategory.UNCERTAIN_SCRIPT,
                True,
                "All commands require explicit approval in Request All mode.",
            )

        # In AUTO mode: unclassified scripts or commands require approval
        return (
            RiskCategory.UNCERTAIN_SCRIPT,
            True,
            f"Unclassified executable or script '{first_token}' requires explicit approval in Auto mode.",
        )

    def _extract_first_executable(self, command: str, shell: str = "powershell") -> str:
        """Extracts the primary executable name or cmdlet from a command string."""
        s = command.strip()
        # Handle environment variables prefix if any, e.g. FOO=BAR cmd
        if "=" in s and not s.startswith(("-", "/")):
            parts = s.split(None, 1)
            if len(parts) > 1 and "=" in parts[0]:
                s = parts[1]

        # Handle pipelines: primary command is the first element before '|'
        if "|" in s:
            s = s.split("|", 1)[0].strip()

        # Handle redirections: remove redirection targets
        for op in (">>", ">", "<"):
            if op in s:
                s = s.split(op, 1)[0].strip()

        # Tokenize preserving quotes
        tokens = []
        try:
            tokens = shlex.split(s, posix=False)
        except Exception:
            tokens = s.split()

        if not tokens:
            return ""

        raw_first = tokens[0].strip("\"'")
        # Strip path prefixes like .\foo.exe or bin/foo
        first_name = Path(raw_first).name

        # Resolve PowerShell aliases
        if shell == "powershell":
            first_name = POWERSHELL_ALIASES.get(first_name.lower(), first_name)

        return first_name

    def _extract_git_subcommand(self, command: str) -> str:
        """Extracts the git subcommand (e.g. status, diff, commit)."""
        tokens = command.strip().split()
        for idx, t in enumerate(tokens):
            if t.lower() in ("git", "git.exe") and idx + 1 < len(tokens):
                # Skip flags like -C, --no-pager
                for next_t in tokens[idx + 1:]:
                    if not next_t.startswith("-"):
                        return next_t.lower()
        return "unknown"

    def execute(
        self,
        request: CommandExecutionRequest,
        approval_granted: bool = False,
    ) -> CommandExecutionResult:
        """Executes a command through the authoritative state machine."""
        t0 = time.time()
        result = CommandExecutionResult(
            execution_id=request.execution_id,
            command=request.command,
            shell=request.shell,
            working_directory=request.working_directory or str(self.workspace_root),
            status=CommandStatus.CREATED,
            permissions_mode=request.permissions_mode,
            started_at=t0,
        )

        # 1. State: VALIDATING
        result.status = CommandStatus.VALIDATING
        cmd_text = request.command.strip()
        if not cmd_text:
            result.status = CommandStatus.FAILED
            result.error_message = "Command string is empty."
            result.finished_at = time.time()
            result.duration_s = round(result.finished_at - t0, 3)
            return result

        # Check unconditionally forbidden commands
        forbidden = find_forbidden_payload(cmd_text)
        if forbidden:
            result.status = CommandStatus.BLOCKED
            result.error_message = f"Security boundary violation: Command contains forbidden catastrophic payload '{forbidden}'."
            result.risk_category = RiskCategory.SYSTEM_MODIFICATION
            result.finished_at = time.time()
            result.duration_s = round(result.finished_at - t0, 3)
            return result

        # Validate working directory
        wd = Path(request.working_directory).resolve() if request.working_directory else self.workspace_root
        try:
            self.boundary.validate_path(wd, allow_write=False)
        except (SecurityViolationError, ValueError) as exc:
            result.status = CommandStatus.BLOCKED
            result.error_message = f"Security boundary violation: Invalid working directory: {exc}"
            result.risk_category = RiskCategory.OUTSIDE_WORKSPACE
            result.finished_at = time.time()
            result.duration_s = round(result.finished_at - t0, 3)
            return result

        if not wd.exists() or not wd.is_dir():
            result.status = CommandStatus.FAILED
            result.error_message = f"Working directory does not exist or is not a directory: {wd}"
            result.finished_at = time.time()
            result.duration_s = round(result.finished_at - t0, 3)
            return result

        # 2. Risk Classification & Permission Evaluation
        risk_cat, requires_approval, rationale = self.classify_risk(
            command=cmd_text,
            shell=request.shell,
            working_directory=wd,
            permissions_mode=request.permissions_mode,
        )
        result.risk_category = risk_cat
        result.requires_approval = requires_approval

        # 3. State: AWAITING_APPROVAL vs APPROVED
        if requires_approval and not approval_granted:
            result.status = CommandStatus.AWAITING_APPROVAL
            result.metadata["approval_reason"] = rationale
            result.finished_at = time.time()
            result.duration_s = round(result.finished_at - t0, 3)
            return result

        result.approved_by_user = True if requires_approval else None
        result.status = CommandStatus.APPROVED

        # 4. State: RUNNING
        result.status = CommandStatus.RUNNING

        # Build shell execution args
        shell_type = request.shell.lower()
        if shell_type == "powershell":
            # Use PowerShell with execution policy bypass, no profile, non-interactive
            exec_args = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd_text,
            ]
        elif shell_type == "cmd":
            exec_args = ["cmd.exe", "/c", cmd_text]
        elif shell_type == "bash":
            bash_exe = self._resolve_bash_executable()
            exec_args = [bash_exe, "-c", cmd_text]
        elif shell_type == "direct":
            try:
                exec_args = shlex.split(cmd_text, posix=False)
                # Unquote outer tokens
                cleaned = []
                for t in exec_args:
                    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
                        cleaned.append(t[1:-1])
                    else:
                        cleaned.append(t)
                exec_args = cleaned
            except Exception:
                exec_args = cmd_text.split()
        else:
            # Default to powershell
            exec_args = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd_text,
            ]

        # Execute windowless child process with Job Object tracking
        try:
            exit_code, stdout_str, stderr_str, duration = self.process_manager.run(
                exec_args,
                cwd=wd,
                env=request.env_overrides if request.env_overrides else None,
                shell=False,
                timeout=float(request.timeout_seconds),
            )
        except Exception as exc:
            result.status = CommandStatus.FAILED
            result.error_message = f"Process execution failure: {exc}"
            result.finished_at = time.time()
            result.duration_s = round(result.finished_at - t0, 3)
            return result

        # 5. State: VERIFYING
        result.status = CommandStatus.VERIFYING
        result.exit_code = exit_code
        result.stdout = stdout_str
        result.stderr = stderr_str
        result.duration_s = duration
        result.finished_at = time.time()

        # 6. Terminal State: SUCCEEDED vs FAILED
        if exit_code == 0:
            result.status = CommandStatus.SUCCEEDED
        else:
            result.status = CommandStatus.FAILED
            if "timed out after" in stderr_str:
                result.error_message = f"Command timed out after {request.timeout_seconds} seconds."
            else:
                result.error_message = f"Command failed with exit code {exit_code}."

        return result

    @staticmethod
    def _resolve_bash_executable() -> str:
        """Finds Git Bash or system bash on Windows."""
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ):
            try:
                if Path(candidate).is_file():
                    return candidate
            except OSError:
                continue
        found = shutil.which("bash")
        return found if found else "bash.exe"
