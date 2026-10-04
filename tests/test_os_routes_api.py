"""Functional tests for /api/os/* against the real sandbox, filesystem, kernel and terminal."""

import asyncio
import json
import os
import subprocess
import sys
import time

import psutil
import pytest

from tests.helpers.os_app import FakeJarvis, build_app, client_for

PY = f'"{sys.executable}"'


async def py_cmd(c, code):
    """A command that runs ``code`` with this interpreter, quoted for the default shell
    (PowerShell needs ``&`` to invoke a quoted path; Git Bash wants forward slashes)."""
    shell = (await c.get("/api/os/terminal/shells")).json()["shells"][0]["id"]
    exe = sys.executable
    if shell in ("powershell", "pwsh"):
        return f'& "{exe}" -c "{code}"'
    if shell == "cmd":
        return f'"{exe}" -c "{code}"'
    return f'"{exe.replace(chr(92), "/")}" -c "{code}"'


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    jarvis = FakeJarvis(tmp_path / "jarvis")
    await jarvis.start()
    app = build_app(jarvis, admins=("admin", "admin2"))
    async with client_for(app, user="admin") as client:
        yield client, jarvis, app
    await jarvis.stop()


def home(jarvis):
    return jarvis.os_sandbox.get_mount("Home").root


# ------------------------------------------------------------------------ boot
async def test_boot_describes_the_machine(env):
    c, jarvis, _ = env
    boot = (await c.get("/api/os/boot")).json()
    assert boot["ready"] is True and boot["user"] == "admin" and boot["version"] == "test"
    assert boot["mounts"][0]["name"] == "Home" and boot["mounts"][0]["path"] == "/Home"
    assert boot["system"]["hostname"] and boot["system"]["threads"] >= 1
    assert boot["shells"] and all("path" not in s for s in boot["shells"]), "real shell paths must not be exposed"
    assert boot["limits"]["max_upload_bytes"] == 5000


# ----------------------------------------------------------------------- files
async def test_list_read_write_roundtrip(env):
    c, jarvis, _ = env
    w = await c.put("/api/os/fs/write", json={"path": "/Home/Documents/a.txt", "content": "hello\nworld"})
    assert w.status_code == 200 and w.json()["created"] is True
    listing = (await c.get("/api/os/fs/list", params={"path": "/Home/Documents"})).json()
    assert [e["name"] for e in listing["entries"]] == ["a.txt"]
    doc = (await c.get("/api/os/fs/read", params={"path": "/Home/Documents/a.txt"})).json()
    assert doc["content"] == "hello\nworld" and doc["eol"] == "lf"
    assert (home(jarvis) / "Documents" / "a.txt").read_text() == "hello\nworld"


async def test_saving_over_a_changed_file_is_a_409_and_does_not_overwrite(env):
    c, jarvis, _ = env
    await c.put("/api/os/fs/write", json={"path": "/Home/n.txt", "content": "v1"})
    opened = (await c.get("/api/os/fs/read", params={"path": "/Home/n.txt"})).json()
    (home(jarvis) / "n.txt").write_text("changed elsewhere")
    r = await c.put("/api/os/fs/write", json={"path": "/Home/n.txt", "content": "mine", "version": opened["version"]})
    assert r.status_code == 409
    assert (home(jarvis) / "n.txt").read_text() == "changed elsewhere"
    ok = await c.put("/api/os/fs/write", json={"path": "/Home/n.txt", "content": "mine"})  # no version: last write wins
    assert ok.status_code == 200


@pytest.mark.parametrize("path", ["/Home/../x", "/Nope/x", "C:\\Windows\\win.ini", "/etc/passwd", "relative.txt", "/Home/a:b"])
async def test_paths_outside_the_sandbox_are_refused(env, path):
    c, *_ = env
    r = await c.get("/api/os/fs/read", params={"path": path})
    assert r.status_code in (400, 403, 404), (path, r.status_code, r.text)
    assert "content" not in r.text


