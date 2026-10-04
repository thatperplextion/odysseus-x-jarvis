"""Deterministic quick-capture parser behind the desktop's "Capture" bar.

One line of text in, one structured *draft* out -- no model call, so it answers instantly, works
offline and can be tested with a table of phrases. The result is only ever a draft: nothing is
stored until the caller confirms it (``POST /api/os/capture/commit``).

Kinds
-----
``automation``  recurring phrase ("every weekday at 7am ...", "daily ...", "every 2 hours ...")
``event``       a date/time plus an event-ish phrase ("lunch with Sara friday 1pm", "meeting at 3pm")
``reminder``    "remind me ...", or a task with a clock time ("call mom at 6pm"), or "in 30 minutes ..."
``todo``        everything else ("buy oat milk", "submit report by friday")

All times are the *user's* wall clock: ``now`` is passed in as a naive local ``datetime`` and the
UTC conversion for scheduled automations happens in :func:`automation_payload`, using the browser's
``getTimezoneOffset()`` (minutes, UTC minus local), because the task scheduler stores UTC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

KINDS = ("todo", "event", "reminder", "automation")

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
_WD_ALT = "monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues|tue|wed|thurs|thur|thu|fri|sat|sun"
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MON_ALT = "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LONG_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

EVENT_WORDS = (
    "meeting", "meet", "call with", "lunch", "dinner", "breakfast", "brunch", "coffee", "standup", "stand-up",
    "sync", "appointment", "interview", "demo", "review", "class", "lecture", "exam", "flight", "trip",
    "party", "birthday", "wedding", "conference", "workshop", "webinar", "session", "1:1", "one-on-one",
    "retro", "offsite", "dentist", "doctor", "gym", "concert", "movie", "visit", "holiday", "vacation",
    "presentation", "reservation", "game", "match", "deadline", "kickoff", "kick-off", "planning", "catch up",
    "catch-up", "huddle", "townhall", "town hall", "anniversary",
)
_EVENT_RE = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(w) for w in EVENT_WORDS) + r")(?![a-z])", re.I)

_ORD = r"(?:st|nd|rd|th)"

# ---------------------------------------------------------------------------------- helpers
def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fmt_time(h: int, m: int) -> str:
    ap = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ap}"


def fmt_day(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if 1 < delta < 7:
        return DAY_NAMES[d.weekday()]
    label = f"{DAY_NAMES[d.weekday()]} {d.day} {d.strftime('%b')}"
    return label if d.year == today.year else f"{label} {d.year}"


def _sentence(s: str) -> str:
    s = _clean(s)
    return s[:1].upper() + s[1:] if s else s


# ------------------------------------------------------------------------------- when parser
@dataclass
class When:
    start: Optional[datetime] = None        # naive local
    end: Optional[datetime] = None
    has_date: bool = False
    has_time: bool = False
    relative: bool = False                  # "in 30 minutes"
    spans: List[Tuple[int, int]] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.has_date or self.has_time or self.relative


_TIME_AP = r"(?P<ap>a\.?\s?m\.?|p\.?\s?m\.?)"
_RANGE_RE = re.compile(
    r"(?:\bfrom\s+)?(?<![\d:])(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ap1>[ap]\.?m\.?)?\s*(?:-|–|—|to|until|till)\s*"
    r"(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ap2>[ap]\.?m\.?)?(?![\w:])", re.I)
_TIME_RE = re.compile(
    r"(?:(?:\bat|@)\s*)?(?<![\d:.])(?:(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)(?![a-z])"
    r"|(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)(?![\d:])|(?P<word>noon|midnight)\b)", re.I)
_AT_BARE_RE = re.compile(r"\b(?:at|@)\s*(?P<h>\d{1,2})(?::(?P<m>\d{2}))?(?![\d:]|\s*(?:" + _MON_ALT + r")\b)", re.I)
_REL_RE = re.compile(r"\bin\s+(?:(?P<n>\d+)|(?P<a>an?|half an?)|(?P<h>one|two|three|four|five))\s*(?P<unit>minutes?|mins?|hours?|hrs?|days?|weeks?)\b", re.I)
_ISO_RE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
_DMON_RE = re.compile(r"\b(?:the\s+)?(?P<d>\d{1,2})" + _ORD + r"?\s+(?:of\s+)?(?P<mon>" + _MON_ALT + r")\b\.?(?:,?\s+(?P<y>\d{4}))?", re.I)
_MOND_RE = re.compile(r"\b(?P<mon>" + _MON_ALT + r")\.?\s+(?P<d>\d{1,2})" + _ORD + r"?\b(?:,?\s+(?P<y>\d{4}))?", re.I)
_DAYWORD_RE = re.compile(r"\b(?P<w>day after tomorrow|tomorrow|tmrw|tmr|today|tonight)\b", re.I)
_WEEKDAY_RE = re.compile(r"\b(?:(?P<mod>next|this|on|coming)\s+)?(?P<wd>" + _WD_ALT + r")\b(?!\.?\s*(?:am|pm))", re.I)
_DUR_RE = re.compile(r"\bfor\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>minutes?|mins?|hours?|hrs?|h)\b", re.I)
_ALLDAY_RE = re.compile(r"\ball[\s-]day\b", re.I)

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _ap_hour(h: int, ap: Optional[str]) -> Optional[int]:
    if ap:
        a = ap.lower()[0]
        if not (1 <= h <= 12):
            return None
        if a == "p" and h < 12:
            h += 12
        elif a == "a" and h == 12:
            h = 0
        return h
    return h if 0 <= h <= 23 else None


def _guess_ampm(h: int) -> int:
    """'at 3' means 3 pm, 'at 9' means 9 am, 'at 12' means noon."""
    if h == 12:
        return 12
    if 1 <= h <= 6:
        return h + 12
    return h


def _overlaps(spans: List[Tuple[int, int]], a: int, b: int) -> bool:
    return any(a < y and x < b for x, y in spans)


def parse_when(text: str, now: datetime) -> When:
    """Find a date and/or time in ``text``. ``now`` is naive local time."""
    w = When()
    spans = w.spans
    today = now.date()
    hh: Optional[int] = None
    mm = 0
    end_hm: Optional[Tuple[int, int]] = None
    all_day = bool(_ALLDAY_RE.search(text))
    if all_day:
        for m in _ALLDAY_RE.finditer(text):
            spans.append(m.span())

    # -- relative offsets: "in 30 minutes", "in an hour", "in 2 days"
    m = _REL_RE.search(text)
    if m:
        unit = m.group("unit").lower()
        if m.group("n"):
            n = float(m.group("n"))
        elif m.group("h"):
            n = float(_NUM_WORDS[m.group("h").lower()])
        else:
            n = 0.5 if (m.group("a") or "").lower().startswith("half") else 1.0
        if unit.startswith(("min", "m")):
            delta = timedelta(minutes=n)
        elif unit.startswith(("h")):
            delta = timedelta(hours=n)
        elif unit.startswith("d"):
            delta = timedelta(days=n)
        else:
            delta = timedelta(weeks=n)
        target = now.replace(second=0, microsecond=0) + delta
        w.relative = True
        w.has_date = True
        w.has_time = unit.startswith(("min", "m", "h"))
        w.start = target if w.has_time else datetime.combine(target.date(), datetime.min.time())
        spans.append(m.span())
        return _finish_duration(text, w)

    # -- time range ("2-3pm", "from 9:00 to 10:30")
    for m in _RANGE_RE.finditer(text):
        ap1, ap2 = m.group("ap1"), m.group("ap2")
        both_colon = bool(m.group("m1")) and bool(m.group("m2"))
        if not (ap1 or ap2 or both_colon):
            continue
        h1, h2 = int(m.group("h1")), int(m.group("h2"))
        m1, m2 = int(m.group("m1") or 0), int(m.group("m2") or 0)
        if not ap1 and ap2:
            ap1 = ap2
            # "11-1pm" -> 11am-1pm
            if h1 > h2 and h1 != 12:
                ap1 = "am"
        a = _ap_hour(h1, ap1) if ap1 else (h1 if h1 < 24 else None)
        b = _ap_hour(h2, ap2) if ap2 else (h2 if h2 < 24 else None)
        if a is None or b is None or m1 > 59 or m2 > 59:
            continue
        hh, mm, end_hm = a, m1, (b, m2)
        spans.append(m.span())
        w.has_time = True
        break

    # -- single clock time
    if hh is None:
        for m in _TIME_RE.finditer(text):
            if _overlaps(spans, *m.span()):
                continue
            if m.group("word"):
                hh, mm = (12, 0) if m.group("word").lower() == "noon" else (0, 0)
            elif m.group("ap"):
                hh = _ap_hour(int(m.group("h")), m.group("ap"))
                mm = int(m.group("m") or 0)
            else:
                hh, mm = int(m.group("h24")), int(m.group("m24"))
            if hh is None or mm > 59:
                hh = None
                continue
            spans.append(m.span())
            w.has_time = True
            break
    if hh is None:
        for m in _AT_BARE_RE.finditer(text):
            if _overlaps(spans, *m.span()):
                continue
            h = int(m.group("h"))
            if h > 23:
                continue
            hh = _guess_ampm(h)
            mm = int(m.group("m") or 0)
            if mm > 59:
                hh = None
                continue
            spans.append(m.span())
            w.has_time = True
            break

    # -- date
    base: Optional[date] = None
    m = _ISO_RE.search(text)
    if m:
        try:
            base = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
            spans.append(m.span())
        except ValueError:
            base = None
    if base is None:
        for rx in (_DMON_RE, _MOND_RE):
            m = rx.search(text)
            if not m or _overlaps(spans, *m.span()):
                continue
            mon = MONTHS.get(m.group("mon").lower()[:4] if m.group("mon").lower().startswith("sept") else m.group("mon").lower()[:3])
            day = int(m.group("d"))
            if not mon or not (1 <= day <= 31):
                continue
            year = int(m.group("y")) if m.group("y") else today.year
            try:
                cand = date(year, mon, day)
            except ValueError:
                continue
            if not m.group("y") and cand < today:
                try:
                    cand = date(year + 1, mon, day)
                except ValueError:
                    continue
            base = cand
            spans.append(m.span())
            break
    tonight = False
    if base is None:
        m = _DAYWORD_RE.search(text)
        if m:
            word = m.group("w").lower()
            if word == "day after tomorrow":
                base = today + timedelta(days=2)
            elif word in ("tomorrow", "tmrw", "tmr"):
                base = today + timedelta(days=1)
            else:
                base = today
                tonight = word == "tonight"
            spans.append(m.span())
    if base is None:
        for m in _WEEKDAY_RE.finditer(text):
            if _overlaps(spans, *m.span()):
                continue
            wd = WEEKDAYS[m.group("wd").lower()]
            ahead = (wd - today.weekday()) % 7
            mod = (m.group("mod") or "").lower()
            if ahead == 0 and (mod in ("next", "coming") or (hh is not None and datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm) <= now)):
                ahead = 7
            base = today + timedelta(days=ahead)
            spans.append(m.span())
            break
    if base is not None:
        w.has_date = True

    if all_day and base is not None:
        w.start = datetime.combine(base, datetime.min.time())
        w.has_time = False
        return w

    if hh is None and tonight:
        hh, mm = 20, 0
        w.has_time = True

    if base is None and hh is not None:
        base = today
        if datetime.combine(today, datetime.min.time()).replace(hour=hh, minute=mm) <= now:
            base = today + timedelta(days=1)
    if base is not None:
        w.start = datetime.combine(base, datetime.min.time())
        if hh is not None:
            w.start = w.start.replace(hour=hh, minute=mm)
        if end_hm is not None and w.start is not None:
            end = w.start.replace(hour=end_hm[0], minute=end_hm[1])
            if end <= w.start:
                end += timedelta(days=1)
            w.end = end
    return _finish_duration(text, w)


def _finish_duration(text: str, w: When) -> When:
    m = _DUR_RE.search(text)
    if m and w.start is not None and w.end is None and w.has_time:
        n = float(m.group("n"))
        unit = m.group("unit").lower()
        w.end = w.start + (timedelta(minutes=n) if unit.startswith("m") else timedelta(hours=n))
        w.spans.append(m.span())
    return w


def _strip_spans(text: str, spans: List[Tuple[int, int]]) -> str:
    out = text
    for a, b in sorted(spans, reverse=True):
        out = out[:a] + " " + out[b:]
    return out


_LEAD_FILLER = re.compile(
    r"^\s*(?:(?:please\s+)?(?:add\s+(?:a\s+|an\s+)?(?:new\s+)?(?:todo|to-do|task|reminder|event|automation)\s*(?:to|:|-)?\s*)"
    r"|(?:todo|to-do|task|reminder|event|automation|automate|capture|note)\s*(?::|-|—)\s*"
    r"|(?:please\s+)?remind\s+me\s+(?:to\s+|about\s+|that\s+)?"
    r"|(?:please\s+)?remember\s+to\s+"
    r"|(?:please\s+)?(?:schedule|book|set\s+up)\s+(?:in\s+)?(?:a\s+|an\s+|the\s+)?"
    r"|(?:i\s+(?:need|have|want)\s+to\s+|don'?t\s+forget\s+to\s+))+",
    re.I)
_TRAIL_CONNECTOR = re.compile(r"(?:\s+|^)(?:on|at|by|for|from|to|until|till|due|before|this|next|in|around|@|and|then|the|every|each)\s*$", re.I)
_LEAD_CONNECTOR = re.compile(r"^\s*(?:on|at|by|for|from|to|until|till|due|@|and|then|-|,|:|—)\s+", re.I)


def tidy_title(text: str) -> str:
    s = _clean(text)
    prev = None
    while prev != s:
        prev = s
        s = _LEAD_FILLER.sub("", s)
        s = _LEAD_CONNECTOR.sub("", s)
        s = _TRAIL_CONNECTOR.sub("", s)
        s = s.strip(" \t,;:-–—.@")
        s = re.sub(r"\(\s*\)", "", s)
        s = re.sub(r"\s+([,.;:])", r"\1", s)
        s = _clean(s)
    return _sentence(s)


# ----------------------------------------------------------------------- recurrence parser
_TOD_DEFAULT = {"morning": (8, 0), "afternoon": (14, 0), "evening": (18, 0), "night": (21, 0), "nightly": (21, 0)}


def _expand_days(spec: str) -> List[int]:
    out: List[int] = []
    for name in re.findall(r"[a-z]+", spec.lower()):
        key = name[:-1] if name.endswith("s") and name[:-1] in WEEKDAYS else name
        if key in WEEKDAYS and WEEKDAYS[key] not in out:
            out.append(WEEKDAYS[key])
    return sorted(out)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# "every monday morning ...", "daily in the evening ...", "... at night every weekday": a time-of-day word next to the schedule IS
# the time (morning 08:00, afternoon 14:00, evening 18:00, night 21:00) and must not stay behind in the task's prompt. Not when it
# is part of what the task is about ("good morning message", "morning emails", "morning brief").
_TOD_WORD = r"(?P<tod>morning|afternoon|evening|night)s?"
_TOD_AFTER = re.compile(r"\s*(?:,\s*)?(?:(?:in|during|at|around)\s+(?:the\s+)?)?" + _TOD_WORD + r"\b(?!\s+(?:brief|briefing|digest|summary|routine|report|news|e-?mails?|standup|meeting))", re.I)
_TOD_BEFORE = re.compile(r"(?:\b(?:in|during|at|around)\s+(?:the\s+)?)?\b" + _TOD_WORD + r"\s*,?\s*$", re.I)
_TOD_FOLLOWS_GOOD = re.compile(r"\bgood\s*$", re.I)


def _attach_tod(rec: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Give ``rec`` its ``tod`` (and the word's span, so it is stripped) when a time-of-day word sits right next to the schedule."""
    if rec.get("tod") or rec.get("freq") == "interval" or not rec["spans"]:
        return rec
    start = min(a for a, _ in rec["spans"])
    end = max(b for _, b in rec["spans"])
    m = _TOD_AFTER.match(text, end)
    if m:
        rec["spans"].append((end, m.end()))
        rec["tod"] = _TOD_DEFAULT[m.group("tod").lower()]
        return rec
    head = text[:start]
    m = _TOD_BEFORE.search(head)
    if m and not _TOD_FOLLOWS_GOOD.search(head[:m.start()]):
        rec["spans"].append((m.start(), start))
        rec["tod"] = _TOD_DEFAULT[m.group("tod").lower()]
    return rec


