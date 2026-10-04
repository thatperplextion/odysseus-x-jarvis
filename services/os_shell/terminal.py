"""Streaming command execution for the Terminal app.

Each command runs in a fresh shell process (no PTY: ConPTY isn't available to
asyncio on Windows and the app is browser-based), with output streamed as it is
produced. Two things make that feel like a persistent session:

* **cwd tracking** -- after the user's command, the shell prints a one-line
  sentinel carrying its final working directory and exit status; the client sends
  that directory back with the next command, so ``cd`` sticks.
* **environment** -- a sanitised copy of the server's environment (no API keys,
  no Odysseus virtualenv leaking into the user's ``python``).

This runs *real* commands as the server's OS user. It is admin-only and audited by
the route layer; the sandbox and command guard deliberately do not apply here.
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from .procgroup import ProcessGroup
from .procs import kill_process_tree

_IS_WINDOWS = os.name == "nt"

DEFAULT_TIMEOUT = 3600.0
MAX_STREAM_BYTES = 20 * 1024 * 1024
MAX_CONCURRENT = 8
_CREATE_NO_WINDOW = 0x08000000

_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE)", re.IGNORECASE)
_KEEP = {"SSH_AUTH_SOCK", "GPG_AGENT_INFO", "KEYBOARD_LAYOUT", "XDG_SESSION_KEY"}

_active = 0


class TerminalBusy(Exception):
    pass


class UnknownShell(Exception):
    pass


# ----------------------------------------------------------------------- shells
def _find_bash() -> Optional[str]:
    try:
        from core.platform_compat import find_bash

        found = find_bash()
        if found:
            return str(found)
    except Exception:
        pass
    return shutil.which("bash")


def available_shells() -> List[Dict[str, Any]]:
    shells: List[Dict[str, Any]] = []
    if _IS_WINDOWS:
        if shutil.which("pwsh"):
            shells.append({"id": "pwsh", "label": "PowerShell 7", "path": shutil.which("pwsh")})
        ps = shutil.which("powershell")
        if ps:
            shells.append({"id": "powershell", "label": "Windows PowerShell", "path": ps})
        cmd = os.environ.get("ComSpec") or shutil.which("cmd")
        if cmd:
            shells.append({"id": "cmd", "label": "Command Prompt", "path": cmd})
        bash = _find_bash()
        if bash:
            shells.append({"id": "bash", "label": "Git Bash", "path": bash})
    else:
        seen = set()
        for candidate in (os.environ.get("SHELL"), shutil.which("bash"), shutil.which("zsh"), shutil.which("sh")):
            if candidate and os.path.exists(candidate):
                name = os.path.basename(candidate)
                if name not in seen:
                    seen.add(name)
                    shells.append({"id": name, "label": name, "path": candidate})
    for i, s in enumerate(shells):
        s["default"] = i == 0
    return shells


def default_shell_id() -> Optional[str]:
    shells = available_shells()
    return shells[0]["id"] if shells else None


# ------------------------------------------------------------------ environment
def terminal_env() -> Dict[str, str]:
    """The server's environment minus secrets and minus the Odysseus virtualenv."""
    env: Dict[str, str] = {}
    for k, v in os.environ.items():
        if _SECRET_NAME.search(k) and k not in _KEEP:
            continue
        env[k] = v
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    prefix = os.path.normcase(os.path.abspath(sys.prefix))
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):  # we are in a venv: drop its bin dir from PATH
        parts = [p for p in env.get("PATH", "").split(os.pathsep)
                 if not os.path.normcase(os.path.abspath(p)).startswith(prefix)]
        env["PATH"] = os.pathsep.join(parts)
    env["PYTHONUNBUFFERED"] = "1"  # so `python script.py` streams as it prints
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("TERM", "dumb")
    env["NO_COLOR"] = "1"
    return env


# ----------------------------------------------------------------- command build
_ps_probe: Dict[str, bool] = {}


def _ps_file_mode_ok(ps_path: str) -> bool:
    """Can this machine run a temp .ps1 with ``-ExecutionPolicy Bypass``? (Group policy can forbid
    it.) Probed once per PowerShell binary; the result is cached."""
    if ps_path in _ps_probe:
        return _ps_probe[ps_path]
    ok = False
    tmp = _write_temp(".ps1", "\ufeffWrite-Output 'ody-ok'")
    try:
        r = subprocess.run(
            [ps_path, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(tmp)],
            capture_output=True, timeout=20, creationflags=_CREATE_NO_WINDOW if _IS_WINDOWS else 0,
        )
        ok = b"ody-ok" in r.stdout
    except Exception:
        ok = False
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    _ps_probe[ps_path] = ok
    return ok


