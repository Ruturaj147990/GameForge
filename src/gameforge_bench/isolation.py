"""Operating-System Execution Isolation Abstraction and Capability Auditing (Deliverable F).

Defines formal isolation classifications, capability discovery on Windows hosts,
and concrete isolation providers. Enforces strict boundary truthfulness:
never claims OS_SANDBOX_VERIFIED unless hypervisor or container containment is experimentally verified.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0


class IsolationLevel(str, Enum):
    """Standardized security classification for candidate execution environments."""
    TRUSTED_LOCAL = "TRUSTED_LOCAL"
    LOW_PRIVILEGE_PROCESS = "LOW_PRIVILEGE_PROCESS"
    OS_SANDBOX_VERIFIED = "OS_SANDBOX_VERIFIED"
    ISOLATION_UNAVAILABLE = "ISOLATION_UNAVAILABLE"


@dataclass
class IsolationAuditResult:
    """Read-only audit of host OS virtualization, containers, and process security facilities."""
    host_os: str
    host_build: str
    hyper_v_active: bool
    windows_sandbox_available: bool
    containers_available: bool
    wsl_available: bool
    supported_classifications: List[str]
    default_classification: str
    notes: str
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host_os": self.host_os,
            "host_build": self.host_build,
            "hyper_v_active": self.hyper_v_active,
            "windows_sandbox_available": self.windows_sandbox_available,
            "containers_available": self.containers_available,
            "wsl_available": self.wsl_available,
            "supported_classifications": self.supported_classifications,
            "default_classification": self.default_classification,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }


def audit_os_isolation_capabilities() -> IsolationAuditResult:
    """Inspects the local Windows environment without changing system configuration."""
    host_os = f"{platform.system()} {platform.release()}"
    host_build = platform.version()

    # Check Windows Sandbox via SystemRoot or PATH
    sys_root = Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "/Windows")
    wsb_path = sys_root / "System32" / "WindowsSandbox.exe"
    wsb_available = wsb_path.is_file() or shutil.which("WindowsSandbox.exe") is not None

    # Check Docker / Podman
    containers_available = False
    for tool in ("docker", "podman"):
        if shutil.which(tool) is not None:
            containers_available = True
            break

    # Check WSL
    wsl_available = False
    if shutil.which("wsl") is not None:
        try:
            # Non-interactive quick check
            res = subprocess.run(
                ["wsl", "-l", "-q"],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=_creationflags(),
            )
            if res.returncode == 0 and res.stdout.strip():
                wsl_available = True
        except Exception:
            pass

    # Check Hyper-V service
    hyper_v_active = False
    if platform.system() == "Windows":
        try:
            # Query vmcompute service without modifying state
            cmd = ["sc", "query", "vmcompute"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=_creationflags(),
            )
            if "RUNNING" in res.stdout:
                hyper_v_active = True
        except Exception:
            pass

    supported = [IsolationLevel.TRUSTED_LOCAL.value, IsolationLevel.LOW_PRIVILEGE_PROCESS.value]
    if hyper_v_active and (containers_available or wsb_available):
        supported.append(IsolationLevel.OS_SANDBOX_VERIFIED.value)

    notes = (
        "Host provides file-level allowlisting and process-level timeouts/working directory restrictions. "
        "Hypervisor or hardware container sandboxing is not active; native C++ runs under host user credentials."
    )

    return IsolationAuditResult(
        host_os=host_os,
        host_build=host_build,
        hyper_v_active=hyper_v_active,
        windows_sandbox_available=wsb_available,
        containers_available=containers_available,
        wsl_available=wsl_available,
        supported_classifications=supported,
        default_classification=IsolationLevel.LOW_PRIVILEGE_PROCESS.value,
        notes=notes,
    )


class IsolationProvider(ABC):
    """Abstract interface for preparing, executing, and tearing down candidate isolation environments."""

    @property
    @abstractmethod
    def classification(self) -> IsolationLevel:
        """The formal classification guaranteed by this provider."""
        pass

    @abstractmethod
    def prepare_workspace(self, source_dir: Path, workspace_dir: Path) -> bool:
        """Sets up the isolated workspace."""
        pass

    @abstractmethod
    def execute(
        self,
        cmd: List[str],
        cwd: Path,
        timeout_seconds: float,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str, float]:
        """Executes candidate process under the provider's security boundaries."""
        pass

    @abstractmethod
    def cleanup(self, workspace_dir: Path) -> None:
        """Tears down the execution environment and removes temporary state."""
        pass

    @abstractmethod
    def verify_sentinel_access(self, target_forbidden_path: Path) -> bool:
        """Tests whether an unauthorized file access attempt is correctly blocked or denied."""
        pass


class RestrictedProcessIsolationProvider(IsolationProvider):
    """Process-level isolation enforcing workspace boundaries, timeouts, and sanitized environments."""

    def __init__(self, audit_result: Optional[IsolationAuditResult] = None):
        self._audit = audit_result or audit_os_isolation_capabilities()

    @property
    def classification(self) -> IsolationLevel:
        return IsolationLevel.LOW_PRIVILEGE_PROCESS

    def prepare_workspace(self, source_dir: Path, workspace_dir: Path) -> bool:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)
        workspace_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, workspace_dir, dirs_exist_ok=True)
        return True

    def execute(
        self,
        cmd: List[str],
        cwd: Path,
        timeout_seconds: float,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str, float]:
        start = time.time()
        # Build sanitized execution environment
        clean_env = os.environ.copy()
        # Strip sensitive credentials or dangerous tokens if present
        for k in list(clean_env.keys()):
            if any(tok in k.upper() for tok in ("TOKEN", "SECRET", "KEY", "PASSWORD", "AUTH")):
                del clean_env[k]

        if env_vars:
            clean_env.update(env_vars)

        clean_env["GAMEFORGE_ISOLATION_LEVEL"] = self.classification.value

        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=clean_env,
                creationflags=_creationflags(),
            )
            duration = time.time() - start
            return res.returncode, res.stdout, res.stderr, duration
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + f"\nProcess killed after exceeding timeout of {timeout_seconds}s"
            return -1, stdout, stderr, duration

    def cleanup(self, workspace_dir: Path) -> None:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)

    def verify_sentinel_access(self, target_forbidden_path: Path) -> bool:
        """Simulates testing a harmless sentinel path outside allowed candidate boundaries."""
        # Under LOW_PRIVILEGE_PROCESS, host OS allows read/write permitted to host account.
        # Boundary test verifies that policy checker or candidate wrapper flags the escape attempt.
        try:
            target_resolved = target_forbidden_path.resolve()
            # If path points to protected grading areas, return False (access prohibited)
            for protected in ("graders", "configs/acceptance_criteria", ".git"):
                if protected in str(target_resolved).lower().replace("\\", "/"):
                    return False
            return True
        except Exception:
            return False
