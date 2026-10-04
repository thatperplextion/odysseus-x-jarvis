"""Human-approval tokens for AI-originated actions.

When the assistant wants to change the machine (run a command, write a file, delete
something...) it does not act. It stores the exact action here and hands the client
an opaque token; only a later call presenting that token executes it. A token is:

* **server-issued and unguessable** (``secrets.token_urlsafe``),
* **single use** (consumed on first redemption, valid or not),
* **expiring** (default 5 minutes),
* **bound to its owner** (user A cannot redeem user B's approval), and
* **bound to the stored action**, never to whatever text accompanies the redemption.

The store is in-memory and bounded; a server restart simply invalidates pending
approvals, which is the safe failure mode.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class _Pending:
    payload: Dict[str, Any]
    owner: Optional[str]
    expires: float


class ApprovalStore:
    def __init__(self, ttl_seconds: float = 300, max_pending: int = 50, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl_seconds
        self.max_pending = max_pending
        self._clock = clock
        self._items: Dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def create(self, payload: Dict[str, Any], owner: Optional[str] = None) -> str:
        now = self._clock()
        with self._lock:
            self._items = {t: p for t, p in self._items.items() if p.expires > now}
            while len(self._items) >= self.max_pending:
                self._items.pop(next(iter(self._items)))  # drop the oldest
            token = secrets.token_urlsafe(18)
            self._items[token] = _Pending(payload=payload, owner=owner, expires=now + self.ttl)
            return token

    def take(self, token: Optional[str], owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Redeem ``token``. Returns the stored payload, or ``None`` if the token is unknown,
        expired, already used, or belongs to a different owner. The token is consumed
        in every case where it existed, so a wrong-owner probe burns it."""
        if not token or not isinstance(token, str):
            return None
        with self._lock:
            pending = self._items.pop(token, None)
        if pending is None or pending.expires <= self._clock():
            return None
        if pending.owner != owner:
            return None
        return pending.payload

    def expire(self, token: str) -> None:
        """Force a token to be expired (used by tests and for explicit cancellation)."""
        with self._lock:
            if token in self._items:
                self._items[token].expires = 0

    def cancel(self, token: str, owner: Optional[str] = None) -> bool:
        with self._lock:
            pending = self._items.get(token)
            if pending is None or pending.owner != owner:
                return False
            del self._items[token]
            return True
