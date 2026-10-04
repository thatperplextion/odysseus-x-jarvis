"""Process and system introspection for the Task Manager, plus safe process control.

Replaces the kernel/interface ad-hoc versions, which reported the Windows
``System Idle Process`` at 1300% CPU (per-process CPU was not normalised by core
count) and would happily terminate the server's own process.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

import psutil

from .sandbox import SandboxError
from .textcodec import decode_console_output

_IS_WINDOWS = os.name == "nt"
logger = logging.getLogger(__name__)

_PROTECTED_WINDOWS = {
    "system", "system idle process", "registry", "memory compression", "secure system",
    "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
    "svchost.exe", "dwm.exe", "fontdrvhost.exe",
}
_PROTECTED_POSIX = {"systemd", "init", "launchd", "kernel_task", "kthreadd"}
_CMDLINE_LIMIT = 300


class ProcessError(SandboxError):
    status = 400


class ProcessNotFound(ProcessError):
    status = 404


class ProtectedProcess(ProcessError):
    status = 403


# --------------------------------------------------------------------- killing
def kill_process_tree(pid: int) -> None:
    """Kill a process and all of its descendants.

    ``shell=True`` on Windows runs ``cmd.exe /c <command>``, so killing only the
    direct child would orphan the real work.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        victims = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    for proc in victims:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass


def _server_lineage() -> Set[int]:
    """This process and every ancestor: killing any of them takes the server down."""
    pids: Set[int] = set()
    try:
        p: Optional[psutil.Process] = psutil.Process(os.getpid())
        while p is not None and p.pid not in pids:
            pids.add(p.pid)
            p = p.parent()
    except psutil.Error:
        pass
    pids.add(os.getpid())
    return pids


def protection_reason(proc: psutil.Process) -> Optional[str]:
    """Why this process must not be terminated from the UI, or ``None``."""
    pid = proc.pid
    if pid in (0, 4) or (not _IS_WINDOWS and pid == 1):
        return "core system process"
    if pid in _server_lineage():
        return "this is the Odysseus server (or the shell that launched it)"
    try:
        name = (proc.name() or "").lower()
    except psutil.Error:
        return None
    if _IS_WINDOWS and name in _PROTECTED_WINDOWS:
        return f"{name} is critical to Windows"
    if not _IS_WINDOWS and name in _PROTECTED_POSIX:
        return f"{name} is critical to the operating system"
    return None


def terminate(pid: int, force: bool = False, wait: float = 3.0) -> Dict[str, Any]:
    if not isinstance(pid, int) or pid < 0:
        raise ProcessError("invalid pid")
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        raise ProcessNotFound(f"no such process: {pid}")
    reason = protection_reason(proc)
    if reason:
        raise ProtectedProcess(f"refusing to terminate PID {pid}: {reason}")
    try:
        name = proc.name()
        proc.kill() if force else proc.terminate()
        try:
            proc.wait(timeout=wait)
            return {"pid": pid, "name": name, "result": "killed" if force else "terminated"}
        except psutil.TimeoutExpired:
            return {"pid": pid, "name": name, "result": "signalled", "note": "still running; try force"}
    except psutil.NoSuchProcess:
        return {"pid": pid, "result": "already exited"}
    except psutil.AccessDenied:
        raise ProtectedProcess(f"access denied terminating PID {pid} (it belongs to another user or is elevated)")


# -------------------------------------------------------------------- listing
_state_lock = threading.Lock()
_meta_cache: Dict[Any, Dict[str, str]] = {}   # (pid, create_time) -> {"user", "cmdline"}; fixed for a process's life
_cpu_prev: Dict[Any, Any] = {}                # (pid, create_time) -> (cpu_seconds, monotonic_ts)


def _is_protected_name(name: str) -> bool:
    return name.lower() in (_PROTECTED_WINDOWS if _IS_WINDOWS else _PROTECTED_POSIX)


def _meta_for(pid: int, create_time: float) -> Dict[str, str]:
    """Username and command line never change for a given process, so look them up once."""
    key = (pid, round(create_time, 1))
    meta = _meta_cache.get(key)
    if meta is None:
        user, cmd = "", ""
        try:
            p = psutil.Process(pid)
            try:
                user = p.username() or ""
            except psutil.Error:
                pass
            try:
                cmd = " ".join(p.cmdline())[:_CMDLINE_LIMIT]
            except psutil.Error:
                pass
        except psutil.Error:
            pass
        meta = {"user": user, "cmdline": cmd}
        _meta_cache[key] = meta
    return meta


