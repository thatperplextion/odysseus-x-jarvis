"""Reminders made in Odysseus OS fire on the server - with no OS tab open - and are not announced twice.

Uses a real temp database, the real OS commit function that quick capture uses, Odysseus' own scanner
(``action_ping_notes``) and the real ``dispatch_reminder``; only the Windows toast and the notification centre
are stand-ins (so nothing pops up on the machine running the tests).
"""
import json
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.database as cdb
from tests.helpers.sqlite_db import make_temp_sqlite
from services.os_shell import reminders as rem


class FakeCenter:
    def __init__(self):
        self.notifications = []

    async def send_notification(self, title, message, severity="info", channels=None):
        nid = f"n{len(self.notifications) + 1}"
        self.notifications.append({"id": nid, "title": title, "message": message, "severity": severity})
        return nid


@pytest.fixture()
def env(monkeypatch, tmp_path):
    import routes.note_routes as note_routes
    import routes.os_today_routes as today
    import src.builtin_actions as ba
    import src.constants as constants
    import src.settings as settings

    SessionLocal, engine, _tmp = make_temp_sqlite(cdb.Base.metadata)
    monkeypatch.setattr(cdb, "SessionLocal", SessionLocal)
    monkeypatch.setattr(today, "SessionLocal", SessionLocal)
    monkeypatch.setattr(note_routes, "SessionLocal", SessionLocal)
    for mod in (ba, note_routes, constants):
        monkeypatch.setattr(mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "load_settings", lambda: {"reminder_channel": "browser"})

    center = FakeCenter()
    toasts = []

    async def fake_toast(title, body, timeout=20.0):
        toasts.append((title, body))
        return True

    monkeypatch.setattr(rem, "desktop_toast", fake_toast)
    monkeypatch.setattr(rem, "desktop_enabled", lambda owner="": True)
    monkeypatch.setattr(rem, "_last_os_poll", 0.0)
    rem._deferred_once.clear()
    rem.bind(types.SimpleNamespace(state=types.SimpleNamespace(
        jarvis=types.SimpleNamespace(subsystems={"communication": types.SimpleNamespace(notification_system=center)}))))
    yield types.SimpleNamespace(SessionLocal=SessionLocal, center=center, toasts=toasts, tmp=tmp_path, today=today, ba=ba)
    engine.dispose()


def _add_note(SessionLocal, due: datetime, title="Call mom", owner=None) -> str:
    nid = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(cdb.Note(id=nid, owner=owner, title=title, note_type="note", due_date=due.strftime("%Y-%m-%dT%H:%M:%S"),
                        repeat="none", source="user", pinned=False, sort_order=0))
        db.commit()
    finally:
        db.close()
    return nid


async def _scan(env_):
    from src.builtin_actions import TaskNoop

    try:
        return await env_.ba.action_ping_notes(owner="")
    except TaskNoop as e:
        return str(e), None


def _local(offset_seconds: float) -> datetime:
    return datetime.now() + timedelta(seconds=offset_seconds)


async def test_os_commit_reminder_fires_on_the_server_once(env):
    """The note quick capture creates is exactly what Odysseus' scanner picks up."""
    c = env.today.Ctx(owner="", tz_offset=0, now_utc=datetime.now(timezone.utc).replace(tzinfo=None), focus_path=Path("x"))
    db = env.SessionLocal()
    try:
        due = _local(5).strftime("%Y-%m-%dT%H:%M")      # minute resolution like the OS page, i.e. within +-60 s of now
        res = env.today._commit_reminder(db, c, {"title": "Call mom", "due": due})
    finally:
        db.close()
    assert res["kind"] == "reminder"

    msg, ok = await _scan(env)
    assert ok is True, msg
    assert len(env.toasts) == 1 and env.toasts[0][0] == "Call mom"
    assert [n["title"] for n in env.center.notifications] == ["Call mom"]
    key = env.center.notifications[0].get("key")
    assert key and key.startswith(f"reminder:{res['id']}:")
    # the fired flag Odysseus itself uses: note_pings_<owner>.json, with the channel kept (not clobbered)
    cache = json.loads((env.tmp / "note_pings_default.json").read_text(encoding="utf-8"))
    assert isinstance(cache[res["id"]], dict) and cache[res["id"]]["channel"] == "browser"

    # next minute's scan: nothing again (flag + key)
    await _scan(env)
    assert len(env.toasts) == 1 and len(env.center.notifications) == 1