def parse_recurrence(text: str) -> Optional[Dict[str, Any]]:
    """``{freq, spans, days?, dom?, interval?, unit?, tod?}`` or None when the text isn't recurring."""
    rec = _parse_recurrence(text)
    return _attach_tod(rec, text) if rec else rec


def _parse_recurrence(text: str) -> Optional[Dict[str, Any]]:
    t = text
    spans: List[Tuple[int, int]] = []

    def hit(rx: str) -> Optional["re.Match[str]"]:
        m = re.search(rx, t, re.I)
        if m:
            spans.append(m.span())
        return m

    if hit(r"\b(?:every|each|on)\s+(?:week[\s-]?days?|work[\s-]?days?|business days?)\b") or hit(r"\bweek[\s-]?days\b") or hit(r"\bmon(?:day)?\s*(?:-|to|through)\s*fri(?:day)?\b"):
        return {"freq": "weekly", "days": [0, 1, 2, 3, 4], "spans": spans, "label": "weekday"}
    if hit(r"\b(?:every|each|on)\s+weekends?\b"):
        return {"freq": "weekly", "days": [5, 6], "spans": spans, "label": "weekend"}
    m = hit(r"\b(?:every|each)\s+((?:(?:" + _WD_ALT + r")s?)(?:\s*(?:,|and|&|\+)\s*(?:(?:" + _WD_ALT + r")s?))*)\b")
    if m:
        days = _expand_days(m.group(1))
        if days:
            return {"freq": "weekly", "days": days, "spans": spans}
        spans.pop()
    m = hit(r"\bevery\s+(?:other\s+)?(\d+)\s*(minutes?|mins?|hours?|hrs?)\b")
    if m:
        n = max(1, int(m.group(1)))
        return {"freq": "interval", "interval": n, "unit": "minute" if m.group(2).lower().startswith("m") else "hour", "spans": spans}
    if hit(r"\b(?:hourly|every\s+hour)\b"):
        return {"freq": "interval", "interval": 1, "unit": "hour", "spans": spans}
    m = hit(r"\b(?:every|each)\s+(?:month\b(?:\s+on\s+the\s+(\d{1,2})" + _ORD + r"?)?|(\d{1,2})" + _ORD + r"\b)")
    if m:
        d = int(m.group(1) or m.group(2) or 1)
        return {"freq": "monthly", "dom": min(max(d, 1), 31), "spans": spans}
    if hit(r"\bmonthly\b"):
        om = re.search(r"\bon\s+the\s+(\d{1,2})" + _ORD + r"\b", t, re.I)
        if om:
            spans.append(om.span())
        return {"freq": "monthly", "dom": int(om.group(1)) if om else 1, "spans": spans}
    m = hit(r"\b(?:every|each)\s+(morning|afternoon|evening|night)\b")
    if m:
        return {"freq": "daily", "tod": _TOD_DEFAULT[m.group(1).lower()], "spans": spans}
    if hit(r"\b(?:every\s*day|each\s+day|daily)\b"):
        return {"freq": "daily", "spans": spans}
    if hit(r"\bnightly\b"):
        return {"freq": "daily", "tod": _TOD_DEFAULT["night"], "spans": spans}
    if hit(r"\b(?:every|each)\s+week\b") or hit(r"\bweekly\b"):
        return {"freq": "weekly", "days": None, "spans": spans}
    return None


