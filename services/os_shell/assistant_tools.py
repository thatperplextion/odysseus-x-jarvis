"""Jarvis tools for the daily cycle: automations, to-dos, calendar events and reminders.

These are planner tools (see ``planner.py``) that work on Odysseus's own data, owner-scoped through the
same code the Automations / Notes / Calendar apps use:

* **Read-only** (no approval): ``list_automations``, ``get_agenda``, ``list_todos``.
* **Mutating** (an approval card first, executed only after the user approves): ``create_automation``,
  ``update_automation_status``, ``run_automation``, ``add_todo``, ``complete_todo``, ``create_event``,
  ``create_reminder``.

Rows are created by calling the real route handlers in-process (``POST /api/tasks``, ``POST /api/notes``,
``POST /api/calendar/events`` ... found on ``request.app``), so validation, ``next_run`` computation, owner
stamping and every other side effect are identical to a row made in the UI. Nothing here makes an HTTP call.

Shell automations (``run_local`` / ``ssh_command`` / ``run_script``) are never created by the assistant.
Automations of kind "ai_prompt" run with Odysseus's agent tools, so a prompt that is really a shell command is
refused too (best effort; the approval card always shows the full prompt).

Time handling: the user's *local* time is what people say and what the model reads, so a ``TimeContext``
(clock, timezone) is injected everywhere. The scheduler stores schedules in UTC, exactly like the Tasks UI does,
so schedules are converted at the edge (including the weekday shift when a local time falls on another UTC day).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone, tzinfo
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from .command_guard import check_command

logger = logging.getLogger(__name__)

PERSONAL_READ = frozenset({"list_automations", "get_agenda", "list_todos"})
PERSONAL_WRITE = frozenset({
    "create_automation", "update_automation_status", "run_automation",
    "add_todo", "complete_todo", "create_event", "create_reminder",
})
PERSONAL_TOOLS = PERSONAL_READ | PERSONAL_WRITE

# tool -> {arg: (type, required)}.  ``object`` = a scalar the model may write as text or a number ("day": 1).
PERSONAL_SCHEMAS: Dict[str, Dict[str, Tuple[type, bool]]] = {
    "list_automations": {"query": (str, False)},
    "get_agenda": {"start": (str, False), "end": (str, False), "days": (int, False)},
    "list_todos": {"include_done": (bool, False)},
    "create_automation": {
        "name": (str, True), "kind": (str, True), "prompt": (str, False), "action": (str, False),
        "schedule": (str, True), "time": (str, False), "day": (object, False), "date": (str, False),
        "cron": (str, False), "output_target": (str, False),
    },
    "update_automation_status": {"automation": (str, True), "status": (str, True)},
    "run_automation": {"automation": (str, True)},
    "add_todo": {"text": (str, True), "due": (str, False)},
    "complete_todo": {"ref": (str, False), "text": (str, False)},
    "create_event": {
        "title": (str, True), "start": (str, True), "end": (str, False), "duration_minutes": (int, False),
        "location": (str, False), "all_day": (bool, False),
    },
    "create_reminder": {"text": (str, True), "when": (str, True)},
}

SHELL_ACTIONS = frozenset({"run_local", "ssh_command", "run_script"})
# Not offered to the assistant: they need setup the assistant cannot do (a served model, ...).
NON_ASSISTANT_ACTIONS = frozenset({"cookbook_serve"})
OUTPUT_TARGETS = ("notification", "session", "email")
TODO_LIST_TITLE = "To-do"
_TODO_TITLES = {"to-do", "todo", "to do", "todos", "to-dos", "to-do list", "todo list", "my todos", "my to-dos"}

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

ORGANISER_HINT = re.compile(
    r"\b(automat\w*|schedul\w*|every|daily|weekly|monthly|remind\w*|todos?|to-?dos?|to do|tasks?|calendar|agenda|"
    r"events?|meetings?|appointments?|brief\w*|pause|resume|my day|tomorrow|today|tonight|morning|evening|"
    r"next week|inbox|triage|what'?s on|plan my)\b", re.I)

# Used to keep an AI-prompt automation from being a shell job in disguise.
_SHELLISH = re.compile(
    r"(?:\b(?:run|execute|exec|launch|invoke|start)\b[^.\n]{0,60}(?:`[^`\n]+`|\b(?:command|script|shell|terminal|bash|powershell|cmd|batch)\b))"
    r"|\b(?:rm\s+-\w*[rf]|rmdir\s+/s|del\s+/[sq]|remove-item|taskkill|kill\s+-9|sudo|chmod\s+-r|mkfs|powershell|pwsh|cmd\.exe|"
    r"os\.system|subprocess|ssh\s+\S+@|run_local|ssh_command|run_script)\b"
    # "...using the terminal", "via a shell command", "in PowerShell", "a bash script", "use the command line": the shell named as the means
    r"|\b(?:using|via|through|with|in|from)\s+(?:the\s+|a\s+|an\s+|my\s+)?(?:terminal|shell|command[\s-]?line|command\s+prompt|powershell|pwsh|bash|zsh|cmd)\b"
    r"|\b(?:terminal|shell|bash|zsh|powershell|pwsh|command[\s-]?line|command\s+prompt|cmd)\s+(?:commands?|scripts?|window|session)\b"
    r"|\buse\s+(?:the\s+|a\s+|my\s+)?(?:terminal|shell|command[\s-]?line|powershell|bash)\b"
    # wiping files in bulk is not something an unattended AI prompt should be set up to do
    r"|\b(?:delete|remove|erase|wipe|purge|shred|empty|clear\s+out)\b[^.\n]{0,50}\b(?:all|every|everything|entire|whole)\b[^.\n]{0,50}\b(?:files?|folders?|director(?:y|ies)|drive|disk)\b",
    re.I)


class ToolArgError(ValueError):
    """The model asked for something invalid or not allowed. The message goes back to the model."""


# ====================================================================================== time
@dataclass
class TimeContext:
    """The user's clock and timezone. ``clock`` returns an aware datetime (UTC) and is injected in tests."""

    tz: tzinfo
    tz_name: str = ""
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))

    @classmethod
    def build(cls, hints: Optional[Dict[str, Any]] = None, clock: Optional[Callable[[], datetime]] = None) -> "TimeContext":
        """From what the browser sends (``{"tz": "Asia/Karachi", "offset_min": 300}``); the server's own zone otherwise."""
        hints = hints if isinstance(hints, dict) else {}
        clock = clock or (lambda: datetime.now(timezone.utc))
        name = str(hints.get("tz") or "").strip()
        tz: Optional[tzinfo] = None
        if name and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", name):
            try:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(name)
            except Exception:  # noqa: BLE001 - unknown zone / no tzdata: fall back to the offset
                tz = None
        if tz is None:
            name = ""
            off = hints.get("offset_min")
            if isinstance(off, (int, float)) and not isinstance(off, bool) and -840 <= off <= 840:
                tz = timezone(timedelta(minutes=int(off)))
            else:
                tz = clock().astimezone().tzinfo or timezone.utc
        return cls(tz=tz, tz_name=name, clock=clock)

    def now(self) -> datetime:
        n = self.clock()
        if n.tzinfo is None:
            n = n.replace(tzinfo=timezone.utc)
        return n.astimezone(self.tz).replace(microsecond=0)

    def now_utc(self) -> datetime:
        return self.now().astimezone(timezone.utc)

    def offset_min(self, at: Optional[datetime] = None) -> int:
        at = at or self.now()
        off = at.astimezone(self.tz).utcoffset() or timedelta()
        return int(off.total_seconds() // 60)

    def label(self) -> str:
        off = self.offset_min()
        sign = "+" if off >= 0 else "-"
        hh, mm = divmod(abs(off), 60)
        base = f"UTC{sign}{hh:02d}:{mm:02d}"
        return f"{self.tz_name}, {base}" if self.tz_name else base

    def local(self, naive: datetime) -> datetime:
        return naive.replace(tzinfo=self.tz)

    # -- formatting -------------------------------------------------------------------------------
    def day(self, d: datetime) -> str:
        s = f"{d.strftime('%a')} {d.day} {_MONTHS[d.month - 1]}"
        return s if d.year == self.now().year else f"{s} {d.year}"

    def hm(self, d: datetime) -> str:
        return f"{d.hour:02d}:{d.minute:02d}"

    def when(self, d: datetime, has_time: bool = True) -> str:
        return f"{self.day(d)} {self.hm(d)}" if has_time else self.day(d)

    def span(self, start: datetime, end: datetime, all_day: bool = False) -> str:
        if all_day:
            last = end - timedelta(days=1)
            return f"{self.day(start)} (all day)" if last.date() <= start.date() else f"{self.day(start)} – {self.day(last)} (all day)"
        if start.date() == end.date():
            return f"{self.day(start)} {self.hm(start)}–{self.hm(end)}"
        return f"{self.when(start)} – {self.when(end)}"


_TOD = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?")


def parse_time_of_day(text: str) -> Optional[Tuple[int, int]]:
    t = (text or "").strip().lower()
    if t in ("noon", "midday"):
        return 12, 0
    if t == "midnight":
        return 0, 0
    m = _TOD.fullmatch(t)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "")[:1]
    if minute > 59:
        return None
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm == "p" else 0)
    elif hour > 23:
        return None
    return hour, minute


