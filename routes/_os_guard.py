"""Request guard shared by every OS-level route (``/api/os/*`` and ``/api/jarvis/*``).

These routes read and write files, run commands and signal processes, so they get
three checks beyond normal authentication:

1. **Admin only** -- same rule as ``shell_routes`` (RCE-after-signup otherwise).
2. **No cross-site browser requests** -- ``Sec-Fetch-Site: cross-site`` is refused.
3. **Loopback hosts only when authentication is off.** With ``AUTH_ENABLED=false``
   the only protection is that the server listens on loopback, but a web page you
   visit can rebind its own DNS name to 127.0.0.1 and talk to this server as
   "same-origin". Requiring a loopback ``Host`` header defeats that. (With auth on,
   the rebinding page has no session cookie, so the check isn't needed and would
   only get in the way of reverse-proxy deployments.)
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Set

from fastapi import HTTPException, Request

from core.middleware import require_admin

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _auth_disabled() -> bool:
    return os.getenv("AUTH_ENABLED", "true").lower() == "false"


def _allowed_hosts() -> Set[str]:
    extra = {h.strip().lower() for h in os.getenv("ODYSSEUS_ALLOWED_HOSTS", "").split(",") if h.strip()}
    bind = os.getenv("APP_BIND", "").strip().lower()
    if bind and bind not in ("0.0.0.0", "::"):
        extra.add(bind)
    return _LOOPBACK_HOSTS | extra


def _hostname(host_header: str) -> str:
    host = (host_header or "").strip().lower()
    if host.startswith("["):  # [::1]:7000
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


async def os_admin_guard(request: Request) -> Optional[str]:
    """FastAPI dependency. Raises 403 unless the caller may use OS-level routes.

    ``async`` on purpose: the checks are a few header reads and a dict lookup, and a plain ``def`` dependency is run
    in the shared worker-thread pool - so with that pool busy (slow mail/IMAP handlers, long scans) even the OS
    page's liveness probe, ``GET /api/os/session``, would queue for a thread and look like a hung server."""
    if request.headers.get("sec-fetch-site") == "cross-site":
        logger.warning("OS route %s refused: cross-site request", request.url.path)
        raise HTTPException(403, "Cross-site request rejected")

    if _auth_disabled() and _hostname(request.headers.get("host", "")) not in _allowed_hosts():
        logger.warning("OS route %s refused: Host %r not allowed while authentication is off",
                       request.url.path, request.headers.get("host"))
        raise HTTPException(
            403,
            "Host not allowed: with authentication disabled the OS shell only answers on loopback "
            "(set ODYSSEUS_ALLOWED_HOSTS or enable authentication).",
        )

    require_admin(request)
    return getattr(request.state, "current_user", None)