def describe_recurrence(freq: str, *, days: Optional[List[int]], dom: Optional[int], interval: Optional[int], unit: Optional[str], hm: Tuple[int, int]) -> str:
    when = fmt_time(*hm)
    if freq == "interval":
        n = interval or 1
        if unit == "minute":
            return "Every minute" if n == 1 else f"Every {n} minutes"
        return "Every hour" if n == 1 else f"Every {n} hours"
    if freq == "monthly":
        return f"Monthly on the {_ordinal(dom or 1)} at {when}"
    if freq == "weekly":
        d = sorted(days or [])
        if d == [0, 1, 2, 3, 4]:
            return f"Every weekday at {when}"
        if d == [5, 6]:
            return f"Every weekend at {when}"
        if len(d) == 7:
            return f"Every day at {when}"
        names = ", ".join(LONG_DAY_NAMES[i] for i in d)
        return f"Every {names} at {when}"
    return f"Every day at {when}"


# --------------------------------------------------------------------------- main entry
_BRIEF_RE = re.compile(r"\b(?:(?:morning|daily|evening)\s+(?:brief(?:ing)?|digest|summary)|brief\s+me|daily\s+brief)\b", re.I)
_EMAIL_OUT_RE = re.compile(r"\b(?:email|mail)\s+(?:it\s+to\s+)?me\b|\bsend\s+me\s+an?\s+email\b", re.I)
_NOTIFY_RE = re.compile(r"\bnotif(?:y|ication)\b|\bremind\b", re.I)

