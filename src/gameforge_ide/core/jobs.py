"""Background jobs and child-process ownership. Every child the IDE starts joins one Windows job object that is
created with KILL_ON_JOB_CLOSE, so all children die with the IDE even if it crashes (Blueprint §8.1)."""
from __future__ import annotations

import atexit
import concurrent.futures
import ctypes
import logging
import subprocess
import sys
import threading
import time
import weakref
from ctypes import wintypes
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger(__name__)

_JOB = None
_LOCK = threading.Lock()
_ACTIVE_PROCESSES: Set[subprocess.Popen] = set()
_PROC_LOCK = threading.Lock()
ENGINE_LOCK = threading.RLock()  # serialises every engine-mutating job and Forge step (design rule 6)

PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001

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
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _k32.CloseHandle.restype = wintypes.BOOL


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
                _k32.CloseHandle(h)
                raise ctypes.WinError(ctypes.get_last_error())
            _JOB = h
        return _JOB


def adopt(proc: subprocess.Popen) -> bool:
    """Put an already-started child into the IDE job. Returns False (and logs) if Windows refuses."""
    with _PROC_LOCK:
        _ACTIVE_PROCESSES.add(proc)
        dead = [p for p in _ACTIVE_PROCESSES if p.poll() is not None]
        for p in dead:
            _ACTIVE_PROCESSES.discard(p)

    job = _job()
    if job is None:
        return False

    raw_handle = getattr(proc, "_handle", None)
    if raw_handle is not None:
        try:
            handle = wintypes.HANDLE(int(raw_handle))
            ok = bool(_k32.AssignProcessToJobObject(job, handle))
            if not ok:
                err = ctypes.get_last_error()
                logger.warning(
                    "AssignProcessToJobObject failed for PID %s (error %s); tracked in fallback registry",
                    getattr(proc, "pid", "?"),
                    err,
                )
            return ok
        except Exception as exc:
            logger.warning(
                "AssignProcessToJobObject exception for PID %s: %s; tracked in fallback registry",
                getattr(proc, "pid", "?"),
                exc,
            )
            return False

    pid = getattr(proc, "pid", None)
    if pid is not None and sys.platform == "win32":
        proc_handle = _k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
        if not proc_handle:
            return False
        try:
            return bool(_k32.AssignProcessToJobObject(job, proc_handle))
        finally:
            _k32.CloseHandle(proc_handle)
    return False


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and all its descendants to prevent orphaned child processes."""
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    if pid is not None:
        try:
            import psutil
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    startupinfo=si,
                )
            except Exception:
                pass
    try:
        proc.kill()
    except (ProcessLookupError, Exception):
        pass
    try:
        proc.wait(timeout=0.2)
    except Exception:
        pass


def terminate_all_children(exit_code: int = 1) -> bool:
    """Terminate all child processes running in the IDE job object and fallback registry."""
    terminated_job = False
    global _JOB
    if sys.platform == "win32":
        with _LOCK:
            if _JOB is not None:
                try:
                    terminated_job = bool(_k32.TerminateJobObject(_JOB, exit_code))
                except Exception as exc:
                    logger.warning("TerminateJobObject failed: %s", exc)
                finally:
                    try:
                        _k32.CloseHandle(_JOB)
                    except Exception:
                        pass
                    _JOB = None

    with _PROC_LOCK:
        procs = list(_ACTIVE_PROCESSES)
        _ACTIVE_PROCESSES.clear()

    for p in procs:
        try:
            if p.poll() is None:
                kill_process_tree(p)
        except Exception:
            pass

    t_end = time.time() + 0.3
    for p in procs:
        rem = max(0.01, t_end - time.time())
        try:
            p.wait(timeout=rem)
        except Exception:
            pass

    for p in procs:
        try:
            if p.poll() is None:
                p.kill()
        except (ProcessLookupError, Exception):
            pass

    return terminated_job or bool(procs)


def get_active_children() -> List[subprocess.Popen]:
    """Return a list of currently running child processes tracked by the system."""
    with _PROC_LOCK:
        active = [p for p in _ACTIVE_PROCESSES if p.poll() is None]
        _ACTIVE_PROCESSES.intersection_update(active)
        return list(active)


def spawn(argv: Union[Sequence[str], str], **popen_kwargs) -> subprocess.Popen:
    """The only way product code starts child processes (editor, UBT, UAT, games, Ollama helpers)."""
    if popen_kwargs.get("shell"):
        raise ValueError("shell=True is forbidden")
    args = argv if isinstance(argv, str) else list(argv)
    if sys.platform == "win32":
        if "creationflags" not in popen_kwargs:
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            popen_kwargs["creationflags"] |= subprocess.CREATE_NO_WINDOW
        if "startupinfo" not in popen_kwargs:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            popen_kwargs["startupinfo"] = si
        elif popen_kwargs["startupinfo"] is not None:
            popen_kwargs["startupinfo"].dwFlags |= subprocess.STARTF_USESHOWWINDOW
            popen_kwargs["startupinfo"].wShowWindow = subprocess.SW_HIDE
    proc = subprocess.Popen(args, **popen_kwargs)
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
        self.name = name or f"job_{id(self)}"
        self.cancel_event = cancel_event

        def _on_future_done(fut: concurrent.futures.Future) -> None:
            if not fut.cancelled():
                try:
                    exc = fut.exception()
                    if exc is not None:
                        logger.error("Job %r failed with unhandled exception: %s", self.name, exc, exc_info=exc)
                        try:
                            from .events import default_bus
                            default_bus().publish(
                                "job.failed",
                                {"job_name": self.name, "error": str(exc), "type": type(exc).__name__},
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

        self._future.add_done_callback(_on_future_done)

    def cancel(self) -> bool:
        if self.cancel_event is not None:
            self.cancel_event.set()
        return self._future.cancel()

    def done(self) -> bool:
        return self._future.done()

    def result(self, timeout: Optional[float] = None) -> Any:
        return self._future.result(timeout=timeout)

    @property
    def status(self) -> str:
        if self._future.cancelled():
            return "CANCELLED"
        if not self._future.done():
            return "RUNNING"
        if self._future.exception() is not None:
            return "FAILED"
        return "DONE"

    @property
    def error(self) -> Optional[BaseException]:
        if self._future.done() and not self._future.cancelled():
            return self._future.exception()
        return None

    def add_done_callback(self, fn: Callable[[JobHandle], None]) -> None:
        def _wrapper(fut: concurrent.futures.Future) -> None:
            fn(self)
        self._future.add_done_callback(_wrapper)


class _DaemonThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor variant that creates daemon worker threads."""
    def _adjust_thread_count(self) -> None:
        try:
            if hasattr(self, "_idle_semaphore") and self._idle_semaphore.acquire(timeout=0):
                return
            from concurrent.futures.thread import _worker, _threads_queues

            def weakref_cb(_, q=self._work_queue):
                try:
                    q.put(None)
                except Exception:
                    pass

            num_threads = len(self._threads)
            if num_threads < self._max_workers:
                thread_name = f"{self._thread_name_prefix or 'job'}_{num_threads}"
                t = threading.Thread(
                    name=thread_name,
                    target=_worker,
                    args=(weakref.ref(self, weakref_cb), self._create_worker_context(), self._work_queue),
                    daemon=True,
                )
                t.start()
                self._threads.add(t)
                _threads_queues[t] = self._work_queue
        except Exception:
            super()._adjust_thread_count()


