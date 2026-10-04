"""Process listing/termination guards and the bounded command runner."""

import os
import subprocess
import sys
import time

import psutil
import pytest

from services.os_shell import procs
from services.os_shell.procs import (
    ProcessError,
    ProcessNotFound,
    ProtectedProcess,
    list_processes,
    run_capped,
    system_info,
    system_snapshot,
    terminate,
)

PY = f'"{sys.executable}"'


def _py(code: str) -> str:
    return f'{PY} -c "{code}"'


def _spawn_sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


# ------------------------------------------------------------------ listing
def test_list_processes_includes_this_process_flagged_as_the_server():
    rows = list_processes()
    me = next(r for r in rows if r["pid"] == os.getpid())
    assert me["is_server"] is True and me["protected"] is True
    assert me["memory"] > 0


def test_cpu_is_normalised_to_a_0_100_percentage_per_machine():
    list_processes()  # prime
    time.sleep(0.2)
    rows = list_processes()
    assert all(0.0 <= r["cpu"] <= 100.0 for r in rows), "per-core sums must not leak through (idle process showed 1300%)"


def test_listing_is_fast_enough_to_poll():
    """psutil's per-process Windows path took 9-15 s for ~440 processes."""
    list_processes()  # first call also fills the user/cmdline cache
    started = time.time()
    rows = list_processes()
    assert rows
    assert time.time() - started < 3.0


def test_busy_process_shows_nonzero_cpu_between_snapshots():
    child = subprocess.Popen([sys.executable, "-c", "while True: pass"])
    try:
        time.sleep(0.5)
        # A venv's python.exe on Windows is a launcher whose *child* does the work.
        family = {child.pid} | {c.pid for c in psutil.Process(child.pid).children(recursive=True)}
        list_processes()
        time.sleep(1.0)
        busy = sum(r["cpu"] for r in list_processes() if r["pid"] in family)
        assert busy > 0.0
        assert busy <= 100.0
    finally:
        procs.kill_process_tree(child.pid)


@pytest.mark.skipif(os.name != "nt", reason="native snapshot is Windows-only")
def test_native_windows_snapshot_agrees_with_psutil_for_this_process():
    from services.os_shell import winproc

    mine = next(r for r in winproc.snapshot() if r["pid"] == os.getpid())
    p = psutil.Process()
    assert mine["ppid"] == p.ppid()
    assert mine["name"].lower() == p.name().lower()
    assert abs(mine["create_time"] - p.create_time()) < 2
    assert abs(mine["memory"] - p.memory_info().rss) < max(p.memory_info().rss * 0.5, 32 << 20)
    assert mine["threads"] >= 1


def test_pid_zero_never_reports_cpu():
    rows = list_processes()
    for r in rows:
        if r["pid"] == 0:
            assert r["cpu"] == 0.0


def test_cmdline_is_truncated():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60) #" + "x" * 2000])
    try:
        time.sleep(0.3)
        row = next(r for r in list_processes() if r["pid"] == child.pid)
        assert len(row["cmdline"]) <= 300
    finally:
        child.kill()


# -------------------------------------------------------------- termination
def test_terminate_stops_an_ordinary_process():
    child = _spawn_sleeper()
    out = terminate(child.pid)
    assert out["result"] in ("terminated", "signalled")
    child.wait(timeout=5)
    assert child.returncode is not None


def test_force_kill():
    child = _spawn_sleeper()
    assert terminate(child.pid, force=True)["result"] == "killed"
    child.wait(timeout=5)


def test_refuses_to_terminate_the_server_itself():
    with pytest.raises(ProtectedProcess, match="Odysseus server"):
        terminate(os.getpid())
    assert psutil.pid_exists(os.getpid())


def test_refuses_to_terminate_the_servers_parent_shell():
    parent = psutil.Process(os.getpid()).parent()
    if parent is None:
        pytest.skip("no parent process")
    with pytest.raises(ProtectedProcess):
        terminate(parent.pid)


@pytest.mark.parametrize("pid", [0, 4])
def test_refuses_core_system_pids(pid):
    with pytest.raises((ProtectedProcess, ProcessNotFound)):
        terminate(pid)