def _weekday_index(word: str) -> Optional[int]:
    w = (word or "").strip().lower().rstrip(".")
    if len(w) < 3:
        return None
    for i, name in enumerate(WEEKDAYS):
        n = name.lower()
        if n.startswith(w) or (w in ("tues", "thur", "thurs") and n.startswith(w[:3])):
            return i
    return None


def _try_iso(s: str, tc: TimeContext) -> Optional[Tuple[datetime, bool]]:
    c = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c):
        try:
            d = date.fromisoformat(c)
        except ValueError:
            raise ToolArgError(f"{s!r} is not a real date")
        return datetime.combine(d, dtime(0, 0), tzinfo=tc.tz), False
    if re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}", c):
        try:
            dt = datetime.fromisoformat(c.replace("Z", "+00:00"))
        except ValueError:
            raise ToolArgError(f"{s!r} is not a valid date and time")
        dt = dt.replace(tzinfo=tc.tz) if dt.tzinfo is None else dt.astimezone(tc.tz)
        return dt.replace(second=0, microsecond=0), True
    return None


_DAY_WORDS = r"today|tonight|tomorrow|tmrw|yesterday|day after tomorrow|(?:(?:next|this|on)\s+)?[a-z]{3,9}"


def _resolve_day(words: str, today: datetime) -> Optional[Tuple[datetime, bool]]:
    """(local midnight of that day, explicit?) for 'tomorrow', 'next tuesday', 'friday' ... or None."""
    w = words.strip().lower()
    if w in ("today", "tonight"):
        return today, True
    if w in ("tomorrow", "tmrw"):
        return today + timedelta(days=1), True
    if w == "yesterday":
        return today - timedelta(days=1), True
    if w == "day after tomorrow":
        return today + timedelta(days=2), True
    m = re.fullmatch(r"(next|this|on)?\s*([a-z]{3,9})", w)
    if m:
        idx = _weekday_index(m.group(2))
        if idx is not None:
            delta = (idx - today.weekday()) % 7
            if m.group(1) == "next" and delta == 0:
                delta = 7
            return today + timedelta(days=delta), m.group(1) != "this"
    return None


def parse_when(text: str, tc: TimeContext) -> Tuple[datetime, bool]:
    """A local datetime from ISO or a few plain phrases, resolved against the injected clock.

    Returns ``(aware local datetime, has_time)``. Accepts ISO ('2026-10-03T11:00', '2026-10-03', with Z/offset),
    'tomorrow at 11', 'next tuesday 3pm', '9am friday', 'in 2 hours', 'noon'. Anything else is an error that
    tells the model to use ISO.
    """
    s = (text or "").strip()
    if not s:
        raise ToolArgError("a date/time is required")
    iso = _try_iso(s, tc)
    if iso:
        return iso
    now = tc.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    lower = re.sub(r"\s+", " ", s.lower()).strip(" .,")

    m = re.fullmatch(r"in (\d+|an?|half an?) ?(minute|min|hour|hr|day|week)s?(?: from now)?", lower)
    if m:
        n = {"a": 1, "an": 1, "half a": 0.5, "half an": 0.5}.get(m.group(1)) or int(m.group(1))
        unit = {"minute": "minutes", "min": "minutes", "hour": "hours", "hr": "hours", "day": "days", "week": "weeks"}[m.group(2)]
        return (now + timedelta(**{unit: n})).replace(second=0), True

    # "<day> [at] <time>"   /   "<time> [on] <day>"   /   "<day>"   /   "<time>"
    day_part = time_part = None
    m = re.fullmatch(rf"({_DAY_WORDS})(?: (?:at|@) | )?(.*)", lower)
    if m and _resolve_day(m.group(1), today):
        day_part, time_part = m.group(1), m.group(2).strip()
        if time_part.startswith(("at ", "@")):
            time_part = time_part.lstrip("@").removeprefix("at ").strip()
    else:
        m = re.fullmatch(rf"(.+?) (?:on )?({_DAY_WORDS})", lower)
        if m and _resolve_day(m.group(2), today):
            day_part, time_part = m.group(2), m.group(1).strip().removeprefix("at ").strip()
    if day_part is None:
        t = parse_time_of_day(lower.removeprefix("at ").strip())
        if t:
            cand = today.replace(hour=t[0], minute=t[1])
            return (cand if cand > now else cand + timedelta(days=1)), True
    else:
        base, _ = _resolve_day(day_part, today)  # type: ignore[misc]
        if not time_part:
            return base, False
        t = parse_time_of_day(time_part)
        if t:
            cand = base.replace(hour=t[0], minute=t[1])
            plain_weekday = _weekday_index(day_part.split()[-1]) is not None and not day_part.startswith("next")
            if plain_weekday and cand <= now:  # "friday 9am" said on Friday afternoon means next week
                cand += timedelta(days=7)
            return cand, True

    if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", lower):
        try:
            from dateutil import parser as du

            parsed = du.parse(s, default=today.replace(tzinfo=None), fuzzy=False)
            has_time = bool(re.search(r"\d{1,2}:\d{2}|\b\d{1,2}\s*(am|pm)\b", lower))
            return parsed.replace(tzinfo=tc.tz, second=0, microsecond=0), has_time
        except (ValueError, OverflowError):
            pass
    raise ToolArgError(f"I couldn't understand the date/time {text!r}. Use ISO local time, for example 2026-10-03T11:00.")


# ================================================================================ schedules
def _compress(nums: List[int]) -> str:
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"{nums[i]}-{nums[j]}" if j - i >= 2 else ",".join(str(n) for n in nums[i:j + 1]))
        i = j + 1
    return ",".join(out)


_CRON_DOW = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


def _dow_set(field_: str) -> List[int]:
    out: List[int] = []
    for tok in field_.split(","):
        tok = tok.strip().lower()
        m = re.fullmatch(r"([a-z]{3}|\d)(?:-([a-z]{3}|\d))?", tok)
        if not m:
            raise ToolArgError("use plain weekday numbers or names in a cron weekday field (for example 1-5 or mon-fri)")
        a = _CRON_DOW.get(m.group(1), None) if m.group(1).isalpha() else int(m.group(1))
        b = a if m.group(2) is None else (_CRON_DOW.get(m.group(2)) if m.group(2).isalpha() else int(m.group(2)))
        if a is None or b is None or a > 7 or b > 7 or b < a:
            raise ToolArgError("that cron weekday field is not valid")
        out.extend(x % 7 for x in range(a, b + 1))
    return sorted(set(out))


