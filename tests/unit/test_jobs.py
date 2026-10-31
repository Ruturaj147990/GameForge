import subprocess
import sys
import threading
import time
import pytest
import psutil

from src.gameforge_ide.core.jobs import (
    ENGINE_LOCK,
    JobManager,
    default_job_manager,
    spawn,
)


def test_job_manager_submit_and_result():
    mgr = JobManager(max_workers=2)

    def work(x: int, y: int) -> int:
        return x + y

    handle = mgr.submit(work, 3, 4, name="add")
    res = handle.result(timeout=5.0)
    assert res == 7
    assert handle.done() is True
    mgr.shutdown(wait=True)


def test_job_manager_cancel():
    mgr = JobManager(max_workers=2)
    cancel_ev = threading.Event()

    def cancellable_work():
        while not cancel_ev.is_set():
            time.sleep(0.01)
        return "cancelled"

    handle = mgr.submit(cancellable_work, name="cancellable", cancel_event=cancel_ev)
    assert not cancel_ev.is_set()
    handle.cancel()
    assert cancel_ev.is_set()
    res = handle.result(timeout=5.0)
    assert res == "cancelled"
    mgr.shutdown(wait=True)


def test_engine_lock_mutual_exclusion():
    history = []

    def task(n: int):
        with ENGINE_LOCK:
            history.append(f"start_{n}")
            time.sleep(0.05)
            history.append(f"end_{n}")

    t1 = threading.Thread(target=task, args=(1,))
    t2 = threading.Thread(target=task, args=(2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # With serialisation, each task must complete both start and end before the other begins
    if history[0] == "start_1":
        assert history == ["start_1", "end_1", "start_2", "end_2"]
    else:
        assert history == ["start_2", "end_2", "start_1", "end_1"]


def test_spawn_forbids_shell():
    with pytest.raises(ValueError, match="shell=True is forbidden"):
        spawn(["dir"], shell=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object is Windows-only")
def test_job_object_kills_child_on_helper_exit():
    # Helper process spawns a 60s sleeping child via jobs.spawn, outputs child PID, then waits
    helper_code = (
        "import sys, time\n"
        "from src.gameforge_ide.core import jobs\n"
        "proc = jobs.spawn([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(proc.pid, flush=True)\n"
        "time.sleep(10)\n"
    )

    helper = subprocess.Popen(
        [sys.executable, "-c", helper_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Read the grandchild PID
    child_pid_line = helper.stdout.readline().strip()
    assert child_pid_line.isdigit(), f"Expected numeric PID, got: {child_pid_line!r}"
    child_pid = int(child_pid_line)

    # Verify grandchild is alive
    assert psutil.pid_exists(child_pid)

    # Terminate the helper process
    helper.terminate()
    helper.wait(timeout=5)

    # Assert that within 5 seconds the grandchild is terminated by the Job Object
    t0 = time.time()
    grandchild_alive = True
    while time.time() - t0 < 5.0:
        if not psutil.pid_exists(child_pid):
            grandchild_alive = False
            break
        time.sleep(0.1)

    assert not grandchild_alive, f"Child process {child_pid} leaked after helper exit!"