def test_missing_and_invalid_pids():
    with pytest.raises(ProcessNotFound):
        terminate(2**22 + 12345)
    for bad in (-1, "1", None, 1.5):
        with pytest.raises(ProcessError):
            terminate(bad)  # type: ignore[arg-type]


def test_protection_reason_flags_critical_windows_names(monkeypatch):
    class Fake:
        pid = 99999

        def name(self):
            return "LSASS.EXE"

    monkeypatch.setattr(procs, "_IS_WINDOWS", True)
    assert "critical" in procs.protection_reason(Fake())


# ------------------------------------------------------------------- tree kill
def test_kill_process_tree_takes_children_too():
    parent = subprocess.Popen(
        [sys.executable, "-c",
         "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)"]
    )
    deadline = time.time() + 5
    kids = []
    while time.time() < deadline and not kids:
        kids = psutil.Process(parent.pid).children(recursive=True)
        time.sleep(0.1)
    assert kids, "child never started"
    procs.kill_process_tree(parent.pid)
    parent.wait(timeout=5)
    time.sleep(0.3)
    assert not [k.pid for k in kids if psutil.pid_exists(k.pid)]


def test_kill_process_tree_on_a_dead_pid_is_a_noop():
    procs.kill_process_tree(2**22 + 54321)


# -------------------------------------------------------------- bounded runner
def test_run_capped_captures_streams_separately():
    r = run_capped(_py("import sys; print('out'); sys.stderr.write('err'); sys.exit(2)"), timeout=20)
    assert r.stdout.strip() == "out" and r.stderr.strip() == "err"
    assert r.returncode == 2 and r.timed_out is False


def test_run_capped_times_out_and_kills_the_tree():
    started = time.time()
    r = run_capped(_py("import time; time.sleep(60)"), timeout=1)
    assert r.timed_out is True and r.returncode is None
    assert time.time() - started < 10


def test_run_capped_bounds_memory_for_runaway_output():
    r = run_capped(_py("print('x' * 3000000)"), timeout=30, max_bytes=10_000)
    assert len(r.stdout) == 10_000
    assert r.returncode == 0  # the child finished: we kept draining so it never blocked on a full pipe


def test_run_capped_does_not_inherit_stdin():
    r = run_capped(_py("import sys; print(repr(sys.stdin.read()))"), timeout=20)
    assert r.stdout.strip() == "''"


# -------------------------------------------------------------------- system
def test_system_snapshot_shape():
    snap = system_snapshot()
    assert 0 <= snap["cpu"]["percent"] <= 100
    assert snap["memory"]["total"] > 0 and 0 <= snap["memory"]["percent"] <= 100
    assert snap["uptime"] > 0
    assert isinstance(snap["disks"], list)
    assert snap["network"]["sent"] >= 0


def test_system_snapshot_lists_the_system_drive_first(monkeypatch):
    """The Today System widget shows disks[0]; it must be the drive the OS is on, not whichever letter sorts first."""
    import services.os_shell.procs as procs

    class Part:
        def __init__(self, mount, opts=""): self.mountpoint, self.opts, self.fstype = mount, opts, "NTFS"

    class Usage:
        total, used, percent = 100, 50, 50.0

    monkeypatch.setattr(procs, "_IS_WINDOWS", True)
    monkeypatch.setenv("SystemDrive", "C:")
    monkeypatch.setattr(procs.psutil, "disk_partitions", lambda all=False: [Part("A:\\"), Part("C:\\"), Part("D:\\")])
    monkeypatch.setattr(procs.psutil, "disk_usage", lambda p: Usage())
    monkeypatch.setitem(procs._disk_cache, "at", 0.0)
    disks = procs._disks()
    monkeypatch.setitem(procs._disk_cache, "at", 0.0)   # do not leak the fake list to other tests
    assert [d["mount"] for d in disks] == ["C:\\", "A:\\", "D:\\"]
    assert [d["system"] for d in disks] == [True, False, False]


def test_system_info_shape():
    info = system_info()
    assert info["hostname"] and info["os"] and info["threads"] >= 1
