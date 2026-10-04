"""The chat page asks "is anything running for this chat?" every time a chat is opened.
"Nothing" is the normal answer and must be a 200, not a 404 the browser logs as a network error - while someone
else's chat / research must still look like it does not exist (404)."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _req(user=None):
    return SimpleNamespace(state=SimpleNamespace(current_user=user), client=SimpleNamespace(host="127.0.0.1"),
                           headers={}, cookies={}, url=SimpleNamespace(path="/x"))


# ------------------------------------------------------------------ research status
@pytest.fixture()
def research(tmp_path, monkeypatch):
    import routes.research_routes as rr

    monkeypatch.setattr(rr, "DEEP_RESEARCH_DIR", str(tmp_path))
    rh = MagicMock()
    rh._active_tasks = {}
    rh.get_status.return_value = None
    router = rr.setup_research_routes(rh)
    target = next(r.endpoint for r in router.routes if getattr(r, "path", "") == "/api/research/status/{session_id}")
    return rh, target, tmp_path


SID = "123e4567-e89b-12d3-a456-426614174000"


def test_research_status_no_research_is_200_none(research):
    rh, target, _ = research
    assert asyncio.run(target(session_id=SID, request=_req("alice"))) == {"status": "none"}


def test_research_status_of_someone_elses_task_is_still_404(research):
    rh, target, _ = research
    rh._active_tasks = {SID: {"owner": "alice", "status": "running"}}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id=SID, request=_req("bob")))
    assert exc.value.status_code == 404


def test_research_status_of_someone_elses_finished_task_is_still_404(research):
    rh, target, tmp = research
    (tmp / f"{SID}.json").write_text(json.dumps({"owner": "alice"}), encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id=SID, request=_req("bob")))
    assert exc.value.status_code == 404


def test_research_status_own_running_task_is_returned(research):
    rh, target, _ = research
    rh._active_tasks = {SID: {"owner": "alice", "status": "running"}}
    rh.get_status.return_value = {"status": "running", "progress": {}}
    assert asyncio.run(target(session_id=SID, request=_req("alice")))["status"] == "running"


# ------------------------------------------------------------------ stream status
@pytest.fixture()
def chat(monkeypatch):
    import core.database as cdb
    import routes.chat_routes as cr
    from tests.helpers.sqlite_db import make_temp_sqlite

    SessionLocal, engine, _tmp = make_temp_sqlite(cdb.Base.metadata)
    monkeypatch.setattr(cr, "SessionLocal", SessionLocal)
    # chat_routes holds the function object it imported at load time; patch the module globals THAT function
    # reads (other tests may have swapped routes.session_routes in sys.modules since).
    g = cr._verify_session_owner.__globals__
    monkeypatch.setitem(g, "SessionLocal", SessionLocal)
    monkeypatch.setitem(g, "_auth_disabled", lambda: False)
    router = cr.setup_chat_routes(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
    target = next(r.endpoint for r in router.routes if getattr(r, "path", "") == "/api/chat/stream_status/{session_id}")
    db = SessionLocal()
    db.add(cdb.Session(id="mine", name="m", endpoint_url="", model="", owner="alice"))
    db.add(cdb.Session(id="theirs", name="t", endpoint_url="", model="", owner="bob"))
    db.commit()
    db.close()
    yield cr, target
    engine.dispose()


def test_stream_status_idle_for_own_chat_without_stream(chat):
    cr, target = chat
    assert asyncio.run(target(request=_req("alice"), session_id="mine")) == {"status": "idle"}


def test_stream_status_idle_for_a_chat_that_has_no_row_yet(chat):
    cr, target = chat
    assert asyncio.run(target(request=_req("alice"), session_id="brand-new-chat")) == {"status": "idle"}


def test_stream_status_someone_elses_chat_is_still_404(chat):
    cr, target = chat
    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(request=_req("alice"), session_id="theirs"))
    assert exc.value.status_code == 404


def test_stream_status_reports_a_live_stream(chat):
    cr, target = chat
    cr._active_streams["mine"] = {"status": "streaming", "mode": "chat"}
    try:
        assert asyncio.run(target(request=_req("alice"), session_id="mine"))["status"] == "streaming"
    finally:
        cr._active_streams.pop("mine", None)