def _cmd_batch_syntax(command: str) -> str:
    """Terminal input is typed the way you would at a ``cmd`` prompt, but it runs from a batch file, where a ``for``
    variable has to be written ``%%i`` instead of ``%i`` ("i was unexpected at this time"). Double the single-percent
    ones (``%i``, ``%~nxi``) of every ``for %x in (`` loop so one-liners from the web behave as they do interactively."""
    names = set(re.findall(r"(?<![%\w])%([A-Za-z])\s+in\s*\(", command))
    for v in names:
        command = re.sub(r"(?<!%)%(~[A-Za-z]*)?" + v + r"(?![A-Za-z0-9_%])", lambda m, v=v: "%%" + (m.group(1) or "") + v, command)
    return command


def _build(shell_id: str, command: str, marker: str) -> Tuple[List[str], Optional[Path]]:
    """Returns ``(argv, temp_file_to_delete)``. The wrapper prints
    ``\\n<marker><exit>;;<cwd>`` after the user's command, whatever it did."""
    shells = {s["id"]: s for s in available_shells()}
    if shell_id not in shells:
        raise UnknownShell(f"unknown shell: {shell_id}")
    path = shells[shell_id]["path"]

    if shell_id in ("powershell", "pwsh"):
        script = (
            "try{[Console]::OutputEncoding=[System.Text.Encoding]::UTF8}catch{};"
            "$OutputEncoding=[System.Text.Encoding]::UTF8;"
            "$ProgressPreference='SilentlyContinue';"
            "$global:LASTEXITCODE=$null;\n"
            "try {\n" + command + "\n} finally { "
            "[Console]::Out.Write(\"`n" + marker + "\" + [string]$global:LASTEXITCODE + \";;\" + (Get-Location).ProviderPath) }"
        )
        if _ps_file_mode_ok(path):
            # A temp .ps1 run with -File: errors arrive as plain text. (-EncodedCommand with
            # redirected stderr makes Windows PowerShell emit "#< CLIXML" XML instead, and
            # no -OutputFormat setting prevents it.) Bypass applies to this process only.
            tmp = _write_temp(".ps1", "\ufeff" + script)
            return [path, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-File", str(tmp)], tmp
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return [path, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], None

    if shell_id == "cmd":
        body = "@echo off\r\nchcp 65001>nul\r\n" + _cmd_batch_syntax(command).replace("\r\n", "\n").replace("\n", "\r\n") + (
            "\r\necho.\r\necho " + marker + "%errorlevel%;;%cd%\r\n")
        tmp = _write_temp(".cmd", body)
        return [path, "/d", "/q", "/c", str(tmp)], tmp

    # POSIX-style shells (including Git Bash on Windows)
    pwd_expr = '"$(cygpath -w "$PWD" 2>/dev/null || pwd)"' if _IS_WINDOWS else '"$PWD"'
    script = command + "\n__ody_rc=$?\nprintf '\\n" + marker + "%s;;%s' \"$__ody_rc\" " + pwd_expr + "\n"
    if _IS_WINDOWS:
        tmp = _write_temp(".sh", script.replace("\r\n", "\n"))
        return [path, "--noprofile", "--norc", str(tmp)], tmp
    return [path, "-c", script], None


def _write_temp(suffix: str, text: str) -> Path:
    fd, name = tempfile.mkstemp(prefix="ody-term-", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(text.encode("utf-8"))
    return Path(name)


# ---------------------------------------------------------------------- streaming
def _hold_len(text: str, marker: str) -> int:
    """How many trailing characters of ``text`` must wait for the next read.

    The wrapper prints ``\\n<marker>...`` after the user's command, and we strip that
    leading newline. So we can only safely emit text up to (but not including) a
    trailing newline and any partial marker; everything else streams immediately.
    """
    n = 0
    for k in range(min(len(marker) - 1, len(text)), 0, -1):
        if text.endswith(marker[:k]):
            n = k
            break
    head = text[: len(text) - n]
    if head.endswith("\r\n"):
        n += 2
    elif head.endswith("\n"):
        n += 1
    return n


async def stream_command(
    command: str,
    cwd: str,
    shell_id: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> AsyncIterator[Dict[str, Any]]:
    """Run ``command`` and yield events:

    ``{"t": "start", "pid", "shell"}``, ``{"t": "out", "d": text}`` (stdout and stderr
    interleaved in order), then one ``{"t": "exit", "code", "cwd", "ms", ...}``.
    Closing the generator (client disconnect) kills the whole process tree.
    """
    global _active
    shell_id = shell_id or default_shell_id()
    if not shell_id:
        raise UnknownShell("no shell available")
    if not os.path.isdir(cwd):
        raise FileNotFoundError(f"working directory does not exist: {cwd}")
    if _active >= MAX_CONCURRENT:
        raise TerminalBusy(f"too many commands running ({MAX_CONCURRENT}); stop one first")

    marker = f"@@ODY{secrets.token_hex(6)}@@"
    if shell_id in ("powershell", "pwsh") and not _ps_probe:
        await asyncio.to_thread(_ps_file_mode_ok, next(x["path"] for x in available_shells() if x["id"] == shell_id))
    argv, tmp = _build(shell_id, command, marker)
    # PowerShell mentions the temp script in error text; show "<command>" instead. Match on the unique
    # file name (the directory may be printed in long or 8.3 short form).
    scrub = (
        re.compile(r"(?:[A-Za-z]:\\[^\r\n]*?)?" + re.escape(tmp.name))
        if tmp is not None and tmp.suffix == ".ps1" else None
    )

    def clean(text: str) -> str:
        return scrub.sub("<command>", text) if scrub else text

    flags = _CREATE_NO_WINDOW if _IS_WINDOWS else 0
    kwargs: Dict[str, Any] = {"creationflags": flags} if _IS_WINDOWS else {"start_new_session": True}

    _active += 1
    started = time.monotonic()
    proc = None
    group: Optional[ProcessGroup] = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=terminal_env(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **kwargs,
        )
        group = ProcessGroup.attach(proc.pid)
        yield {"t": "start", "pid": proc.pid, "shell": shell_id}

        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pending = ""          # held back in case the marker straddles two reads
        tail = ""             # everything from the marker onward
        total = 0
        timed_out = truncated = False
        deadline = started + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(32768), timeout=remaining)
            except asyncio.TimeoutError:
                timed_out = True
                break
            if not chunk:
                break
            total += len(chunk)
            text = pending + decoder.decode(chunk)
            pending = ""
            if tail:
                tail += text
                continue
            idx = text.find(marker)
            if idx >= 0:
                tail = text[idx:]
                visible = text[:idx]
                if visible.endswith("\r\n"):
                    visible = visible[:-2]
                elif visible.endswith("\n"):
                    visible = visible[:-1]
                if visible:
                    yield {"t": "out", "d": clean(visible)}
            else:
                hold = _hold_len(text, marker)
                emit = text[: len(text) - hold]
                pending = text[len(text) - hold:]
                if emit:
                    yield {"t": "out", "d": clean(emit)}
            if total > MAX_STREAM_BYTES:
                truncated = True
                break

        if pending and not tail:
            yield {"t": "out", "d": clean(pending)}
        if timed_out or truncated:
            group.kill()
        code = await proc.wait()

        final_cwd, rc = cwd, None
        if tail:
            payload = tail[len(marker):].strip()
            rc_text, _, cwd_text = payload.partition(";;")
            if cwd_text and os.path.isdir(cwd_text.strip()):
                final_cwd = cwd_text.strip()
            if rc_text.strip().lstrip("-").isdigit():
                rc = int(rc_text.strip())
        yield {
            "t": "exit",
            # the process's own status is authoritative; fall back to the shell's report
            "code": None if (timed_out or truncated) else (code if code else (rc or 0)),
            "cwd": final_cwd,
            "ms": int((time.monotonic() - started) * 1000),
            "timeout": timed_out,
            "truncated": truncated,
        }
    finally:
        _active -= 1
        if group is not None:
            if proc is not None and proc.returncode is None:
                group.kill()  # client went away (or an error): nothing may be left running
            group.close()
        elif proc is not None and proc.returncode is None:
            kill_process_tree(proc.pid)
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
