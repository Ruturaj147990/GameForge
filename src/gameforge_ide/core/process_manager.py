"""Windows Process Lifecycle & Lock-Aware File Cleanup for GameForge IDE.

Authoritative implementation conforming to DEF-305:
- Manages subprocess lifecycles using Windows Job Objects (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE).
- Enforces CREATE_NO_WINDOW (0x08000000) and hidden window flags on all Windows process invocations.
- Prevents orphaned background processes and zombie trees.
- Lock-aware file cleanup utility that retries transient Windows sharing violations
  (e.g. .pdb, .exe, .dll locks from compilers or indexers) with bounded exponential backoff and jitter.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, TypeVar, Union

from . import jobs

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Windows constants
CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001

# Explicit 64-bit Windows Job Object ctypes signatures (prevents 32-bit c_int handle truncation on 64-bit Windows)
if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _k32.CloseHandle.restype = wintypes.BOOL


def assign_pid_to_job_object(job_handle: Any, pid: int) -> bool:
    """Assign a process by PID to a Windows Job Object, guaranteeing CloseHandle runs in finally."""
    if sys.platform != "win32" or not job_handle or not pid:
        return False
    proc_handle = _k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
    if not proc_handle:
        return False
    try:
        return bool(_k32.AssignProcessToJobObject(wintypes.HANDLE(int(job_handle)), proc_handle))
    finally:
        _k32.CloseHandle(proc_handle)


# Sensitive environment prefixes and keys that must never leak to child processes
SENSITIVE_ENV_PREFIXES = ("GAMEFORGE_API_", "GAMEFORGE_BRIDGE_", "GAMEFORGE_TOKEN", "GAMEFORGE_SECRET", "GAMEFORGE_AUTH")
SENSITIVE_ENV_KEYS = frozenset({
    "GAMEFORGE_API_TOKEN",
    "GAMEFORGE_BRIDGE_TOKEN",
    "GAMEFORGE_SESSION_TOKEN",
    "GAMEFORGE_SECRET_KEY",
})


def sanitize_environment(
    base_env: Optional[Dict[str, str]] = None,
    extra_env: Optional[Dict[str, str]] = None,
    allowlist_keys: Optional[Set[str]] = None,
) -> Dict[str, str]:
    """Sanitize environment variables for child process execution (DEF-REM-P4A).

    Removes administrative API tokens, secrets, and sensitive GAMEFORGE_* variables.
    """
    raw = dict(base_env if base_env is not None else os.environ)
    clean: Dict[str, str] = {}
    for k, v in raw.items():
        k_upper = k.upper()
        if allowlist_keys and k in allowlist_keys:
            clean[k] = v
            continue
        if k_upper in SENSITIVE_ENV_KEYS or any(k_upper.startswith(prefix) for prefix in SENSITIVE_ENV_PREFIXES):
            continue
        clean[k] = v
    if extra_env:
        for k, v in extra_env.items():
            k_upper = k.upper()
            if not allowlist_keys or k not in allowlist_keys:
                if k_upper in SENSITIVE_ENV_KEYS or any(k_upper.startswith(prefix) for prefix in SENSITIVE_ENV_PREFIXES):
                    continue
            clean[k] = v
    return clean


# Transient Windows error codes indicating sharing/locking violations
SHARING_VIOLATION_ERRNOS = {13}  # PermissionError (EACCES)
SHARING_VIOLATION_WINERRORS = {
    5,   # ERROR_ACCESS_DENIED
    32,  # ERROR_SHARING_VIOLATION
    33,  # ERROR_LOCK_VIOLATION
}


class ProcessLifecycleManager:
    """Manages child processes, guaranteeing Job Object containment and windowless execution."""

    _instance: Optional["ProcessLifecycleManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tracked_processes: Set[subprocess.Popen] = set()

    @classmethod
    def get_instance(cls) -> "ProcessLifecycleManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def get_windowless_startupinfo() -> Optional[subprocess.STARTUPINFO]:
        """Creates a hidden window STARTUPINFO for Windows."""
        if sys.platform != "win32":
            return None
        si = subprocess.STARTUPINFO()
        si.dwFlags |= STARTF_USESHOWWINDOW
        si.wShowWindow = SW_HIDE
        return si

    def spawn(
        self,
        args: Union[str, Sequence[str]],
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
        shell: bool = False,
        capture_output: bool = True,
        text: bool = True,
        encoding: str = "utf-8",
        errors: str = "replace",
        timeout: Optional[float] = None,
        extra_creationflags: int = 0,
        **kwargs: Any,
    ) -> subprocess.Popen:
        """Spawns a child process within the IDE Windows Job Object with CREATE_NO_WINDOW."""
        creationflags = extra_creationflags
        startupinfo = kwargs.pop("startupinfo", None)

        if sys.platform == "win32":
            creationflags |= CREATE_NO_WINDOW
            if startupinfo is None:
                startupinfo = self.get_windowless_startupinfo()

        stdout = kwargs.pop("stdout", subprocess.PIPE if capture_output else None)
        stderr = kwargs.pop("stderr", subprocess.PIPE if capture_output else None)
        stdin = kwargs.pop("stdin", subprocess.PIPE)

        cwd_str = str(cwd) if cwd is not None else None

        # Sanitize child environment to prevent administrative token leakage (DEF-REM-P4A)
        proc_env = sanitize_environment(extra_env=env)

        proc = subprocess.Popen(
            args,
            cwd=cwd_str,
            env=proc_env,
            shell=shell,
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            text=text,
            encoding=encoding if text else None,
            errors=errors if text else None,
            creationflags=creationflags,
            startupinfo=startupinfo,
            **kwargs,
        )

        # Enforce Windows Job Object attachment
        self.adopt(proc)
        return proc

    def adopt(self, proc: subprocess.Popen) -> bool:
        """Adopts an already started process into the Windows Job Object and registry."""
        with self._lock:
            self._tracked_processes.add(proc)
            dead = [p for p in self._tracked_processes if p.poll() is not None]
            for p in dead:
                self._tracked_processes.discard(p)

        ok = jobs.adopt(proc)
        if not ok and sys.platform == "win32" and getattr(proc, "pid", None):
            try:
                jh = jobs._job()
                if jh:
                    ok = assign_pid_to_job_object(jh, proc.pid)
            except Exception:
                pass
        return ok

    def run(
        self,
        args: Union[str, Sequence[str]],
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
        shell: bool = False,
        timeout: Optional[float] = 60.0,
        text: bool = True,
        encoding: str = "utf-8",
        errors: str = "replace",
        **kwargs: Any,
    ) -> Tuple[int, str, str, float]:
        """Runs a process to completion, returning (exit_code, stdout, stderr, duration_seconds).

        Guarantees process tree termination on timeout or exception.
        """
        t0 = time.time()
        proc = self.spawn(
            args,
            cwd=cwd,
            env=env,
            shell=shell,
            capture_output=True,
            text=text,
            encoding=encoding,
            errors=errors,
            **kwargs,
        )

        stdout_data = ""
        stderr_data = ""
        try:
            out, err = proc.communicate(timeout=timeout)
            stdout_data = out or ""
            stderr_data = err or ""
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            self.terminate_tree(proc)
            out = exc.stdout or ""
            err = exc.stderr or ""
            stdout_data = out if isinstance(out, str) else (out.decode(encoding, errors=errors) if out else "")
            stderr_data = err if isinstance(err, str) else (err.decode(encoding, errors=errors) if err else "")
            stderr_data += f"\nProcess timed out after {timeout} seconds."
            exit_code = -1
        except Exception as exc:
            self.terminate_tree(proc)
            exit_code = -1
            stderr_data = f"Process execution failed: {exc}"
        finally:
            with self._lock:
                self._tracked_processes.discard(proc)

        duration = round(time.time() - t0, 3)
        return exit_code, stdout_data, stderr_data, duration

    def terminate_tree(self, proc: subprocess.Popen, timeout: float = 2.0) -> None:
        """Kills a process and its full descendant tree."""
        if proc is None:
            return
        jobs.kill_process_tree(proc)
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout)
        except Exception:
            pass
        with self._lock:
            self._tracked_processes.discard(proc)

    def terminate_all(self) -> None:
        """Terminates all tracked child processes."""
        with self._lock:
            procs = list(self._tracked_processes)
            self._tracked_processes.clear()

        for p in procs:
            if p.poll() is None:
                self.terminate_tree(p, timeout=0.5)

        jobs.terminate_all_children()

    kill_all = terminate_all

    def list_active(self) -> List[subprocess.Popen]:
        """Returns all active processes tracked in ProcessLifecycleManager and core.jobs."""
        with self._lock:
            active = {p for p in self._tracked_processes if p.poll() is None}
            self._tracked_processes = set(active)
        for jp in jobs.get_active_children():
            active.add(jp)
        return list(active)

    def get_active_count(self) -> int:
        """Returns the number of currently active managed child processes."""
        return len(self.list_active())


ProcessManager = ProcessLifecycleManager

# Global singleton instance
default_process_manager = ProcessLifecycleManager.get_instance()


def is_sharing_violation(exc: BaseException) -> bool:
    """Checks whether an exception represents a Windows sharing violation or access lock."""
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in SHARING_VIOLATION_WINERRORS:
            return True
        if getattr(exc, "errno", None) in SHARING_VIOLATION_ERRNOS:
            return True
    return False


def retry_on_sharing_violation(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 6,
    initial_delay: float = 0.05,
    max_delay: float = 1.0,
    jitter: bool = True,
    **kwargs: Any,
) -> T:
    """Executes func with exponential backoff and jitter if a sharing violation occurs."""
    attempt = 0
    delay = initial_delay

    while True:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            if not is_sharing_violation(exc) or attempt > max_retries:
                raise

            sleep_duration = min(max_delay, delay)
            if jitter:
                sleep_duration += random.uniform(0.005, 0.035)

            logger.debug(
                "Transient file sharing violation (attempt %d/%d), retrying in %.3fs: %s",
                attempt,
                max_retries,
                sleep_duration,
                exc,
            )
            time.sleep(sleep_duration)
            delay *= 2.0


def safe_remove_file(
    file_path: Union[str, Path],
    max_retries: int = 6,
    initial_delay: float = 0.05,
    max_delay: float = 1.0,
    jitter: bool = True,
) -> bool:
    """Safely deletes a file, retrying transient sharing violations (.pdb, .exe, etc.).

    If locked persistently, moves to a temporary quarantine name to avoid blocking callers.
    """
    path = Path(os.path.abspath(os.fspath(file_path)))
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink():
        try:
            path.unlink()
            return True
        except OSError as exc:
            logger.warning("Could not unlink symlink %s: %s", path, exc)
            return False

    def _unlink() -> None:
        path.unlink(missing_ok=True)

    try:
        retry_on_sharing_violation(
            _unlink,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Persistent lock on file %s after %d retries: %s. Attempting quarantine rename.",
            path,
            max_retries,
            exc,
        )
        try:
            quarantine_name = path.with_name(f".quarantine_{uuid.uuid4().hex[:6]}_{path.name}")
            path.rename(quarantine_name)
            try:
                quarantine_name.unlink(missing_ok=True)
                return not quarantine_name.exists()
            except Exception as cleanup_exc:
                logger.warning(
                    "File %s was quarantined as %s but remains on disk: %s",
                    path, quarantine_name, cleanup_exc,
                )
                return False
        except Exception as rename_exc:
            logger.error("Failed to quarantine locked file %s: %s", path, rename_exc)
            return False


def safe_remove_directory(
    dir_path: Union[str, Path],
    max_retries: int = 6,
    initial_delay: float = 0.05,
    max_delay: float = 1.0,
    jitter: bool = True,
) -> bool:
    """Safely removes a directory tree, retrying transient sharing violations on nested files."""
    path = Path(os.path.abspath(os.fspath(dir_path)))
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink():
        try:
            path.unlink()
            return True
        except OSError as exc:
            logger.warning("Could not unlink directory symlink %s: %s", path, exc)
            return False

    def _rmtree() -> None:
        shutil.rmtree(path, ignore_errors=False)

    try:
        retry_on_sharing_violation(
            _rmtree,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Directory tree removal encountered sharing violation on %s (%s). Attempting leaf-first cleanup.",
            path,
            exc,
        )
        success = True
        for root, dirs, files in os.walk(str(path), topdown=False):
            for f in files:
                f_path = Path(root) / f
                if not safe_remove_file(f_path, max_retries=3, initial_delay=0.02):
                    success = False
            for d in dirs:
                d_path = Path(root) / d
                try:
                    d_path.rmdir()
                except Exception:
                    pass
        try:
            path.rmdir()
        except Exception:
            pass
        return not path.exists()
