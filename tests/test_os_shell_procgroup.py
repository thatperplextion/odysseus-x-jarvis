"""ProcessGroup: kill a command and everything it started, including orphans.

Regression: walking the process tree misses descendants whose recorded parent has
already exited (Git Bash/msys children, double-forking daemons). A 1.5 s timeout on
``bash script.sh`` running ``sleep 30`` took 30 s because ``sleep`` survived.
"""

import os
import shutil
import subprocess
import sys
import time

import psutil
import pytest

from services.os_shell.procgroup import ProcessGroup

_POSIX = os.name != "nt"


def _popen(code: str):
    kwargs = {"start_new_session": True} if _POSIX else {}
    return subprocess.Popen([sys.executable, "-c", code], **kwargs)


def _wait_for(predicate, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()


def _descendants(pid):
    try:
        return {c.pid for c in psutil.Process(pid).children(recursive=True)}
    except psutil.NoSuchProcess:
        return set()


GRANDCHILD = (
    "import subprocess, sys, time; "
    "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
    "print(c.pid, flush=True); time.sleep(60)"
)


def test_kill_reaches_children_and_grandchildren():
    p = _popen(GRANDCHILD)
    group = ProcessGroup.attach(p.pid)
    try:
        kids = _wait_for(lambda: _descendants(p.pid))
        assert kids, "child never started"
        group.kill()
        p.wait(timeout=5)
        assert _wait_for(lambda: not [k for k in kids if psutil.pid_exists(k)])
    finally:
        group.close()
        if p.poll() is None:
            p.kill()


def test_kill_reaches_an_orphan_whose_parent_already_exited():
    """The msys case: the child's recorded parent is gone, so a tree walk can't find it."""
    code = (
        "import subprocess, sys, time; "
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "print(c.pid, flush=True); time.sleep(0.5)"  # parent exits, orphaning the child
    )
    kwargs = {"start_new_session": True} if _POSIX else {}
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, **kwargs)
    group = ProcessGroup.attach(p.pid)
    orphan = int(p.stdout.readline().strip())
    try:
        p.wait(timeout=10)
        assert psutil.pid_exists(orphan), "test setup: the child should have outlived its parent"
        group.kill()
        assert _wait_for(lambda: not psutil.pid_exists(orphan)), "orphan survived group.kill()"
    finally:
        group.close()
        try:
            psutil.Process(orphan).kill()
        except psutil.NoSuchProcess:
            pass


def test_close_does_not_kill_what_the_command_left_running():
    """`Start-Process` / `nohup ... &` must outlive the command that started it."""
    p = _popen(GRANDCHILD)
    group = ProcessGroup.attach(p.pid)
    kids = _wait_for(lambda: _descendants(p.pid))
    assert kids
    group.close()
    time.sleep(0.5)
    try:
        assert psutil.pid_exists(p.pid) and all(psutil.pid_exists(k) for k in kids)
    finally:
        for pid in list(kids) + [p.pid]:
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass


def test_kill_after_close_and_double_close_are_safe():
    p = _popen("import time; time.sleep(60)")
    group = ProcessGroup.attach(p.pid)
    group.close()
    group.close()
    group.kill()  # falls back to the tree walk
    p.wait(timeout=5)


def test_attach_to_a_dead_pid_never_raises():
    p = _popen("pass")
    p.wait(timeout=5)
    group = ProcessGroup.attach(p.pid)
    group.kill()
    group.close()


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash (Git Bash/msys on Windows)")
def test_msys_bash_sleep_is_killed_promptly():
    """The original symptom: `bash -c 'sleep 30'` kept running after the shell was killed."""
    flags = {"creationflags": 0x08000000} if os.name == "nt" else {"start_new_session": True}
    p = subprocess.Popen([shutil.which("bash"), "-c", "sleep 30"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **flags)
    group = ProcessGroup.attach(p.pid)
    time.sleep(1.0)
    started = time.time()
    group.kill()
    p.wait(timeout=10)
    p.stdout.read()  # EOF only arrives once *every* writer (including sleep) is gone
    assert time.time() - started < 5, "sleep outlived the shell"
    group.close()
