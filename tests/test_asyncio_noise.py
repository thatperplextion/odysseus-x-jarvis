"""Windows asyncio: client-disconnect noise filter and the 'reset connection kills the listener' fix."""
import asyncio
import socket
import struct
import sys

import pytest

from src import asyncio_noise as an


def _reset(winerror=10054):
    return ConnectionResetError(winerror, "An existing connection was forcibly closed by the remote host", None, winerror, None)


def test_benign_disconnect_is_recognised_precisely():
    ctx = {"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
           "exception": _reset()}
    assert an.is_benign_client_disconnect(ctx)
    assert an.is_benign_client_disconnect({"message": "Fatal read error on socket transport", "exception": _reset(10053)})
    # same exception from somewhere else in the app is NOT swallowed
    assert not an.is_benign_client_disconnect({"message": "Task exception was never retrieved", "exception": _reset()})
    # other errors from a Proactor callback are NOT swallowed
    assert not an.is_benign_client_disconnect({"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
                                               "exception": RuntimeError("boom")})
    assert not an.is_benign_client_disconnect({"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
                                               "exception": ConnectionResetError(104, "reset")})


async def test_installed_handler_swallows_only_the_benign_case():
    loop = asyncio.get_running_loop()
    seen = []
    loop.set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))
    an.install(loop)
    loop.call_exception_handler({"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
                                 "exception": _reset()})
    loop.call_exception_handler({"message": "something real", "exception": RuntimeError("x")})
    assert seen == ["something real"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Proactor loop only")
async def test_reset_connections_do_not_kill_the_listening_socket():
    assert an.patch_proactor_accept()
    seen = []
    asyncio.get_running_loop().set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))

    async def handle(r, w):
        await r.readline()
        w.write(b"pong\n")
        await w.drain()
        w.close()

    srv = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    try:
        for _ in range(200):              # connect + RST before the server gets to accept
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            s.setblocking(False)
            try:
                s.connect_ex(("127.0.0.1", port))
            except OSError:
                pass
            s.close()
        await asyncio.sleep(1.0)
        assert srv.sockets[0].fileno() != -1, "the listening socket was closed"
        assert "Accept failed on a socket" not in seen
        r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 5)
        w.write(b"ping\n")
        await w.drain()
        assert await asyncio.wait_for(r.readline(), 5) == b"pong\n"
        w.close()
    finally:
        srv.close()
        await srv.wait_closed()