_FORCE_PREFIX = [
    ("automation", re.compile(r"^\s*(?:add\s+(?:an?\s+)?(?:new\s+)?automation\s*[:\-]?|automation\s*[:\-]|automate\s*[:\-]?)\s*", re.I)),
    ("reminder", re.compile(r"^\s*(?:(?:please\s+)?remind\s+me\b|remember\s+to\b|reminder\s*[:\-]|add\s+(?:a\s+)?reminder\s*[:\-]?)", re.I)),
    ("event", re.compile(r"^\s*(?:event\s*[:\-]|add\s+(?:an?\s+)?(?:new\s+)?event\s*[:\-]?|schedule\s*[:\-]|new\s+event\s*[:\-]?)\s*", re.I)),
    ("todo", re.compile(r"^\s*(?:todo\s*[:\-]|to-do\s*[:\-]|task\s*[:\-]|add\s+(?:a\s+)?(?:todo|to-do|task)\s*[:\-]?|to\s+do\s*[:\-])\s*", re.I)),
]


class CaptureError(ValueError):
    pass


def _task_name(prompt: str) -> str:
    words = _clean(prompt).split(" ")
    name = " ".join(words[:6])
    if len(name) > 48:
        name = name[:48].rsplit(" ", 1)[0]
    return _sentence(name.rstrip(".,;:"))