class JobManager:
    @classmethod
    def instance(cls) -> JobManager:
        return default_job_manager()

    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        try:
            self._executor = _DaemonThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="gameforge-job",
            )
        except Exception:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="gameforge-job",
            )
        self._jobs_lock = threading.Lock()
        self._jobs: Dict[str, JobHandle] = {}
        self._failed_jobs: List[Tuple[str, BaseException]] = []

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        name: str = "",
        cancel_event: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> JobHandle:
        future = self._executor.submit(fn, *args, **kwargs)
        job_name = name or f"job_{time.time_ns()}"
        handle = JobHandle(future, name=job_name, cancel_event=cancel_event)

        with self._jobs_lock:
            self._jobs[job_name] = handle

        def _track_completion(jh: JobHandle) -> None:
            with self._jobs_lock:
                err = jh.error
                if err is not None:
                    self._failed_jobs.append((jh.name, err))
                    if len(self._failed_jobs) > 50:
                        self._failed_jobs.pop(0)

        handle.add_done_callback(_track_completion)
        return handle

    def active_jobs(self) -> List[JobHandle]:
        """Return list of currently pending or running jobs."""
        with self._jobs_lock:
            active = [h for h in self._jobs.values() if not h.done()]
            self._jobs = {h.name: h for h in active}
            return active

    def failed_jobs(self) -> List[Tuple[str, BaseException]]:
        """Return recently recorded failed jobs and their exceptions."""
        with self._jobs_lock:
            return list(self._failed_jobs)

    def cancel_all(self) -> int:
        """Cancel all pending/running jobs."""
        cancelled_count = 0
        for h in self.active_jobs():
            if h.cancel():
                cancelled_count += 1
        return cancelled_count

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """Shut down the thread pool and optionally cancel queued tasks."""
        self.cancel_all()
        try:
            self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            try:
                self._executor.shutdown(wait=wait)
            except Exception:
                pass
        except Exception:
            pass


_DEFAULT_MANAGER: Optional[JobManager] = None
_MGR_LOCK = threading.Lock()


def default_job_manager() -> JobManager:
    global _DEFAULT_MANAGER
    with _MGR_LOCK:
        if _DEFAULT_MANAGER is None:
            _DEFAULT_MANAGER = JobManager(max_workers=4)
        return _DEFAULT_MANAGER


def reset_default_job_manager(wait: bool = False) -> None:
    """Reset the default job manager instance for clean shutdown or test isolation."""
    global _DEFAULT_MANAGER
    with _MGR_LOCK:
        if _DEFAULT_MANAGER is not None:
            try:
                _DEFAULT_MANAGER.shutdown(wait=wait, cancel_futures=True)
            except Exception:
                pass
            _DEFAULT_MANAGER = None


def _cleanup_at_exit() -> None:
    """Clean up background workers and child processes upon process exit."""
    try:
        reset_default_job_manager(wait=False)
    except Exception:
        pass
    try:
        terminate_all_children()
    except Exception:
        pass


atexit.register(_cleanup_at_exit)
