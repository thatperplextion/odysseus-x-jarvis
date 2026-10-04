"""GET /api/os/session is the OS page's liveness probe: it must answer promptly while the server is busy.

Two things used to make it queue behind unrelated work and look like a hung server:
  * the guard dependency was a plain ``def`` -> run in the shared worker-thread pool;
  * the handler read its file via ``asyncio.to_thread`` -> the shared default executor.
Here both pools are saturated with slow handlers and the probe must still come back immediately.
"""
import asyncio
import json
import time

import pytest

from tests.helpers.os_app import FakeJarvis, build_app, client_for


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    from routes import os_routes

    os_routes._SESSION_CACHE.clear()
    jarvis = FakeJarvis(tmp_path / "jarvis")
    await jarvis.start()
    app = build_app(jarvis, admins=("admin",))

    @app.get("/slow-sync")
    def slow_sync():                       # runs in anyio's worker-thread pool (40 slots)
        time.sleep(1.5)
        return {"ok": True}

    @app.get("/slow-thread")
    async def slow_thread():               # runs in the event loop's default executor
        await asyncio.to_thread(time.sleep, 1.5)
        return {"ok": True}

    async with client_for(app, user="admin") as client:
        yield client, jarvis
    await jarvis.stop()


async def test_session_probe_answers_while_both_worker_pools_are_saturated(env):
    client, _ = env
    busy = [asyncio.create_task(client.get("/slow-sync")) for _ in range(90)]
    busy += [asyncio.create_task(client.get("/slow-thread")) for _ in range(90)]
    await asyncio.sleep(0.4)               # let the slow handlers occupy every worker

    t0 = time.perf_counter()
    r = await client.get("/api/os/session")
    took = time.perf_counter() - t0

    assert r.status_code == 200 and r.json()["boot_id"]
    assert took < 0.5, f"liveness probe took {took:.2f}s while workers were busy"
    for t in busy:
        t.cancel()
    await asyncio.gather(*busy, return_exceptions=True)


async def test_session_probe_answers_while_the_event_loop_is_awaiting_slow_io(env):
    client, _ = env

    async def slow_async():
        await asyncio.sleep(1.0)

    busy = [asyncio.create_task(slow_async()) for _ in range(200)]
    t0 = time.perf_counter()
    r = await client.get("/api/os/session")
    assert r.status_code == 200 and time.perf_counter() - t0 < 0.5
    for t in busy:
        t.cancel()
    await asyncio.gather(*busy, return_exceptions=True)


async def test_session_roundtrip_and_preexisting_file(env, tmp_path):
    client, jarvis = env
    # a session saved by an earlier run is returned on the first read
    d = jarvis.jarvis_data_dir / "os_sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / "admin.json").write_text(json.dumps({"windows": [1, 2]}), encoding="utf-8")
    r = await client.get("/api/os/session")
    assert r.json()["session"] == {"windows": [1, 2]}
    # PUT writes through to disk and to the in-memory copy GET serves
    assert (await client.put("/api/os/session", json={"windows": [3]})).json() == {"ok": True}
    assert (await client.get("/api/os/session")).json()["session"] == {"windows": [3]}
    assert json.loads((d / "admin.json").read_text(encoding="utf-8")) == {"windows": [3]}


async def test_non_admin_is_still_refused(env, monkeypatch):
    client, jarvis = env
    from tests.helpers.os_app import build_app as _b, client_for as _c

    app = _b(jarvis, admins=("admin",))
    async with _c(app, user="bob") as other:
        assert (await other.get("/api/os/session")).status_code == 403
