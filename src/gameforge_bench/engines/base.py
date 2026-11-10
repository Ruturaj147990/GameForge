"""Common Engine Adapter Interface and Safe Subprocess Execution."""

from __future__ import annotations

import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


@dataclass
class SubprocessResult:
    command: list[str]
    return_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_log_path: Optional[str] = None
    stderr_log_path: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.return_code == 0 and not self.timed_out


@dataclass
class EngineDiscoveryResult:
    engine_name: str
    is_installed: bool
    version: Optional[str] = None
    executable_path: Optional[str] = None
    build_toolchain_path: Optional[str] = None
    is_runnable: bool = False
    notes: str = ""


@dataclass
class BuildResult:
    success: bool
    duration_seconds: float
    return_code: int
    log_output: str
    error_summary: Optional[str] = None
    is_infrastructure_failure: bool = False


@dataclass
class TestResult:
    __test__ = False
    name: str
    passed: bool
    duration_seconds: float
    message: str = ""
    error_trace: Optional[str] = None


@dataclass
class ProbeMeasurement:
    probe_id: str
    target_value: Any
    measured_value: Any
    tolerance: Any
    passed: bool
    unit: str = ""
    details: str = ""


@dataclass
class AssetValidationResult:
    passed: bool
    missing_components: List[str] = field(default_factory=list)
    missing_assets: List[str] = field(default_factory=list)
    unresolved_references: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def safe_subprocess_run(
    cmd: List[str],
    cwd: Optional[Path | str] = None,
    timeout_seconds: float = 300.0,
    log_dir: Optional[Path | str] = None,
    log_prefix: str = "proc",
    env: Optional[Dict[str, str]] = None,
) -> SubprocessResult:
    """Executes a subprocess safely with timeouts, process tree cleanup, and logging."""
    start_time = time.time()
    timed_out = False
    stdout_str = ""
    stderr_str = ""
    return_code = -1

    out_log_file = None
    err_log_file = None
    if log_dir:
        ld = Path(log_dir)
        ld.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        out_log_file = ld / f"{log_prefix}_{ts}_stdout.log"
        err_log_file = ld / f"{log_prefix}_{ts}_stderr.log"

    sub_env = os.environ.copy()
    if env:
        sub_env.update(env)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sub_env,
            creationflags=creationflags,
        )

        try:
            out, err = proc.communicate(timeout=timeout_seconds)
            stdout_str = out or ""
            stderr_str = err or ""
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            # Safely terminate child processes using psutil or taskkill
            killed_tree = False
            try:
                if psutil is not None:
                    parent = psutil.Process(proc.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except Exception:
                            pass
                    parent.kill()
                    killed_tree = True
            except Exception:
                pass

            if not killed_tree and os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        creationflags=creationflags,
                    )
                    killed_tree = True
                except Exception:
                    pass

            if not killed_tree:
                try:
                    proc.kill()
                except Exception:
                    pass

            out, err = proc.communicate()
            stdout_str = out or ""
            stderr_str = (err or "") + f"\n[Process killed: exceeded timeout of {timeout_seconds}s]"
            return_code = -999

    except Exception as exc:
        stderr_str = f"Failed to launch command: {exc}"
        return_code = -1

    duration = time.time() - start_time

    if out_log_file:
        try:
            out_log_file.write_text(stdout_str, encoding="utf-8", errors="replace")
        except Exception:
            pass
    if err_log_file:
        try:
            err_log_file.write_text(stderr_str, encoding="utf-8", errors="replace")
        except Exception:
            pass

    return SubprocessResult(
        command=cmd,
        return_code=return_code,
        duration_seconds=duration,
        stdout=stdout_str,
        stderr=stderr_str,
        timed_out=timed_out,
        stdout_log_path=str(out_log_file) if out_log_file else None,
        stderr_log_path=str(err_log_file) if err_log_file else None,
    )


class EngineAdapter(ABC):
    """Abstract interface defining the lifecycle of an engine integration adapter."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Name of the engine (e.g. 'unreal' or 'unity')."""
        pass

    @abstractmethod
    def discover(self) -> EngineDiscoveryResult:
        """Discovers the installed engine version, executable path, and toolchain."""
        pass

    @abstractmethod
    def validate_project_structure(self, project_path: Path) -> tuple[bool, str]:
        """Validates that the candidate project directory has the expected engine structure."""
        pass

    @abstractmethod
    def prepare_clean_workspace(self, fixture_path: Path, target_path: Path) -> None:
        """Prepares an isolated, clean evaluation copy of the project fixture."""
        pass

    @abstractmethod
    def build_project(self, project_path: Path, log_dir: Path) -> BuildResult:
        """Executes the engine project build or asset compilation step."""
        pass

    @abstractmethod
    def execute_automated_tests(self, project_path: Path, log_dir: Path) -> List[TestResult]:
        """Executes automated gameplay and unit tests."""
        pass

    @abstractmethod
    def execute_behavior_probes(
        self, project_path: Path, log_dir: Path, acceptance_config: Dict[str, Any]
    ) -> List[ProbeMeasurement]:
        """Executes runtime gameplay behavior probes (speed, apex, timing, camera)."""
        pass

    @abstractmethod
    def inspect_saved_assets(
        self, project_path: Path, acceptance_config: Dict[str, Any]
    ) -> AssetValidationResult:
        """Inspects saved native assets, components, and references."""
        pass
