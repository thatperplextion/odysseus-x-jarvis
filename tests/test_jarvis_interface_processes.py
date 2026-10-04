"""Jarvis system interface: process listing/control and the dashboard refresher.

Regression: the dashboard's PROCESS_LIST widget called psutil's per-process listing
synchronously from the event loop every 10 s (2-15 s on Windows), freezing the whole server.
"""

import asyncio
import os
import subprocess
import sys
import time

import psutil
import pytest

from JARVIS.interface.system_interface import ProcessManager
from JARVIS.ui.jarvis_ui import DashboardWidget, JarvisUI


def test_list_processes_is_fast_and_normalised():
    pm = ProcessManager({})
    pm.list_processes()  # primes CPU deltas
    started = time.perf_counter()
    rows = pm.list_processes()
    assert time.perf_counter() - started < 3.0
    assert rows and {"pid", "name", "user", "cpu_percent", "memory_percent"} <= set(rows[0])
    assert all(0 <= r["cpu_percent"] <= 100 for r in rows), "idle process used to read 1300%"
    assert any(r["pid"] == os.getpid() for r in rows)


async def test_terminate_is_off_by_default():
    pm = ProcessManager({})
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert await pm.terminate_process(child.pid) is False
        assert child.poll() is None
    finally:
        child.kill()


async def test_terminate_when_enabled_stops_ordinary_processes_but_never_the_server():
    pm = ProcessManager({"permissions": {"process_control": "unrestricted"}})
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert await pm.terminate_process(child.pid) is True
        child.wait(timeout=5)
        assert await pm.terminate_process(os.getpid()) is False
        assert psutil.pid_exists(os.getpid())
        assert await pm.terminate_process(psutil.Process().parent().pid) is False  # the shell that started us
    finally:
        if child.poll() is None:
            child.kill()


async def test_start_process_does_not_deadlock_on_chatty_children():
    """stdout/stderr were PIPEs that nobody read: output past ~64 KB blocked the child forever."""
    pm = ProcessManager({"permissions": {"process_control": "unrestricted"}})
    cmd = f'"{sys.executable}" -c "print(\'x\' * 400000)"'
    pid = await pm.start_process(cmd)
    assert pid
    deadline = time.time() + 15
    while time.time() < deadline and psutil.pid_exists(pid):
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        await asyncio.sleep(0.1)
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE, "child is stuck on a full pipe"


async def test_dashboard_refresh_keeps_the_event_loop_responsive():
    class SlowInterface:
        def list_processes(self):
            time.sleep(0.6)  # what the old psutil path effectively did
            return []

        def get_system_metrics(self):
            time.sleep(0.3)
            return {}

        def get_network_stats(self):
            time.sleep(0.3)
            return {}

    ui = JarvisUI({"interface": SlowInterface()})
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    t = asyncio.create_task(ticker())
    started = time.perf_counter()
    await asyncio.gather(*(ui._update_widget_data(w) for w in ui.widgets.values()
                           if w.widget_type in (DashboardWidget.PROCESS_LIST, DashboardWidget.SYSTEM_METRICS, DashboardWidget.NETWORK_STATS)))
    elapsed = time.perf_counter() - started
    t.cancel()
    assert elapsed < 1.2, "the three blocking reads should overlap on worker threads"
    assert ticks >= 20, f"the loop was starved: only {ticks} ticks in {elapsed:.2f}s"
