"""
Today -- the data behind the Odysseus OS desktop's command centre (``/api/os/today`` and friends).

One aggregated, owner-scoped payload so the home screen paints in a single round trip:
agenda, todos, automations, inbox, focus, model and a deterministic one-line summary. Every section is
computed on its own worker thread with its own timeout, so one broken subsystem (an unreachable mail
index, a locked database) shows up as ``{"error": ...}`` in that section while the others still render.
Nothing here talks to the network: mail comes from the local message index only.

Also here: quick capture (parse a line of text into a todo / event / reminder / automation *draft*, then
commit it through the same tables the Notes, Calendar and Tasks apps use), the focus-session log, and a
small "push to the notification centre" endpoint with de-duplication.

All routes use the same admin/loopback guard as the rest of ``/api/os``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_

from core.database import (
    CalendarCal, CalendarEvent, EmailAccount, ModelEndpoint, Note, ScheduledTask, SessionLocal, TaskRun,
)
from routes._os_guard import os_admin_guard
from services.os_shell import capture as cap
from services.os_shell.focus import FocusStore

logger = logging.getLogger(__name__)

SECTION_TIMEOUT = 4.0           # seconds; a section that takes longer reports an error instead of stalling the page
CAPTURE_NOTE_TITLE = "Quick capture"
MAX_OPEN_TODOS = 12
INBOX_FOLDER = "INBOX"


# --------------------------------------------------------------------------- request context
@dataclass
class Ctx:
    owner: str                  # "" = single-user / auth off
    tz_offset: int              # minutes, UTC minus local (JS getTimezoneOffset)
    now_utc: datetime           # naive UTC
    focus_path: Path

    @property
    def off(self) -> timedelta:
        return timedelta(minutes=self.tz_offset)

    @property
    def now_local(self) -> datetime:
        return self.now_utc - self.off

    @property
    def now_ms(self) -> int:
        return int(self.now_utc.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _owner_of(request: Request) -> str:
    return getattr(request.state, "current_user", None) or ""


def _focus_path(request: Request) -> Path:
    jarvis = getattr(request.app.state, "jarvis", None)
    base = getattr(jarvis, "jarvis_data_dir", None)
    if base is None:
        from src.constants import DATA_DIR

        base = Path(DATA_DIR) / "jarvis"
    return Path(base) / "os" / "focus.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _server_offset_min() -> int:
    """This machine's UTC offset in JS getTimezoneOffset terms (minutes, UTC minus local); the default when a client sends none."""
    off = datetime.now().astimezone().utcoffset()
    return -int(off.total_seconds() // 60) if off else 0


def _ctx(request: Request, tz_offset: Optional[int], now: Optional[str] = None) -> Ctx:
    tz_offset = max(-14 * 60, min(14 * 60, _server_offset_min() if tz_offset is None else int(tz_offset)))
    now_utc = _utc_now()
    if now:  # tests / replays: a naive *local* ISO timestamp
        try:
            now_utc = datetime.fromisoformat(now) + timedelta(minutes=tz_offset)
        except ValueError:
            raise HTTPException(400, "now must be an ISO timestamp")
    return Ctx(owner=_owner_of(request), tz_offset=tz_offset, now_utc=now_utc, focus_path=_focus_path(request))


def _scoped(q, model, owner: str):
    """Owner scope exactly like the Notes/Tasks routes: strict when someone is signed in, no filter when auth is off."""
    return q.filter(model.owner == owner) if owner else q


def _ms(dt_utc: datetime) -> int:
    return int(dt_utc.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _iso_z(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _naive(s: str) -> datetime:
    """Parse the ISO strings the calendar code emits ('...Z' for UTC rows, 'YYYY-MM-DD' for all-day) to naive."""
    s = (s or "").strip()
    if len(s) == 10:
        return datetime.fromisoformat(s)
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _rel(delta_s: float) -> str:
    """'now' / 'in 25 min' / 'in 2 h 5 min' / 'in 3 d'."""
    s = int(delta_s)
    if s < 45:
        return "now"
    m = round(s / 60)
    if m < 60:
        return f"in {m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"in {h} h" + (f" {m} min" if m else "")
    return f"in {h // 24} d"


# ------------------------------------------------------------------------------- sections
def _sec_agenda(c: Ctx) -> Dict[str, Any]:
    from routes.calendar_routes import FALLBACK_OWNER, _expand_rrule

    cal_owner = c.owner or FALLBACK_OWNER
    day0 = c.now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day1, day2 = day0 + timedelta(days=1), day0 + timedelta(days=2)
    q_start, q_end = day0 - timedelta(days=1), day2 + timedelta(days=1)      # padded: rows are local-naive OR UTC-naive
    now_ms = c.now_ms

    db = SessionLocal()
    try:
        rows = (
            db.query(CalendarEvent).join(CalendarCal, CalendarEvent.calendar_id == CalendarCal.id)
            .filter(
                CalendarEvent.status != "cancelled",
                CalendarCal.owner == cal_owner,
                or_(
                    and_(or_(CalendarEvent.rrule == "", CalendarEvent.rrule.is_(None)), CalendarEvent.dtstart < q_end, CalendarEvent.dtend > q_start),
                    and_(CalendarEvent.rrule.isnot(None), CalendarEvent.rrule != "", CalendarEvent.dtstart < q_end),
                ),
            )
            .order_by(CalendarEvent.dtstart).limit(400).all()
        )
        expanded: List[dict] = []
        for ev in rows:
            expanded.extend(_expand_rrule(ev, q_start, q_end))
        # reminders: notes with a dated-and-timed due_date inside the window
        notes = (_scoped(db.query(Note), Note, c.owner).filter(Note.archived == False, Note.due_date.isnot(None))  # noqa: E712
                 .limit(300).all())
        note_rows = [(n.id, n.title or "Reminder", n.due_date, n.items) for n in notes]
    finally:
        db.close()

    events: List[dict] = []
    for d in expanded:
        try:
            ds, de = _naive(d["dtstart"]), _naive(d["dtend"])
        except (ValueError, KeyError):
            continue
        all_day = bool(d.get("all_day"))
        if not all_day and d.get("is_utc"):
            ds, de = ds - c.off, de - c.off                      # utc -> user's wall clock
        if de <= ds:
            de = ds + timedelta(days=1 if all_day else 0, minutes=0 if all_day else 30)
        if not (ds < day2 and de > day0):
            continue
        s_utc, e_utc = ds + c.off, de + c.off
        events.append({
            "kind": "event", "uid": d.get("uid"), "summary": d.get("summary") or "(untitled)",
            "start": ds.strftime("%Y-%m-%dT%H:%M"), "end": de.strftime("%Y-%m-%dT%H:%M"),
            "start_ts": _ms(s_utc), "end_ts": _ms(e_utc), "all_day": all_day,
            "location": d.get("location") or "", "color": d.get("color") or "", "calendar": d.get("calendar") or "",
            "day": "today" if ds < day1 else "tomorrow",
        })
    events.sort(key=lambda e: (not e["all_day"], e["start_ts"]))

    reminders: List[dict] = []
    for nid, title, due, items in note_rows:
        if not isinstance(due, str) or not re.search(r"T\d{2}:\d{2}", due):
            continue
        try:
            dd = datetime.fromisoformat(due.replace("Z", "+00:00"))
        except ValueError:
            continue
        local = (dd.astimezone(timezone.utc).replace(tzinfo=None) - c.off) if dd.tzinfo else dd
        if not (day0 <= local < day2):
            continue
        if items:
            try:
                its = json.loads(items)
                if isinstance(its, list) and its and all(isinstance(i, dict) and i.get("done") for i in its):
                    continue
            except (ValueError, TypeError):
                pass
        ts = _ms(local + c.off)
        reminders.append({"kind": "reminder", "id": nid, "summary": title, "start": local.strftime("%Y-%m-%dT%H:%M"),
                          "start_ts": ts, "end_ts": ts, "all_day": False, "day": "today" if local < day1 else "tomorrow", "due": due,
                          "key": f"reminder:{nid}:{ts}"})
    reminders.sort(key=lambda r: r["start_ts"])
    # The server announces due reminders itself (desktop toast + the notification centre) when no OS tab is open.
    # `server_fired` is true once that, or an OS tab's own toast, has happened - a page that opens afterwards must not
    # announce the same reminder again. `key` is the de-duplication key both sides use for POST /api/os/notify.
    try:
        from services.os_shell import reminders as _rem

        _alt = {r["id"]: _rem.reminder_key(r["id"], r.get("due")) for r in reminders}
        _done = _rem.announced_keys([r["key"] for r in reminders] + [k for k in _alt.values() if k])
        for r in reminders:
            r["server_fired"] = r["key"] in _done or (_alt.get(r["id"]) in _done)
    except Exception:
        for r in reminders:
            r.setdefault("server_fired", False)

    timed = sorted([e for e in events if not e["all_day"]] + reminders, key=lambda x: x["start_ts"])
    next_up = next((x for x in timed if x["end_ts"] > now_ms), None)
    if next_up and next_up["start_ts"] <= now_ms < next_up["end_ts"]:
        next_up = {**next_up, "ongoing": True}
    return {
        "events": events, "reminders": reminders, "next_up": next_up,
        "today_count": sum(1 for e in events if e["day"] == "today"), "tomorrow_count": sum(1 for e in events if e["day"] == "tomorrow"),
        "today_reminders": sum(1 for r in reminders if r["day"] == "today"),
    }


def _sec_todos(c: Ctx) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        notes = (_scoped(db.query(Note), Note, c.owner).filter(Note.archived == False)  # noqa: E712
                 .order_by(Note.pinned.desc(), Note.sort_order.asc(), Note.updated_at.desc()).limit(300).all())
        rows = [(n.id, n.title or "", n.items) for n in notes if n.items]
    finally:
        db.close()
    open_items: List[dict] = []
    total_open = lists = 0
    for nid, title, raw in rows:
        try:
            items = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(items, list):
            continue
        lists += 1
        for idx, it in enumerate(items):
            if not isinstance(it, dict) or it.get("done"):
                continue
            text = str(it.get("text") or "").strip()
            if not text:
                continue
            total_open += 1
            if len(open_items) < MAX_OPEN_TODOS:
                open_items.append({"note_id": nid, "index": idx, "text": text[:300], "list": title})
    return {"open": total_open, "lists": lists, "items": open_items, "more": max(0, total_open - len(open_items))}


def _housekeeping_actions() -> List[str]:
    try:
        from src.task_scheduler import HOUSEKEEPING_DEFAULTS

        return list(HOUSEKEEPING_DEFAULTS.keys())
    except Exception:  # noqa: BLE001
        return []


def _cron_label(expr: str, off_min: int) -> Optional[str]:
    """A few common cron shapes in plain words (times shifted from UTC to the user's clock)."""
    parts = (expr or "").split()
    if len(parts) != 5:
        return None
    mi, hr, dom, mon, dow = parts
    if mi.startswith("*/") and hr == dom == mon == dow == "*":
        return f"Every {mi[2:]} minutes"
    if mi.isdigit() and hr == "*" and dom == mon == dow == "*":
        return "Every hour"
    if mi == "0" and hr.startswith("*/") and dom == mon == dow == "*":
        return f"Every {hr[2:]} hours"
    if mi.isdigit() and hr.isdigit() and dom == mon == "*":
        local = datetime(2024, 1, 1, int(hr), int(mi)) - timedelta(minutes=off_min)
        when = cap.fmt_time(local.hour, local.minute)
        carry = (local.date() - datetime(2024, 1, 1).date()).days
        if dow == "*":
            return f"Daily at {when}"
        days = set()
        for part in dow.split(","):
            r = re.fullmatch(r"(\d)-(\d)", part)
            if r:
                days.update(range(int(r.group(1)), int(r.group(2)) + 1))
            elif part.isdigit():
                days.add(int(part))
            else:
                return None
        days = {(d - carry) % 7 for d in days}
        if days == {1, 2, 3, 4, 5}:
            return f"Weekdays at {when}"
        names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return f"{', '.join(names[d % 7] for d in sorted(days))} at {when}"
    return None


def _schedule_label(t: ScheduledTask, off_min: int) -> str:
    tt = t.trigger_type or "schedule"
    if tt == "event":
        return f"Every {t.trigger_count or 1} {(t.trigger_event or 'event').replace('_', ' ')}"
    if tt == "webhook":
        return "Webhook"
    if t.schedule == "cron":
        return _cron_label(t.cron_expression or "", off_min) or f"Cron {t.cron_expression}"
    if t.schedule == "once":
        return "Once"
    try:
        hh, mm = [int(x) for x in (t.scheduled_time or "09:00").split(":")[:2]]
    except ValueError:
        return t.schedule or "Scheduled"
    local = datetime(2024, 1, 1, hh, mm) - timedelta(minutes=off_min)
    when = cap.fmt_time(local.hour, local.minute)
    carry = (local.date() - datetime(2024, 1, 1).date()).days
    if t.schedule == "weekly":
        return f"Weekly on {cap.DAY_NAMES[((t.scheduled_day or 0) - carry) % 7]} at {when}"
    if t.schedule == "monthly":
        return f"Monthly on the {cap._ordinal(t.scheduled_day or 1)} at {when}"
    return f"Daily at {when}"


def _one_line(text: Optional[str], limit: int = 140) -> str:
    s = re.sub(r"\s+", " ", (text or "")).strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


_RUN_PLACEHOLDER = re.compile(r"^(Starting|Queued)\b", re.I)


def _run_text(r) -> str:
    """A run's output for display. A failed run keeps its start-up placeholder ("Starting...") in `result` and the reason
    in `error`, so `result or error` would hide why it failed. (Same rule as static/os/js/runtext.js.)"""
    result, error = (r.result or "").strip(), (r.error or "").strip()
    if error and (r.status or "") in ("error", "aborted", "skipped"):
        return error if not result or _RUN_PLACEHOLDER.match(result) else f"{error}\n\n{result}"
    return result or error


def _sec_automations(c: Ctx) -> Dict[str, Any]:
    housekeeping = _housekeeping_actions()
    db = SessionLocal()
    try:
        q = _scoped(db.query(ScheduledTask), ScheduledTask, c.owner)
        tasks = q.order_by(ScheduledTask.created_at.desc()).limit(500).all()
        mine = [t for t in tasks if not (t.task_type == "action" and t.action in housekeeping)]
        builtin_active = sum(1 for t in tasks if t.task_type == "action" and t.action in housekeeping and t.status == "active")
        mine_ids = [t.id for t in mine]
        upcoming_src = sorted((t for t in mine if t.status == "active" and t.next_run and (t.trigger_type or "schedule") == "schedule"),
                              key=lambda t: t.next_run)[:5]
        upcoming = [{"id": t.id, "name": t.name, "next_run": _iso_z(t.next_run), "next_ts": _ms(t.next_run),
                     "label": _schedule_label(t, c.tz_offset)} for t in upcoming_src]
        recent: List[dict] = []
        running: List[str] = []
        ran_since = 0
        if mine_ids:
            by_id = {t.id: t for t in mine}
            runs = (db.query(TaskRun).filter(TaskRun.task_id.in_(mine_ids)).order_by(TaskRun.started_at.desc()).limit(5).all())
            for r in runs:
                recent.append({"id": r.id, "task_id": r.task_id, "name": by_id[r.task_id].name, "status": r.status or "",
                               "started_at": _iso_z(r.started_at), "finished_at": _iso_z(r.finished_at),
                               "started_ts": _ms(r.started_at) if r.started_at else None,
                               "summary": _one_line(_run_text(r))})
            running = [r.task_id for r in db.query(TaskRun).filter(TaskRun.task_id.in_(mine_ids), TaskRun.status == "running").limit(20).all()]
            hour = c.now_local.hour
            since_local = c.now_local.replace(hour=0, minute=0, second=0, microsecond=0) - (timedelta(hours=6) if hour < 12 else timedelta())
            since = since_local + c.off
            ran_since = db.query(TaskRun).filter(TaskRun.task_id.in_(mine_ids), TaskRun.started_at >= since, TaskRun.status != "running").count()
            failed_since = db.query(TaskRun).filter(TaskRun.task_id.in_(mine_ids), TaskRun.started_at >= since, TaskRun.status == "error").count()
        else:
            failed_since = 0
        return {
            "total": len(mine), "active": sum(1 for t in mine if t.status == "active"), "paused": sum(1 for t in mine if t.status == "paused"),
            "builtin_active": builtin_active, "builtin_actions": housekeeping, "upcoming": upcoming, "recent": recent, "running": running,
            "ran_since": ran_since, "failed_since": failed_since, "since_label": "overnight" if c.now_local.hour < 12 else "today",
        }
    finally:
        db.close()


def _email_db() -> str:
    from src.constants import SCHEDULED_EMAILS_DB

    return str(SCHEDULED_EMAILS_DB)


def _sec_inbox(c: Ctx) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        accounts = _scoped(db.query(EmailAccount), EmailAccount, c.owner).filter(EmailAccount.enabled == True).all()  # noqa: E712
        configured = any((a.imap_host or a.oauth_provider) for a in accounts)
    finally:
        db.close()
    if not configured:
        return {"configured": False}
    # Local message index only: a mail server that is slow or unreachable must never stall the desktop.
    out: Dict[str, Any] = {"configured": True, "unread": None, "top_senders": [], "synced": False}
    try:
        conn = sqlite3.connect(f"file:{_email_db()}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return out
    try:
        where = "owner=? AND folder=? AND (flags IS NULL OR instr(flags, '\\Seen') = 0)"
        args = (c.owner or "", INBOX_FOLDER)
        total = conn.execute("SELECT COUNT(*), MAX(updated_at) FROM email_message_index WHERE owner=? AND folder=?", args).fetchone()
        if total and total[0]:
            out["synced"] = True
            out["as_of"] = total[1]
            out["unread"] = conn.execute(f"SELECT COUNT(*) FROM email_message_index WHERE {where}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT COALESCE(NULLIF(from_name, ''), from_address, '?') AS s, COUNT(*) AS n FROM email_message_index WHERE {where} "
                "GROUP BY s ORDER BY n DESC, MAX(date_epoch) DESC LIMIT 3", args).fetchall()
            out["top_senders"] = [{"name": r[0], "count": r[1]} for r in rows]
    except sqlite3.Error as e:
        logger.debug("inbox index unreadable: %s", e)
    finally:
        conn.close()
    return out


def _sec_focus(c: Ctx) -> Dict[str, Any]:
    st = FocusStore(c.focus_path).stats(c.owner, c.tz_offset, now=c.now_ms / 1000)
    return {"minutes_today": st["today"]["minutes"], "sessions_today": st["today"]["sessions"], "week_minutes": st["week_minutes"]}


def _sec_model(c: Ctx) -> Dict[str, Any]:
    from urllib.parse import urlparse

    from src.settings import load_settings

    settings = load_settings() or {}
    ep_id = (settings.get("default_endpoint_id") or "").strip()
    model = (settings.get("default_model") or "").strip()
    db = SessionLocal()
    try:
        ep = None
        if ep_id:
            ep = db.query(ModelEndpoint).filter(ModelEndpoint.id == ep_id, ModelEndpoint.is_enabled == True).first()  # noqa: E712
        if ep is None:
            ep = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True).first()  # noqa: E712
            if ep is not None and ep_id:
                model = ""      # the configured endpoint is gone: don't pair its model name with a different provider
        if ep is None:
            return {"configured": False}
        if not model and ep.cached_models:
            try:
                cached = json.loads(ep.cached_models) or []
                model = str(cached[0]) if cached else ""
            except (ValueError, TypeError):
                model = ""
        host = urlparse(ep.base_url or "").hostname or ""
        return {"configured": bool(model), "model": model, "endpoint_id": ep.id, "endpoint_name": ep.name, "host": host}
    finally:
        db.close()


def build_summary(s: Dict[str, Any], now_ms: int) -> Dict[str, Any]:
    """The deterministic one-liner: '3 events . next: Standup in 25 min . 5 todos . 2 automations ran overnight'."""
    parts: List[str] = []
    ag = s.get("agenda") or {}
    if "error" not in ag and ag:
        n = ag.get("today_count", 0)
        if n:
            parts.append(f"{n} event{'s' if n != 1 else ''}")
        nu = ag.get("next_up")
        if nu and nu.get("day", "today") == "today":
            if nu.get("ongoing"):
                parts.append(f"now: {nu['summary']}")
            else:
                parts.append(f"next: {nu['summary']} {_rel((nu['start_ts'] - now_ms) / 1000)}")
        elif not n and not ag.get("today_reminders"):
            parts.append("nothing on the calendar")
    td = s.get("todos") or {}
    if "error" not in td and td.get("open"):
        parts.append(f"{td['open']} todo{'s' if td['open'] != 1 else ''}")
    au = s.get("automations") or {}
    if "error" not in au and au.get("ran_since"):
        k = au["ran_since"]
        txt = f"{k} automation{'s' if k != 1 else ''} ran {au.get('since_label', 'today')}"
        if au.get("failed_since"):
            txt += f" ({au['failed_since']} failed)"
        parts.append(txt)
    ib = s.get("inbox") or {}
    if ib.get("configured") and ib.get("unread"):
        parts.append(f"{ib['unread']} unread")
    fo = s.get("focus") or {}
    if "error" not in fo and fo.get("minutes_today"):
        parts.append(f"{int(round(fo['minutes_today']))} min focused")
    return {"text": " · ".join(parts) if parts else "A clear day ahead.", "parts": parts}


SECTIONS: Dict[str, Callable[[Ctx], Dict[str, Any]]] = {
    "agenda": _sec_agenda, "todos": _sec_todos, "automations": _sec_automations,
    "inbox": _sec_inbox, "focus": _sec_focus, "model": _sec_model,
}


async def _run_section(name: str, fn: Callable[[Ctx], Dict[str, Any]], c: Ctx) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, c), timeout=SECTION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("today section %s timed out", name)
        return {"error": "Timed out"}
    except Exception as e:  # noqa: BLE001 - one broken section must not take the others down
        logger.warning("today section %s failed: %s", name, e)
        return {"error": str(e)[:200] or e.__class__.__name__}


# ----------------------------------------------------------------------------- capture helpers
def _local_now_for(c: Ctx) -> datetime:
    return c.now_local.replace(second=0, microsecond=0)


def _capture_note(db, owner: str) -> Note:
    q = _scoped(db.query(Note), Note, owner).filter(Note.title == CAPTURE_NOTE_TITLE, Note.archived == False)  # noqa: E712
    note = q.first()
    if note is None:
        note = Note(id=str(uuid.uuid4()), owner=owner or None, title=CAPTURE_NOTE_TITLE, note_type="checklist",
                    items="[]", pinned=False, source="user", repeat="none", sort_order=0)
        db.add(note)
        db.flush()
    return note


def _commit_todo(db, c: Ctx, draft: Dict[str, Any]) -> Dict[str, Any]:
    text = str(draft.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Todo text is required")
    if len(text) > 500:
        raise HTTPException(400, "Todo text is too long (500 characters max)")
    note = _capture_note(db, c.owner)
    try:
        items = json.loads(note.items or "[]")
    except (ValueError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []
    item = {"id": uuid.uuid4().hex[:10], "text": text, "done": False}
    items.append(item)
    note.items = json.dumps(items)
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(note, "items")
    db.commit()
    return {"kind": "todo", "id": note.id, "item_id": item["id"], "label": f"Added to {CAPTURE_NOTE_TITLE}", "open": {"app": "notes"}}


def _commit_reminder(db, c: Ctx, draft: Dict[str, Any]) -> Dict[str, Any]:
    title = str(draft.get("title") or "").strip()
    due = str(draft.get("due") or "").strip()
    if not title:
        raise HTTPException(400, "Reminder text is required")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", due):
        raise HTTPException(400, "Reminder time must look like 2026-10-03T18:00")
    try:
        datetime.fromisoformat(due)
    except ValueError:
        raise HTTPException(400, "Reminder time is not a real date")
    note = Note(id=str(uuid.uuid4()), owner=c.owner or None, title=title[:300], note_type="note", due_date=due,
                repeat="none", source="user", pinned=False, sort_order=0)
    db.add(note)
    db.commit()
    return {"kind": "reminder", "id": note.id, "label": "Reminder set", "open": {"app": "notes"}}


def _commit_event(db, c: Ctx, draft: Dict[str, Any]) -> Dict[str, Any]:
    from routes.calendar_routes import FALLBACK_OWNER, _parse_dt_pair

    summary = str(draft.get("summary") or "").strip()
    if not summary:
        raise HTTPException(400, "Event title is required")
    all_day = bool(draft.get("all_day"))
    try:
        start, _ = _parse_dt_pair(str(draft.get("dtstart") or ""))
        if draft.get("dtend"):
            end, _ = _parse_dt_pair(str(draft.get("dtend")))
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    except ValueError:
        raise HTTPException(400, "Event date is not valid")
    if end <= start:
        end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    cal_owner = c.owner or FALLBACK_OWNER
    # A local calendar only: CalDAV calendars need a write-back round trip this endpoint must not block on.
    cal = db.query(CalendarCal).filter(CalendarCal.owner == cal_owner, or_(CalendarCal.source == "local", CalendarCal.source.is_(None))).first()
    if cal is None:
        cal = CalendarCal(id=str(uuid.uuid4()), owner=cal_owner, name="Personal", color="#5b8abf", source="local")
        db.add(cal)
        db.flush()
    ev = CalendarEvent(uid=str(uuid.uuid4()), calendar_id=cal.id, summary=summary[:300], description=str(draft.get("description") or "")[:2000],
                       location=str(draft.get("location") or "")[:200], dtstart=start, dtend=end, all_day=all_day, is_utc=False, rrule="")
    db.add(ev)
    db.commit()
    return {"kind": "event", "id": ev.uid, "label": "Added to your calendar", "open": {"app": "calendar"}}


def _commit_automation(db, c: Ctx, draft: Dict[str, Any], tz_offset: int) -> Dict[str, Any]:
    from src.task_scheduler import compute_next_run

    if draft.get("action") not in (None, "", "daily_brief"):
        raise HTTPException(400, "Quick capture can only create AI-prompt or daily-brief automations")
    if (draft.get("task_type") or "llm") == "action" and draft.get("action") != "daily_brief":
        raise HTTPException(400, "Quick capture can only create AI-prompt or daily-brief automations")
    payload = cap.automation_payload(draft, tz_offset)
    if payload.get("task_type") == "llm" and not str(payload.get("prompt") or "").strip():
        raise HTTPException(400, "Say what the automation should do, e.g. “every weekday at 7am summarize my unread email”")
    if payload.get("task_type") not in ("llm", "action"):
        raise HTTPException(400, "Unsupported automation type")
    if payload.get("output_target") not in ("session", "notification", "email"):
        payload["output_target"] = "session"
    next_run = compute_next_run(payload["schedule"], payload.get("scheduled_time"), payload.get("scheduled_day"), None,
                                cron_expression=payload.get("cron_expression"))
    if next_run is None:
        raise HTTPException(400, "That schedule does not produce a next run")
    name = (payload.get("name") or "").strip() or cap._task_name(payload.get("prompt") or "Automation")
    task = ScheduledTask(
        id=str(uuid.uuid4()), owner=c.owner or None, name=name[:120], prompt=payload.get("prompt"),
        task_type=payload["task_type"], action=payload.get("action"), schedule=payload["schedule"],
        scheduled_time=payload.get("scheduled_time"), scheduled_day=payload.get("scheduled_day"),
        cron_expression=payload.get("cron_expression"), trigger_type="schedule", trigger_counter=0,
        next_run=next_run, status="active", output_target=payload["output_target"],
        notifications_enabled=payload["task_type"] != "action" or payload["output_target"] == "notification",
    )
    db.add(task)
    db.commit()
    return {"kind": "automation", "id": task.id, "label": "Automation created", "next_run": _iso_z(next_run),
            "open": {"app": "automations", "props": {"intent": "show", "id": task.id}}}


def _undo(db, c: Ctx, kind: str, ident: str, item_id: Optional[str]) -> Dict[str, Any]:
    if kind == "todo":
        note = _scoped(db.query(Note), Note, c.owner).filter(Note.id == ident).first()
        if note is None:
            raise HTTPException(404, "Not found")
        items = json.loads(note.items or "[]")
        kept = [i for i in items if not (isinstance(i, dict) and i.get("id") == item_id)]
        note.items = json.dumps(kept)
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(note, "items")
    elif kind == "reminder":
        note = _scoped(db.query(Note), Note, c.owner).filter(Note.id == ident).first()
        if note is None:
            raise HTTPException(404, "Not found")
        db.delete(note)
    elif kind == "event":
        from routes.calendar_routes import FALLBACK_OWNER

        ev = (db.query(CalendarEvent).join(CalendarCal, CalendarEvent.calendar_id == CalendarCal.id)
              .filter(CalendarEvent.uid == ident, CalendarCal.owner == (c.owner or FALLBACK_OWNER)).first())
        if ev is None:
            raise HTTPException(404, "Not found")
        db.delete(ev)
    elif kind == "automation":
        task = _scoped(db.query(ScheduledTask), ScheduledTask, c.owner).filter(ScheduledTask.id == ident).first()
        if task is None:
            raise HTTPException(404, "Not found")
        db.delete(task)
    else:
        raise HTTPException(400, "Unknown kind")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------- request models
class CaptureBody(BaseModel):
    text: str = Field("", max_length=2000)
    kind: Optional[str] = Field(None, max_length=16)       # pin the classification (the Edit step)
    tz_offset: Optional[int] = None
    now: Optional[str] = Field(None, max_length=40)        # naive local ISO; tests and replays only


class CommitBody(BaseModel):
    kind: str = Field(..., max_length=16)
    draft: Dict[str, Any] = Field(default_factory=dict)
    tz_offset: Optional[int] = None


class UndoBody(BaseModel):
    kind: str = Field(..., max_length=16)
    id: str = Field(..., min_length=1, max_length=128)
    item_id: Optional[str] = Field(None, max_length=64)


class FocusBody(BaseModel):
    minutes: float = Field(..., gt=0, le=240)
    label: str = Field("", max_length=120)
    completed: bool = True
    tz_offset: Optional[int] = None


class NotifyBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field("", max_length=600)
    severity: str = Field("info", pattern="^(info|success|warning|error)$")
    key: Optional[str] = Field(None, max_length=128)       # de-duplication: the same key is only recorded once


# --------------------------------------------------------------------------------- router
def setup_os_today_routes() -> APIRouter:
    router = APIRouter(prefix="/api/os", tags=["os-today"], dependencies=[Depends(os_admin_guard)])

    @router.get("/today")
    async def today(request: Request, tz_offset: Optional[int] = None, now: Optional[str] = None):
        c = _ctx(request, tz_offset, now)
        try:
            from services.os_shell import reminders as _rem

            _rem.touch_os_tab()        # an OS page is open and polling: it announces due reminders itself
        except Exception:
            pass
        t0 = time.perf_counter()
        names = list(SECTIONS)
        results = await asyncio.gather(*(_run_section(n, SECTIONS[n], c) for n in names))
        out: Dict[str, Any] = dict(zip(names, results))
        out["summary"] = build_summary(out, c.now_ms)
        out["generated_at"] = c.now_ms
        out["tz_offset"] = c.tz_offset
        out["took_ms"] = round((time.perf_counter() - t0) * 1000)
        return out

    @router.post("/capture")
    async def capture(body: CaptureBody, request: Request):
        c = _ctx(request, body.tz_offset, body.now)
        try:
            res = cap.classify_and_parse(body.text, _local_now_for(c), force=body.kind)
        except cap.CaptureError as e:
            raise HTTPException(400, str(e))
        d = res["draft"]
        res["can_commit"] = not (res["kind"] == "automation" and d.get("needs_prompt"))
        res["kinds"] = list(cap.KINDS)
        return res

    @router.post("/capture/commit")
    async def capture_commit(body: CommitBody, request: Request):
        c = _ctx(request, body.tz_offset)
        if body.kind not in cap.KINDS:
            raise HTTPException(400, "Unknown kind")

        def work():
            db = SessionLocal()
            try:
                if body.kind == "todo":
                    return _commit_todo(db, c, body.draft)
                if body.kind == "reminder":
                    return _commit_reminder(db, c, body.draft)
                if body.kind == "event":
                    return _commit_event(db, c, body.draft)
                return _commit_automation(db, c, body.draft, c.tz_offset)
            except HTTPException:
                db.rollback()
                raise
            except Exception:
                db.rollback()
                logger.exception("capture commit failed")
                raise HTTPException(500, "Could not save that")
            finally:
                db.close()

        return await asyncio.to_thread(work)

    @router.post("/capture/undo")
    async def capture_undo(body: UndoBody, request: Request):
        c = _ctx(request, 0)

        def work():
            db = SessionLocal()
            try:
                return _undo(db, c, body.kind, body.id, body.item_id)
            except HTTPException:
                db.rollback()
                raise
            finally:
                db.close()

        return await asyncio.to_thread(work)

    @router.post("/focus")
    async def focus_log(body: FocusBody, request: Request):
        c = _ctx(request, body.tz_offset)
        store = FocusStore(c.focus_path)
        try:
            entry = await asyncio.to_thread(store.log, c.owner, body.minutes, body.label, body.completed)
        except ValueError as e:
            raise HTTPException(400, str(e))
        stats = await asyncio.to_thread(store.stats, c.owner, c.tz_offset)
        return {"session": entry, **stats}

    @router.get("/focus/stats")
    async def focus_stats(request: Request, tz_offset: Optional[int] = None):
        c = _ctx(request, tz_offset)
        return await asyncio.to_thread(FocusStore(c.focus_path).stats, c.owner, c.tz_offset)

    @router.post("/notify")
    async def notify(body: NotifyBody, request: Request):
        """Add an entry to the OS notification centre (the bell). The same ``key`` is recorded only once, so several
        open tabs reporting the same finished automation don't stack duplicates."""
        from routes.os_routes import _jarvis

        jarvis = _jarvis(request)
        comm = jarvis.subsystems.get("communication")
        ns = getattr(comm, "notification_system", None) if comm else None
        if ns is None:
            raise HTTPException(503, "Notification centre unavailable")
        if body.key:
            for n in ns.notifications:
                if n.get("key") == body.key:
                    return {"ok": True, "duplicate": True, "id": n.get("id")}
        nid = await ns.send_notification(body.title, body.message, body.severity)
        if body.key:
            for n in reversed(ns.notifications):
                if n.get("id") == nid:
                    n["key"] = body.key
                    break
        return {"ok": True, "duplicate": False, "id": nid}

    return router
