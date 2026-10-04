"""
chroma_client.py

Singleton ChromaDB HTTP client.
Connects to a ChromaDB instance running as a standalone service.
"""

import os
import socket
import time
import logging

logger = logging.getLogger(__name__)

_client = None

# A short connect probe so an unreachable ChromaDB fails fast instead of
# blocking on the OS connection timeout (~30-60s, WinError 10060 on Windows),
# which otherwise stalls app startup. Tunable via CHROMADB_CONNECT_TIMEOUT.
_CONNECT_TIMEOUT = float(os.getenv("CHROMADB_CONNECT_TIMEOUT", "2.0"))


# On Windows a connection to a port nothing listens on is refused only after ~2 s, and startup probes
# ChromaDB from several places (document RAG, memory vectors, tool index) one after the other - without
# memory of the last failure that is 6-8 s of dead time at every boot when ChromaDB simply is not running.
# So a failed probe is remembered briefly, and a loopback target (which answers at once when it is up)
# gets a short timeout. Only the implicit (production) call uses this; an explicit timeout always probes.
_NEGATIVE_TTL = float(os.getenv("CHROMADB_PROBE_CACHE_SECONDS", "30"))
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_last_failure: dict = {}


def _port_open(host: str, port: int, timeout: float = None) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    implicit = timeout is None
    key = (host, port)
    if implicit:
        failed_at = _last_failure.get(key)
        if failed_at is not None and time.monotonic() - failed_at < _NEGATIVE_TTL:
            return False
        timeout = min(_CONNECT_TIMEOUT, 0.5) if host.lower() in _LOOPBACK_HOSTS else _CONNECT_TIMEOUT
    try:
        with socket.create_connection((host, port), timeout=timeout):
            _last_failure.pop(key, None)
            return True
    except OSError:
        if implicit:
            _last_failure[key] = time.monotonic()
        return False


def get_chroma_client():
    """Get or create the singleton ChromaDB HTTP client.

    Raises RuntimeError with a clear install hint if the `chromadb` package
    is not installed — it's an optional dependency (RAG + memory vectors).
    """
    global _client
    if _client is not None:
        return _client

    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8100"))

    # Probe the port BEFORE importing chromadb: the import alone costs several
    # seconds and tens of MB, and there is no point paying that when the service
    # is not running (the usual state on a machine without Docker).
    if not _port_open(host, port):
        raise RuntimeError(
            f"ChromaDB is not reachable at {host}:{port}. Start the ChromaDB "
            f"service (e.g. `docker compose up chromadb`) or set CHROMADB_HOST / "
            f"CHROMADB_PORT to point at a running instance."
        )

    try:
        import chromadb
    except ImportError as e:
        raise RuntimeError(
            "ChromaDB integration is not installed. Install the optional "
            "dependency with: pip install chromadb-client"
        ) from e

    client = chromadb.HttpClient(host=host, port=port)

    # Health check before caching — if the port is open but the service isn't
    # healthy yet (e.g. still starting), don't poison the singleton with a dead
    # client; leave _client unset so the next call retries.
    client.heartbeat()
    _client = client
    logger.info(f"ChromaDB connected: {host}:{port}")
    return _client


def reset_client():
    """Reset the singleton (e.g. after config change)."""
    global _client
    _client = None
    _last_failure.clear()
