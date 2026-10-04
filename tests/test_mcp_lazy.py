"""Lazy stdio MCP servers: register from a cached tool list, start on first use, stop when idle.

Uses a real (tiny) stdio MCP server, tests/helpers/fake_mcp_server.py, so the whole path -
handshake, tool call, shutdown from another task - is exercised, not mocked.
"""
import asyncio
import gc
import logging
import sys
from pathlib import Path

import psutil
import pytest

from src import mcp_manager as mm
from src.mcp_manager import McpManager

SERVER = str(Path(__file__).parent / "helpers" / "fake_mcp_server.py")
PY = sys.executable


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "_tools_cache_path", lambda: str(tmp_path / "mcp_tools.json"))
    monkeypatch.setenv("ODYSSEUS_MCP_LAZY", "1")
    monkeypatch.setenv("ODYSSEUS_MCP_CONNECT_TIMEOUT", "20")


def _pid(result):
    assert result["exit_code"] == 0, result
    return int(result["stdout"].rsplit("|", 1)[1])


async def _wait_gone(pid, seconds=10.0):
    for _ in range(int(seconds * 10)):
        if not psutil.pid_exists(pid):
            return True
        await asyncio.sleep(0.1)
    return False


async def test_first_boot_learns_tools_then_stops_the_process():
    mgr = McpManager()
    assert await mgr.register_stdio("fake", "Fake", PY, [SERVER], {})
    assert not mgr._sessions and not mgr._stacks, "no process may be left running after learning the tools"
    st = mgr.get_server_status("fake")
    assert st["status"] == "connected" and st["tool_count"] == 1 and st["lazy"] and not st["running"]
    assert [t["name"] for t in mgr._tools["fake"]] == ["echo"]


async def test_cached_server_starts_on_first_call_and_stops_when_idle():
    first = McpManager()
    assert await first.register_stdio("fake", "Fake", PY, [SERVER], {})

    mgr = McpManager()  # a new boot: nothing running, tools come from the cache
    assert await mgr.register_stdio("fake", "Fake", PY, [SERVER], {})
    assert not mgr._sessions and not mgr._stacks
    assert [t["name"] for t in mgr._tools["fake"]] == ["echo"]
    assert "mcp__fake__echo" in {s["function"]["name"] for s in mgr.get_all_openai_schemas()}

    res = await mgr.call_tool("mcp__fake__echo", {"text": "hi"})
    pid = _pid(res)
    assert res["stdout"].startswith("hi|")
    assert psutil.pid_exists(pid) and "fake" in mgr._sessions

    # still busy / recently used -> kept
    assert await mgr.release_idle(3600) == []
    # idle -> stopped, but still advertised and restartable
    assert await mgr.release_idle(0) == ["fake"]
    assert await _wait_gone(pid)
    assert not mgr._sessions and mgr._tools["fake"]
    pid2 = _pid(await mgr.call_tool("mcp__fake__echo", {"text": "again"}))
    assert pid2 != pid
    await mgr.disconnect_all()
    assert await _wait_gone(pid2)


async def test_concurrent_first_calls_start_one_process():
    await McpManager().register_stdio("fake", "Fake", PY, [SERVER], {})
    mgr = McpManager()
    await mgr.register_stdio("fake", "Fake", PY, [SERVER], {})
    results = await asyncio.gather(*[mgr.call_tool("mcp__fake__echo", {"text": str(i)}) for i in range(4)])
    assert len({_pid(r) for r in results}) == 1
    await mgr.disconnect_all()


async def test_changed_definition_invalidates_the_cache():
    await McpManager().register_stdio("fake", "Fake", PY, [SERVER], {})
    mgr = McpManager()
    # different env => different fingerprint => must be started once to re-learn its tools
    assert await mgr.register_stdio("fake", "Fake", PY, [SERVER], {"X": "1"})
    assert not mgr._sessions  # learned, then stopped again
    assert mgr._tools["fake"]