def _list_windows(limit: int) -> List[Dict[str, Any]]:
    from . import winproc

    now = time.monotonic()
    ncpu = psutil.cpu_count(logical=True) or 1
    total_mem = psutil.virtual_memory().total or 1
    lineage = _server_lineage()
    rows = winproc.snapshot()

    out: List[Dict[str, Any]] = []
    with _state_lock:
        next_prev: Dict[Any, Any] = {}
        live_meta: Set[Any] = set()
        for r in rows[:limit]:
            pid = r["pid"]
            key = (pid, round(r["create_time"], 1))
            cpu_s = r["cpu_ticks"] / 1e7
            prev = _cpu_prev.get(key)
            cpu = 0.0
            if prev is not None and pid != 0:
                dt = now - prev[1]
                if dt > 0:
                    cpu = max(0.0, min(100.0, (cpu_s - prev[0]) / dt / ncpu * 100.0))
            next_prev[key] = (cpu_s, now)
            live_meta.add(key)
            meta = _meta_for(pid, r["create_time"]) if pid not in (0, 4) else {"user": "SYSTEM", "cmdline": ""}
            out.append({
                "pid": pid,
                "ppid": r["ppid"],
                "name": r["name"],
                "user": meta["user"],
                "cpu": round(cpu, 1),
                "memory": r["memory"],
                "memory_percent": round(r["memory"] / total_mem * 100.0, 1),
                "status": "running",
                "started": r["create_time"] or None,
                "threads": r["threads"],
                "cmdline": meta["cmdline"],
                "is_server": pid in lineage,
                "protected": pid in (0, 4) or pid in lineage or _is_protected_name(r["name"]),
            })
        _cpu_prev.clear()
        _cpu_prev.update(next_prev)
        for k in [k for k in _meta_cache if k not in live_meta]:
            del _meta_cache[k]
    return out


def _list_psutil(limit: int) -> List[Dict[str, Any]]:
    ncpu = psutil.cpu_count(logical=True) or 1
    lineage = _server_lineage()
    out: List[Dict[str, Any]] = []
    attrs = ["pid", "ppid", "name", "username", "memory_info", "memory_percent", "status", "create_time", "num_threads", "cmdline"]
    for p in psutil.process_iter():
        try:
            with p.oneshot():
                info = p.as_dict(attrs=attrs, ad_value=None)
                cpu = 0.0 if p.pid == 0 else min(100.0, p.cpu_percent(None) / ncpu)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        mem = info.get("memory_info")
        name = info.get("name") or f"pid-{info['pid']}"
        out.append({
            "pid": info["pid"],
            "ppid": info.get("ppid"),
            "name": name,
            "user": info.get("username") or "",
            "cpu": round(cpu, 1),
            "memory": mem.rss if mem else 0,
            "memory_percent": round(info.get("memory_percent") or 0.0, 1),
            "status": info.get("status") or "",
            "started": info.get("create_time"),
            "threads": info.get("num_threads") or 0,
            "cmdline": " ".join(info.get("cmdline") or [])[:_CMDLINE_LIMIT],
            "is_server": info["pid"] in lineage,
            "protected": info["pid"] in (0, 4) or info["pid"] in lineage or _is_protected_name(name),
        })
        if len(out) >= limit:
            break
    return out


def list_processes(limit: int = 2000) -> List[Dict[str, Any]]:
    """Snapshot of running processes.

    ``cpu`` is percent of *total* machine capacity (0-100), like Task Manager. It is
    computed from the change since the previous snapshot, so the first call
    reports 0 for everything.

    On Windows this is a single native query (~10 ms for 400+ processes); psutil's
    per-process path takes 9-15 s there (see ``winproc``).
    """
    if _IS_WINDOWS:
        try:
            return _list_windows(limit)
        except Exception:  # never let a native-struct surprise take the Task Manager down
            logger.exception("native Windows process snapshot failed; falling back to psutil")
    return _list_psutil(limit)


# --------------------------------------------------------------------- system
psutil.cpu_percent(interval=None, percpu=True)  # prime: the first reading is always 0


_DISK_TTL = 30.0
_disk_cache: Dict[str, Any] = {"at": 0.0, "value": []}