def _default_hm(rec: Dict[str, Any], when: When) -> Tuple[int, int]:
    if when.has_time and when.start is not None:
        return when.start.hour, when.start.minute
    return rec.get("tod") or (9, 0)


def _automation(text: str, now: datetime) -> Dict[str, Any]:
    rec = parse_recurrence(text)
    if rec is None:  # explicit "automation: ..." with no schedule words -> daily, shown in the preview
        rec = {"freq": "daily", "spans": []}
    stripped = _strip_spans(text, rec["spans"])
    when = parse_when(stripped, now)
    remainder = tidy_title(_strip_spans(stripped, when.spans))
    hm = _default_hm(rec, when)
    freq = rec["freq"]
    days = rec.get("days")
    if freq == "weekly" and days is None:
        days = [now.weekday()]
    draft: Dict[str, Any] = {
        "freq": freq, "days": days, "dom": rec.get("dom"), "interval": rec.get("interval"), "unit": rec.get("unit"),
        "time": f"{hm[0]:02d}:{hm[1]:02d}", "trigger_type": "schedule",
    }
    if _BRIEF_RE.search(remainder) or _BRIEF_RE.search(text):
        draft.update(task_type="action", action="daily_brief", name="Daily brief", prompt=None, output_target="notification")
        brief = True
    else:
        brief = False
        prompt = remainder
        draft.update(task_type="llm", action=None, prompt=prompt or "", name=_task_name(prompt) if prompt else "",
                     output_target="email" if _EMAIL_OUT_RE.search(text) else "notification" if _NOTIFY_RE.search(text) else "session")
    draft["human"] = describe_recurrence(freq, days=days, dom=draft["dom"], interval=draft["interval"], unit=draft["unit"], hm=hm)
    draft["needs_prompt"] = not brief and not draft["prompt"]
    what = "Daily brief" if brief else (draft["name"] or "(say what it should do)")
    return {"kind": "automation", "draft": draft, "preview_text": f"{what} · {draft['human']}"}


