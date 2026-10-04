"""Reminders that fire on the server, with or without an Odysseus OS tab open.

A reminder made in Odysseus OS (quick capture, or Jarvis ``create_reminder``) is an ordinary Odysseus note with a
``due_date``. Odysseus' own scanner (``_note_pings_loop`` -> ``action_ping_notes`` -> ``dispatch_reminder``) already picks
those up every minute, whether or not any browser is open, and sends them down the configured channel (email / ntfy /
webhook). What it could not do, in the usual single-user "browser" setup, was reach anybody when no tab is open: the in-app
queue is only drained by a signed-in page. This module closes that gap and keeps the OS page from announcing the same
reminder a second time:

* ``announce`` runs when the scanner fires a reminder. It puts the reminder in the OS notification centre (the bell) and,
  on a single-user Windows machine, shows a native desktop toast. Both are recorded under one key,
  ``reminder:<note id>:<due time in ms>`` - the exact key the OS page uses for its own toast - so whoever announces first wins
  and the other skips.
* While an OS tab is open and polling (``touch_os_tab`` is called by the Today endpoint) the first scan leaves the reminder
  to that tab, which toasts at the due time and has a "Done" button; if the tab turns out not to have announced it by the
  next scan, the server does.
* ``announced_keys`` is what the Today endpoint returns as ``server_fired`` so a freshly opened OS page does not re-toast a
  reminder that already went out.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

logger = logging.getLogger(__name__)

OS_TAB_FRESH_SECONDS = 75.0          # the OS page polls Today every ~30 s while it is visible
_STATE_FILE = "os_reminders_announced.json"
_KEEP_SECONDS = 3 * 24 * 3600

_app: Any = None
_last_os_poll = 0.0
_deferred_once: Dict[str, float] = {}


# ------------------------------------------------------------------------------- wiring
def bind(app: Any) -> None:
    """Give the module access to ``app.state.jarvis`` (the notification centre). Called once at start-up."""
    global _app
    _app = app


def touch_os_tab() -> None:
    global _last_os_poll
    _last_os_poll = time.monotonic()


def os_tab_active() -> bool:
    return (time.monotonic() - _last_os_poll) < OS_TAB_FRESH_SECONDS


# ------------------------------------------------------------------------------- keys
def due_ms(due: Optional[str]) -> Optional[int]:
    """Epoch milliseconds of a note's ``due_date`` ("2026-10-03T18:00" = server-local wall clock, or an ISO string with Z)."""
    if not due or not isinstance(due, str):
        return None
    try:
        s = due.strip()
        d = datetime.fromisoformat(s[:-1] + "+00:00") if s.endswith("Z") else datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.astimezone()                      # naive = local time of this machine
        return int(d.astimezone(timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


def reminder_key(note_id: str, due: Optional[str]) -> Optional[str]:
    ms = due_ms(due)
    return f"reminder:{note_id}:{ms}" if note_id and ms is not None else None


# ------------------------------------------------------------------------------- persisted flags
def _state_path() -> Path:
    from src.constants import DATA_DIR

    return Path(DATA_DIR) / _STATE_FILE


def _read_state() -> Dict[str, float]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _mark(key: str) -> None:
    state = _read_state()
    now = time.time()
    state = {k: v for k, v in state.items() if now - v < _KEEP_SECONDS}
    state[key] = now
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.debug("reminder flag not saved: %s", e)


def _center() -> Any:
    jarvis = getattr(getattr(_app, "state", None), "jarvis", None)
    comm = (getattr(jarvis, "subsystems", None) or {}).get("communication") if jarvis else None
    return getattr(comm, "notification_system", None) if comm else None


def announced_keys(keys: Iterable[str]) -> Set[str]:
    """Which of ``keys`` were already announced (by the server or by an OS tab)."""
    wanted = {k for k in keys if k}
    if not wanted:
        return set()
    found = wanted & set(_read_state())
    ns = _center()
    if ns is not None:
        found |= wanted & {n.get("key") for n in list(getattr(ns, "notifications", []))}
    return found


# ------------------------------------------------------------------------------- delivery
def desktop_enabled(owner: str = "") -> bool:
    """Native desktop toast: Windows, and only for the single-user (no sign-in) setup unless forced with
    ODYSSEUS_DESKTOP_REMINDERS=1 - a shared server must not pop up every user's reminders on its own screen."""
    if sys.platform != "win32":
        return False
    forced = os.environ.get("ODYSSEUS_DESKTOP_REMINDERS", "").strip().lower()
    if forced in ("0", "false", "no", "off"):
        return False
    if owner and forced not in ("1", "true", "yes", "on"):
        return False
    try:
        from src.settings import get_setting

        return bool(get_setting("reminder_desktop_notify", True))
    except Exception:
        return True


_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $xml.GetElementsByTagName('text')
[void]$text.Item(0).AppendChild($xml.CreateTextNode($env:ODY_TOAST_TITLE))
[void]$text.Item(1).AppendChild($xml.CreateTextNode($env:ODY_TOAST_BODY))
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


async def desktop_toast(title: str, body: str, timeout: float = 20.0) -> bool:
    """Show a Windows toast. The text travels in environment variables, never in the script, so it cannot break out of it.
    Never raises; returns whether PowerShell reported success."""
    if sys.platform != "win32":
        return False
    encoded = base64.b64encode(_TOAST_PS.encode("utf-16-le")).decode("ascii")
    env = dict(os.environ, ODY_TOAST_TITLE=(title or "Reminder")[:120], ODY_TOAST_BODY=(body or "")[:400])
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-EncodedCommand", encoded,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            env=env, creationflags=0x08000000,                  # CREATE_NO_WINDOW
        )
    except (OSError, NotImplementedError) as e:
        logger.debug("desktop toast could not start: %s", e)
        return False
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return False
    if proc.returncode != 0:
        logger.debug("desktop toast failed: %s", (err or b"").decode("utf-8", "replace")[:200])
    return proc.returncode == 0


async def _add_to_center(title: str, message: str, key: Optional[str]) -> bool:
    ns = _center()
    if ns is None:
        return False
    try:
        nid = await ns.send_notification(title, message, "info")
        if key:
            for n in reversed(ns.notifications):
                if n.get("id") == nid:
                    n["key"] = key
                    break
        return True
    except Exception as e:
        logger.debug("reminder not added to the notification centre: %s", e)
        return False


async def announce(*, note_id: str, title: str, body: str, due: Optional[str], owner: str = "") -> Dict[str, Any]:
    """Announce a reminder the scanner just fired. Returns what happened:
    ``{"deferred", "duplicate", "center", "desktop"}`` (``deferred``: an open OS tab will announce it)."""
    out = {"deferred": False, "duplicate": False, "center": False, "desktop": False}
    key = reminder_key(note_id, due)
    if key and announced_keys([key]):
        out["duplicate"] = True
        return out
    if key and os_tab_active() and key not in _deferred_once:
        # Somebody is looking at the OS: let the page show it (in context, with a Done button). If it has not by the
        # next scan - the page closed, or its timers were throttled - this runs again and the server delivers it.
        now = time.monotonic()
        for k in [k for k, t in _deferred_once.items() if now - t > 900]:
            _deferred_once.pop(k, None)
        _deferred_once[key] = now
        out["deferred"] = True
        return out
    text = (body or title or "").strip()
    out["center"] = await _add_to_center(title or "Reminder", text, key)
    if desktop_enabled(owner):
        out["desktop"] = await desktop_toast(title or "Reminder", text)
    if key and (out["center"] or out["desktop"]):
        _mark(key)
    _deferred_once.pop(key or "", None)
    return out