async def test_errors_use_proper_status_codes(env):
    c, jarvis, _ = env
    assert (await c.get("/api/os/fs/read", params={"path": "/Home/missing.txt"})).status_code == 404
    (home(jarvis) / "bin.dat").write_bytes(b"\x00\x01")
    assert (await c.get("/api/os/fs/read", params={"path": "/Home/bin.dat"})).status_code == 415
    (home(jarvis) / "big.txt").write_text("x" * 3000)
    assert (await c.get("/api/os/fs/read", params={"path": "/Home/big.txt"})).status_code == 413


async def test_mkdir_create_rename_transfer_delete_and_trash(env):
    c, jarvis, _ = env
    assert (await c.post("/api/os/fs/mkdir", json={"path": "/Home/proj"})).status_code == 200
    assert (await c.post("/api/os/fs/mkdir", json={"path": "/Home/proj"})).status_code == 409
    assert (await c.post("/api/os/fs/create", json={"path": "/Home/proj/a.txt"})).status_code == 200
    r = await c.post("/api/os/fs/rename", json={"path": "/Home/proj/a.txt", "name": "b.txt"})
    assert r.json()["path"] == "/Home/proj/b.txt"
    assert (await c.post("/api/os/fs/rename", json={"path": "/Home/proj/b.txt", "name": "../evil"})).status_code == 400
    cp = await c.post("/api/os/fs/transfer", json={"src": "/Home/proj/b.txt", "dst_dir": "/Home", "copy": True})
    assert cp.json()["path"] == "/Home/b.txt"
    mv = await c.post("/api/os/fs/transfer", json={"src": "/Home/b.txt", "dst_dir": "/Home/proj", "name": "c.txt"})
    assert mv.json()["path"] == "/Home/proj/c.txt"

    d = await c.post("/api/os/fs/delete", json={"path": "/Home/proj/c.txt"})
    assert d.status_code == 200 and not (home(jarvis) / "proj" / "c.txt").exists()
    items = (await c.get("/api/os/fs/trash")).json()["items"]
    assert [i["name"] for i in items] == ["c.txt"] and items[0]["original"] == "/Home/proj/c.txt"
    restored = await c.post("/api/os/fs/trash/restore", json={"id": items[0]["id"]})
    assert restored.json()["path"] == "/Home/proj/c.txt"
    await c.post("/api/os/fs/delete", json={"path": "/Home/proj/c.txt"})
    assert (await c.post("/api/os/fs/trash/empty")).json()["emptied"] == 1
    assert (await c.get("/api/os/fs/trash")).json()["items"] == []


async def test_deleting_a_mount_root_or_missing_path_fails(env):
    c, *_ = env
    assert (await c.post("/api/os/fs/delete", json={"path": "/Home"})).status_code == 400
    assert (await c.post("/api/os/fs/delete", json={"path": "/Home/nothing"})).status_code == 404


async def test_search(env):
    c, jarvis, _ = env
    (home(jarvis) / "Documents" / "Report 2026.md").write_text("x")
    r = (await c.get("/api/os/fs/search", params={"path": "/Home", "q": "report"})).json()
    assert [x["path"] for x in r["results"]] == ["/Home/Documents/Report 2026.md"]


# --------------------------------------------------------------------- upload
async def test_streaming_upload_and_overwrite_rules(env):
    c, jarvis, _ = env
    r = await c.put("/api/os/fs/upload", params={"path": "/Home/up.bin"}, content=b"abcdef")
    assert r.status_code == 200 and r.json()["size"] == 6
    assert (home(jarvis) / "up.bin").read_bytes() == b"abcdef"
    assert (await c.put("/api/os/fs/upload", params={"path": "/Home/up.bin"}, content=b"zzz")).status_code == 409
    assert (home(jarvis) / "up.bin").read_bytes() == b"abcdef"
    ok = await c.put("/api/os/fs/upload", params={"path": "/Home/up.bin", "overwrite": "true"}, content=b"zzz")
    assert ok.status_code == 200 and (home(jarvis) / "up.bin").read_bytes() == b"zzz"