async def test_non_lazy_mode_keeps_the_server_running(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_MCP_LAZY", "0")
    mgr = McpManager()
    assert await mgr.register_stdio("fake", "Fake", PY, [SERVER], {})
    assert "fake" in mgr._sessions
    assert mgr.start_idle_reaper() is None
    await mgr.disconnect_all()


async def test_bare_npx_is_refused_without_starting_anything(caplog):
    assert mm.launcher_needs_args("npx", [])
    assert mm.launcher_needs_args(r"C:\Program Files\nodejs\npx.cmd", ["  "])
    assert not mm.launcher_needs_args("npx", ["-y", "pkg"])
    assert not mm.launcher_needs_args(PY, [SERVER])
    mgr = McpManager()
    caplog.set_level(logging.WARNING)
    assert await mgr.connect_server("bad", "Filesystem", "stdio", command="npx", args=[]) is False
    st = mgr.get_server_status("bad")
    assert st["status"] == "error" and "no arguments" in st["error"]
    assert not mgr._sessions and not mgr._stacks
    # a definition problem is a warning without traceback, not an ERROR
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_hung_server_times_out_without_asyncio_noise(monkeypatch, caplog):
    monkeypatch.setenv("ODYSSEUS_MCP_CONNECT_TIMEOUT", "2")
    loop = asyncio.get_running_loop()
    problems = []
    loop.set_exception_handler(lambda l, ctx: problems.append(ctx))
    mgr = McpManager()
    caplog.set_level(logging.WARNING)
    ok = await mgr.connect_server("hang", "Hang", "stdio", command=PY, args=[SERVER, "hang"])
    assert ok is False
    assert mgr.get_server_status("hang")["status"] == "error"
    assert not mgr._stacks and not mgr._sessions
    gc.collect()
    await asyncio.sleep(0.3)
    assert problems == [], f"asyncio reported leftover task errors: {problems}"
    assert "cancel scope" not in caplog.text


async def test_cancelling_the_connect_cleans_up_in_the_owning_task(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_MCP_CONNECT_TIMEOUT", "60")
    loop = asyncio.get_running_loop()
    problems = []
    loop.set_exception_handler(lambda l, ctx: problems.append(ctx))
    mgr = McpManager()
    with pytest.raises(asyncio.TimeoutError):
        # exactly what app.py does around connect_all_enabled
        await asyncio.wait_for(mgr.connect_server("hang", "Hang", "stdio", command=PY, args=[SERVER, "hang"]), 2)
    gc.collect()
    await asyncio.sleep(0.5)
    assert problems == [], problems
    assert not mgr._sessions


async def test_crashed_server_is_restarted_by_the_next_call():
    await McpManager().register_stdio("fake", "Fake", PY, [SERVER, "die-after"], {})
    mgr = McpManager()
    await mgr.register_stdio("fake", "Fake", PY, [SERVER, "die-after"], {})
    pid = _pid(await mgr.call_tool("mcp__fake__echo", {"text": "one"}))
    assert await _wait_gone(pid)           # the server exits on its own after answering
    # the session object is dead now; the call must notice, start a fresh server and answer
    pid2 = _pid(await mgr.call_tool("mcp__fake__echo", {"text": "two"}))
    assert pid2 != pid
    await mgr.disconnect_all()


async def test_one_broken_user_server_does_not_block_the_next(monkeypatch):
    """connect_all_enabled isolates servers: the first (bare npx) must not stop the second."""
    from types import SimpleNamespace
    import json
    rows = [
        SimpleNamespace(id="a", name="Bare", transport="stdio", command="npx", args="[]", env="{}", url=None),
        SimpleNamespace(id="b", name="Fake", transport="stdio", command=PY, args=json.dumps([SERVER]), env="{}", url=None),
    ]

    class FakeQuery:
        def filter(self, *a, **k):
            return self

        def all(self):
            return rows

    class FakeDb:
        def query(self, *a):
            return FakeQuery()

        def close(self):
            pass

    stub = SimpleNamespace(McpServer=SimpleNamespace(is_enabled=None), SessionLocal=lambda: FakeDb())
    monkeypatch.setitem(sys.modules, "src.database", stub)
    mgr = McpManager()
    await mgr.connect_all_enabled()
    assert mgr.get_server_status("a")["status"] == "error"
    assert mgr.get_server_status("b")["status"] == "connected"
    assert [t["name"] for t in mgr._tools["b"]] == ["echo"]
    await mgr.disconnect_all()


def test_non_json_stdout_line_is_one_warning_not_a_traceback(caplog):
    logger = logging.getLogger("mcp.client.stdio")
    caplog.set_level(logging.DEBUG, logger="mcp.client.stdio")
    from pydantic import ValidationError
    from mcp import types

    def emit(line):
        try:
            types.JSONRPCMessage.model_validate_json(line)
        except ValidationError:
            logger.exception("Failed to parse JSONRPC message from server")

    # caplog's handler sits on the root logger; the filter is on the "mcp.client.stdio" logger
    emit("Microsoft Windows [Version 10.0]")
    emit("Microsoft Windows [Version 10.0]")   # same line again: suppressed
    emit("(c) Microsoft Corporation")
    recs = [r for r in caplog.records if r.name == "mcp.client.stdio"]
    assert len(recs) == 2
    assert all(r.levelno == logging.WARNING and r.exc_info is None for r in recs)
    assert "Microsoft Windows" in recs[0].getMessage()
