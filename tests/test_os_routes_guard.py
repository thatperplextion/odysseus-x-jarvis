"""Access control for the OS-level routes (/api/os/* and /api/jarvis/*).

Regression: /api/jarvis/os/* (read/write/delete files, run commands) and several other
/api/jarvis/* paths were listed as authentication-exempt in app.py, so anyone who could
reach the port had remote code execution.
"""

import pytest

from tests.helpers.os_app import FakeJarvis, build_app, client_for

pytestmark = pytest.mark.area_security

READ_ROUTES = [
    "/api/os/boot",
    "/api/os/fs/roots",
    "/api/os/fs/list?path=/Home",
    "/api/os/processes",
    "/api/os/system",
    "/api/os/jobs",
    "/api/os/terminal/shells",
    "/api/os/audit",
    "/api/os/notifications",
    "/api/os/session",
    "/api/jarvis/status",
    "/api/jarvis/metrics",
    "/api/jarvis/processes",
    "/api/jarvis/notifications",
    "/api/jarvis/patterns",
    "/api/jarvis/os/history",
]

# (method, url, json body) -- the dangerous ones
WRITE_ROUTES = [
    ("POST", "/api/jarvis/os/execute_command", {"command": "echo pwned"}),
    ("POST", "/api/jarvis/os/read_file", {"file_path": "/etc/passwd"}),
    ("POST", "/api/jarvis/os/write_file", {"file_path": "/Home/x", "content": "x"}),
    ("POST", "/api/jarvis/os/delete_file", {"file_path": "/Home/x"}),
    ("POST", "/api/jarvis/os/list_directory", {"dir_path": "/Home"}),
    ("POST", "/api/jarvis/command", {"command": "run echo hi"}),
    ("POST", "/api/jarvis/autonomous/create_plan", {"goal": "x"}),
    ("POST", "/api/os/terminal/exec", {"command": "echo pwned"}),
    ("PUT", "/api/os/fs/write", {"path": "/Home/x.txt", "content": "x"}),
    ("POST", "/api/os/fs/delete", {"path": "/Home/x.txt"}),
    ("POST", "/api/os/mounts", {"name": "Root", "path": "/"}),
    ("POST", "/api/os/assistant", {"message": "hi"}),
    ("POST", "/api/os/processes/1/terminate", {"force": True}),
    ("POST", "/api/os/jobs", {"command": "echo hi"}),
]


@pytest.fixture
async def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("ODYSSEUS_ALLOWED_HOSTS", raising=False)
    jarvis = FakeJarvis(tmp_path / "jarvis")
    await jarvis.start()
    yield build_app(jarvis, admins=("admin",))
    await jarvis.stop()


async def _send(client, method, url, body=None):
    if method == "GET":
        return await client.get(url)
    return await client.request(method, url, json=body)


@pytest.mark.parametrize("url", READ_ROUTES)
async def test_anonymous_callers_are_rejected(app, url):
    async with client_for(app, user=None) as c:
        assert (await c.get(url)).status_code == 403


@pytest.mark.parametrize("url", READ_ROUTES)
async def test_non_admin_users_are_rejected(app, url):
    async with client_for(app, user="bob") as c:
        assert (await c.get(url)).status_code == 403


@pytest.mark.parametrize("method,url,body", WRITE_ROUTES)
async def test_dangerous_routes_reject_anonymous_and_non_admin(app, method, url, body):
    for user in (None, "bob"):
        async with client_for(app, user=user) as c:
            r = await _send(c, method, url, body)
            assert r.status_code == 403, f"{method} {url} as {user!r} -> {r.status_code}"


@pytest.mark.parametrize("url", ["/api/os/boot", "/api/os/fs/roots", "/api/os/system", "/api/jarvis/status"])
async def test_admin_is_allowed(app, url):
    async with client_for(app, user="admin") as c:
        assert (await c.get(url)).status_code == 200


@pytest.mark.parametrize("method,url,body", WRITE_ROUTES[:3])
async def test_cross_site_requests_are_refused_even_for_admin(app, method, url, body):
    async with client_for(app, user="admin") as c:
        r = await c.request(method, url, json=body, headers={"sec-fetch-site": "cross-site"})
        assert r.status_code == 403 and "Cross-site" in r.text


async def test_same_origin_and_same_site_browser_requests_are_fine(app):
    async with client_for(app, user="admin") as c:
        for site in ("same-origin", "same-site", "none"):
            assert (await c.get("/api/os/fs/roots", headers={"sec-fetch-site": site})).status_code == 200


# ---- DNS rebinding: AUTH_ENABLED=false trusts loopback, so the Host header must be loopback ----
@pytest.fixture
async def unauthenticated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("ODYSSEUS_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("APP_BIND", raising=False)
    jarvis = FakeJarvis(tmp_path / "jarvis")
    await jarvis.start()
    yield build_app(jarvis)
    await jarvis.stop()


@pytest.mark.parametrize("host", ["localhost", "localhost:7000", "127.0.0.1", "127.0.0.1:7000", "[::1]:7000"])
async def test_without_auth_loopback_hosts_are_accepted(unauthenticated_app, host):
    async with client_for(unauthenticated_app, user=None, host=host) as c:
        assert (await c.get("/api/os/fs/roots")).status_code == 200


@pytest.mark.parametrize("host", ["attacker.example", "attacker.example:7000", "127.0.0.1.attacker.example", "192.168.1.10:7000", "localhost.attacker.example"])
async def test_without_auth_rebinding_hosts_are_refused(unauthenticated_app, host):
    """A page on attacker.example rebinds its DNS to 127.0.0.1 and then talks to us as same-origin."""
    async with client_for(unauthenticated_app, user=None, host=host) as c:
        r = await c.post("/api/jarvis/os/execute_command", json={"command": "echo pwned"})
        assert r.status_code == 403 and "Host not allowed" in r.text
        assert (await c.get("/api/os/fs/roots")).status_code == 403


async def test_extra_hosts_can_be_allowed_explicitly(unauthenticated_app, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_ALLOWED_HOSTS", "os.home.lan, other.lan")
    async with client_for(unauthenticated_app, user=None, host="os.home.lan:7000") as c:
        assert (await c.get("/api/os/fs/roots")).status_code == 200


async def test_with_auth_on_the_host_header_is_not_restricted(app):
    """Behind a reverse proxy the Host is the public name; the session cookie is the protection."""
    async with client_for(app, user="admin", host="odysseus.example.com") as c:
        assert (await c.get("/api/os/fs/roots")).status_code == 200


async def test_jarvis_not_running_gives_a_clear_503_not_a_crash(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    app = build_app(None, jarvis_error="No module named 'psutil'")
    async with client_for(app, user="admin") as c:
        r = await c.get("/api/os/fs/roots")
        assert r.status_code == 503 and "psutil" in r.text
        boot = (await c.get("/api/os/boot")).json()
        assert boot["ready"] is False and boot["jarvis_error"] == "No module named 'psutil'"
