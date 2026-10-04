"""Quiet the one asyncio log line every Windows web server produces.

When a browser tab closes, reloads or loses its connection, the Proactor event loop's transport is
reset by the peer and asyncio logs, at ERROR, with a traceback:

    asyncio - ERROR - Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)
    ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host

Nothing is wrong - the client simply went away - and the server keeps running. This module installs a
loop exception handler that recognises exactly that case (a ConnectionResetError/ConnectionAbortedError
with WinError 10054/10053 coming from a Proactor transport callback) and logs it at DEBUG. Every other
exception still goes to asyncio's default handler, unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_CLIENT_GONE_WINERRORS = {10054, 10053}   # WSAECONNRESET, WSAECONNABORTED
_TRANSPORT_MARKERS = (
    "_ProactorBasePipeTransport",
    "_ProactorBaseWritePipeTransport",
    "_ProactorReadPipeTransport",
    "_ProactorSocketTransport",
    "_call_connection_lost",
    "Fatal read error on socket transport",
    "Fatal write error on socket transport",
    "Fatal error on pipe transport",
)


def is_benign_client_disconnect(context: Dict[str, Any]) -> bool:
    """True only for 'the peer reset a Proactor transport' - not for any other exception."""
    exc = context.get("exception")
    if not isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
        return False
    if getattr(exc, "winerror", None) not in _CLIENT_GONE_WINERRORS:
        return False
    where = f"{context.get('message', '')} {context.get('handle', '')} {context.get('transport', '')}"
    return any(marker in where for marker in _TRANSPORT_MARKERS)


def install(loop: asyncio.AbstractEventLoop) -> None:
    """Route benign client disconnects to DEBUG; leave everything else to the previous handler."""
    previous = loop.get_exception_handler()

    def handler(lp: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        if is_benign_client_disconnect(context):
            logger.debug("client disconnected (%s)", context.get("message", "connection reset"))
            return
        if previous is not None:
            previous(lp, context)
        else:
            lp.default_exception_handler(context)

    loop.set_exception_handler(handler)


# ── Windows: a reset connection must not kill the listening socket ────────────────────────────────
#
# CPython's Proactor loop (the default on Windows) re-arms its AcceptEx after every accepted
# connection. If a client connects and is reset before the server accepts it - a browser tab closed
# mid-load, a port probe, an aborted fetch, a burst of reconnects - the accept completes with
# WinError 64 / 10054 and _start_serving() answers "Accept failed on a socket" by CLOSING THE LISTENING
# SOCKET. The process keeps running (uvicorn even still says it is serving) but nothing can connect to
# it any more: the page reports "Failed to fetch" until the server is restarted. (Reproduced on
# Python 3.13.5 with a burst of connect+RST: listener fileno -> -1, the next normal client is refused.)
#
# patch_proactor_accept() replaces IocpProactor.accept with the same operation that, instead of failing,
# just accepts again when the failure is one of those per-connection resets. Anything else (listener
# closed, out of resources, cancellation) is reported exactly as before.

_ACCEPT_RESET_WINERRORS = {64, 10054, 10053, 1236}   # NETNAME_DELETED, CONNRESET, CONNABORTED, CONNECTION_ABORTED
_ACCEPT_RETRY_LIMIT = 10_000                          # per accept slot; a safety stop, never hit in practice


def _is_accept_reset(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    return (getattr(exc, "winerror", None) in _ACCEPT_RESET_WINERRORS
            or isinstance(exc, (ConnectionResetError, ConnectionAbortedError)))


def patch_proactor_accept() -> bool:
    """Apply the accept fix. Returns True when the patch is (already) in place, False when not applicable
    (not Windows, or this Python's Proactor internals differ from what the patch was written against)."""
    import sys
    if sys.platform != "win32":
        return False
    try:
        import socket
        import struct
        import _overlapped
        from asyncio import windows_events
        proactor_cls = windows_events.IocpProactor
        if not all(hasattr(proactor_cls, n) for n in ("_register_with_iocp", "_get_accept_socket", "_register", "accept")):
            return False
        null = windows_events.NULL
        so_update = _overlapped.SO_UPDATE_ACCEPT_CONTEXT
    except Exception:
        return False
    if getattr(proactor_cls.accept, "_odysseus_patched", False):
        return True

    def accept(self, listener):
        loop = self._loop
        outer = loop.create_future()
        state = {"inner": None, "retries": 0}

        def attempt(first: bool = False) -> None:
            try:
                self._register_with_iocp(listener)
                conn = self._get_accept_socket(listener.family)
                ov = _overlapped.Overlapped(null)
                ov.AcceptEx(listener.fileno(), conn.fileno())
            except OSError as exc:
                if first:
                    raise                      # same as the stock method: synchronous failure
                if not outer.done():
                    outer.set_exception(exc)
                return

            def finish_accept(trans, key, ov):
                ov.getresult()
                # Use SO_UPDATE_ACCEPT_CONTEXT so getsockname() etc work.
                conn.setsockopt(socket.SOL_SOCKET, so_update, struct.pack("@P", listener.fileno()))
                conn.settimeout(listener.gettimeout())
                return conn, conn.getpeername()

            inner = self._register(ov, listener, finish_accept)
            state["inner"] = inner

            def done(f) -> None:
                if f.cancelled():
                    conn.close()
                    if not outer.done():
                        outer.cancel()
                    return
                exc = f.exception()           # retrieves it: nothing is left for asyncio to log
                if exc is None:
                    if outer.done():
                        conn.close()
                    else:
                        outer.set_result(f.result())
                    return
                conn.close()
                if outer.done():
                    return
                if (_is_accept_reset(exc) and listener.fileno() != -1 and not loop.is_closed()
                        and state["retries"] < _ACCEPT_RETRY_LIMIT):
                    state["retries"] += 1
                    logger.debug("accept: a connection was reset before it was accepted (%s); accepting again", exc)
                    if state["retries"] <= 1000:
                        loop.call_soon(attempt)           # drain the reset backlog without starving other work
                    else:
                        loop.call_later(0.01, attempt)    # sustained storm: breathe between retries
                    return
                outer.set_exception(exc)

            inner.add_done_callback(done)

        attempt(first=True)

        def on_outer_done(o) -> None:
            inner = state["inner"]
            if o.cancelled() and inner is not None and not inner.done():
                inner.cancel()

        outer.add_done_callback(on_outer_done)
        return outer

    accept._odysseus_patched = True            # type: ignore[attr-defined]
    accept._odysseus_original = proactor_cls.accept   # type: ignore[attr-defined]
    proactor_cls.accept = accept
    return True


def unpatch_proactor_accept() -> None:
    """Undo patch_proactor_accept (tests)."""
    try:
        from asyncio import windows_events
    except ImportError:
        return
    cls = getattr(windows_events, "IocpProactor", None)
    original = getattr(getattr(cls, "accept", None), "_odysseus_original", None)
    if original is not None:
        cls.accept = original
