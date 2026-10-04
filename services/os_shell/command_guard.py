"""Accident-prevention guard for *non-interactive* command execution.

Used where a command was not typed by the person at the keyboard: the
assistant's natural-language ``run ...`` intent, the autonomous coding/planning
agents, and the legacy ``/api/jarvis/os/execute_command`` endpoint.

This is a speed bump for catastrophic mistakes (a mis-parsed sentence, a
hallucinated command), **not** a security boundary: shells offer unlimited ways
to spell a command, so command execution stays admin-only and audited. The
interactive Terminal app deliberately does not use this guard.

The previous implementation was a substring blocklist (``'dd' in command``),
which refused ``git add .`` and ``echo information`` while allowing
``Remove-Item -Recurse C:\\``. These are word-boundary patterns instead.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

_ROOT_TARGET = r"""(?:/|/\*|~/?|\*|\$home|\$\{home\}|[a-z]:\\?\*?|%(?:systemroot|windir|userprofile|homedrive)%\\?|\$env:(?:userprofile|systemroot|windir)\\?)"""
_END = r"""["']?(?=\s|;|&|\||$)"""
_START = r"""(?:^|[;&|`(\s])"""

_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(_START + r"""rm\s+(?:-[a-z-]+\s+)*-[a-z]*[rf][a-z]*\s+(?:-[a-z-]+\s+)*(?:--no-preserve-root\s+)?["']?""" + _ROOT_TARGET + _END, re.I),
     "recursively deletes a drive root or home folder"),
    (re.compile(_START + r"""(?:del|erase)\s+(?:/[a-z]\s+)*/[sq]\b.*?\s["']?""" + _ROOT_TARGET + _END, re.I),
     "deletes a whole drive or user folder"),
    (re.compile(_START + r"""(?:rd|rmdir)\s+(?:/[a-z]\s+)*/s\b.*?\s["']?""" + _ROOT_TARGET + _END, re.I),
     "removes a whole drive or user folder"),
    # PowerShell takes the target before or after -Recurse, so look for -Recurse anywhere
    # in the statement and a root target anywhere in it.
    (re.compile(r"""\bremove-item\b(?=[^;&|]*-recurse)[^;&|]*?\s["']?""" + _ROOT_TARGET + _END, re.I),
     "recursively deletes a drive root or home folder"),
    (re.compile(_START + r"""format(?:\.com)?\s+[a-z]:""", re.I), "formats a drive"),
    (re.compile(_START + r"""(?:diskpart|fdisk|cfdisk|wipefs|bcdedit)(?:\.exe)?\b""", re.I), "edits disks or boot configuration"),
    (re.compile(_START + r"""mkfs(?:\.\w+)?\b""", re.I), "creates a filesystem (erases a disk)"),
    (re.compile(r"""\bdd\s+[^;&|]*\bof=/dev/(?!null\b)""", re.I), "writes raw data to a device"),
    (re.compile(r""">\s*/dev/(?!null\b|stdout\b|stderr\b|tty\b)""", re.I), "redirects output onto a device"),
    (re.compile(r"""\bshred\b[^;&|]*\s/dev/""", re.I), "shreds a device"),
    (re.compile(_START + r"""(?:chmod|chown)\s+-[a-z]*r[a-z]*\s+[^;&|]*\s/(?:\s|$)""", re.I), "changes permissions on the whole filesystem"),
    (re.compile(_START + r"""(?:shutdown|reboot|halt|poweroff)(?:\.exe|\.com)?(?:\s|$|;|&|\|)""", re.I), "shuts down or restarts the machine"),
    (re.compile(_START + r"""init\s+[06](?:\s|$)""", re.I), "changes the runlevel to halt/reboot"),
    (re.compile(r"""\b(?:stop|restart)-computer\b""", re.I), "shuts down or restarts the machine"),
    (re.compile(r""":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"""), "is a fork bomb"),
    (re.compile(r"""\breg(?:\.exe)?\s+delete\s+hk(?:lm|cu|cr)\b""", re.I), "deletes registry hives"),
    (re.compile(r"""\bcipher(?:\.exe)?\s+/w""", re.I), "wipes free disk space"),
    (re.compile(r"""\b(?:curl|wget|iwr|invoke-webrequest|irm|invoke-restmethod)\b[^;&]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|iex|invoke-expression|powershell|pwsh|python\d?)\b""", re.I),
     "pipes a download straight into an interpreter"),
]


def check_command(command: str) -> Optional[str]:
    """Return a human-readable reason if the command looks catastrophic, else ``None``."""
    if not isinstance(command, str) or not command.strip():
        return "empty command"
    if "\x00" in command:
        return "contains a NUL byte"
    for pattern, reason in _RULES:
        if pattern.search(command):
            return f"blocked: this command {reason}. Run it yourself in the Terminal app if you really mean it."
    return None
