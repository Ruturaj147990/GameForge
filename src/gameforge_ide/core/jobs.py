"""Background jobs and child-process ownership. Every child the IDE starts joins one Windows job object that is
created with KILL_ON_JOB_CLOSE, so all children die with the IDE even if it crashes (Blueprint §8.1)."""
from __future__ import annotations

import concurrent.futures
import ctypes
import subprocess
import sys
import threading
from ctypes import wintypes
from typing import Any, Callable, Optional, Sequence

_JOB = None
_LOCK = threading.Lock()
ENGINE_LOCK = threading.RLock()  # serialises every engine-mutating job and Forge step (design rule 6)

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _IO(ctypes.Structure):
        _fields_ = [
            (n, ctypes.c_ulonglong)
            for n in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _EXT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BASIC),
            ("IoInfo", _IO),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)


def _job():
    global _JOB
    if sys.platform != "win32":
        return None
    with _LOCK:
        if _JOB is None:
            h = _k32.CreateJobObjectW(None, None)
            if not h:
                raise ctypes.WinError(ctypes.get_last_error())
            info = _EXT()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            _JOB = h
        return _JOB


def adopt(proc: subprocess.Popen) -> bool:
    """Put an already-started child into the IDE job. Returns False (and logs) if Windows refuses."""
    job = _job()
    if job is None:
        return False
    try:
        handle = wintypes.HANDLE(int(proc._handle))
        return bool(_k32.AssignProcessToJobObject(job, handle))
    except Exception:
        return False


def spawn(argv: Sequence[str], **popen_kwargs) -> subprocess.Popen:
    """The only way product code starts child processes (editor, UBT, UAT, games, Ollama helpers)."""
    if popen_kwargs.get("shell"):
        raise ValueError("shell=True is forbidden")
    proc = subprocess.Popen(list(argv), **popen_kwargs)
    adopt(proc)
    return proc


class JobHandle:
    def __init__(
        self,
        future: concurrent.futures.Future,
        name: str = "",
        cancel_event: Optional[threading.Event] = None,
    ):
        self._future = future
        self.name = name
        self.cancel_event = cancel_event

    def cancel(self) -> bool:
        if self.cancel_event is not None:
            self.cancel_event.set()
        return self._future.cancel()

    def done(self) -> bool:
        return self._future.done()

    def result(self, timeout: Optional[float] = None) -> Any:
        return self._future.result(timeout=timeout)


class JobManager:
    def __init__(self, max_workers: int = 2):
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="gameforge-job",
        )

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        name: str = "",
        cancel_event: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> JobHandle:
        future = self._executor.submit(fn, *args, **kwargs)
        return JobHandle(future, name=name, cancel_event=cancel_event)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


_DEFAULT_MANAGER: Optional[JobManager] = None
_MGR_LOCK = threading.Lock()


def default_job_manager() -> JobManager:
    global _DEFAULT_MANAGER
    with _MGR_LOCK:
        if _DEFAULT_MANAGER is None:
            _DEFAULT_MANAGER = JobManager(max_workers=2)
        return _DEFAULT_MANAGER
