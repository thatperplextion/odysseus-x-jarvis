"""The desktop's Today dashboard: /api/os/today aggregation, quick capture, focus log, notifications.

Real SQLAlchemy tables (a throw-away SQLite file per test) behind the real routers; only authentication is
faked (see tests/helpers/os_app.py). The clock is pinned with ``now=`` (a naive *local* timestamp) so the
assertions don't depend on when the suite runs.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
import routes.os_today_routes as today_mod
from core.database import CalendarCal, CalendarEvent, EmailAccount, ModelEndpoint, Note, ScheduledTask, TaskRun
from routes.os_today_routes import setup_os_today_routes
from services.os_shell import capture as cap
from services.os_shell.focus import FocusStore
from tests.helpers.os_app import FakeJarvis, build_app, client_for

NOW = "2026-10-02T10:25"            # a Friday, local wall clock
NOW_DT = datetime(2026, 10, 2, 10, 25)
Q = {"now": NOW, "tz_offset": 0}


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'today.db'}", connect_args={"check_same_thread": False}, poolclass=NullPool)
    cdb.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(today_mod, "SessionLocal", factory)
    return factory


@pytest.fixture
async def env(tmp_path, session_factory, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setattr(today_mod, "_email_db", lambda: str(tmp_path / "email.db"))
    jarvis = FakeJarvis(tmp_path / "jarvis")
    await jarvis.start()
    app = build_app(jarvis, admins=("admin", "other"))
    app.include_router(setup_os_today_routes())
    async with client_for(app, user="admin") as client:
        yield client, jarvis, app, session_factory
    await jarvis.stop()


def seed_calendar(factory, owner="admin"):
    db = factory()
    try:
        cal = CalendarCal(id="cal-" + owner, owner=owner, name="Personal", color="#5b8abf", source="local")
        db.add(cal)
        ev = lambda uid, summary, start, end, **kw: CalendarEvent(uid=uid, calendar_id=cal.id, summary=summary, dtstart=start, dtend=end, **kw)  # noqa: E731
        db.add_all([
            ev("e1", "Breakfast", datetime(2026, 10, 2, 8, 0), datetime(2026, 10, 2, 9, 0)),            # already over
            ev("e2", "Standup", datetime(2026, 10, 2, 10, 50), datetime(2026, 10, 2, 11, 20), location="Room 4"),   # in 25 min
            ev("e3", "Design review", datetime(2026, 10, 3, 14, 0), datetime(2026, 10, 3, 15, 0)),      # tomorrow
            ev("e4", "Offsite", datetime(2026, 10, 2), datetime(2026, 10, 3), all_day=True),
            ev("e5", "Next week", datetime(2026, 10, 9, 9, 0), datetime(2026, 10, 9, 10, 0)),           # outside the window
            ev("e6", "Daily sync", datetime(2026, 9, 30, 16, 0), datetime(2026, 9, 30, 16, 30), rrule="FREQ=DAILY"),
            ev("e7", "Cancelled thing", datetime(2026, 10, 2, 12, 0), datetime(2026, 10, 2, 13, 0), status="cancelled"),
        ])
        db.commit()
    finally:
        db.close()


def seed_notes(factory, owner="admin"):
    db = factory()
    try:
        db.add_all([
            Note(id="n1", owner=owner, title="Groceries", note_type="checklist", pinned=True,
                 items=json.dumps([{"id": "a", "text": "Oat milk", "done": False}, {"id": "b", "text": "Bread", "done": True}, {"id": "c", "text": "Coffee", "done": False}])),
            Note(id="n2", owner=owner, title="Work", note_type="checklist",
                 items=json.dumps([{"id": "d", "text": "Send invoice", "done": False}, {"id": "e", "text": "   ", "done": False}])),
            Note(id="n3", owner=owner, title="Archived list", note_type="checklist", archived=True, items=json.dumps([{"id": "f", "text": "Hidden", "done": False}])),
            Note(id="n4", owner=owner, title="Call the dentist", note_type="note", due_date="2026-10-02T16:30"),
            Note(id="n5", owner=owner, title="Plain note", note_type="note", content="no list, no due date"),
            Note(id="nx", owner="someone-else", title="Not mine", note_type="checklist", items=json.dumps([{"id": "z", "text": "Secret", "done": False}])),
        ])
        db.commit()
    finally:
        db.close()


def seed_tasks(factory, owner="admin"):
    db = factory()
    try:
        t1 = ScheduledTask(id="t1", owner=owner, name="Morning brief", task_type="action", action="daily_brief", schedule="daily",
                           scheduled_time="04:00", status="active", next_run=datetime(2026, 10, 3, 4, 0), output_target="notification")
        t2 = ScheduledTask(id="t2", owner=owner, name="Weekly review", task_type="llm", prompt="review", schedule="weekly", scheduled_day=4,
                           scheduled_time="12:00", status="active", next_run=datetime(2026, 10, 2, 12, 0))
        t3 = ScheduledTask(id="t3", owner=owner, name="Paused thing", task_type="llm", prompt="x", schedule="daily", scheduled_time="01:00", status="paused")
        t4 = ScheduledTask(id="t4", owner=owner, name="Email Tags", task_type="action", action="check_email_urgency", schedule="cron",
                           cron_expression="0 * * * *", status="active", next_run=datetime(2026, 10, 2, 11, 0))      # housekeeping: not counted as "mine"
        t5 = ScheduledTask(id="t5", owner="someone-else", name="Not mine", task_type="llm", prompt="x", schedule="daily", scheduled_time="02:00",
                           status="active", next_run=datetime(2026, 10, 3, 2, 0))
        db.add_all([t1, t2, t3, t4, t5])
        db.flush()
        db.add_all([
            TaskRun(id="r1", task_id="t1", started_at=datetime(2026, 10, 2, 4, 0), finished_at=datetime(2026, 10, 2, 4, 1), status="success", result="Daily brief\n  Calendar: nothing"),
            TaskRun(id="r2", task_id="t2", started_at=datetime(2026, 10, 1, 12, 0), finished_at=datetime(2026, 10, 1, 12, 1), status="error", error="model unreachable"),
            TaskRun(id="r3", task_id="t2", started_at=datetime(2026, 10, 2, 9, 0), status="running"),
            TaskRun(id="r4", task_id="t4", started_at=datetime(2026, 10, 2, 5, 0), finished_at=datetime(2026, 10, 2, 5, 1), status="success", result="housekeeping"),
        ])
        db.commit()
    finally:
        db.close()


# ============================================================================ /api/os/today
async def test_today_aggregates_every_section(env):
    c, _, _, factory = env
    seed_calendar(factory)
    seed_notes(factory)
    seed_tasks(factory)
    r = await c.get("/api/os/today", params=Q)
    assert r.status_code == 200
    d = r.json()
    assert set(d) >= {"agenda", "todos", "automations", "inbox", "focus", "model", "summary", "generated_at"}
    assert not [k for k in ("agenda", "todos", "automations", "inbox", "focus", "model") if "error" in d[k]], d

    ag = d["agenda"]
    names_today = [e["summary"] for e in ag["events"] if e["day"] == "today"]
    assert names_today == ["Offsite", "Breakfast", "Daily sync", "Standup"] or set(names_today) == {"Offsite", "Breakfast", "Daily sync", "Standup"}
    assert [e["summary"] for e in ag["events"] if e["day"] == "tomorrow"].count("Design review") == 1
    assert "Next week" not in [e["summary"] for e in ag["events"]] and "Cancelled thing" not in [e["summary"] for e in ag["events"]]
    assert next(e for e in ag["events"] if e["summary"] == "Offsite")["all_day"] is True
    # the recurring series expands onto today and tomorrow
    assert sum(1 for e in ag["events"] if e["summary"] == "Daily sync") == 2
    # next up is the first timed thing that has not finished: the daily sync (4pm) comes after the 10:50 standup
    assert ag["next_up"]["summary"] == "Standup" and ag["next_up"]["start"] == "2026-10-02T10:50"
    assert ag["next_up"]["start_ts"] - d["generated_at"] == 25 * 60 * 1000
    assert [r["summary"] for r in ag["reminders"]] == ["Call the dentist"]
    assert ag["today_count"] == 4 and ag["tomorrow_count"] == 2

    td = d["todos"]
    assert td["open"] == 3 and td["lists"] == 2
    assert [(i["text"], i["list"], i["index"]) for i in td["items"]] == [("Oat milk", "Groceries", 0), ("Coffee", "Groceries", 2), ("Send invoice", "Work", 0)]
    assert "Secret" not in json.dumps(d) and "Hidden" not in json.dumps(d)       # other owner / archived

    au = d["automations"]
    assert (au["total"], au["active"], au["paused"], au["builtin_active"]) == (3, 2, 1, 1)
    assert [u["id"] for u in au["upcoming"]] == ["t2", "t1"]                          # soonest first, housekeeping and other owners excluded
    assert au["upcoming"][1]["label"] == "Daily at 4:00 am"
    assert [r["id"] for r in au["recent"]] == ["r3", "r1", "r2"] and au["recent"][1]["summary"] == "Daily brief Calendar: nothing"
    assert au["running"] == ["t2"] and au["ran_since"] == 1 and au["failed_since"] == 0 and au["since_label"] == "overnight"

    assert d["inbox"] == {"configured": False}
    assert d["focus"]["minutes_today"] == 0
    assert d["model"] == {"configured": False}
    s = d["summary"]["text"]
    assert s.startswith("4 events") and "next: Standup in 25 min" in s and "3 todos" in s and "1 automation ran overnight" in s, s


async def test_today_is_fast_and_empty_state_is_calm(env):
    c, *_ = env
    d = (await c.get("/api/os/today", params=Q)).json()
    assert d["took_ms"] < 1500
    assert d["agenda"]["events"] == [] and d["agenda"]["next_up"] is None
    assert d["todos"]["open"] == 0 and d["automations"]["total"] == 0
    assert d["summary"]["text"] == "nothing on the calendar"


async def test_a_failing_section_does_not_take_the_others_down(env, monkeypatch):
    c, _, _, factory = env
    seed_notes(factory)

    def boom(ctx):
        raise RuntimeError("calendar database is locked")

    monkeypatch.setitem(today_mod.SECTIONS, "agenda", boom)
    d = (await c.get("/api/os/today", params=Q)).json()
    assert d["agenda"] == {"error": "calendar database is locked"}
    assert d["todos"]["open"] == 3 and "error" not in d["automations"]
    assert "3 todos" in d["summary"]["text"]            # the summary skips the broken section


async def test_a_slow_section_times_out_instead_of_stalling(env, monkeypatch):
    import time

    c, *_ = env
    monkeypatch.setattr(today_mod, "SECTION_TIMEOUT", 0.2)
    monkeypatch.setitem(today_mod.SECTIONS, "inbox", lambda ctx: time.sleep(1.0) or {"configured": True})
    t0 = time.perf_counter()
    d = (await c.get("/api/os/today", params=Q)).json()
    assert d["inbox"] == {"error": "Timed out"} and time.perf_counter() - t0 < 0.9
    assert "error" not in d["todos"]


async def test_today_is_owner_scoped(env):
    c, _, app, factory = env
    seed_calendar(factory, owner="other")
    seed_notes(factory, owner="other")
    seed_tasks(factory, owner="other")
    async with client_for(app, user="admin") as admin:
        d = (await admin.get("/api/os/today", params=Q)).json()
    # "admin" owns none of it (only the rows owned by "someone-else" / "other" exist)
    assert d["agenda"]["events"] == [] and d["todos"]["open"] == 0 and d["automations"]["total"] == 0
    async with client_for(app, user="other") as other:
        d = (await other.get("/api/os/today", params=Q)).json()
    assert d["agenda"]["today_count"] == 4 and d["todos"]["open"] == 3 and d["automations"]["total"] == 3


async def test_agenda_converts_utc_rows_to_the_users_clock(env):
    c, _, _, factory = env
    db = factory()
    cal = CalendarCal(id="c1", owner="admin", name="P", source="local")
    db.add(cal)
    # stored as UTC (is_utc): 05:30 UTC is 10:30 in UTC+5, so a "today" event for a user at tz_offset=-300
    db.add(CalendarEvent(uid="u1", calendar_id="c1", summary="UTC row", dtstart=datetime(2026, 10, 2, 5, 30), dtend=datetime(2026, 10, 2, 6, 30), is_utc=True))
    db.commit()
    db.close()
    d = (await c.get("/api/os/today", params={"now": NOW, "tz_offset": -300})).json()
    ev = d["agenda"]["events"][0]
    assert ev["start"] == "2026-10-02T10:30" and ev["day"] == "today"
    assert d["agenda"]["next_up"]["summary"] == "UTC row"


async def test_inbox_section_never_touches_the_network(env, tmp_path):
    c, _, _, factory = env
    # no account configured -> calm "connect" state
    assert (await c.get("/api/os/today", params=Q)).json()["inbox"] == {"configured": False}
    db = factory()
    db.add(EmailAccount(id="a1", owner="admin", name="Work", enabled=True, imap_host="imap.example.com", imap_user="me@example.com"))
    db.commit()
    db.close()
    # configured but the local index has never been filled -> unread unknown (null), not an error
    d = (await c.get("/api/os/today", params=Q)).json()["inbox"]
    assert d["configured"] is True and d["unread"] is None and d["synced"] is False
    conn = sqlite3.connect(str(tmp_path / "email.db"))
    conn.execute("""CREATE TABLE email_message_index (owner TEXT, account_key TEXT, folder TEXT, uid TEXT, message_id TEXT, subject TEXT,
        from_name TEXT, from_address TEXT, to_text TEXT, cc_text TEXT, date_iso TEXT, date_display TEXT, date_epoch REAL, size INT, flags TEXT,
        has_attachments INT, updated_at TEXT)""")
    rows = [("admin", "default", "INBOX", str(i), "", "s", name, name + "@x.io", "", "", "", "", i, 1, flags, 0, "2026-10-02T09:00:00Z")
            for i, (name, flags) in enumerate([("Ana", ""), ("Ana", ""), ("Bo", ""), ("Cy", "\\Seen"), ("Ana", None)])]
    conn.executemany("INSERT INTO email_message_index VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    d = (await c.get("/api/os/today", params=Q)).json()
    assert d["inbox"]["unread"] == 4 and d["inbox"]["top_senders"][0] == {"name": "Ana", "count": 3}
    assert "4 unread" in d["summary"]["text"]


async def test_model_section_reads_the_default_endpoint(env, monkeypatch):
    c, _, _, factory = env
    db = factory()
    db.add(ModelEndpoint(id="ep1", name="Local Ollama", base_url="http://127.0.0.1:11434/v1", is_enabled=True, cached_models=json.dumps(["qwen3", "llama3"])))
    db.commit()
    db.close()
    import src.settings as settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"default_endpoint_id": "ep1", "default_model": "llama3"})
    m = (await c.get("/api/os/today", params=Q)).json()["model"]
    assert m == {"configured": True, "model": "llama3", "endpoint_id": "ep1", "endpoint_name": "Local Ollama", "host": "127.0.0.1"}
    monkeypatch.setattr(settings, "load_settings", lambda: {})
    m = (await c.get("/api/os/today", params=Q)).json()["model"]
    assert m["model"] == "qwen3" and m["endpoint_name"] == "Local Ollama"          # falls back to the first enabled endpoint's first model


async def test_today_requires_the_os_guard(env):
    c, _, app, _ = env
    async with client_for(app, user="not-an-admin") as nobody:
        assert (await nobody.get("/api/os/today", params=Q)).status_code == 403
        assert (await nobody.post("/api/os/capture", json={"text": "x"})).status_code == 403
        assert (await nobody.post("/api/os/focus", json={"minutes": 5})).status_code == 403
    async with client_for(app, user="admin", **{"sec-fetch-site": "cross-site"}) as cross:
        assert (await cross.get("/api/os/today", params=Q)).status_code == 403


# ================================================================================ capture
TABLE = [
    # phrase,                                              kind,         must appear in preview_text
    ("every weekday at 7am summarize my unread email",     "automation", "Every weekday at 7:00 am"),
    ("daily 8am morning brief",                            "automation", "Daily brief"),
    ("each monday at 9 send me a weekly review",           "automation", "Every Monday at 9:00 am"),
    ("every 2 hours check disk space",                     "automation", "Every 2 hours"),
    ("every month on the 1st pay rent",                    "automation", "Monthly on the 1st"),
    ("every tuesday and thursday at 6pm go for a run",     "automation", "Tuesday, Thursday"),
    # a time-of-day word next to the schedule is the time, not part of the task
    ("every monday morning check my email",                "automation", "Check my email · Every Monday at 8:00 am"),
    ("every weekday evening review my todos",              "automation", "Review my todos · Every weekday at 6:00 pm"),
    ("every friday afternoon send the weekly update",      "automation", "Send the weekly update · Every Friday at 2:00 pm"),
    ("every sunday night plan the week ahead",             "automation", "Plan the week ahead · Every Sunday at 9:00 pm"),
    ("daily in the evening write a journal entry",         "automation", "Write a journal entry · Every day at 6:00 pm"),
    ("check the logs at night every monday",               "automation", "Check the logs · Every Monday at 9:00 pm"),
    ("every monday morning at 7:30 check my email",        "automation", "Check my email · Every Monday at 7:30 am"),
    ("every monday and thursday mornings stretch",         "automation", "Stretch · Every Monday, Thursday at 8:00 am"),
    ("remind me to call mom tomorrow at 6pm",              "reminder",   "Call mom · Tomorrow, 6:00 pm"),
    ("remind me to drink water",                           "reminder",   "Drink water"),
    ("in 30 minutes stretch",                              "reminder",   "Stretch · Today, 10:55 am"),
    ("call mom at 5pm",                                    "reminder",   "Call mom · Today, 5:00 pm"),
    ("lunch with Sara friday 1pm",                         "event",      "Lunch with Sara · Today, 1:00 pm"),
    ("standup tomorrow 9:30am",                            "event",      "Standup · Tomorrow, 9:30 am"),
    ("dentist appointment on 12 oct at 4pm",               "event",      "Dentist appointment · Mon 12 Oct, 4:00 pm"),
    ("design review 2-3pm tomorrow",                       "event",      "2:00 pm–3:00 pm"),
    ("team offsite 20 nov all day",                        "event",      "Fri 20 Nov, all day"),
    ("buy oat milk",                                       "todo",       "Buy oat milk"),
    ("call the bank",                                      "todo",       "Call the bank"),
    ("todo: renew passport",                               "todo",       "Renew passport"),
    ("add todo: write tests for the parser",               "todo",       "Write tests for the parser"),
    ("submit expense report by friday",                    "todo",       "Submit expense report (by today)"),
]


@pytest.mark.parametrize("phrase,kind,expect", TABLE, ids=[t[0][:40] for t in TABLE])
def test_capture_classification_table(phrase, kind, expect):
    res = cap.classify_and_parse(phrase, NOW_DT)
    assert res["kind"] == kind, res
    assert expect in res["preview_text"], res


@pytest.mark.parametrize("phrase,time,prompt", [
    ("every monday morning check my email",             "08:00", "Check my email"),
    ("every weekday evening review my todos",           "18:00", "Review my todos"),
    ("every friday afternoon send the weekly update",   "14:00", "Send the weekly update"),
    ("every sunday night plan the week ahead",          "21:00", "Plan the week ahead"),
    ("every weekday in the morning check the news",     "08:00", "Check the news"),
    ("every day at night back up my notes",             "21:00", "Back up my notes"),
    ("every month on the 1st in the evening pay rent",  "18:00", "Pay rent"),
    ("every monday morning at 7:30 check my email",     "07:30", "Check my email"),   # an explicit time wins; the word still goes
    # words that belong to what the task does are kept, and the time falls back to the 09:00 default
    ("every day send a good morning message to the team", "09:00", "Send a good morning message to the team"),
    ("every day summarize my morning emails",           "09:00", "Summarize my morning emails"),
    ("every weekday write up last night's incidents",   "09:00", "Write up last night's incidents"),
])
def test_capture_time_of_day_words_become_the_time_not_the_prompt(phrase, time, prompt):
    res = cap.classify_and_parse(phrase, NOW_DT)
    assert res["kind"] == "automation", res
    d = res["draft"]
    assert (d["time"], d["prompt"]) == (time, prompt), d


def test_morning_brief_is_still_a_brief_not_a_time_word():
    d = cap.classify_and_parse("every weekday morning brief", NOW_DT)["draft"]
    assert d["action"] == "daily_brief"


def test_capture_never_produces_a_shell_command_automation():
    for phrase in ("every day at 9 run_local rm -rf /", "every hour ssh_command uptime", "every weekday run the script backup.sh"):
        res = cap.classify_and_parse(phrase, NOW_DT)
        assert res["draft"].get("action") in (None, "daily_brief") and res["draft"]["task_type"] in ("llm", "action")
        assert "command" not in res["draft"]


def test_capture_rejects_empty_and_oversized_input():
    with pytest.raises(cap.CaptureError):
        cap.classify_and_parse("   ", NOW_DT)
    with pytest.raises(cap.CaptureError):
        cap.classify_and_parse("x " * 400, NOW_DT)
    with pytest.raises(cap.CaptureError):
        cap.classify_and_parse("buy milk", NOW_DT, force="spaceship")


def test_forcing_a_kind_reparses_the_same_text():
    assert cap.classify_and_parse("lunch with Sara friday 1pm", NOW_DT, force="reminder")["kind"] == "reminder"
    assert cap.classify_and_parse("lunch with Sara friday 1pm", NOW_DT, force="todo")["kind"] == "todo"
    assert cap.classify_and_parse("buy milk tomorrow 5pm", NOW_DT, force="event")["draft"]["dtstart"] == "2026-10-03T17:00:00"


def test_automation_payload_converts_local_time_to_the_schedulers_utc():
    d = cap.classify_and_parse("every weekday at 7am summarize my email", NOW_DT)["draft"]
    p = cap.automation_payload(d, tz_offset_min=-300)        # UTC+5: 07:00 local is 02:00 UTC
    assert p["schedule"] == "cron" and p["cron_expression"] == "0 2 * * 1,2,3,4,5"
    # crossing midnight shifts the weekday too: Monday 01:00 in UTC+5 is Sunday 20:00 UTC
    p = cap.automation_payload(cap.classify_and_parse("every monday at 1am backup notes", NOW_DT)["draft"], tz_offset_min=-300)
    assert (p["schedule"], p["scheduled_day"], p["scheduled_time"]) == ("weekly", 6, "20:00")
    p = cap.automation_payload(cap.classify_and_parse("every day at 9:30am plan my day", NOW_DT)["draft"], tz_offset_min=-330)    # half-hour zone
    assert (p["schedule"], p["scheduled_time"]) == ("daily", "04:00")
    p = cap.automation_payload(cap.classify_and_parse("every 15 minutes check the build", NOW_DT)["draft"], tz_offset_min=-300)
    assert p["cron_expression"] == "*/15 * * * *"


async def test_capture_endpoint_returns_a_draft_and_writes_nothing(env):
    c, _, _, factory = env
    r = await c.post("/api/os/capture", json={"text": "remind me to call mom tomorrow at 6pm", "now": NOW, "tz_offset": 0})
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "reminder" and d["draft"] == {"title": "Call mom", "due": "2026-10-03T18:00"} and d["can_commit"] is True
    assert d["kinds"] == ["todo", "event", "reminder", "automation"]
    db = factory()
    assert db.query(Note).count() == 0 and db.query(ScheduledTask).count() == 0
    db.close()
    assert (await c.post("/api/os/capture", json={"text": "  "})).status_code == 400
    assert (await c.post("/api/os/capture", json={"text": "x", "kind": "nope"})).status_code == 400
    res = (await c.post("/api/os/capture", json={"text": "every day at 8", "now": NOW})).json()
    assert res["kind"] == "automation" and res["can_commit"] is False and res["draft"]["needs_prompt"] is True


async def test_commit_creates_real_rows_for_every_kind_and_undo_removes_them(env):
    c, _, _, factory = env
    body = lambda text, **kw: {"text": text, "now": NOW, "tz_offset": 0, **kw}  # noqa: E731

    async def capture_and_commit(text):
        draft = (await c.post("/api/os/capture", json=body(text))).json()
        r = await c.post("/api/os/capture/commit", json={"kind": draft["kind"], "draft": draft["draft"], "tz_offset": 0})
        assert r.status_code == 200, r.text
        return draft, r.json()

    # todo -> an item in the "Quick capture" checklist (created once, then reused)
    _, t1 = await capture_and_commit("buy oat milk")
    _, t2 = await capture_and_commit("todo: renew passport")
    assert t1["id"] == t2["id"] and t1["kind"] == "todo"
    db = factory()
    note = db.query(Note).filter(Note.id == t1["id"]).one()
    assert note.title == "Quick capture" and note.note_type == "checklist" and note.owner == "admin"
    assert [(i["text"], i["done"]) for i in json.loads(note.items)] == [("Buy oat milk", False), ("Renew passport", False)]
    db.close()
    # ... and it shows up in Today's todos straight away
    td = (await c.get("/api/os/today", params=Q)).json()["todos"]
    assert td["open"] == 2 and td["items"][0]["list"] == "Quick capture"

    # reminder -> a Note with a datetime due_date, the shape the Notes app fires reminders from
    _, rem = await capture_and_commit("remind me to call mom tomorrow at 6pm")
    db = factory()
    n = db.query(Note).filter(Note.id == rem["id"]).one()
    assert (n.title, n.due_date, n.owner) == ("Call mom", "2026-10-03T18:00", "admin")
    db.close()

    # event -> a CalendarEvent on the user's local calendar
    _, ev = await capture_and_commit("lunch with Sara friday 1pm")
    db = factory()
    e = db.query(CalendarEvent).filter(CalendarEvent.uid == ev["id"]).one()
    assert (e.summary, e.dtstart, e.dtend, e.all_day) == ("Lunch with Sara", datetime(2026, 10, 2, 13, 0), datetime(2026, 10, 2, 14, 0), False)
    assert e.calendar.owner == "admin" and e.calendar.source == "local"
    db.close()
    ag = (await c.get("/api/os/today", params=Q)).json()["agenda"]
    assert "Lunch with Sara" in [x["summary"] for x in ag["events"]] and "Call mom" in [x["summary"] for x in ag["reminders"]]

    # automation -> a ScheduledTask the scheduler will pick up (UTC times, next_run computed)
    _, au = await capture_and_commit("every weekday at 7am summarize my unread email")
    assert au["open"] == {"app": "automations", "props": {"intent": "show", "id": au["id"]}}
    db = factory()
    t = db.query(ScheduledTask).filter(ScheduledTask.id == au["id"]).one()
    assert (t.owner, t.status, t.task_type, t.schedule, t.name) == ("admin", "active", "llm", "cron", "Summarize my unread email")
    assert t.prompt == "Summarize my unread email" and t.next_run is not None and t.cron_expression == "0 7 * * 1,2,3,4,5"
    db.close()
    auto = (await c.get("/api/os/today", params=Q)).json()["automations"]
    assert auto["total"] == 1 and auto["upcoming"][0]["name"] == "Summarize my unread email"

    # a daily brief is an action task, never a shell command
    _, brief = await capture_and_commit("daily 8am morning brief")
    db = factory()
    t = db.query(ScheduledTask).filter(ScheduledTask.id == brief["id"]).one()
    assert (t.task_type, t.action, t.output_target) == ("action", "daily_brief", "notification")
    db.close()

    # undo removes exactly what was created
    for kind, created in (("reminder", rem), ("event", ev), ("automation", au), ("automation", brief)):
        assert (await c.post("/api/os/capture/undo", json={"kind": kind, "id": created["id"]})).status_code == 200
    assert (await c.post("/api/os/capture/undo", json={"kind": "todo", "id": t1["id"], "item_id": t1["item_id"]})).status_code == 200
    db = factory()
    assert db.query(CalendarEvent).count() == 0 and db.query(ScheduledTask).count() == 0
    assert [i["text"] for i in json.loads(db.query(Note).filter(Note.id == t1["id"]).one().items)] == ["Renew passport"]
    assert db.query(Note).filter(Note.id == rem["id"]).count() == 0
    db.close()
    assert (await c.post("/api/os/capture/undo", json={"kind": "event", "id": "nope"})).status_code == 404


async def test_commit_validates_and_refuses_shell_automations(env):
    c, *_ = env

    async def commit(kind, draft):
        return await c.post("/api/os/capture/commit", json={"kind": kind, "draft": draft, "tz_offset": 0})

    assert (await commit("todo", {"text": " "})).status_code == 400
    assert (await commit("todo", {"text": "x" * 501})).status_code == 400
    assert (await commit("reminder", {"title": "x", "due": "tomorrow"})).status_code == 400
    assert (await commit("reminder", {"title": "x", "due": "2026-13-45T99:99"})).status_code == 400
    assert (await commit("event", {"summary": "x", "dtstart": "garbage"})).status_code == 400
    assert (await commit("event", {"summary": "", "dtstart": "2026-10-03T10:00:00"})).status_code == 400
    assert (await commit("spaceship", {})).status_code == 400
    # an automation with nothing to do, and any attempt to smuggle in a shell-running action
    assert (await commit("automation", {"freq": "daily", "time": "08:00", "task_type": "llm", "prompt": ""})).status_code == 400
    for action in ("run_local", "ssh_command", "run_script"):
        r = await commit("automation", {"freq": "daily", "time": "08:00", "task_type": "action", "action": action, "prompt": "ls"})
        assert r.status_code == 400, action
    r = await commit("automation", {"freq": "daily", "time": "08:00", "task_type": "llm", "action": "run_local", "prompt": "ls"})
    assert r.status_code == 400


# =================================================================================== focus
async def test_focus_sessions_are_logged_atomically_and_summed_per_day(env, tmp_path):
    c, jarvis, app, _ = env
    r = await c.post("/api/os/focus", json={"minutes": 25, "label": "Write the report", "completed": True, "tz_offset": 0})
    assert r.status_code == 200 and r.json()["today"]["sessions"] == 1
    r = await c.post("/api/os/focus", json={"minutes": 10.5, "label": "", "completed": False, "tz_offset": 0})
    body = r.json()
    assert body["today"] == {"minutes": 35.5, "sessions": 1, "started": 2}                # only the completed one counts as a session
    assert len(body["week"]) == 7 and body["week"][-1]["minutes"] == 35.5 and body["week_minutes"] == 35.5

    stats = (await c.get("/api/os/focus/stats", params={"tz_offset": 0})).json()
    assert stats["today"]["minutes"] == 35.5
    assert (await c.get("/api/os/today", params={"tz_offset": 0})).json()["focus"] == {"minutes_today": 35.5, "sessions_today": 1, "week_minutes": 35.5}

    f = jarvis.jarvis_data_dir / "os" / "focus.json"
    assert f.exists() and not list(f.parent.glob("*.tmp"))
    data = json.loads(f.read_text(encoding="utf-8"))
    assert [s["label"] for s in data["sessions"]] == ["Write the report", ""] and all(s["user"] == "admin" for s in data["sessions"])

    # another user's sessions are separate
    async with client_for(app, user="other") as other:
        assert (await other.get("/api/os/focus/stats")).json()["today"]["minutes"] == 0

    for bad in ({"minutes": 0}, {"minutes": -3}, {"minutes": 241}, {"minutes": "abc"}, {}):
        assert (await c.post("/api/os/focus", json=bad)).status_code == 422


def test_focus_stats_use_the_callers_day_and_a_seven_day_window(tmp_path):
    store = FocusStore(tmp_path / "os" / "focus.json")
    now = 1_790_000_000.0
    store.log("u", 30, "a", ts=now)                                    # now
    store.log("u", 20, "b", ts=now - 3 * 86400)                        # 3 days ago
    store.log("u", 99, "old", ts=now - 10 * 86400)                     # outside the window
    store.log("v", 50, "other user", ts=now)
    st = store.stats("u", 0, now=now)
    assert st["today"]["minutes"] == 30 and st["week_minutes"] == 50 and [d["minutes"] for d in st["week"]].count(20) == 1
    assert store.stats("v", 0, now=now)["today"]["minutes"] == 50
    # a session at 23:30 UTC belongs to the NEXT local day for someone at UTC+5 (tz_offset -300)
    ts = datetime(2026, 10, 2, 23, 30, tzinfo=timezone.utc).timestamp()
    store.log("w", 10, ts=ts)
    assert store.stats("w", 0, now=ts + 60)["today"]["minutes"] == 10                    # UTC: still Oct 2
    assert store.stats("w", -300, now=ts + 60)["today"]["minutes"] == 10                 # UTC+5: it is 04:31 on Oct 3 and the session ran at 04:30
    assert store.stats("w", -300, now=ts - 5 * 3600)["today"]["minutes"] == 0            # 23:30 on Oct 2 for them: that session is tomorrow's
    with pytest.raises(ValueError):
        store.log("u", 0)
    (tmp_path / "os" / "focus.json").write_text("not json", encoding="utf-8")            # a corrupt file reads as empty, then recovers
    assert store.stats("u", 0, now=now)["today"]["minutes"] == 0
    store.log("u", 5, ts=now)
    assert store.stats("u", 0, now=now)["today"]["minutes"] == 5


# ================================================================================= notify
async def test_notify_adds_to_the_bell_once_per_key(env):
    c, *_ = env
    r = await c.post("/api/os/notify", json={"title": "Morning brief finished", "message": "Success", "severity": "success", "key": "run:1"})
    assert r.status_code == 200 and r.json()["duplicate"] is False
    again = await c.post("/api/os/notify", json={"title": "Morning brief finished", "message": "Success", "severity": "success", "key": "run:1"})
    assert again.json() == {"ok": True, "duplicate": True, "id": r.json()["id"]}
    await c.post("/api/os/notify", json={"title": "Other", "key": "run:2"})
    await c.post("/api/os/notify", json={"title": "No key"})
    await c.post("/api/os/notify", json={"title": "No key"})
    items = (await c.get("/api/os/notifications", params={"unread_only": "true"})).json()["notifications"]
    assert [n["title"] for n in items] == ["No key", "No key", "Other", "Morning brief finished"]       # newest first, de-duplicated by key
    assert (await c.post("/api/os/notify", json={"title": "", "message": "x"})).status_code == 422
    assert (await c.post("/api/os/notify", json={"title": "x", "severity": "loud"})).status_code == 422


# ============================================================================ run output text
def test_run_text_shows_why_a_run_failed_not_its_start_up_placeholder():
    """QA: a failed run keeps 'Starting…' in `result` and the reason in `error`; the dashboard summary and the
    Automations history must show the reason (same rule as static/os/js/runtext.js)."""
    from types import SimpleNamespace as R
    run_text = today_mod._run_text
    assert run_text(R(status="error", result="Starting…", error="RuntimeError: No model/endpoint configured")) == "RuntimeError: No model/endpoint configured"
    assert run_text(R(status="aborted", result="Queued — waiting for Odysseus to be idle…", error="Stopped by user")) == "Stopped by user"
    assert run_text(R(status="error", result="partial text", error="Timed out")) == "Timed out\n\npartial text"
    assert run_text(R(status="success", result="All good", error=None)) == "All good"
    assert run_text(R(status="running", result="Starting…", error=None)) == "Starting…"
    assert run_text(R(status="success", result="", error="")) == ""
