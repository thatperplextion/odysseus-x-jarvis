"""One-call Windows process snapshot (the data source Task Manager itself uses).

``psutil`` on Windows issues a system-wide ``NtQuerySystemInformation`` query per
attribute per process (and ``ppid``/``status`` aren't batched at all), which is
O(N^2): ~9-15 s for 440 processes. A single ``SystemProcessInformation`` query
returns pid, parent, name, thread/handle counts, working set and CPU times for
*every* process in a few milliseconds.

Windows-only; ``procs.list_processes`` falls back to psutil if this raises.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, Structure, byref, c_long, c_longlong, c_size_t, c_ulong, c_ulonglong, c_ushort, c_void_p
from typing import Dict, List

if os.name != "nt":  # pragma: no cover - guarded by caller
    raise ImportError("winproc is Windows-only")

_SystemProcessInformation = 5
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
_FILETIME_UNIX_EPOCH_DIFF = 116444736000000000  # 100ns ticks between 1601-01-01 and 1970-01-01


class _UNICODE_STRING(Structure):
    _fields_ = [("Length", c_ushort), ("MaximumLength", c_ushort), ("Buffer", c_void_p)]


class _SYSTEM_PROCESS_INFORMATION(Structure):
    # ctypes applies the same natural alignment as the Windows headers, so the
    # field offsets match winternl.h on both x86 and x64.
    _fields_ = [
        ("NextEntryOffset", c_ulong),
        ("NumberOfThreads", c_ulong),
        ("WorkingSetPrivateSize", c_longlong),
        ("HardFaultCount", c_ulong),
        ("NumberOfThreadsHighWatermark", c_ulong),
        ("CycleTime", c_ulonglong),
        ("CreateTime", c_longlong),
        ("UserTime", c_longlong),
        ("KernelTime", c_longlong),
        ("ImageName", _UNICODE_STRING),
        ("BasePriority", c_long),
        ("UniqueProcessId", c_void_p),
        ("InheritedFromUniqueProcessId", c_void_p),
        ("HandleCount", c_ulong),
        ("SessionId", c_ulong),
        ("UniqueProcessKey", c_void_p),
        ("PeakVirtualSize", c_size_t),
        ("VirtualSize", c_size_t),
        ("PageFaultCount", c_ulong),
        ("PeakWorkingSetSize", c_size_t),
        ("WorkingSetSize", c_size_t),
        ("QuotaPeakPagedPoolUsage", c_size_t),
        ("QuotaPagedPoolUsage", c_size_t),
        ("QuotaPeakNonPagedPoolUsage", c_size_t),
        ("QuotaNonPagedPoolUsage", c_size_t),
        ("PagefileUsage", c_size_t),
        ("PeakPagefileUsage", c_size_t),
        ("PrivatePageCount", c_size_t),
    ]


_ntdll = ctypes.WinDLL("ntdll")
_ntdll.NtQuerySystemInformation.argtypes = [c_ulong, c_void_p, c_ulong, POINTER(c_ulong)]
_ntdll.NtQuerySystemInformation.restype = c_ulong


def snapshot() -> List[Dict]:
    """Every process: pid, ppid, name, threads, handles, memory, create_time, cpu_ticks."""
    size = 1 << 20
    for _ in range(8):
        buf = ctypes.create_string_buffer(size)
        needed = c_ulong(0)
        status = _ntdll.NtQuerySystemInformation(_SystemProcessInformation, buf, size, byref(needed))
        if status == _STATUS_INFO_LENGTH_MISMATCH:
            size = max(size * 2, needed.value + (64 << 10))
            continue
        if status != 0:
            raise OSError(f"NtQuerySystemInformation failed: 0x{status:08X}")
        break
    else:
        raise OSError("NtQuerySystemInformation: buffer kept growing")

    out: List[Dict] = []
    base = ctypes.addressof(buf)
    offset = 0
    while True:
        info = _SYSTEM_PROCESS_INFORMATION.from_address(base + offset)
        name_len = info.ImageName.Length // 2
        name = ctypes.wstring_at(info.ImageName.Buffer, name_len) if info.ImageName.Buffer and name_len else ""
        pid = int(info.UniqueProcessId or 0)
        out.append({
            "pid": pid,
            "ppid": int(info.InheritedFromUniqueProcessId or 0),
            "name": name or ("System Idle Process" if pid == 0 else f"pid-{pid}"),
            "threads": info.NumberOfThreads,
            "handles": info.HandleCount,
            "memory": info.WorkingSetSize,
            "private": info.PrivatePageCount,
            "create_time": (info.CreateTime - _FILETIME_UNIX_EPOCH_DIFF) / 1e7 if info.CreateTime else 0.0,
            "cpu_ticks": info.UserTime + info.KernelTime,  # 100 ns units
        })
        if not info.NextEntryOffset:
            break
        offset += info.NextEntryOffset
    return out
