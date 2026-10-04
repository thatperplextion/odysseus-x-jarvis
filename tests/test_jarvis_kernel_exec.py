"""Jarvis kernel command execution: non-blocking, bounded, killable.

Regression: ``ProcessManager._execute_process`` used a blocking
``subprocess.run`` inside a coroutine, which froze the whole server for the
duration of every command and could not be cancelled.
"""

import asyncio
import sys
import time
from types import SimpleNamespace

import psutil
import pytest

from JARVIS.kernel import jarvis_kernel
from JARVIS.kernel.jarvis_kernel import ProcessManager, ProcessState, _run_shell

PY = f'"{sys.executable}"'


def _py(code: str) -> str:
    return f'{PY} -c "{code}"'


async def test_run_shell_returns_output_and_exit_code():
    out, code = await _run_shell(_py("print(42)"), cwd=".", timeout=20)
    assert out.strip() == "42"
    assert code == 0


async def test_run_shell_merges_stderr_and_reports_nonzero_exit():
    out, code = await _run_shell(
        _py("import sys; sys.stderr.write('boom'); sys.exit(3)"), cwd=".", timeout=20
    )
    assert "boom" in out
    assert code == 3


async def test_event_loop_stays_responsive_while_command_runs():
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    t = asyncio.create_task(ticker())
    try:
        started = time.monotonic()
        await _run_shell(_py("import time; time.sleep(1)"), cwd=".", timeout=20)
        elapsed = time.monotonic() - started
    finally:
        t.cancel()
    # A blocking subprocess.run would leave ticks at ~0 for the whole second.
    assert elapsed >= 0.9
    assert ticks >= 10, f"event loop starved: only {ticks} ticks in {elapsed:.2f}s"


async def test_timeout_kills_whole_process_tree():
    code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "time.sleep(60)"
    )
    pids = []
    task = asyncio.create_task(
        _run_shell(_py(code), cwd=".", timeout=1.5, on_start=pids.append)
    )
    tree = set()
    deadline = time.monotonic() + 1.2
    while time.monotonic() < deadline:
        await asyncio.sleep(0.1)
        try:
            tree = {p.pid for p in psutil.Process(pids[0]).children(recursive=True)} | {pids[0]}
        except (IndexError, psutil.NoSuchProcess):
            continue
        # shell wrapper (Windows) + python parent + python child
        if len(tree) >= 2:
            break
    with pytest.raises(TimeoutError):
        await task
    await asyncio.sleep(0.3)
    alive = [pid for pid in tree if psutil.pid_exists(pid)]
    assert tree, "never observed the spawned process tree"
    assert not alive, f"orphaned processes survived timeout: {alive}"


async def test_cancel_kills_process_tree():
    pids = []
    task = asyncio.create_task(
        _run_shell(_py("import time; time.sleep(60)"), cwd=".", timeout=120, on_start=pids.append)
    )
    for _ in range(50):
        if pids:
            break
        await asyncio.sleep(0.05)
    assert pids
    tree = {p.pid for p in psutil.Process(pids[0]).children(recursive=True)} | {pids[0]}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.3)
    assert not [pid for pid in tree if psutil.pid_exists(pid)]


async def test_output_is_capped(monkeypatch):
    monkeypatch.setattr(jarvis_kernel, "MAX_CAPTURED_OUTPUT", 1000)
    out, code = await _run_shell(_py("print('x' * 50000)"), cwd=".", timeout=20)
    assert code == 0  # drained fully, so the child wasn't blocked on a full pipe
    assert len(out) == 1000


async def test_process_manager_runs_command_and_records_result():
    pm = ProcessManager(max_concurrent=2)
    pm.set_kernel(SimpleNamespace(system_interface=object()))
    pid = await pm.create_process("t", _py("print('hello-kernel')"))
    assert await pm.start_process(pid)
    await pm.running_processes[pid]
    status = pm.get_process_status(pid)
    assert status["state"] == ProcessState.COMPLETED.value
    assert "hello-kernel" in status["result"]["output"]
    assert status["result"]["exit_code"] == 0


async def test_process_manager_marks_nonzero_exit_failed():
    pm = ProcessManager()
    pm.set_kernel(SimpleNamespace(system_interface=object()))
    pid = await pm.create_process("t", _py("import sys; sys.exit(7)"))
    await pm.start_process(pid)
    await pm.running_processes[pid]
    status = pm.get_process_status(pid)
    assert status["state"] == ProcessState.FAILED.value
    assert status["result"]["exit_code"] == 7


async def test_process_manager_refuses_to_simulate_without_system_interface():
    pm = ProcessManager()
    pm.set_kernel(SimpleNamespace(system_interface=None))
    pid = await pm.create_process("t", _py("print('should not run')"))
    await pm.start_process(pid)
    await pm.running_processes[pid]
    status = pm.get_process_status(pid)
    assert status["state"] == ProcessState.FAILED.value
    assert "cannot execute" in status["error"]


async def test_cancel_process_stops_a_running_command():
    pm = ProcessManager()
    pm.set_kernel(SimpleNamespace(system_interface=object()))
    pid = await pm.create_process("t", _py("import time; time.sleep(60)"))
    await pm.start_process(pid)
    task = pm.running_processes[pid]
    await asyncio.sleep(0.5)
    assert await pm.cancel_process(pid)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pm.get_process_status(pid)["state"] == ProcessState.CANCELLED.value


async def test_status_reports_the_command_pid_and_source():
    pm = ProcessManager()
    pm.set_kernel(SimpleNamespace(system_interface=object()))
    pid = await pm.create_process("t", _py("print('x')"), metadata={"source": "taskmanager"})
    await pm.start_process(pid)
    await pm.running_processes[pid]
    status = pm.get_process_status(pid)
    assert "print" in status["command"]
    assert isinstance(status["pid"], int)
    assert status["source"] == "taskmanager"


async def test_a_queued_job_can_be_cancelled_and_never_starts(tmp_path):
    marker = tmp_path / "ran.txt"
    pm = ProcessManager()
    pm.set_kernel(SimpleNamespace(system_interface=object()))
    pid = await pm.create_process("t", _py(f"open(r'{marker}', 'w').write('x')"))
    assert await pm.cancel_process(pid) is True
    assert pm.get_process_status(pid)["state"] == ProcessState.CANCELLED.value
    assert await pm.start_process(pid) is True  # consumed, so the queue worker drops it
    assert pid not in pm.running_processes
    await asyncio.sleep(0.5)
    assert not marker.exists()
