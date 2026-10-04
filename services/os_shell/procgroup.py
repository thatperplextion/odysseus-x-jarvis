"""Kill a command *and everything it started*, reliably.

Walking the process tree (``psutil.children``) misses descendants whose recorded
parent has already exited: Git Bash/msys children are the common case, and any
double-forking daemon is another. Observed here: ``bash script.sh`` running
``sleep 30`` -- killing the tree left ``sleep.exe`` alive holding the output pipe,
so a 1.5 s timeout took 30 s to take effect.

* **Windows**: a Job Object. A process assigned to a job (and everything it spawns
  afterwards, whatever its recorded parent) can be terminated as a unit.
* **POSIX**: the command is started in its own session (``start_new_session``), so
  its process group id equals its pid and ``killpg`` reaches every member.

Closing a group does **not** kill it: a command that deliberately leaves something
running (``Start-Process``, ``nohup ... &``) keeps it. Only :meth:`kill` does.
"""

from __future__ import annotations

import os
import signal
from typing import Optional

from .procs import kill_process_tree

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]

    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001


class ProcessGroup:
    """Handle for one spawned command and its descendants."""

    def __init__(self, pid: int, job: Optional[int] = None):
        self.pid = pid
        self._job = job
        self._closed = False

    @classmethod
    def attach(cls, pid: int) -> "ProcessGroup":
        """Call right after spawning. On POSIX the process must have been started with
        ``start_new_session=True``. Never raises: falls back to a plain tree kill."""
        if not _IS_WINDOWS:
            return cls(pid)
        job = None
        try:
            job = _k32.CreateJobObjectW(None, None)
            if job:
                hproc = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
                if hproc:
                    try:
                        if not _k32.AssignProcessToJobObject(job, hproc):
                            _k32.CloseHandle(job)
                            job = None
                    finally:
                        _k32.CloseHandle(hproc)
                else:
                    _k32.CloseHandle(job)
                    job = None
        except Exception:  # noqa: BLE001 - degrade to the psutil walk
            job = None
        return cls(pid, job)

    def kill(self) -> None:
        """Terminate the command and every descendant."""
        if _IS_WINDOWS:
            if self._job:
                _k32.TerminateJobObject(self._job, 1)
            kill_process_tree(self.pid)  # also covers the case where the job could not be set up
        else:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            kill_process_tree(self.pid)

    def close(self) -> None:
        """Release the handle. Does not kill: whatever is still running keeps running."""
        if self._closed:
            return
        self._closed = True
        if _IS_WINDOWS and self._job:
            _k32.CloseHandle(self._job)
            self._job = None

    def __enter__(self) -> "ProcessGroup":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