def _event(text: str, now: datetime, when: When) -> Dict[str, Any]:
    title = tidy_title(_strip_spans(text, when.spans)) or "Event"
    start = when.start or datetime.combine(now.date(), datetime.min.time())
    today = now.date()
    if when.has_time:
        end = when.end or start + timedelta(hours=1)
        draft = {"summary": title, "dtstart": start.strftime("%Y-%m-%dT%H:%M:00"), "dtend": end.strftime("%Y-%m-%dT%H:%M:00"),
                 "all_day": False, "location": "", "description": ""}
        span = f"{fmt_time(start.hour, start.minute)}–{fmt_time(end.hour, end.minute)}" if end.date() == start.date() else fmt_time(start.hour, start.minute)
        human = f"{fmt_day(start.date(), today)}, {span}"
    else:
        draft = {"summary": title, "dtstart": start.strftime("%Y-%m-%d"), "dtend": (start + timedelta(days=1)).strftime("%Y-%m-%d"),
                 "all_day": True, "location": "", "description": ""}
        human = f"{fmt_day(start.date(), today)}, all day"
    return {"kind": "event", "draft": draft, "preview_text": f"{title} · {human}"}


def _reminder(text: str, now: datetime, when: When) -> Dict[str, Any]:
    title = tidy_title(_strip_spans(text, when.spans)) or "Reminder"
    if when.start is not None:
        due = when.start
        if not when.has_time:
            due = due.replace(hour=9, minute=0)
    else:
        due = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
    draft = {"title": title, "due": due.strftime("%Y-%m-%dT%H:%M")}
    human = f"{fmt_day(due.date(), now.date())}, {fmt_time(due.hour, due.minute)}"
    return {"kind": "reminder", "draft": draft, "preview_text": f"{title} · {human}"}


