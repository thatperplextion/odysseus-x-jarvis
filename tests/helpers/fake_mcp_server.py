"""A tiny stdio MCP server used by tests/test_mcp_lazy.py.

    python fake_mcp_server.py            -> serves one tool, ``echo``
    python fake_mcp_server.py hang       -> never answers the handshake
    python fake_mcp_server.py die-after  -> serves, then exits after the first tool call
    python fake_mcp_server.py noisy      -> prints a banner line to stdout before serving
"""
import os
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "ok"

if mode == "hang":
    time.sleep(3600)
    raise SystemExit(0)

if mode == "noisy":
    sys.stdout.write("Fake Banner (c) not json-rpc\n")
    sys.stdout.flush()

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("fake")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the text back with the server pid."""
    if mode == "die-after":
        # leave after answering: schedule the exit shortly after the reply is flushed
        import threading
        threading.Timer(0.3, lambda: os._exit(0)).start()
    return f"{text}|{os.getpid()}"


if __name__ == "__main__":
    mcp.run("stdio")
