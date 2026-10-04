"""A scheduled task delivering to a chat session must not insert the session twice.

The scheduler inserts the sessions row itself and then calls
SessionManager.ensure_task_session(); that used to look only at the in-memory cache (which only holds
recent non-empty sessions), miss, and INSERT the same id again -> "UNIQUE constraint failed: sessions.id"
logged at ERROR for every new task session.
"""
import logging
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import core.database as cdb
import core.session_manager as sm_mod
from tests.helpers.sqlite_db import make_temp_sqlite


@pytest.fixture()
def manager(monkeypatch):
    SessionLocal, engine, tmp = make_temp_sqlite(cdb.Base.metadata)
    monkeypatch.setattr(sm_mod, "SessionLocal", SessionLocal)
    mgr = sm_mod.SessionManager()
    assert mgr.sessions == {}
    yield mgr, SessionLocal
    engine.dispose()


def _insert_like_the_scheduler(SessionLocal, sid):
    db = SessionLocal()
    try:
        db.add(cdb.Session(id=sid, name="[Task] x", endpoint_url="http://ep", model="m", owner="alice",
                           folder="Tasks", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        db.commit()
    finally:
        db.close()


def _count(SessionLocal, sid):
    db = SessionLocal()
    try:
        return db.query(cdb.Session).filter(cdb.Session.id == sid).count()
    finally:
        db.close()


def test_existing_row_not_in_cache_is_adopted_not_reinserted(manager, caplog):
    mgr, SessionLocal = manager
    _insert_like_the_scheduler(SessionLocal, "task-sess-1")
    task = SimpleNamespace(session_id=None)
    caplog.set_level(logging.ERROR)

    session = mgr.ensure_task_session("task-sess-1", "[Task] x", "http://ep", "m", owner="alice", task=task)

    assert session.id == "task-sess-1" and mgr.sessions["task-sess-1"] is session
    assert task.session_id == "task-sess-1"
    assert _count(SessionLocal, "task-sess-1") == 1
    assert "UNIQUE" not in caplog.text and not [r for r in caplog.records if r.levelno >= logging.ERROR]
    # and a second call is a plain cache hit
    assert mgr.ensure_task_session("task-sess-1", "[Task] x", "http://ep", "m", owner="alice") is session


def test_missing_session_is_still_created(manager):
    mgr, SessionLocal = manager
    task = SimpleNamespace(session_id=None)
    session = mgr.ensure_task_session("brand-new", "[Task] y", "http://ep", "m", owner="alice", task=task)
    assert _count(SessionLocal, "brand-new") == 1
    assert session.name == "[Task] y" and task.session_id == "brand-new"


def test_two_runs_racing_on_the_same_id_insert_once(manager, caplog):
    mgr, SessionLocal = manager
    caplog.set_level(logging.ERROR)
    errors, results = [], []
    barrier = threading.Barrier(4)

    def run():
        barrier.wait()
        try:
            results.append(mgr.ensure_task_session("racy", "[Task] z", "http://ep", "m", owner="alice"))
        except Exception as e:  # pragma: no cover - the failure being tested
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert errors == []
    assert len({id(r) for r in results}) == 1
    assert _count(SessionLocal, "racy") == 1
    assert "UNIQUE" not in caplog.text