def _todo(text: str, now: datetime, when: When) -> Dict[str, Any]:
    body = tidy_title(_strip_spans(text, when.spans)) if when.found else tidy_title(text)
    if not body:
        raise CaptureError("Nothing to capture")
    if when.has_date and when.start is not None:
        label = fmt_day(when.start.date(), now.date())
        body = f"{body} (by {label.lower() if label in ('Today', 'Tomorrow') else label})"
    draft = {"text": body}
    return {"kind": "todo", "draft": draft, "preview_text": body}


def classify_and_parse(text: str, now: datetime, force: Optional[str] = None) -> Dict[str, Any]:
    """Return ``{kind, draft, preview_text}``. ``force`` pins the kind (used by the Edit step)."""
    raw = _clean(text)
    if not raw:
        raise CaptureError("Nothing to capture")
    if len(raw) > 600:
        raise CaptureError("That's a bit long for a quick capture (600 characters max)")
    if force is not None and force not in KINDS:
        raise CaptureError(f"Unknown kind {force!r}")

    kind = force
    body = raw
    if kind is None:
        for k, rx in _FORCE_PREFIX:
            if rx.match(raw):
                kind = k
                break
    if force is None and kind == "todo":
        body = _FORCE_PREFIX[3][1].sub("", raw)
    elif force is None and kind == "automation":
        body = _FORCE_PREFIX[0][1].sub("", raw)

    rec = parse_recurrence(body)
    if kind == "automation" or (kind is None and rec is not None):
        return _automation(body, now)
    if kind == "todo":
        return _todo(body, now, parse_when(body, now))

    when = parse_when(body, now)
    if kind is None:
        has_event_word = bool(_EVENT_RE.search(body))
        soft_event = bool(re.match(r"^\s*(?:schedule|book)\b", body, re.I))
        if when.relative and not has_event_word:
            kind = "reminder"
        elif when.found and (has_event_word or soft_event):
            kind = "event"
        elif when.has_time:
            kind = "reminder"
        else:
            kind = "todo"
    if kind == "event":
        if not when.found:
            # an event without any date: put it on today as all-day rather than guessing a time
            when.start = datetime.combine(now.date(), datetime.min.time())
            when.has_date = True
        return _event(body, now, when)
    if kind == "reminder":
        return _reminder(body, now, when)
    return _todo(body, now, when)