async def test_oversized_upload_is_413_and_leaves_nothing(env):
    c, jarvis, _ = env
    r = await c.put("/api/os/fs/upload", params={"path": "/Home/huge.bin"}, content=b"x" * 6000)
    assert r.status_code == 413
    assert not any(p.name.startswith(("huge", ".huge")) for p in home(jarvis).iterdir())


async def test_upload_into_a_readonly_mount_or_outside_is_refused(env, tmp_path):
    c, jarvis, _ = env
    ro = tmp_path / "ro"
    ro.mkdir()
    await c.post("/api/os/mounts", json={"name": "Ref", "path": str(ro), "readonly": True})
    assert (await c.put("/api/os/fs/upload", params={"path": "/Ref/x.bin"}, content=b"x")).status_code == 403
    assert (await c.put("/api/os/fs/upload", params={"path": "/Home/../x.bin"}, content=b"x")).status_code == 400
    assert list(ro.iterdir()) == []


# ------------------------------------------------------------------ raw/download
async def test_raw_serves_images_inline_with_a_locked_down_policy(env):
    c, jarvis, _ = env
    (home(jarvis) / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    r = await c.get("/api/os/fs/raw", params={"path": "/Home/pic.png"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["content-disposition"].startswith("inline")
    assert "sandbox" in r.headers["content-security-policy"]


@pytest.mark.parametrize("name,body", [("page.html", b"<script>alert(1)</script>"), ("v.svg", b"<svg onload=alert(1)/>"), ("a.js", b"alert(1)"), ("d.pdf", b"%PDF-1.4")])
async def test_active_content_is_never_served_inline(env, name, body):
    """Inline HTML/SVG from the app origin would run script with the admin's session."""
    c, jarvis, _ = env
    (home(jarvis) / name).write_bytes(body)
    r = await c.get("/api/os/fs/raw", params={"path": f"/Home/{name}"})
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["content-type"] == "application/octet-stream"


async def test_download_flag_forces_attachment_for_images(env):
    c, jarvis, _ = env
    (home(jarvis) / "pic.png").write_bytes(b"\x89PNG" + b"0" * 10)
    r = await c.get("/api/os/fs/raw", params={"path": "/Home/pic.png", "download": "true"})
    assert r.headers["content-disposition"].startswith("attachment")


# ----------------------------------------------------------------------- mounts
async def test_mounts_can_be_added_changed_removed_and_persist(env, tmp_path):
    c, jarvis, _ = env
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "f.txt").write_text("hi")
    added = (await c.post("/api/os/mounts", json={"name": "Proj", "path": str(proj)})).json()
    assert [m["name"] for m in added["mounts"]] == ["Home", "Proj"]
    assert (await c.get("/api/os/fs/read", params={"path": "/Proj/f.txt"})).json()["content"] == "hi"

    ro = (await c.patch("/api/os/mounts/Proj", json={"readonly": True})).json()
    assert ro["mounts"][1]["readonly"] is True
    assert (await c.put("/api/os/fs/write", json={"path": "/Proj/f.txt", "content": "x"})).status_code == 403

    # persisted: a fresh SandboxConfig (as after a restart) sees it, read-only included
    from services.os_shell.sandbox import SandboxConfig

    reloaded = SandboxConfig(jarvis.jarvis_data_dir).load()
    assert reloaded.get_mount("Proj").readonly is True

    removed = (await c.delete("/api/os/mounts/Proj")).json()
    assert [m["name"] for m in removed["mounts"]] == ["Home"]
    assert (await c.get("/api/os/fs/read", params={"path": "/Proj/f.txt"})).status_code == 403
    assert SandboxConfig(jarvis.jarvis_data_dir).load().get_mount("Proj") is None


async def test_mount_validation(env, tmp_path):
    c, *_ = env
    f = tmp_path / "file.txt"
    f.write_text("x")
    assert (await c.post("/api/os/mounts", json={"name": "Bad", "path": str(f)})).status_code == 400
    assert (await c.post("/api/os/mounts", json={"name": "Bad", "path": str(tmp_path / "missing")})).status_code == 400
    assert (await c.post("/api/os/mounts", json={"name": "../x", "path": str(tmp_path)})).status_code == 400
    assert (await c.post("/api/os/mounts", json={"name": "Root", "path": os.path.abspath(os.sep)})).status_code == 400
    assert (await c.post("/api/os/mounts", json={"name": "home", "path": str(tmp_path)})).status_code == 400  # duplicate
    assert (await c.delete("/api/os/mounts/Home")).status_code == 400
    assert (await c.delete("/api/os/mounts/Nope")).status_code == 400


# -------------------------------------------------------------------- processes
async def test_process_list_and_system_snapshot(env):
    c, *_ = env
    procs = (await c.get("/api/os/processes")).json()["processes"]
    me = next(p for p in procs if p["pid"] == os.getpid())
    assert me["is_server"] and me["protected"]
    assert all(0 <= p["cpu"] <= 100 for p in procs)
    snap = (await c.get("/api/os/system")).json()
    assert 0 <= snap["cpu"]["percent"] <= 100 and snap["memory"]["total"] > 0


async def test_terminating_a_process_works_and_is_audited(env):
    c, jarvis, _ = env
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        r = await c.post(f"/api/os/processes/{child.pid}/terminate", json={"force": True})
        assert r.status_code == 200 and r.json()["result"] == "killed"
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
    events = [e for e in jarvis.security.get_security_events() if e.event_type == "process_terminate"]
    assert events and events[-1].details["pid"] == child.pid and events[-1].details["user"] == "admin"


async def test_the_server_and_missing_processes_cannot_be_terminated(env):
    c, jarvis, _ = env
    r = await c.post(f"/api/os/processes/{os.getpid()}/terminate", json={"force": True})
    assert r.status_code == 403 and "server" in r.text
    assert psutil.pid_exists(os.getpid())
    assert (await c.post("/api/os/processes/4194000/terminate", json={})).status_code == 404
    refused = [e for e in jarvis.security.get_security_events() if e.event_type == "process_terminate_refused"]
    assert refused


# ------------------------------------------------------------------------- jobs
async def _wait_job(c, job_id, states=("completed", "failed", "cancelled"), timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = (await c.get(f"/api/os/jobs/{job_id}")).json()
        if j["state"] in states:
            return j
        await asyncio.sleep(0.1)
    raise AssertionError("job did not finish")


async def test_background_job_runs_in_home_and_reports_output(env):
    c, jarvis, _ = env
    r = await c.post("/api/os/jobs", json={"command": f'{PY} -c "import os; print(os.getcwd())"'})
    job = await _wait_job(c, r.json()["id"])
    assert job["state"] == "completed" and job["source"] == "taskmanager"
    assert os.path.realpath(job["result"]["output"].strip()) == os.path.realpath(str(home(jarvis)))
    listed = (await c.get("/api/os/jobs")).json()["jobs"]
    assert any(j["id"] == r.json()["id"] for j in listed)
    assert "output" not in json.dumps(listed), "the list view stays small; output comes from /jobs/{id}"


async def test_failed_job_and_cancel(env):
    c, *_ = env
    bad = await c.post("/api/os/jobs", json={"command": f'{PY} -c "import sys; sys.exit(5)"'})
    assert (await _wait_job(c, bad.json()["id"]))["state"] == "failed"
    slow = await c.post("/api/os/jobs", json={"command": f'{PY} -c "import time; time.sleep(60)"'})
    jid = slow.json()["id"]
    await _wait_job(c, jid, states=("running",))
    assert (await c.post(f"/api/os/jobs/{jid}/cancel")).status_code == 200
    assert (await _wait_job(c, jid))["state"] == "cancelled"
    assert (await c.post(f"/api/os/jobs/{jid}/cancel")).status_code == 409
    assert (await c.get("/api/os/jobs/nope")).status_code == 404


async def test_job_cwd_must_be_inside_a_mount(env, tmp_path):
    c, *_ = env
    r = await c.post("/api/os/jobs", json={"command": "echo hi", "cwd": str(tmp_path)})
    assert r.status_code == 403


# --------------------------------------------------------------------- terminal
async def _exec(c, command, **kw):
    # Browsers always send Accept-Encoding: gzip; the app's GZipMiddleware must leave this stream alone.
    r = await c.post("/api/os/terminal/exec", json={"command": command, **kw}, headers={"accept-encoding": "gzip"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "content-encoding" not in r.headers, "a gzipped stream is buffered until it ends: output would not appear live"
    frames = [f for f in r.text.split("\n\n") if f.strip()]
    assert all(f.startswith("data: ") for f in frames), frames[:2]
    return [json.loads(f[len("data: "):]) for f in frames]


async def test_terminal_streams_start_out_exit_events_and_tracks_cwd(env):
    c, jarvis, _ = env
    events = await _exec(c, "cd Documents")
    assert events[0]["t"] == "start" and events[-1]["t"] == "exit"
    cwd = events[-1]["cwd"]
    assert os.path.basename(cwd) == "Documents" and events[-1]["code"] == 0
    shells = (await c.get("/api/os/terminal/shells")).json()["shells"]
    pwd = {"cmd": "cd", "powershell": "(Get-Location).Path", "pwsh": "(Get-Location).Path"}.get(shells[0]["id"], "pwd")
    out = "".join(e["d"] for e in await _exec(c, pwd, cwd=cwd) if e["t"] == "out")
    assert "Documents" in out


async def test_terminal_accepts_a_virtual_cwd_and_defaults_to_home(env):
    c, jarvis, _ = env
    shells = (await c.get("/api/os/terminal/shells")).json()["shells"]
    pwd = {"cmd": "cd", "powershell": "(Get-Location).Path", "pwsh": "(Get-Location).Path"}.get(shells[0]["id"], "pwd")
    default_out = "".join(e["d"] for e in await _exec(c, pwd) if e["t"] == "out")
    assert os.path.basename(str(home(jarvis))) in default_out
    virtual = "".join(e["d"] for e in await _exec(c, pwd, cwd="/Home/Music") if e["t"] == "out")
    assert "Music" in virtual


async def test_terminal_reports_exit_codes(env):
    c, *_ = env
    events = await _exec(c, await py_cmd(c, "import sys; sys.exit(7)"))
    assert events[-1]["code"] == 7


async def test_terminal_errors_are_clean_http_errors(env):
    c, *_ = env
    assert (await c.post("/api/os/terminal/exec", json={"command": "echo", "shell": "nope"})).status_code == 400
    assert (await c.post("/api/os/terminal/exec", json={"command": "echo", "cwd": "/Home/does-not-exist"})).status_code in (400, 404)
    assert (await c.post("/api/os/terminal/exec", json={"command": ""})).status_code == 422


async def test_terminal_commands_are_audited_with_user_and_cwd(env):
    c, jarvis, _ = env
    await _exec(c, "echo audited-marker")
    ev = [e for e in jarvis.security.get_security_events() if e.event_type == "terminal_exec"]
    assert ev and "audited-marker" in ev[-1].details["command"] and ev[-1].details["user"] == "admin"


async def test_terminal_is_not_sandboxed_but_the_secrets_are_scrubbed(env, monkeypatch):
    """It is a real shell (admin-only, audited); it must still not hand over the server's API keys."""
    c, *_ = env
    monkeypatch.setenv("ODY_ROUTE_TEST_API_KEY", "sk-leak-me")
    shells = (await c.get("/api/os/terminal/shells")).json()["shells"]
    probe = {"cmd": "echo [%ODY_ROUTE_TEST_API_KEY%]", "powershell": "$env:ODY_ROUTE_TEST_API_KEY", "pwsh": "$env:ODY_ROUTE_TEST_API_KEY"}.get(
        shells[0]["id"], "echo [$ODY_ROUTE_TEST_API_KEY]")
    out = "".join(e["d"] for e in await _exec(c, probe) if e["t"] == "out")
    assert "sk-leak-me" not in out


# -------------------------------------------------------------------- assistant
async def test_assistant_runs_safe_requests_immediately(env):
    c, jarvis, _ = env
    jarvis.subsystems["interface"] = type("I", (), {
        "get_system_metrics": staticmethod(lambda: {"cpu": {"percent": 12.5}, "memory": {"percent": 40}, "disk": {"percent": 70}})
    })()
    r = (await c.post("/api/os/assistant", json={"message": "cpu"})).json()
    assert r["success"] is True and r["requires_confirmation"] is False
    assert r["response"] == "CPU: 12.5%, Memory: 40.0%, Disk: 70.0%"


async def test_assistant_asks_before_running_a_command_then_runs_it(env):
    c, jarvis, _ = env
    asked = (await c.post("/api/os/assistant", json={"message": "run echo from-assistant"})).json()
    assert asked["requires_confirmation"] is True and asked["confirm_token"]
    assert asked["action"]["kind"] == "run_command" and asked["action"]["detail"] == "echo from-assistant"
    assert asked["success"] is False
    done = (await c.post("/api/os/assistant", json={"message": "", "confirm_token": asked["confirm_token"]})).json()
    assert done["success"] is True and "from-assistant" in done["response"]
    again = (await c.post("/api/os/assistant", json={"message": "", "confirm_token": asked["confirm_token"]})).json()
    assert again["success"] is False and "expired or was already used" in again["response"]


async def test_assistant_approvals_are_bound_to_the_user_who_was_asked(env):
    c, jarvis, app = env
    asked = (await c.post("/api/os/assistant", json={"message": "run echo secret-job"})).json()
    async with client_for(app, user="admin2") as other:
        stolen = (await other.post("/api/os/assistant", json={"message": "", "confirm_token": asked["confirm_token"]})).json()
    assert stolen["success"] is False
    # the failed redemption burned it
    mine = (await c.post("/api/os/assistant", json={"message": "", "confirm_token": asked["confirm_token"]})).json()
    assert mine["success"] is False


async def test_assistant_cancel_discards_a_pending_approval(env):
    c, *_ = env
    asked = (await c.post("/api/os/assistant", json={"message": "run echo nope"})).json()
    assert (await c.post("/api/os/assistant/cancel", json={"confirm_token": asked["confirm_token"]})).json()["ok"] is True
    after = (await c.post("/api/os/assistant", json={"message": "", "confirm_token": asked["confirm_token"]})).json()
    assert after["success"] is False


async def test_assistant_blocks_catastrophic_commands_even_when_approved(env):
    c, jarvis, _ = env
    asked = (await c.post("/api/os/assistant", json={"message": "run rm -rf /"})).json()
    done = (await c.post("/api/os/assistant", json={"message": "", "confirm_token": asked["confirm_token"]})).json()
    assert done["success"] is False and "blocked" in done["response"]
    assert [e for e in jarvis.security.get_security_events() if e.event_type == "assistant_command_blocked"]


async def test_assistant_requires_a_message_or_a_token(env):
    c, *_ = env
    assert (await c.post("/api/os/assistant", json={"message": "   "})).status_code == 400


async def test_assistant_returns_listing_data_but_not_internal_state(env):
    c, jarvis, _ = env
    (home(jarvis) / "Documents" / "x.txt").write_text("x")
    # wire the interface the real core has, backed by the shared sandbox
    from JARVIS.interface.system_interface import FileSystemManager

    mgr = FileSystemManager({})
    mgr.attach_sandbox(jarvis.os_sandbox, jarvis.os_fs)
    jarvis.subsystems["interface"] = type("I", (), {"list_directory": staticmethod(mgr.list_directory)})()
    r = (await c.post("/api/os/assistant", json={"message": "list /Home/Documents"})).json()
    assert r["intent"] == "list_directory" and [i["name"] for i in r["data"]] == ["x.txt"]
    status = (await c.post("/api/os/assistant", json={"message": "status"})).json()
    assert status["data"] is None


# ------------------------------------------------- session / audit / notifications
async def test_session_roundtrip_is_per_user_and_validated(env):
    c, jarvis, app = env
    assert (await c.get("/api/os/session")).json()["session"] == {}
    layout = {"windows": [{"app": "files", "x": 10, "y": 20}], "wallpaper": "ink"}
    assert (await c.put("/api/os/session", json=layout)).status_code == 200
    assert (await c.get("/api/os/session")).json()["session"] == layout
    async with client_for(app, user="admin2") as other:
        assert (await other.get("/api/os/session")).json()["session"] == {}
    assert (await c.put("/api/os/session", content=b"not json")).status_code == 400
    assert (await c.put("/api/os/session", json=[1, 2])).status_code == 400
    assert (await c.put("/api/os/session", content=b'{"x":"' + b"a" * 200_000 + b'"}')).status_code == 413


async def test_boot_and_session_carry_the_process_id_the_desktop_uses_to_spot_a_restart(env):
    """The desktop probes GET /api/os/session while Odysseus is unreachable; the same boot_id in /boot and /session means
    "the same server came back", a different one means "Odysseus restarted" (static/os/js/net.js)."""
    c, jarvis, app = env
    boot = (await c.get("/api/os/boot")).json()
    session = (await c.get("/api/os/session")).json()
    assert boot["boot_id"] and boot["boot_id"] == session["boot_id"]
    assert (await c.get("/api/os/session")).json()["boot_id"] == session["boot_id"]   # stable for the life of the process


async def test_session_file_names_cannot_escape_the_sessions_folder(env):
    c, jarvis, app = env
    app.state.auth_manager.admins.add("../../evil")
    async with client_for(app, user="../../evil") as evil:
        assert (await evil.put("/api/os/session", json={"x": 1})).status_code == 200
    assert not (jarvis.jarvis_data_dir.parent / "evil.json").exists()
    assert not (jarvis.jarvis_data_dir / "evil.json").exists()
    sessions = jarvis.jarvis_data_dir / "os_sessions"
    written = list(sessions.iterdir())
    assert len(written) == 1
    assert written[0].parent == sessions and "/" not in written[0].name and "\\" not in written[0].name


async def test_audit_log_records_file_changes_newest_first(env):
    c, *_ = env
    await c.put("/api/os/fs/write", json={"path": "/Home/audit1.txt", "content": "a"})
    await c.post("/api/os/fs/mkdir", json={"path": "/Home/audit-dir"})
    events = (await c.get("/api/os/audit")).json()["events"]
    types = [e["type"] for e in events]
    assert types[:2] == ["fs_mkdir", "fs_write"]
    assert events[0]["details"]["user"] == "admin" and events[0]["severity"] == "info"


async def test_notifications_list_and_mark_read(env):
    c, jarvis, _ = env
    await jarvis.notifications.send_notification("Hello", "world", "info")
    items = (await c.get("/api/os/notifications")).json()["notifications"]
    assert items[0]["title"] == "Hello" and items[0]["read"] is False
    assert (await c.post("/api/os/notifications/read", json={"id": items[0]["id"]})).json()["ok"] is True
    unread = (await c.get("/api/os/notifications", params={"unread_only": "true"})).json()["notifications"]
    assert unread == []
    assert (await c.post("/api/os/notifications/read", json={"id": "nope"})).json()["ok"] is False


# ------------------------------------------------------- legacy /api/jarvis/os/*
async def test_legacy_os_endpoints_use_the_same_sandbox(env):
    c, jarvis, _ = env
    # the real core wires OSOperations to the shared fs; do the same here
    from JARVIS.os_integration import OSOperations

    jarvis.subsystems["os_operations"] = OSOperations(fs=jarvis.os_fs)
    w = (await c.post("/api/jarvis/os/write_file", json={"file_path": "/Home/legacy.txt", "content": "hi"})).json()
    assert w["success"] is True
    assert (home(jarvis) / "legacy.txt").read_text() == "hi"
    outside = (await c.post("/api/jarvis/os/read_file", json={"file_path": str(home(jarvis).parent / "jarvis-secret.txt")})).json()
    assert outside["success"] is False
    refused = (await c.post("/api/jarvis/os/execute_command", json={"command": "rm -rf /"})).json()
    assert refused["success"] is False and "blocked" in refused["error"]
    ran = (await c.post("/api/jarvis/os/execute_command", json={"command": f'{PY} -c "print(123)"'})).json()
    assert ran["success"] is True and "123" in ran["data"]["stdout"]