def _disks() -> List[Dict[str, Any]]:
    """Disk usage changes slowly and querying a dead network drive can stall, so cache it."""
    with _state_lock:
        if time.monotonic() - _disk_cache["at"] < _DISK_TTL:
            return _disk_cache["value"]
    disks = []
    # The drive the OS lives on: %SystemDrive% on Windows, "/" elsewhere. Listed first and flagged, so a widget
    # that shows one drive shows this one instead of whichever letter happens to sort first (often a USB stick).
    sys_root = (os.environ.get("SystemDrive", "C:") + "\\") if _IS_WINDOWS else "/"
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in (part.opts or "") or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        is_sys = os.path.normcase(os.path.normpath(part.mountpoint)) == os.path.normcase(os.path.normpath(sys_root))
        disks.append({"mount": part.mountpoint, "fstype": part.fstype, "total": u.total, "used": u.used, "percent": u.percent, "system": is_sys})
    disks.sort(key=lambda d: not d["system"])   # stable: the system drive first, the rest keep their order
    with _state_lock:
        _disk_cache.update(at=time.monotonic(), value=disks)
    return disks


def system_snapshot() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    net = psutil.net_io_counters()
    disks = _disks()
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    battery = None
    try:
        b = psutil.sensors_battery()
        if b is not None:
            battery = {"percent": round(b.percent), "plugged": b.power_plugged, "seconds_left": b.secsleft if b.secsleft >= 0 else None}
    except (AttributeError, NotImplementedError):
        pass
    load = None
    if hasattr(os, "getloadavg"):
        try:
            load = list(os.getloadavg())
        except OSError:
            pass
    freq = None
    try:
        f = psutil.cpu_freq()
        freq = round(f.current) if f else None
    except Exception:
        pass
    return {
        "time": time.time(),
        "cpu": {
            "percent": round(sum(per_core) / len(per_core), 1) if per_core else 0.0,
            "per_core": [round(c, 1) for c in per_core],
            "cores": psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "mhz": freq,
        },
        "memory": {"total": vm.total, "used": vm.total - vm.available, "percent": vm.percent},
        "swap": {"total": sw.total, "used": sw.used, "percent": sw.percent},
        "disks": disks,
        "network": {"sent": net.bytes_sent, "recv": net.bytes_recv} if net else {"sent": 0, "recv": 0},
        "battery": battery,
        "load": load,
        "uptime": time.time() - psutil.boot_time(),
        "processes": len(psutil.pids()),
    }


def system_info() -> Dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "user": _safe_user(),
        "cores": psutil.cpu_count(logical=False),
        "threads": psutil.cpu_count(logical=True),
        "memory_total": psutil.virtual_memory().total,
        "boot_time": psutil.boot_time(),
    }


def _safe_user() -> str:
    try:
        return psutil.Process().username()
    except Exception:
        return os.environ.get("USERNAME") or os.environ.get("USER") or ""


# -------------------------------------------------- bounded synchronous runner
@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: Optional[int]
    timed_out: bool


def run_capped(
    command: str,
    cwd: Optional[str] = None,
    timeout: float = 30,
    max_bytes: int = 1024 * 1024,
) -> RunResult:
    """Run ``command`` through the shell, bounded in time and memory. Blocking: call
    from a worker thread (``asyncio.to_thread``), never from the event loop.

    Output beyond ``max_bytes`` per stream is drained and dropped so a runaway
    producer (``yes``) can't exhaust RAM; on timeout the whole process tree dies.
    """
    from .procgroup import ProcessGroup  # local: procgroup imports kill_process_tree from this module

    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **({} if _IS_WINDOWS else {"start_new_session": True}),
    )
    group = ProcessGroup.attach(proc.pid)
    timed_out = threading.Event()

    def _expire() -> None:
        timed_out.set()
        group.kill()

    timer = threading.Timer(timeout, _expire)
    timer.start()
    bufs: Dict[str, bytearray] = {"out": bytearray(), "err": bytearray()}

    def _drain(stream, key: str) -> None:
        buf = bufs[key]
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            room = max_bytes - len(buf)
            if room > 0:
                buf += chunk[:room]

    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, "out"), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, "err"), daemon=True),
    ]
    for t in readers:
        t.start()
    try:
        proc.wait()
        for t in readers:
            t.join(timeout=5)
    finally:
        timer.cancel()
        group.close()
        for s in (proc.stdout, proc.stderr):
            try:
                s.close()
            except OSError:
                pass
    return RunResult(
        stdout=decode_console_output(bytes(bufs["out"])),
        stderr=decode_console_output(bytes(bufs["err"])),
        returncode=None if timed_out.is_set() else proc.returncode,
        timed_out=timed_out.is_set(),
    )