# ------------------------------------------------------------- automation -> scheduler payload
def _cron_dow_shift(dow: str, carry: int) -> str:
    if carry == 0 or dow.strip() == "*":
        return dow
    days = set()
    for part in dow.split(","):
        part = part.strip()
        rng = re.fullmatch(r"(\d)-(\d)", part)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            days.update(range(a, b + 1))
        elif part.isdigit():
            days.add(int(part))
        else:
            return dow
    shifted = sorted({(d % 7 + carry) % 7 for d in days})
    return ",".join(str(d) for d in shifted)


def automation_payload(draft: Dict[str, Any], tz_offset_min: int = 0) -> Dict[str, Any]:
    """TaskCreate-shaped dict for the scheduler. The scheduler keeps ``scheduled_time`` and cron fields in
    **UTC**, so wall-clock times are shifted by ``tz_offset_min`` (JS ``getTimezoneOffset``: UTC minus local)."""
    try:
        hh, mm = [int(x) for x in str(draft.get("time") or "09:00").split(":")[:2]]
    except ValueError:
        hh, mm = 9, 0
    off = timedelta(minutes=int(tz_offset_min))
    ref = datetime(2024, 1, 1, hh, mm)                      # a Monday
    utc = ref + off
    carry = (utc.date() - ref.date()).days
    utc_hm = utc.strftime("%H:%M")
    freq = draft.get("freq") or "daily"
    out: Dict[str, Any] = {
        "name": (draft.get("name") or "").strip() or None,
        "task_type": draft.get("task_type") or "llm",
        "action": draft.get("action"),
        "prompt": draft.get("prompt"),
        "output_target": draft.get("output_target") or "session",
        "trigger_type": "schedule",
    }
    if freq == "interval":
        n = int(draft.get("interval") or 1)
        out["schedule"] = "cron"
        out["cron_expression"] = f"*/{n} * * * *" if draft.get("unit") == "minute" else (f"0 */{n} * * *" if n > 1 else "0 * * * *")
    elif freq == "weekly":
        days = sorted(set(draft.get("days") or [0]))
        if len(days) == 1:
            out["schedule"] = "weekly"
            out["scheduled_day"] = (days[0] + carry) % 7
            out["scheduled_time"] = utc_hm
        else:
            # cron day-of-week: 0 = Sunday ... 6 = Saturday; ours is 0 = Monday
            cron_days = ",".join(str(d) for d in sorted(((d + 1) % 7) for d in days))
            out["schedule"] = "cron"
            out["cron_expression"] = f"{utc.minute} {utc.hour} * * {_cron_dow_shift(cron_days, carry)}"
    elif freq == "monthly":
        ref_m = datetime(2024, 1, min(int(draft.get("dom") or 1), 28), hh, mm) + off
        out["schedule"] = "monthly"
        out["scheduled_day"] = ref_m.day if ref_m.month == 1 else min(int(draft.get("dom") or 1), 28)
        out["scheduled_time"] = utc_hm
    else:
        out["schedule"] = "daily"
        out["scheduled_time"] = utc_hm
    return {k: v for k, v in out.items() if v is not None}