async def test_firing_window_is_around_the_due_time(env):
    early = _add_note(env.SessionLocal, _local(300), "five minutes away")
    soon = _add_note(env.SessionLocal, _local(70), "seventy seconds away")
    just_before = _add_note(env.SessionLocal, _local(15), "fifteen seconds away")
    justdue = _add_note(env.SessionLocal, _local(-60), "a minute ago")
    stale = _add_note(env.SessionLocal, _local(-200), "three minutes ago")
    await _scan(env)
    fired = sorted(t for t, _ in env.toasts)
    assert fired == ["a minute ago", "fifteen seconds away"], fired


async def test_open_os_tab_announces_first_and_the_server_does_not_double_it(env):
    nid = _add_note(env.SessionLocal, _local(0), "With a tab")
    due = env.SessionLocal().query(cdb.Note).get(nid).due_date
    rem.touch_os_tab()                       # an OS page is open and polling

    await _scan(env)                         # first scan: leave it to the tab
    assert env.toasts == [] and env.center.notifications == []
    assert not (env.tmp / "note_pings_default.json").exists() or nid not in json.loads(
        (env.tmp / "note_pings_default.json").read_text(encoding="utf-8"))

    # the tab toasts and reports it to the notification centre under the shared key
    key = rem.reminder_key(nid, due)
    await env.center.send_notification("Reminder", "With a tab")
    env.center.notifications[-1]["key"] = key

    rem.touch_os_tab()
    await _scan(env)                         # second scan: already announced by the tab
    assert env.toasts == []
    assert len(env.center.notifications) == 1


async def test_server_delivers_when_the_tab_never_does(env):
    _add_note(env.SessionLocal, _local(0), "Tab throttled")
    rem.touch_os_tab()
    await _scan(env)
    assert env.toasts == []                  # deferred once
    rem.touch_os_tab()
    await _scan(env)                         # still nothing from the tab -> the server delivers
    assert [t for t, _ in env.toasts] == ["Tab throttled"]
    assert len(env.center.notifications) == 1


async def test_agenda_reports_server_fired_so_a_new_tab_does_not_repeat_it(env):
    nid = _add_note(env.SessionLocal, _local(-20), "Already delivered")
    other = _add_note(env.SessionLocal, _local(600), "Later today")
    c = env.today.Ctx(owner="", tz_offset=-int(datetime.now().astimezone().utcoffset().total_seconds() // 60) * -1,
                      now_utc=datetime.now(timezone.utc).replace(tzinfo=None), focus_path=Path("x"))
    # tz_offset is JS-style (UTC minus local)
    c.tz_offset = env.today._server_offset_min()
    before = {r["id"]: r for r in env.today._sec_agenda(c)["reminders"]}
    assert before[nid]["server_fired"] is False and before[nid]["key"].startswith(f"reminder:{nid}:")

    await _scan(env)                          # fires the first one only
    after = {r["id"]: r for r in env.today._sec_agenda(c)["reminders"]}
    assert after[nid]["server_fired"] is True
    assert after[other]["server_fired"] is False


async def test_without_a_notification_centre_or_toast_the_normal_channel_still_works(env, monkeypatch):
    """Server-side announce is additive: with Jarvis absent and toasts off, dispatch still completes and flags the note."""
    rem.bind(types.SimpleNamespace(state=types.SimpleNamespace()))
    monkeypatch.setattr(rem, "desktop_enabled", lambda owner="": False)
    nid = _add_note(env.SessionLocal, _local(0), "Quiet")
    msg, ok = await _scan(env)
    assert env.toasts == []
    cache = json.loads((env.tmp / "note_pings_default.json").read_text(encoding="utf-8"))
    assert nid in cache


def test_toast_text_cannot_break_out_of_the_script():
    # the text is passed through environment variables, never interpolated into the PowerShell source
    assert "$env:ODY_TOAST_TITLE" in rem._TOAST_PS and "$env:ODY_TOAST_BODY" in rem._TOAST_PS
    assert "{title}" not in rem._TOAST_PS and "%s" not in rem._TOAST_PS


def test_desktop_toast_is_single_user_only(monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys, "platform", "win32")
    monkeypatch.delenv("ODYSSEUS_DESKTOP_REMINDERS", raising=False)
    assert rem.desktop_enabled("") is True
    assert rem.desktop_enabled("alice") is False          # signed-in multi-user server: no pop-ups on its own screen
    monkeypatch.setenv("ODYSSEUS_DESKTOP_REMINDERS", "1")
    assert rem.desktop_enabled("alice") is True
    monkeypatch.setenv("ODYSSEUS_DESKTOP_REMINDERS", "0")
    assert rem.desktop_enabled("") is False
