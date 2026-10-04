"""A minimal FastAPI app wired to the *real* OS-shell routers, sandbox, filesystem,
kernel and audit log. Only authentication is faked: the user is read from the
``X-Test-User`` header and ``admin`` is the sole administrator.

Used by tests/test_os_routes_*.py.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request
from starlette.middleware.gzip import GZipMiddleware

from JARVIS.autonomous.autonomous_agent import AutonomousAgent
from JARVIS.communication.communication_manager import NotificationSystem
from JARVIS.kernel.jarvis_kernel import JarvisKernel
from JARVIS.security.security_manager import SecurityManager, ThreatLevel
from routes.jarvis_routes import setup_jarvis_routes
from routes.os_routes import setup_os_routes
from services.os_shell.fs import FileSystem
from services.os_shell.sandbox import SandboxConfig


class FakeAuth:
    is_configured = True

    def __init__(self, admins=("admin",)):
        self.admins = set(admins)

    def is_admin(self, user):
        return user in self.admins


class FakeJarvis:
    """Just enough of JarvisCore for the routes; everything it exposes is real."""

    version = "test"
    state = "running"

    def __init__(self, data_dir: Path):
        self.jarvis_data_dir = data_dir
        self.os_config = SandboxConfig(data_dir)
        self.os_sandbox = self.os_config.load()
        self.os_fs = FileSystem(self.os_sandbox, data_dir / "trash", max_text_bytes=2000, max_upload_bytes=5000)
        self.odysseus_components: Dict[str, Any] = {}
        # Authoritative for the assistant planner: None = "no model configured", never the real
        # Odysseus settings, so tests don't depend on (or call) whatever this machine has set up.
        self.os_llm = None
        self.config = {"autonomous_mode": False}
        self.shutdown_requested = False
        self.kernel = JarvisKernel({"max_concurrent_tasks": 4}, data_dir)
        self.kernel.set_system_interface(object())
        self.security = SecurityManager("high", data_dir)
        notifications = NotificationSystem({})
        comm = SimpleNamespace(get_notifications=notifications.get_notifications, notification_system=notifications)
        self.subsystems = {
            "kernel": self.kernel,
            "security": self.security,
            "communication": comm,
            "interface": None,
        }
        self.notifications = notifications
        self.autonomous_agent = AutonomousAgent(self)

    async def start(self):
        await self.kernel.initialize()

    async def stop(self):
        self.kernel.state = "stopped"

    def audit(self, event_type, details=None, severity="info", source="os"):
        level = {"info": ThreatLevel.INFO, "low": ThreatLevel.LOW, "medium": ThreatLevel.MEDIUM,
                 "high": ThreatLevel.HIGH, "critical": ThreatLevel.CRITICAL}[severity]
        self.security.log_security_event(event_type, level, source, details or {})

    async def process_command(self, text, context=None):
        return await self.autonomous_agent.process_command(text, context)

    def get_status(self):
        return {"uptime_seconds": 1, "version": self.version, "state": self.state, "subsystems": {}}


def build_app(jarvis: Optional[FakeJarvis], admins=("admin",), jarvis_error: Optional[str] = None) -> FastAPI:
    app = FastAPI()
    app.state.auth_manager = FakeAuth(admins)
    app.state.jarvis = jarvis
    app.state.jarvis_error = jarvis_error

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        request.state.current_user = request.headers.get("x-test-user")
        return await call_next(request)

    app.include_router(setup_os_routes())
    app.include_router(setup_jarvis_routes())
    # Same as app.py: it buffers any streamed body that is not text/event-stream until it ends.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
    return app


def client_for(app: FastAPI, user: Optional[str] = "admin", host: str = "localhost", **headers) -> httpx.AsyncClient:
    h = dict(headers)
    if user:
        h["x-test-user"] = user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=f"http://{host}", headers=h, timeout=30
    )
