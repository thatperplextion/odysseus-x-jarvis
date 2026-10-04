"""Decoding of console output."""

from __future__ import annotations

import os


def decode_console_output(data: bytes) -> str:
    """UTF-8 first; fall back to the console's codepage (cmd.exe emits OEM text)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    encoding = None
    if os.name == "nt":
        try:
            import ctypes

            encoding = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except Exception:
            encoding = None
    try:
        return data.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")