def cron_shift(expr: str, delta_min: int) -> str:
    """Shift a cron's fixed ``minute hour`` by ``delta_min`` minutes (positive = later), moving the weekday when the
    day rolls over. Interval expressions (hour ``*`` or ``*/n``) are returned unchanged."""
    parts = (expr or "").split()
    if len(parts) != 5:
        raise ToolArgError("a cron expression needs 5 fields: minute hour day-of-month month weekday")
    minute, hour, dom, mon, dow = parts
    if hour == "*" or hour.startswith("*/"):
        return " ".join(parts)
    if not (re.fullmatch(r"\d{1,2}", minute) and re.fullmatch(r"\d{1,2}(,\d{1,2})*", hour)):
        raise ToolArgError("for a cron schedule use a fixed time like '30 7 * * 1-5' or an interval like '*/30 * * * *'")
    m0, hours = int(minute), [int(x) for x in hour.split(",")]
    if m0 > 59 or any(h > 23 for h in hours):
        raise ToolArgError("that cron time is out of range")
    shifts, new_hours, new_min = set(), [], m0
    for h in hours:
        shift, rem = divmod(h * 60 + m0 + delta_min, 1440)
        shifts.add(shift)
        new_hours.append(rem // 60)
        new_min = rem % 60
    if len(shifts) > 1:
        raise ToolArgError("those times fall on different days in UTC; create one automation per time instead")
    shift = shifts.pop()
    if shift:
        if dom != "*" or mon != "*":
            raise ToolArgError("a date-specific cron at that time falls on another UTC day; use a daily, weekly or monthly schedule")
        if dow != "*":
            dow = _compress([(d + shift) % 7 for d in _dow_set(dow)])
    return f"{new_min} {','.join(str(h) for h in sorted(set(new_hours)))} {dom} {mon} {dow}"


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _next_local(tc: TimeContext, h: int, m: int, weekday: Optional[int] = None, dom: Optional[int] = None) -> datetime:
    """The next local occurrence (strictly after now) of a wall-clock time, optionally on a weekday / day of month."""
    now = tc.now()
    base = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if weekday is not None:
        cand = base + timedelta(days=(weekday - base.weekday()) % 7)
        return cand if cand > now else cand + timedelta(days=7)
    if dom is not None:
        for add in range(0, 14):
            y, mo = divmod(base.month - 1 + add, 12)
            y, mo = base.year + y, mo + 1
            try:
                cand = base.replace(year=y, month=mo, day=dom)
            except ValueError:
                continue
            if cand > now:
                return cand
        raise ToolArgError("that day of the month does not come up soon")
    return base if base > now else base + timedelta(days=1)


def build_schedule(a: Dict[str, Any], tc: TimeContext) -> Dict[str, Any]:
    """Validate a schedule given in the user's local time and return the scheduler fields (UTC, as the Tasks UI
    stores them), a readable description, the (local) next run and a compact local summary."""
    kind = str(a.get("schedule") or "").strip().lower()
    kind = {"day": "daily", "every day": "daily", "everyday": "daily", "week": "weekly", "every week": "weekly",
            "month": "monthly", "every month": "monthly", "one-time": "once", "one time": "once", "oneoff": "once",
            "one-off": "once", "interval": "cron", "weekdays": "cron"}.get(kind, kind)
    if kind not in ("daily", "weekly", "monthly", "once", "cron"):
        raise ToolArgError("schedule must be one of: daily, weekly, monthly, once, cron")
    fields: Dict[str, Any] = {"schedule": kind, "scheduled_time": "09:00", "scheduled_day": None,
                              "scheduled_date": None, "cron_expression": None}
    tod = None
    if a.get("time") not in (None, ""):
        tod = parse_time_of_day(str(a["time"]))
        if tod is None:
            raise ToolArgError(f"time {a['time']!r} is not a time of day; use HH:MM (24 hour, local)")
    h, m = tod if tod else (9, 0)

    if kind == "daily":
        fields["scheduled_time"] = _next_local(tc, h, m).astimezone(timezone.utc).strftime("%H:%M")
        words = f"every day at {_hhmm(h, m)}"
    elif kind == "weekly":
        day = a.get("day")
        idx = _weekday_index(str(day)) if day not in (None, "") and not str(day).strip().lstrip("-").isdigit() else None
        if idx is None and day not in (None, "") and str(day).strip().isdigit() and 0 <= int(str(day)) <= 6:
            idx = int(str(day))                            # 0 = Monday, like the scheduler
        if idx is None:
            raise ToolArgError("a weekly schedule needs 'day' (monday ... sunday)")
        nxt = _next_local(tc, h, m, weekday=idx)
        utc = nxt.astimezone(timezone.utc)
        fields.update(scheduled_time=utc.strftime("%H:%M"), scheduled_day=utc.weekday())
        words = f"every {WEEKDAYS[idx]} at {_hhmm(h, m)}"
    elif kind == "monthly":
        try:
            dom = int(str(a.get("day", "")).strip())
        except ValueError:
            dom = 0
        if not 1 <= dom <= 31:
            raise ToolArgError("a monthly schedule needs 'day' (1-31)")
        nxt = _next_local(tc, h, m, dom=dom)
        utc = nxt.astimezone(timezone.utc)
        if utc.day != dom:
            raise ToolArgError("at that time of day the UTC date falls on a different day of the month; choose another time or day")
        fields.update(scheduled_time=utc.strftime("%H:%M"), scheduled_day=dom)
        words = f"on day {dom} of every month at {_hhmm(h, m)}"
    elif kind == "once":
        raw = a.get("date") or ""
        if not str(raw).strip():
            raise ToolArgError("a one-time schedule needs 'date' (ISO local date and time)")
        when, has_time = parse_when(str(raw), tc)
        if not has_time:
            when = when.replace(hour=h, minute=m)
        if when <= tc.now():
            raise ToolArgError(f"{tc.when(when)} has already passed")
        utc = when.astimezone(timezone.utc)
        fields.update(scheduled_time=utc.strftime("%H:%M"), scheduled_date=utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z")
        words = f"once on {tc.when(when)}"
    else:  # cron: written in local time
        expr = re.sub(r"\s+", " ", str(a.get("cron") or "").strip())
        if not expr:
            raise ToolArgError("a cron schedule needs 'cron' (5 fields, local time)")
        try:
            from croniter import croniter

            if not croniter.is_valid(expr):
                raise ValueError
        except ImportError:  # pragma: no cover
            pass
        except ValueError:
            raise ToolArgError(f"{expr!r} is not a valid cron expression")
        utc_expr = cron_shift(expr, -tc.offset_min())
        fields.update(scheduled_time=None, cron_expression=utc_expr)
        words = cron_words(expr)

    next_utc = _next_run_utc(fields, tc)
    if next_utc is None:
        raise ToolArgError("that schedule never fires")
    return {"fields": fields, "words": words, "next_run": next_utc.astimezone(tc.tz)}


def _next_run_utc(fields: Dict[str, Any], tc: TimeContext) -> Optional[datetime]:
    """Same function the create route uses, but against the injected clock. Returns an aware UTC datetime."""
    from src.task_scheduler import compute_next_run

    sched_date = None
    if fields.get("scheduled_date"):
        sched_date = datetime.fromisoformat(fields["scheduled_date"].replace("Z", "+00:00")).replace(tzinfo=None)
    after = tc.now_utc().replace(tzinfo=None)
    nxt = compute_next_run(fields["schedule"], fields.get("scheduled_time"), fields.get("scheduled_day"), sched_date,
                           after=after, cron_expression=fields.get("cron_expression"))
    return nxt.replace(tzinfo=timezone.utc) if nxt else None


def cron_words(expr: str) -> str:
    """A cron (already in local time) in words for the common shapes; the raw expression otherwise."""
    p = (expr or "").split()
    if len(p) != 5:
        return f"cron {expr}"
    minute, hour, dom, mon, dow = p
    m = re.fullmatch(r"\*/(\d+)", minute)
    if m and hour == "*" and dom == mon == dow == "*":
        return "every minute" if m.group(1) == "1" else f"every {m.group(1)} minutes"
    if minute == "0" and hour == "*" and dom == mon == dow == "*":
        return "every hour"
    m = re.fullmatch(r"\*/(\d+)", hour)
    if minute.isdigit() and m and dom == mon == dow == "*":
        every = "every hour" if m.group(1) == "1" else f"every {m.group(1)} hours"
        return every + (f" at :{int(minute):02d}" if minute != "0" else "")
    if minute.isdigit() and re.fullmatch(r"\d{1,2}(,\d{1,2})*", hour) and dom == "*" and mon == "*":
        times = " and ".join(_hhmm(int(x), int(minute)) for x in hour.split(","))
        if dow == "*":
            return f"every day at {times}"
        try:
            days = _dow_set(dow)
        except ToolArgError:
            return f"cron {expr}"
        if days == [1, 2, 3, 4, 5]:
            return f"every weekday at {times}"
        if days == [0, 6]:
            return f"every weekend day at {times}"
        names = [WEEKDAYS[(d - 1) % 7] for d in days]
        return f"every {', '.join(names)} at {times}"
    return f"cron {expr}"


def schedule_words(t: Dict[str, Any], tc: TimeContext) -> str:
    """A stored task (UTC fields) described in the user's local time."""
    trig = t.get("trigger_type") or "schedule"
    if trig == "event":
        n = int(t.get("trigger_count") or 1)
        return f"after every {n} {(t.get('trigger_event') or 'event').replace('_', ' ')} event{'s' if n != 1 else ''}"
    if trig == "webhook":
        return "when its webhook is called"
    sched, st = t.get("schedule"), t.get("scheduled_time")
    off = tc.offset_min()
    try:
        if sched == "once" and t.get("scheduled_date"):
            d = datetime.fromisoformat(str(t["scheduled_date"]).replace("Z", "+00:00"))
            d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
            return f"once on {tc.when(d.astimezone(tc.tz))}"
        if sched == "cron" and t.get("cron_expression"):
            return cron_words(cron_shift(t["cron_expression"], off))
        if sched in ("daily", "weekly", "monthly") and st:
            uh, um = (int(x) for x in str(st).split(":")[:2])
            shift, rem = divmod(uh * 60 + um + off, 1440)
            lh, lm = rem // 60, rem % 60
            if sched == "daily":
                return f"every day at {_hhmm(lh, lm)}"
            if sched == "weekly":
                utc_day = int(t.get("scheduled_day") or 0)
                return f"every {WEEKDAYS[(utc_day + shift) % 7]} at {_hhmm(lh, lm)}"
            return f"on day {int(t.get('scheduled_day') or 1) + shift} of every month at {_hhmm(lh, lm)}"
    except (ValueError, TypeError, ToolArgError):
        pass
    return sched or "no schedule"


def looks_like_shell_job(prompt: str) -> bool:
    """Best-effort: is this 'AI prompt' really a request to run a command or script?"""
    reason = check_command(prompt)
    return bool(reason and reason.startswith("blocked")) or bool(_SHELLISH.search(prompt or ""))


def _iso_local(d: datetime) -> str:
    return d.replace(microsecond=0).isoformat()


def _clip(s: Any, n: int) -> str:
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _clean_text(s: str, limit: int, what: str) -> str:
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(s or "")).strip()
    t = re.sub(r"[ \t]+", " ", t)
    if not t:
        raise ToolArgError(f"{what} is required")
    if len(t) > limit:
        raise ToolArgError(f"{what} is too long (max {limit} characters)")
    return t


# ================================================================================== the tools
def _walk_routes(routes, prefix: str = ""):
    """(full path, route) for every API route, including routers included into the app. Newer FastAPI keeps an
    included router as one object (``original_router`` + ``include_context``) instead of flattening it."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            extra = getattr(getattr(r, "include_context", None), "prefix", "") or ""
            yield from _walk_routes(inner.routes, prefix + extra)
        elif hasattr(r, "endpoint"):
            yield prefix + (getattr(r, "path", "") or ""), r


class PersonalTools:
    """The owner-scoped bridge from planner actions to Odysseus's tasks, notes and calendar."""

    def __init__(self, request, tc: TimeContext):
        self.request = request
        self.tc = tc
        self._eps: Dict[Tuple[str, str], Callable] = {}

    # ------------------------------------------------------------------------------ plumbing
    def _ep(self, method: str, path: str) -> Callable:
        key = (method, path)
        if key not in self._eps:
            for full_path, r in _walk_routes(getattr(self.request.app, "routes", [])):
                if full_path == path and method in (getattr(r, "methods", None) or ()):
                    self._eps[key] = r.endpoint
                    break
            else:
                raise ToolArgError(f"{method} {path} is not available on this server")
        return self._eps[key]

    async def _call(self, fn: Callable, *args, **kwargs):
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return await asyncio.to_thread(fn, *args, **kwargs)
        except HTTPException as e:
            raise ToolArgError(str(e.detail))

    def _mods(self):
        from routes import calendar_routes, note_routes, task_routes

        return task_routes, note_routes, calendar_routes

    def _task_user(self):
        from src.auth_helpers import get_current_user

        return get_current_user(self.request)

    def _note_user(self):
        from src.auth_helpers import require_user

        try:
            return require_user(self.request) or None
        except HTTPException as e:
            raise ToolArgError(str(e.detail))

    # --------------------------------------------------------------------- data (sync, worker thread)
    def _tasks_sync(self) -> List[Dict[str, Any]]:
        tr = self._mods()[0]
        user = self._task_user()
        db = tr.SessionLocal()
        try:
            q = db.query(tr.ScheduledTask)
            if user:
                q = q.filter(tr.ScheduledTask.owner == user)
            return [tr._task_to_dict(t) for t in q.order_by(tr.ScheduledTask.created_at.desc()).all()]
        finally:
            db.close()

    def _notes_sync(self, *, with_due: bool = False) -> List[Dict[str, Any]]:
        nr = self._mods()[1]
        user = self._note_user()
        db = nr.SessionLocal()
        try:
            q = db.query(nr.Note).filter(nr.Note.archived == False)  # noqa: E712
            if user is not None:
                q = q.filter(nr.Note.owner == user)
            if with_due:
                q = q.filter(nr.Note.due_date.isnot(None), nr.Note.due_date != "")
            else:
                q = q.filter(nr.Note.note_type.in_(("checklist", "todo")))
            return [nr._note_to_dict(n) for n in q.order_by(nr.Note.pinned.desc(), nr.Note.updated_at.desc()).limit(500).all()]
        finally:
            db.close()

    def _todos_sync(self, include_done: bool = False) -> List[Dict[str, Any]]:
        out = []
        for n in self._notes_sync():
            if n.get("label") == "calendar" or n.get("source") == "calendar":
                continue                                       # calendar reminders live in the agenda
            for i, it in enumerate(n.get("items") or []):
                if not isinstance(it, dict) or not str(it.get("text") or "").strip():
                    continue
                done = bool(it.get("done") or it.get("checked"))
                if done and not include_done:
                    continue
                out.append({"ref": f"{n['id'][:8]}#{i}", "note_id": n["id"], "index": i, "text": str(it["text"]).strip(),
                            "done": done, "list": n.get("title") or "", "due": n.get("due_date")})
        return out[:200]

    # ------------------------------------------------------------------------------- formatting
    def _local_dt(self, raw: Any) -> Optional[datetime]:
        """A stored UTC-naive / aware ISO string as aware local time."""
        if not raw:
            return None
        try:
            d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d).astimezone(self.tc.tz)

    def _task_view(self, t: Dict[str, Any]) -> Dict[str, Any]:
        nxt, last = self._local_dt(t.get("next_run")), self._local_dt(t.get("last_run"))
        kind = t.get("action") if t.get("task_type") == "action" else ("research" if t.get("task_type") == "research" else "ai prompt")
        return {
            "id": t["id"], "name": t.get("name") or "(unnamed)", "status": t.get("status") or "active",
            "schedule": schedule_words(t, self.tc), "kind": kind or "ai prompt", "builtin": bool(t.get("is_builtin")),
            "next_run": self.tc.when(nxt) if nxt and t.get("status") == "active" else "",
            "last_run": self.tc.when(last) if last else "", "runs": int(t.get("run_count") or 0),
            "output": t.get("output_target") or "",
        }

    # --------------------------------------------------------------------------------- context
    async def context(self, message: str) -> str:
        """A compact list of the user's automations, only when the request is about their day. (To-dos and the agenda
        are not listed here: the model fetches them with list_todos / get_agenda so the user gets a card.)"""
        if not ORGANISER_HINT.search(message or ""):
            return ""
        try:
            tasks = await asyncio.to_thread(self._tasks_sync)
        except Exception:  # noqa: BLE001 - context is a convenience, never a reason to fail the turn
            return ""
        mine = [t for t in tasks if not t.get("is_builtin")] + [t for t in tasks if t.get("is_builtin")]
        if not mine:
            return ""
        lines = ["Automations (id | name | status | when | kind):"]
        for t in mine[:15]:
            v = self._task_view(t)
            aka = self._builtin_notes(t) if v["builtin"] else ""
            lines.append(f"- {v['id'][:8]} | {_clip(v['name'], 60)} | {v['status']} | {v['schedule']} | {v['kind']}{f' (built-in: {aka})' if v['builtin'] else ''}")
        if len(mine) > 15:
            lines.append(f"… and {len(mine) - 15} more (use list_automations)")
        return "\n".join(lines)

    def _builtin_notes(self, t: Dict[str, Any]) -> str:
        """What a built-in automation does and its older names, so "inbox triage" can be tied to "Email Tags"."""
        try:
            from src.builtin_actions import BUILTIN_ACTION_INFO
            from src.task_scheduler import HOUSEKEEPING_DEFAULTS

            desc = _clip(BUILTIN_ACTION_INFO.get(t.get("action") or "", ""), 70).rstrip(".")
            aka = (HOUSEKEEPING_DEFAULTS.get(t.get("action") or "") or {}).get("legacy_names") or []
            return "; ".join(x for x in (desc, ("also called " + ", ".join(aka)) if aka else "") if x)
        except Exception:  # noqa: BLE001
            return ""

    # ----------------------------------------------------------------------------------- reads
    async def read(self, action: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Run a read-only tool; returns (text for the model, card for the UI)."""
        t, a = action["tool"], action["args"]
        try:
            if t == "list_automations":
                return await self._list_automations(a)
            if t == "list_todos":
                return await self._list_todos(a)
            if t == "get_agenda":
                return await self._agenda(a)
        except ToolArgError as e:
            return f"ERROR: {e}", None
        except Exception as e:  # noqa: BLE001 - a database hiccup is a tool error the model can report, not a crash
            logger.warning("assistant tool %s failed: %s", t, e)
            return f"ERROR: {t} failed ({type(e).__name__}); tell the user it could not be read right now", None
        return f"ERROR: unsupported tool {t}", None

    async def _list_automations(self, a):
        tasks = await asyncio.to_thread(self._tasks_sync)
        q = str(a.get("query") or "").strip().lower()
        views = [self._task_view(t) for t in tasks]
        if q:
            views = [v for v in views if q in v["name"].lower() or q in v["kind"].lower() or all(w in (v["name"] + " " + v["kind"]).lower() for w in q.split())]
        views.sort(key=lambda v: (v["builtin"], v["status"] != "active"))
        if not views:
            return "No automations found." + (" (filter: " + q + ")" if q else ""), {"type": "automations", "items": [], "query": q}
        lines = [f"- [{v['id'][:8]}] {v['name']} - {v['status']} - {v['schedule']} - kind: {v['kind']}"
                 + (f" - next run {v['next_run']}" if v["next_run"] else "") + (f" - last run {v['last_run']}" if v["last_run"] else "")
                 + (" - built-in" if v["builtin"] else "") for v in views[:40]]
        return "\n".join(lines), {"type": "automations", "items": views[:40], "query": q}

    async def _list_todos(self, a):
        todos = await asyncio.to_thread(self._todos_sync, bool(a.get("include_done")))
        if not todos:
            return "No open to-dos.", {"type": "todos", "items": []}
        lines = [f"- [{t['ref']}] {'(done) ' if t['done'] else ''}{t['text']}" for t in todos[:60]]
        return "\n".join(lines), {"type": "todos", "items": [{k: t[k] for k in ("ref", "text", "done", "list")} for t in todos[:60]]}

    def _agenda_window(self, a) -> Tuple[datetime, datetime]:
        tc = self.tc
        start, has_time = parse_when(str(a.get("start") or "today"), tc)
        if not has_time:
            start = start.replace(hour=0, minute=0)
        if a.get("end"):
            end, end_time = parse_when(str(a["end"]), tc)
            if not end_time:
                end = end + timedelta(days=1)
        else:
            days = max(1, min(int(a.get("days") or 1), 31))
            end = start.replace(hour=0, minute=0) + timedelta(days=days)
        if end <= start:
            raise ToolArgError("the end of the range must be after its start")
        if end - start > timedelta(days=31):
            raise ToolArgError("ranges are limited to 31 days")
        return start, end

    async def _agenda(self, a):
        tc = self.tc
        start, end = self._agenda_window(a)
        _, _, cr = self._mods()
        list_events = self._ep("GET", "/api/calendar/events")
        naive = lambda d: d.replace(tzinfo=None).isoformat()  # noqa: E731 - the Calendar UI queries with local wall-clock times
        res = await self._call(list_events, self.request, naive(start), naive(end))
        items: List[Dict[str, Any]] = []
        for ev in res.get("events", []):
            s, e = self._event_dt(ev.get("dtstart")), self._event_dt(ev.get("dtend"))
            if s is None:
                continue
            all_day = bool(ev.get("all_day"))
            items.append({"kind": "event", "start": s, "end": e or s, "all_day": all_day, "title": ev.get("summary") or "(no title)",
                          "location": ev.get("location") or ""})
        for n in await asyncio.to_thread(self._notes_sync, with_due=True):
            if n.get("label") == "calendar" or n.get("source") == "calendar":
                continue
            due = self._due_dt(n.get("due_date"))
            if due and re.search(r"T\d{2}:\d{2}", str(n.get("due_date"))) and start <= due < end:
                items.append({"kind": "reminder", "start": due, "end": due, "all_day": False, "title": n.get("title") or "(reminder)", "location": ""})
        items.sort(key=lambda i: (i["start"], i["kind"]))
        days: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            if it["all_day"]:
                label = "all day"
            elif it["kind"] == "reminder" or it["end"] <= it["start"]:
                label = tc.hm(it["start"])
            else:
                label = f"{tc.hm(it['start'])}–{tc.hm(it['end'])}"
            days.setdefault(tc.day(it["start"]), []).append({"time": label, "title": it["title"], "kind": it["kind"], "location": it["location"]})
        rng = tc.day(start) if (end - start) <= timedelta(days=1) and start.hour == 0 else f"{tc.day(start)} – {tc.day(end - timedelta(seconds=1))}"
        if not items:
            return f"Nothing is scheduled for {rng}.", {"type": "agenda", "range": rng, "days": []}
        lines = [f"Agenda for {rng} ({len(items)} item{'s' if len(items) != 1 else ''}):"]
        for label, rows in days.items():
            lines.append(label)
            lines += [f"- {r['time']} {r['title']} [{r['kind']}]" + (f" @ {r['location']}" if r["location"] else "") for r in rows]
        return "\n".join(lines), {"type": "agenda", "range": rng, "days": [{"label": k, "items": v} for k, v in days.items()]}

    def _event_dt(self, raw: Any) -> Optional[datetime]:
        if not raw:
            return None
        s = str(raw)
        try:
            if len(s) == 10:
                return datetime.combine(date.fromisoformat(s), dtime(0, 0), tzinfo=self.tc.tz)
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d.astimezone(self.tc.tz) if d.tzinfo else d.replace(tzinfo=self.tc.tz)

    def _due_dt(self, raw: Any) -> Optional[datetime]:
        if not raw:
            return None
        try:
            d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        return d.astimezone(self.tc.tz) if d.tzinfo else d.replace(tzinfo=self.tc.tz)

    # ---------------------------------------------------------------------------------- prepare
    async def prepare(self, action: Dict[str, Any]) -> None:
        """Resolve a mutating action into a fixed plan plus a human-readable preview. Raises ToolArgError."""
        t, a = action["tool"], action["args"]
        fn = getattr(self, f"_prepare_{t}")
        try:
            plan, preview = await fn(a)
        except ToolArgError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("assistant tool %s could not be prepared: %s", t, e)
            raise ToolArgError(f"{t} failed ({type(e).__name__}); tell the user it could not be done right now")
        preview.setdefault("notes", [])
        preview.setdefault("warnings", [])
        action["plan"] = plan
        action["preview"] = preview
        action["label"] = preview["label"]

    async def _prepare_create_automation(self, a):
        tc = self.tc
        name = _clean_text(a["name"], 80, "name")
        kind = {"ai_prompt": "ai_prompt", "prompt": "ai_prompt", "llm": "ai_prompt", "ai": "ai_prompt", "ai prompt": "ai_prompt",
                "action": "action", "builtin": "action", "built-in": "action"}.get(str(a["kind"]).strip().lower())
        if kind is None:
            raise ToolArgError("kind must be 'ai_prompt' (an instruction the AI runs on a schedule) or 'action' (a built-in job)")
        fields: Dict[str, Any] = {"name": name, "trigger_type": "schedule"}
        rows: List[List[str]] = []
        notes: List[str] = []
        if kind == "ai_prompt":
            if str(a.get("action") or "").strip():
                raise ToolArgError("an ai_prompt automation takes 'prompt', not 'action'")
            prompt = _clean_text(a.get("prompt") or "", 4000, "prompt")
            if looks_like_shell_job(prompt):
                raise ToolArgError("refused: automations that run shell commands or scripts can only be created by the user in the "
                                   "Automations app. Tell the user that, and offer a non-shell alternative.")
            fields.update(task_type="llm", prompt=prompt)
            run_label = "an AI prompt"
            rows.append(["Prompt", _clip(prompt, 600)])
            notes.append("AI automations can use Odysseus tools each time they run.")
        else:
            action_name = str(a.get("action") or "").strip()
            if not action_name:
                raise ToolArgError("an action automation needs 'action'")
            if action_name in SHELL_ACTIONS:
                raise ToolArgError(f"refused: '{action_name}' runs shell commands or scripts, so it can only be created by the user in "
                                   "the Automations app. Tell the user that.")
            allowed, info = self._allowed_actions()
            if action_name not in allowed:
                raise ToolArgError(f"unknown action {action_name!r}; available: " + ", ".join(sorted(allowed)))
            fields.update(task_type="action", action=action_name)
            run_label = f"runs {action_name}"
            rows.append(["Runs", f"{action_name} — {_clip(info.get(action_name, ''), 140)}".rstrip(" —")])
        # Built-in actions never raise a pop-up notification in the scheduler (only AI-prompt tasks do), so their
        # useful default is a chat session; an AI prompt defaults to a notification.
        target = str(a.get("output_target") or ("session" if kind == "action" else "notification")).strip().lower()
        if target not in OUTPUT_TARGETS:
            raise ToolArgError("output_target must be one of: " + ", ".join(OUTPUT_TARGETS))
        if kind == "action" and target == "notification":
            target = "session"
            notes.append("Built-in actions can't show pop-up notifications, so the result is saved to a chat session (and the run history).")
        fields["output_target"] = target
        sched = build_schedule(a, tc)
        fields.update(sched["fields"])
        for t in await asyncio.to_thread(self._tasks_sync):
            if (t.get("name") or "").strip().lower() == name.lower():
                raise ToolArgError(f"an automation called {name!r} already exists ({t.get('status')}). Ask the user whether to "
                                   "resume or run it, or pick a different name.")
        result = {"notification": "a notification", "session": "a chat session", "email": "an email"}[target]
        rows = [["When", sched["words"]]] + rows + [["Result", f"as {result}"]]
        if sched["next_run"]:
            rows.insert(1, ["Next run", tc.when(sched["next_run"])])
        label = f"Create automation '{name}' — {sched['words']} — {run_label} — result as {result}"
        return ({"task": fields},
                {"label": label, "kind": "automation", "verb": "Create automation", "title": name, "rows": rows, "notes": notes})

    def _allowed_actions(self) -> Tuple[set, Dict[str, str]]:
        try:
            from src.builtin_actions import BUILTIN_ACTION_INFO, BUILTIN_ACTIONS

            allowed = {k for k in BUILTIN_ACTIONS if k in BUILTIN_ACTION_INFO} - SHELL_ACTIONS - NON_ASSISTANT_ACTIONS
            return allowed, dict(BUILTIN_ACTION_INFO)
        except Exception:  # noqa: BLE001
            return {"daily_brief"}, {"daily_brief": "Build a morning digest"}

    def _resolve_task(self, tasks: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        q = (query or "").strip()
        if not q:
            raise ToolArgError("which automation? give its id or name")
        low = q.lower()
        exact = [t for t in tasks if t["id"] == q or (len(q) >= 6 and t["id"].lower().startswith(low))]
        if len(exact) == 1:
            return exact[0]
        names = [t for t in tasks if (t.get("name") or "").strip().lower() == low]
        if len(names) == 1:
            return names[0]
        words = {w for w in re.findall(r"[a-z0-9]{3,}", low) if w not in ("the", "automation", "task", "job", "run", "and", "for", "my")}
        scored = []
        for t in tasks:
            hay = " ".join([t.get("name") or "", t.get("action") or "", t.get("prompt") or "" if t.get("task_type") != "action" else ""]).lower()
            try:
                from src.task_scheduler import HOUSEKEEPING_DEFAULTS

                hay += " " + " ".join((HOUSEKEEPING_DEFAULTS.get(t.get("action") or "") or {}).get("legacy_names") or []).lower()
                from src.builtin_actions import BUILTIN_ACTION_INFO

                hay += " " + BUILTIN_ACTION_INFO.get(t.get("action") or "", "").lower()
            except Exception:  # noqa: BLE001
                pass
            score = (3 if low in hay else 0) + sum(1 for w in words if w in hay)
            if score:
                scored.append((score, t))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            raise ToolArgError(f"no automation matches {q!r}. Use list_automations to see them.")
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            options = "; ".join(f"{t['name']} ({t['id'][:8]})" for _, t in scored[:5])
            raise ToolArgError(f"{q!r} matches more than one automation: {options}. Ask the user which one.")
        return scored[0][1]

    async def _prepare_update_automation_status(self, a):
        status = {"pause": "paused", "paused": "paused", "stop": "paused", "disable": "paused", "off": "paused",
                  "resume": "active", "active": "active", "start": "active", "enable": "active", "on": "active", "unpause": "active"
                  }.get(str(a["status"]).strip().lower())
        if status is None:
            raise ToolArgError("status must be 'paused' or 'active'")
        task = self._resolve_task(await asyncio.to_thread(self._tasks_sync), a["automation"])
        if (task.get("status") or "active") == status:
            raise ToolArgError(f"'{task['name']}' is already {status}.")
        if status == "active" and task.get("status") == "completed" and (task.get("schedule") == "once"):
            raise ToolArgError(f"'{task['name']}' was a one-time automation that has already run.")
        verb = "Pause" if status == "paused" else "Resume"
        v = self._task_view(task)
        rows = [["Schedule", v["schedule"]]] + ([["Last run", v["last_run"]]] if v["last_run"] else [])
        return ({"id": task["id"], "name": task["name"], "status": status},
                {"label": f"{verb} automation '{task['name']}' — {v['schedule']}", "kind": "automation", "verb": f"{verb} automation",
                 "title": task["name"], "rows": rows})

    async def _prepare_run_automation(self, a):
        task = self._resolve_task(await asyncio.to_thread(self._tasks_sync), a["automation"])
        if task.get("status") == "paused":
            note = ["It is paused, so it will only run this once."]
        else:
            note = []
        v = self._task_view(task)
        result = {"notification": "a notification", "session": "a chat session", "email": "an email"}.get(v["output"], v["output"] or "its usual place")
        return ({"id": task["id"], "name": task["name"]},
                {"label": f"Run automation '{task['name']}' now — result as {result}", "kind": "automation", "verb": "Run automation now",
                 "title": task["name"], "rows": [["Runs", v["kind"]], ["Result", f"as {result}"]], "notes": note})

    async def _prepare_add_todo(self, a):
        tc = self.tc
        text = _clean_text(a["text"], 300, "text")
        for t in await asyncio.to_thread(self._todos_sync, False):
            if t["text"].strip().lower() == text.lower():
                raise ToolArgError(f"'{text}' is already on the to-do list.")
        due_iso = None
        rows = [["List", TODO_LIST_TITLE]]
        label = f"Add to-do '{text}'"
        if a.get("due"):
            due, has_time = parse_when(str(a["due"]), tc)
            if not has_time:
                due = due.replace(hour=9, minute=0)
            if due <= tc.now():
                raise ToolArgError(f"{tc.when(due)} has already passed")
            due_iso = _iso_local(due)
            rows.append(["Reminder", tc.when(due)])
            label += f" — reminder {tc.when(due)}"
        return ({"text": text, "due": due_iso}, {"label": label, "kind": "todo", "verb": "Add to-do", "title": text, "rows": rows})

    async def _prepare_complete_todo(self, a):
        ref, text = str(a.get("ref") or "").strip(), str(a.get("text") or "").strip()
        if not ref and not text:
            raise ToolArgError("give the to-do's 'ref' (from list_todos) or its 'text'")
        todos = await asyncio.to_thread(self._todos_sync, False)
        match = None
        if ref:
            match = next((t for t in todos if t["ref"] == ref or t["ref"].startswith(ref)), None)
            if match is None and not text:
                raise ToolArgError(f"no open to-do with ref {ref!r}. Use list_todos.")
        if match is None:
            low = text.lower()
            hits = [t for t in todos if t["text"].lower() == low] or [t for t in todos if low in t["text"].lower() or t["text"].lower() in low]
            if not hits:
                raise ToolArgError(f"no open to-do matches {text!r}. Use list_todos.")
            if len(hits) > 1:
                raise ToolArgError(f"{text!r} matches several to-dos: " + "; ".join(f"{t['text']} [{t['ref']}]" for t in hits[:5]) + ". Ask the user which one.")
            match = hits[0]
        return ({"note_id": match["note_id"], "index": match["index"], "text": match["text"]},
                {"label": f"Mark to-do done: '{match['text']}'", "kind": "todo", "verb": "Mark to-do done", "title": match["text"],
                 "rows": [["List", match["list"] or TODO_LIST_TITLE]]})

    async def _prepare_create_event(self, a):
        tc = self.tc
        title = _clean_text(a["title"], 200, "title")
        start, has_time = parse_when(str(a["start"]), tc)
        all_day = bool(a.get("all_day"))
        location = _clip(a.get("location"), 200) if a.get("location") else ""
        if all_day or (not has_time and not a.get("end")):
            all_day = True
            start = start.replace(hour=0, minute=0)
            end = start + timedelta(days=1)
            if a.get("end"):
                e, e_time = parse_when(str(a["end"]), tc)
                end = e.replace(hour=0, minute=0) + timedelta(days=1)
            ds, de = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        else:
            if not has_time:
                raise ToolArgError("an event with an end needs a start time (ISO local date and time)")
            if a.get("end"):
                end, end_time = parse_when(str(a["end"]), tc)
                if not end_time:
                    raise ToolArgError("the event end needs a time (ISO local date and time)")
            else:
                minutes = int(a["duration_minutes"]) if a.get("duration_minutes") is not None else 60
                if not 1 <= minutes <= 24 * 60:
                    raise ToolArgError("duration_minutes must be between 1 and 1440")
                end = start + timedelta(minutes=minutes)
            ds, de = start.strftime("%Y-%m-%dT%H:%M:00"), end.strftime("%Y-%m-%dT%H:%M:00")
        if end <= start:
            raise ToolArgError("the event must end after it starts")
        if start < tc.now() - timedelta(minutes=5) and not all_day:
            raise ToolArgError(f"{tc.when(start)} has already passed")
        warnings: List[str] = []
        try:  # a gentle conflict check against what is already on the calendar
            res = await self._call(self._ep("GET", "/api/calendar/events"), self.request,
                                   start.replace(tzinfo=None).isoformat(), end.replace(tzinfo=None).isoformat())
            for ev in res.get("events", [])[:5]:
                es = self._event_dt(ev.get("dtstart"))
                if es and not ev.get("all_day"):
                    warnings.append(f"Overlaps '{_clip(ev.get('summary'), 50)}' at {tc.hm(es)}")
        except Exception:  # noqa: BLE001 - the check is advisory
            pass
        when = tc.span(start, end, all_day)
        rows = [["When", when]] + ([["Where", location]] if location else [])
        label = f"Add event '{title}' {when}" + (f" — at {location}" if location else "")
        return ({"summary": title, "dtstart": ds, "dtend": de, "all_day": all_day, "location": location},
                {"label": label, "kind": "event", "verb": "Add event", "title": title, "rows": rows, "warnings": warnings})

    async def _prepare_create_reminder(self, a):
        tc = self.tc
        text = _clean_text(a["text"], 200, "text")
        when, has_time = parse_when(str(a["when"]), tc)
        if not has_time:
            when = when.replace(hour=9, minute=0)
        if when <= tc.now():
            raise ToolArgError(f"{tc.when(when)} has already passed")
        return ({"title": text, "due_date": _iso_local(when)},
                {"label": f"Remind you: '{text}' — {tc.when(when)}", "kind": "reminder", "verb": "Set reminder", "title": text,
                 "rows": [["When", tc.when(when)]]})

    # ---------------------------------------------------------------------------------- execute
    async def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Run one approved action from its stored plan. Returns ``{"ok", "line", "kind", "title", "rows", "open", ...}``."""
        t, plan = action["tool"], action.get("plan")
        if not isinstance(plan, dict):
            return {"ok": False, "line": f"✗ {action.get('label') or t}: this step was never prepared", "kind": None}
        label = action.get("label") or t
        try:
            return await getattr(self, f"_do_{t}")(plan, action)
        except ToolArgError as e:
            return {"ok": False, "line": f"✗ {label}: {e}", "kind": (action.get("preview") or {}).get("kind")}
        except Exception as e:  # noqa: BLE001 - one broken step reports itself, it does not take the desktop down
            return {"ok": False, "line": f"✗ {label}: {e}", "kind": (action.get("preview") or {}).get("kind")}

    async def _do_create_automation(self, plan, action):
        tr = self._mods()[0]
        fields = {k: v for k, v in plan["task"].items() if v is not None}
        if fields.get("action") in SHELL_ACTIONS:   # defence in depth: the stored plan is re-checked before it runs
            raise ToolArgError("shell automations cannot be created by the assistant")
        if fields.get("task_type") == "llm" and looks_like_shell_job(fields.get("prompt", "")):
            raise ToolArgError("shell automations cannot be created by the assistant")
        task = await self._call(self._ep("POST", "/api/tasks"), self.request, tr.TaskCreate(**fields))
        v = self._task_view(task)
        nxt = f" (next run {v['next_run']})" if v["next_run"] else ""
        return {"ok": True, "kind": "automation", "title": task["name"], "line": f"✓ Created automation '{task['name']}' — {v['schedule']}{nxt}",
                "headline": f"Created automation “{task['name']}”",
                "rows": [["When", v["schedule"]]] + ([["Next run", v["next_run"]]] if v["next_run"] else []),
                "automation": v, "open": {"app": "automations", "props": {"intent": "show", "id": task["id"]}, "label": "Open in Automations"}}

    async def _do_update_automation_status(self, plan, action):
        ep = self._ep("POST", "/api/tasks/{task_id}/" + ("pause" if plan["status"] == "paused" else "resume"))
        await self._call(ep, self.request, plan["id"])
        task = next((x for x in await asyncio.to_thread(self._tasks_sync) if x["id"] == plan["id"]), None)
        v = self._task_view(task) if task else None
        word = "Paused" if plan["status"] == "paused" else "Resumed"
        nxt = f" (next run {v['next_run']})" if v and v["next_run"] and plan["status"] == "active" else ""
        return {"ok": True, "kind": "automation", "title": plan["name"], "line": f"✓ {word} automation '{plan['name']}'{nxt}",
                "automation": v, "open": {"app": "automations", "props": {"intent": "show", "id": plan["id"]}, "label": "Open in Automations"}}

    async def _do_run_automation(self, plan, action):
        # Do not wait for the run inside this request: the scheduler holds a run back while an API request is in flight
        # (so it never competes with the person), which would make waiting here pointless. The UI polls ``run_result``.
        since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        await self._call(self._ep("POST", "/api/tasks/{task_id}/run"), self.request, plan["id"])
        return {"ok": True, "kind": "automation", "title": plan["name"],
                "line": f"✓ Started automation '{plan['name']}'; its result shows here when it finishes",
                "run": {"task_id": plan["id"], "since": since},
                "open": {"app": "automations", "props": {"intent": "show", "id": plan["id"]}, "label": "Open in Automations"}}

    async def run_result(self, task_id: str, since: str) -> Dict[str, Any]:
        """The newest run of one of *my* automations since a moment: ``{"status": "waiting"}`` until one exists."""
        task = next((t for t in await asyncio.to_thread(self._tasks_sync) if t["id"] == task_id), None)
        if task is None:
            raise ToolArgError("no such automation")
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise ToolArgError("invalid time")
        run = await asyncio.to_thread(self._latest_run, task_id, since_dt)
        if run is None:
            return {"status": "waiting", "done": False, "output": ""}
        done = run["status"] not in ("running", "queued")
        return {"status": run["status"], "done": done, "ok": run["status"] == "success", "output": run["text"][:3000]}

    def _latest_run(self, task_id: str, since: datetime) -> Optional[Dict[str, str]]:
        tr = self._mods()[0]
        db = tr.SessionLocal()
        try:
            r = (db.query(tr.TaskRun).filter(tr.TaskRun.task_id == task_id, tr.TaskRun.started_at >= since)
                 .order_by(tr.TaskRun.started_at.desc()).first())
            if not r:
                return None
            return {"status": r.status or "", "text": (r.result or r.error or "").strip()}
        finally:
            db.close()

    async def _do_add_todo(self, plan, action):
        nr = self._mods()[1]
        item = {"text": plan["text"], "done": False, "checked": False}
        existing = await asyncio.to_thread(self._todo_list_note)
        if existing:
            items = list(existing.get("items") or []) + [item]
            await self._call(self._ep("PUT", "/api/notes/{note_id}"), self.request, existing["id"], nr.NoteUpdate(items=items))
        else:
            await self._call(self._ep("POST", "/api/notes"), self.request,
                             nr.NoteCreate(title=TODO_LIST_TITLE, note_type="checklist", items=[item], source="agent"))
        line = f"✓ Added '{plan['text']}' to your to-do list"
        if plan.get("due"):
            await self._make_reminder(f"Reminder: {plan['text']}", plan["due"])
            line += f" with a reminder {self.tc.when(datetime.fromisoformat(plan['due']))}"
        return {"ok": True, "kind": "todo", "title": plan["text"], "line": line, "open": {"app": "notes", "props": {}, "label": "Open Notes"}}

    def _todo_list_note(self) -> Optional[Dict[str, Any]]:
        for n in self._notes_sync():
            if (n.get("note_type") == "checklist" and (n.get("title") or "").strip().lower() in _TODO_TITLES
                    and n.get("source") != "calendar"):
                return n
        return None

    async def _make_reminder(self, title: str, due_iso: str) -> Dict[str, Any]:
        nr = self._mods()[1]
        for n in await asyncio.to_thread(self._notes_sync, with_due=True):   # same dedup as the agent's notes tool
            if n.get("due_date") == due_iso and (n.get("title") or "").strip().lower() == title.strip().lower():
                return n
        return await self._call(self._ep("POST", "/api/notes"), self.request,
                                nr.NoteCreate(title=title, note_type="note", due_date=due_iso, source="agent"))

    async def _do_create_reminder(self, plan, action):
        note = await self._make_reminder(plan["title"], plan["due_date"])
        when = self.tc.when(datetime.fromisoformat(plan["due_date"]))
        return {"ok": True, "kind": "reminder", "title": plan["title"], "line": f"✓ Reminder set: '{plan['title']}' — {when}",
                "headline": f"Reminder set: “{plan['title']}”",
                "rows": [["When", when]], "note_id": note.get("id"), "open": {"app": "notes", "props": {}, "label": "Open Notes"}}

    async def _do_complete_todo(self, plan, action):
        res = await self.toggle_todo(f"{plan['note_id']}#{plan['index']}", expect_text=plan["text"], want_done=True)
        return {"ok": True, "kind": "todo", "title": plan["text"],
                "line": f"✓ Marked '{plan['text']}' as done" if res["changed"] else f"✓ '{plan['text']}' was already done",
                "open": {"app": "notes", "props": {}, "label": "Open Notes"}}

    async def toggle_todo(self, ref: str, expect_text: Optional[str] = None, want_done: Optional[bool] = None) -> Dict[str, Any]:
        """Flip (or set) one checklist item. Used by the approved ``complete_todo`` and by the to-do card's checkboxes."""
        m = re.fullmatch(r"([0-9a-fA-F-]{6,36})#(\d{1,4})", (ref or "").strip())
        if not m:
            raise ToolArgError("invalid to-do reference")
        prefix, idx = m.group(1), int(m.group(2))
        notes = await asyncio.to_thread(self._notes_sync)
        note = next((n for n in notes if n["id"].startswith(prefix)), None)
        if not note:
            raise ToolArgError("that to-do list no longer exists")
        items = note.get("items") or []
        if expect_text is not None and not (idx < len(items) and str(items[idx].get("text") or "").strip() == expect_text):
            idx = next((i for i, it in enumerate(items) if str(it.get("text") or "").strip() == expect_text and not it.get("done")), -1)
        if not 0 <= idx < len(items):
            raise ToolArgError("that to-do changed; ask me to list your to-dos again")
        is_done = bool(items[idx].get("done") or items[idx].get("checked"))
        if want_done is not None and is_done == want_done:
            return {"changed": False, "done": is_done, "text": items[idx].get("text")}
        res = await self._call(self._ep("POST", "/api/notes/{note_id}/items/{index}/toggle"), self.request, note["id"], idx)
        item = (res.get("items") or items)[idx]
        return {"changed": True, "done": bool(item.get("done")), "text": item.get("text")}

    async def _do_create_event(self, plan, action):
        cr = self._mods()[2]
        body = cr.EventCreate(summary=plan["summary"], dtstart=plan["dtstart"], dtend=plan["dtend"], all_day=plan["all_day"],
                              location=plan.get("location") or "")
        res = await self._call(self._ep("POST", "/api/calendar/events"), self.request, body)
        pv = (action.get("preview") or {}).get("rows") or []
        when = next((v for k, v in pv if k == "When"), "")
        return {"ok": True, "kind": "event", "title": plan["summary"], "line": f"✓ Added '{plan['summary']}' — {when}", "rows": pv,
                "headline": f"Added “{plan['summary']}” to your calendar",
                "uid": res.get("uid"), "open": {"app": "calendar", "props": {}, "label": "Open Calendar"}}
