"""
mcp_manager.py

Manages connections to MCP (Model Context Protocol) tool servers.
Each server exposes tools that are made available to the agent loop.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from src.runtime_paths import get_app_root

logger = logging.getLogger(__name__)


# ── Memory footprint: lazy stdio servers ────────────────────────────────────
#
# Every stdio MCP server is a child process (a built-in Python server is ~70 MB
# once the Windows venv launcher and conhost are counted; an `npx` server is
# three processes). Keeping all of them alive from boot to shutdown is what
# makes a small machine run out of memory. In lazy mode (the default) a stdio
# server is only *registered* at boot, from a cached copy of its tool list; the
# process starts the first time one of its tools is called and is stopped again
# after ODYSSEUS_MCP_IDLE_SECONDS without use.
#   ODYSSEUS_MCP_LAZY=0               start every server at boot and keep it running (old behaviour)
#   ODYSSEUS_MCP_IDLE_SECONDS=900     stop an idle lazily-started server after N seconds (0 = never)
#   ODYSSEUS_MCP_CONNECT_TIMEOUT=30   per-server handshake timeout in seconds
def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def mcp_lazy_enabled() -> bool:
    return _env_flag("ODYSSEUS_MCP_LAZY", True)


def mcp_connect_timeout() -> float:
    return max(1.0, _env_float("ODYSSEUS_MCP_CONNECT_TIMEOUT", 30.0))


class McpConfigError(ValueError):
    """The server definition itself is unusable (nothing was started)."""


# Launchers that, started with no arguments, do not speak MCP at all: `npx` with
# nothing to run opens an interactive shell (banner on stdout, then waits for
# input forever), `python`/`node` open a REPL. Spawning one just burns a process
# until the connect timeout and fills the log with "Failed to parse JSONRPC".
_ARG_REQUIRED_LAUNCHERS = frozenset({
    "npx", "npm", "pnpm", "pnpx", "yarn", "bunx", "bun", "uvx", "uv", "pipx", "deno",
    "node", "python", "python3", "py", "java", "docker", "dotnet",
    "cmd", "powershell", "pwsh", "bash", "sh",
})


def launcher_needs_args(command: Optional[str], args: Optional[List[str]]) -> bool:
    base = os.path.basename((command or "").strip().strip('"')).lower()
    for ext in (".cmd", ".exe", ".bat", ".ps1"):
        if base.endswith(ext):
            base = base[: -len(ext)]
            break
    return base in _ARG_REQUIRED_LAUNCHERS and not [a for a in (args or []) if str(a).strip()]


class _StdoutNoiseFilter(logging.Filter):
    """`mcp.client.stdio` logs a full ERROR traceback for every stdout line a
    server prints that is not JSON-RPC (startup banners, `print()` debugging).
    The protocol layer ignores those lines, so reduce each distinct one to a
    single WARNING that says what was printed, and stop repeating it."""

    _PREFIX = "Failed to parse JSONRPC message from server"
    _MAX_DISTINCT = 10

    def __init__(self):
        super().__init__()
        self._seen: Set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        if not str(record.msg).startswith(self._PREFIX):
            return True
        snippet = ""
        exc = record.exc_info[1] if record.exc_info else None
        try:
            errs = exc.errors() if exc is not None and hasattr(exc, "errors") else []
            if errs:
                snippet = str(errs[0].get("input", ""))
        except Exception:
            snippet = ""
        snippet = snippet.strip()[:120]
        key = snippet[:40]
        if key in self._seen or len(self._seen) >= self._MAX_DISTINCT:
            return False
        self._seen.add(key)
        record.levelno = logging.WARNING
        record.levelname = "WARNING"
        record.exc_info = None
        record.exc_text = None
        record.msg = "An MCP server wrote a non-JSON line to stdout (ignored; shown once): %r"
        record.args = (snippet,)
        return True


logging.getLogger("mcp.client.stdio").addFilter(_StdoutNoiseFilter())


# ── Tool-list cache (lets lazy servers advertise their tools without running) ─
_tools_cache_lock = threading.Lock()


def _tools_cache_path() -> str:
    try:
        from src.constants import DATA_DIR
    except Exception:  # pragma: no cover - constants always importable in the app
        from src.runtime_paths import get_default_data_dir
        DATA_DIR = os.environ.get("ODYSSEUS_DATA_DIR") or get_default_data_dir()
    return os.path.join(DATA_DIR, "cache", "mcp_tools.json")


def _read_tools_cache() -> Dict[str, Any]:
    try:
        with open(_tools_cache_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_tools_cache(data: Dict[str, Any]) -> None:
    path = _tools_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except OSError as e:
        logger.debug(f"MCP tool cache not written: {e}")


def spec_fingerprint(transport: str, command: Optional[str], args: Optional[List[str]],
                     env: Optional[Dict[str, str]], url: Optional[str] = None) -> str:
    """Stable id of a server definition; the cached tool list is only trusted for the same one.
    A script path in the args also contributes its mtime/size, so editing a built-in server invalidates it."""
    parts: List[Any] = [transport, command or "", list(args or []), sorted((env or {}).items()), url or ""]
    for a in args or []:
        if isinstance(a, str) and a.endswith(".py") and os.path.isfile(a):
            st = os.stat(a)
            parts.append([a, st.st_mtime_ns, st.st_size])
    return hashlib.sha1(json.dumps(parts, default=str, sort_keys=True).encode("utf-8")).hexdigest()


def _tool_to_json(tool: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(tool)
    ann = out.get("annotations")
    if ann is not None and not isinstance(ann, dict):
        try:
            out["annotations"] = ann.model_dump(exclude_none=True)
        except Exception:
            out["annotations"] = None
    return out


def load_cached_tools(server_id: str, fingerprint: str) -> Optional[List[Dict[str, Any]]]:
    with _tools_cache_lock:
        entry = _read_tools_cache().get(server_id)
    if isinstance(entry, dict) and entry.get("fp") == fingerprint and isinstance(entry.get("tools"), list):
        return entry["tools"]
    return None


def store_cached_tools(server_id: str, fingerprint: str, tools: List[Dict[str, Any]]) -> None:
    with _tools_cache_lock:
        data = _read_tools_cache()
        data[server_id] = {"fp": fingerprint, "tools": [_tool_to_json(t) for t in tools]}
        _write_tools_cache(data)


def forget_cached_tools(server_id: str) -> None:
    with _tools_cache_lock:
        data = _read_tools_cache()
        if data.pop(server_id, None) is not None:
            _write_tools_cache(data)


def _is_dead_connection(exc: BaseException) -> bool:
    """The call never reached a live server: its pipe/process is gone."""
    if {c.__name__ for c in type(exc).__mro__} & {"ClosedResourceError", "BrokenResourceError", "EndOfStream"}:
        return True
    return "connection closed" in str(exc).lower()


def _unwrap_group(exc: BaseException) -> BaseException:
    """anyio wraps task-group failures in an ExceptionGroup; report the real cause."""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


class _RunnerHandle:
    """Handle on the task that owns one stdio connection.

    anyio (used inside mcp.client.stdio) requires a task group to be exited by
    the task that entered it. Entering it in whichever request/startup task
    happened to call connect_server and closing it from another one is what
    produced "Attempted to exit cancel scope in a different task". So every
    stdio connection lives in its own task; others only signal it to stop.
    Offers aclose() so it can sit in McpManager._stacks next to AsyncExitStacks.
    """

    def __init__(self, task: "asyncio.Task", stop: "asyncio.Event"):
        self.task = task
        self.stop = stop

    def request_stop(self, cancel: bool = False) -> None:
        self.stop.set()
        if cancel and not self.task.done():
            self.task.cancel()

    async def aclose(self, timeout: float = 15.0) -> None:
        self.stop.set()
        done, _ = await asyncio.wait({self.task}, timeout=timeout)
        if not done:
            self.task.cancel()
            done, _ = await asyncio.wait({self.task}, timeout=5.0)
        for t in done:  # mark the outcome retrieved so asyncio never logs it
            if not t.cancelled():
                t.exception()

def _format_mcp_connection_error(name: str, command: str = "", args: Optional[List[str]] = None, error: Exception = None) -> str:
    """Return a user-actionable MCP connection error message."""
    args = args or []
    raw_error = str(error) if error else "Unknown error"
    command_line = " ".join([command or "", *args]).strip()
    lower_command = command_line.lower()

    if "@playwright/mcp" in lower_command:
        return (
            f"{raw_error}\n\n"
            "Browser MCP could not start. On fresh installs, cache the Playwright MCP package once before connecting:\n\n"
            "npx -y @playwright/mcp@latest --version\n\n"
            "Then restart Odysseus and reconnect the Browser MCP server."
        )

    return raw_error


# Caps for rendering untrusted MCP tool schemas into the agent prompt (issue #2660).
# MCP servers are third-party/user-added, so field names and parameter counts are
# untrusted input — bound them so an odd or hostile schema cannot distort the prompt.
_MCP_PARAM_MAX = 12   # max params rendered per tool
_MCP_TOKEN_MAX = 40   # max chars per rendered name / type token
_MCP_HINT_MAX = 300   # total-length backstop for the whole hint


def _sanitize_schema_token(value: Any, limit: int = _MCP_TOKEN_MAX) -> str:
    """Make an untrusted JSON-Schema token safe to splice into the prompt.

    Replaces control chars / newlines with a space, collapses whitespace, and
    length-caps the result, so a weird field name or type cannot inject newlines
    or run on. Normal short identifiers pass through unchanged.
    """
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _format_mcp_params(input_schema: Any) -> str:
    """Render an MCP tool's JSON-Schema inputs as a compact prompt hint.

    Without this the agent only sees a tool's name + description and has to
    guess its arguments (issue #2509). Produces e.g.
    ` Args (JSON): {"path": string (required), "limit": integer}` — names,
    coarse types, and required-ness, kept short so it stays prompt-friendly.
    Returns "" when there are no parameters.

    MCP servers are third-party, so names/types are sanitized and the parameter
    count + total length are capped (issue #2660); normal schemas are unaffected.
    """
    if not isinstance(input_schema, dict):
        return ""
    props = input_schema.get("properties")
    if not isinstance(props, dict) or not props:
        return ""
    required = set(input_schema.get("required") or [])
    parts = []
    for pname, pinfo in list(props.items())[:_MCP_PARAM_MAX]:
        pinfo = pinfo if isinstance(pinfo, dict) else {}
        ptype = pinfo.get("type") or "any"
        if isinstance(ptype, list):
            ptype = "|".join(str(x) for x in ptype)
        tag = f'"{_sanitize_schema_token(pname)}": {_sanitize_schema_token(ptype)}'
        if pname in required:
            tag += " (required)"
        parts.append(tag)
    extra = len(props) - len(parts)
    if extra > 0:
        parts.append(f"…+{extra} more")
    hint = " Args (JSON): {" + ", ".join(parts) + "}"
    if len(hint) > _MCP_HINT_MAX:
        hint = hint[:_MCP_HINT_MAX - 1].rstrip() + "…"
    return hint


# Tool-name prefixes that denote a read-only/inspection operation. Used to
# classify MCP tools for plan mode when the server provides no readOnlyHint.
# These are PREFIXES, not whole words (matched via str.startswith below), so a
# stem like "summar" intentionally covers "summarise"/"summarize"/"summary".
_MCP_READONLY_VERBS = (
    "list", "get", "read", "search", "fetch", "query", "find", "describe",
    "show", "view", "lookup", "count", "status", "info", "inspect", "summar",
)


def mcp_tool_is_readonly(tool: Dict) -> bool:
    """Classify an MCP tool as safe (non-mutating) for plan mode.

    Prefer the server's own annotations (readOnlyHint / destructiveHint). When
    absent, fall back to a tool-name verb heuristic, and FAIL CLOSED (treat as
    write) for anything that doesn't clearly read — plan mode must not run a
    write tool just because its intent is ambiguous.
    """
    ann = tool.get("annotations")
    # annotations may be a dict or a pydantic model
    read_hint = None
    destructive = None
    if ann is not None:
        if isinstance(ann, dict):
            read_hint = ann.get("readOnlyHint")
            destructive = ann.get("destructiveHint")
        else:
            read_hint = getattr(ann, "readOnlyHint", None)
            destructive = getattr(ann, "destructiveHint", None)
    if read_hint is True:
        return True
    if read_hint is False or destructive is True:
        return False
    # No usable hint — heuristic on the tool name's leading verb.
    name = (tool.get("name") or "").lower()
    return name.startswith(_MCP_READONLY_VERBS)


class McpManager:
    """Manages MCP server connections and tool routing."""

    def __init__(self):
        # server_id -> connection state
        self._connections: Dict[str, Dict[str, Any]] = {}
        # server_id -> list of tool schemas
        self._tools: Dict[str, List[Dict]] = {}
        # server_id -> MCP ClientSession
        self._sessions: Dict[str, Any] = {}
        # server_id -> exit stack (for cleanup)
        self._stacks: Dict[str, Any] = {}
        # server_id -> background connect task (HTTP transport / OAuth)
        self._connect_tasks: Dict[str, Any] = {}
        # Tracking updates to tools/connections for RAG indexing / prompt cache
        self._generation = 0
        # stdio servers that can be (re)started on demand: server_id -> connect kwargs
        self._stdio_specs: Dict[str, Dict[str, Any]] = {}
        self._connect_locks: Dict[str, asyncio.Lock] = {}
        self._inflight: Dict[str, int] = {}
        self._last_used: Dict[str, float] = {}
        self._idle_task: Optional["asyncio.Task"] = None

    async def connect_server(
        self,
        server_id: str,
        name: str,
        transport: str,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
    ) -> bool:
        """Connect to an MCP server via stdio, SSE, or Streamable HTTP transport."""
        try:
            if transport == "stdio":
                res = await self._connect_stdio(server_id, name, command, args or [], env or {})
            elif transport == "sse":
                res = await self._connect_sse(server_id, name, url)
            elif transport == "http":
                res = await self._start_http_connect(server_id, name, url)
            else:
                logger.error(f"Unknown MCP transport: {transport}")
                res = False
            if res:
                self._generation += 1
            return res
        except Exception as e:
            if isinstance(e, McpConfigError):
                # A definition problem, not a crash: say so once, without a traceback.
                logger.warning(f"MCP server {name} ({server_id}) was not started: {e}")
            else:
                logger.error(f"Failed to connect MCP server {name} ({server_id}): {e}")
            error_message = _format_mcp_connection_error(name, command or "", args or [], e)
            self._connections[server_id] = {"status": "error", "error": error_message, "name": name}
            self._generation += 1
            return False

    async def _connect_stdio(self, server_id: str, name: str, command: str, args: List[str], env: Dict[str, str]) -> bool:
        """Connect to an MCP server via stdio transport.

        The connection (process, pipes, anyio task group, ClientSession) is owned
        by a dedicated task - see _RunnerHandle - so it is always closed by the
        task that opened it, on timeout, cancellation, disconnect or idle release.
        """
        if launcher_needs_args(command, args):
            raise McpConfigError(
                f"'{command}' was given no arguments, so there is nothing for it to run (it would only open an "
                "interactive shell and never speak MCP). Edit the server and add its arguments, "
                "e.g. -y @modelcontextprotocol/server-filesystem <folder>."
            )
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            logger.warning("MCP package not installed. Install with: pip install mcp")
            self._connections[server_id] = {"status": "error", "error": "mcp package not installed", "name": name}
            return False

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ, **env} if env else None,
        )

        ready: "asyncio.Future" = asyncio.get_running_loop().create_future()
        # The runner may fail after the caller stopped waiting (timeout/cancel); mark that outcome as seen
        # so asyncio does not log "Future exception was never retrieved" for it.
        ready.add_done_callback(lambda f: f.cancelled() or f.exception())
        stop = asyncio.Event()

        async def runner():
            from contextlib import AsyncExitStack
            stack = AsyncExitStack()
            session = None
            try:
                read_stream, write_stream = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
                tools_result = await session.list_tools()
                if not ready.done():
                    ready.set_result((session, tools_result))
                await stop.wait()
            except BaseException as exc:  # noqa: BLE001 - must also see CancelledError to report it
                real = _unwrap_group(exc)
                if not ready.done():
                    if isinstance(real, asyncio.CancelledError):
                        ready.set_exception(RuntimeError("MCP connection was cancelled before it finished starting"))
                    else:
                        ready.set_exception(real if isinstance(real, Exception) else RuntimeError(repr(real)))
                else:
                    logger.debug(f"MCP server {name} ({server_id}) connection ended: {real!r}")
                if isinstance(exc, asyncio.CancelledError):
                    raise
            finally:
                # Same task that entered the contexts. (Do not wrap this in a new anyio CancelScope: scopes
                # must be exited innermost-first, and aclose() exits the ones opened before it.)
                try:
                    await stack.aclose()
                except BaseException as close_exc:  # noqa: BLE001
                    logger.debug(f"MCP server {name} ({server_id}) cleanup: {_unwrap_group(close_exc)!r}")
                if session is not None and not stop.is_set() and self._sessions.get(server_id) is session:
                    # The connection ended without anyone asking (crash / pipe closed): forget the dead
                    # session so the next call starts the server again instead of failing on it.
                    self._sessions.pop(server_id, None)
                    self._stacks.pop(server_id, None)
                    if server_id in self._stdio_specs and server_id in self._tools:
                        self._set_idle_status(server_id)
                        self._generation += 1

        task = asyncio.create_task(runner(), name=f"mcp-stdio-{server_id}")
        handle = _RunnerHandle(task, stop)
        try:
            done, _ = await asyncio.wait({ready}, timeout=mcp_connect_timeout())
        except BaseException:
            handle.request_stop(cancel=True)  # the caller was cancelled: do not leave the child running
            raise
        if ready not in done:
            handle.request_stop(cancel=True)
            await asyncio.wait({task}, timeout=10.0)
            raise TimeoutError(
                f"MCP server '{name}' did not finish its start-up handshake within {mcp_connect_timeout():.0f}s"
            )
        try:
            session, tools_result = ready.result()
        except BaseException:
            await handle.aclose()
            raise

        tools = []
        for tool in tools_result.tools:
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                # MCP tool annotations (readOnlyHint / destructiveHint) drive
                # plan-mode read-only gating. Absent on many servers, so we
                # fall back to a name heuristic in mcp_tool_is_readonly().
                "annotations": getattr(tool, 'annotations', None),
            })

        self._sessions[server_id] = session
        self._stacks[server_id] = handle
        self._tools[server_id] = tools
        self._last_used[server_id] = time.monotonic()
        # Extract identity hints from env vars (e.g. email address, API name)
        # so tool descriptions can distinguish between multiple instances of
        # the same MCP server (e.g. two email accounts).
        identity_hints = []
        for k, v in (env or {}).items():
            k_lower = k.lower()
            if any(x in k_lower for x in ['email_address', 'account', 'user', 'username']):
                identity_hints.append(v)
        identity = ", ".join(identity_hints) if identity_hints else ""

        self._connections[server_id] = {
            "status": "connected",
            "name": name,
            "transport": "stdio",
            "tool_count": len(tools),
            "identity": identity,
        }
        # Remember how to restart it and what it offers, so a later boot (or an
        # idle release) can advertise these tools without keeping the process.
        self._stdio_specs[server_id] = {
            "name": name, "transport": "stdio", "command": command, "args": list(args), "env": dict(env or {}),
        }
        try:
            store_cached_tools(server_id, spec_fingerprint("stdio", command, args, env), tools)
        except Exception as e:  # cache is an optimisation only
            logger.debug(f"MCP tool cache not updated for {server_id}: {e}")

        logger.info(f"MCP server connected: {name} ({server_id}) - {len(tools)} tools via stdio")
        return True

    # ── lazy start / release ────────────────────────────────────────────────

    async def register_stdio(
        self,
        server_id: str,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        lazy: Optional[bool] = None,
    ) -> bool:
        """Make a stdio server available to the agent.

        Lazy (default, see mcp_lazy_enabled): when the tool list is cached for this exact
        definition the server is only registered - its process starts on the first tool call.
        With no usable cache it is started once to learn its tools (cached for next time) and
        stopped again. Non-lazy: connected now and kept running.
        """
        args = list(args or [])
        env = dict(env or {})
        if lazy is None:
            lazy = mcp_lazy_enabled()
        if not lazy or launcher_needs_args(command, args):
            # A bad definition is reported by connect_server (status "error"), never started.
            return await self.connect_server(server_id=server_id, name=name, transport="stdio",
                                             command=command, args=args, env=env)
        cached = None
        try:
            cached = load_cached_tools(server_id, spec_fingerprint("stdio", command, args, env))
        except Exception as e:
            logger.debug(f"MCP tool cache unreadable for {server_id}: {e}")
        if cached is not None:
            self._stdio_specs[server_id] = {
                "name": name, "transport": "stdio", "command": command, "args": args, "env": env,
            }
            self._tools[server_id] = cached
            self._set_idle_status(server_id)
            self._generation += 1
            logger.info(f"MCP server ready on demand: {name} ({server_id}) - {len(cached)} tools (not started)")
            return True
        ok = await self.connect_server(server_id=server_id, name=name, transport="stdio",
                                       command=command, args=args, env=env)
        if ok:
            await self.release(server_id)
        return ok

    def _set_idle_status(self, server_id: str) -> None:
        spec = self._stdio_specs.get(server_id) or {}
        self._connections[server_id] = {
            "status": "connected",  # what the settings UI and agent code treat as "usable"
            "name": spec.get("name", server_id),
            "transport": "stdio",
            "tool_count": len(self._tools.get(server_id, [])),
            "identity": self._connections.get(server_id, {}).get("identity", ""),
            "lazy": True,
            "running": False,
        }

    async def release(self, server_id: str) -> bool:
        """Stop a running stdio server but keep it registered (tools stay advertised, restarts on use)."""
        handle = self._stacks.pop(server_id, None)
        self._sessions.pop(server_id, None)
        if handle is not None:
            try:
                await handle.aclose()
            except Exception as e:
                logger.warning(f"Error stopping MCP server {server_id}: {e}")
        if server_id in self._stdio_specs and server_id in self._tools:
            self._set_idle_status(server_id)
            self._generation += 1
            return True
        return False

    async def ensure_connected(self, server_id: str) -> bool:
        """Start a registered-but-idle stdio server (no-op when it is already running)."""
        if server_id in self._sessions:
            return True
        spec = self._stdio_specs.get(server_id)
        if not spec:
            return False
        lock = self._connect_locks.setdefault(server_id, asyncio.Lock())
        async with lock:
            if server_id in self._sessions:
                return True
            logger.info(f"Starting MCP server on first use: {spec.get('name', server_id)} ({server_id})")
            return await self.connect_server(
                server_id=server_id, name=spec["name"], transport="stdio",
                command=spec["command"], args=spec["args"], env=spec["env"],
            )

    async def release_idle(self, max_idle_seconds: float) -> List[str]:
        """Stop servers that have not been used for max_idle_seconds. Returns the ids released."""
        now = time.monotonic()
        released = []
        for sid in list(self._stacks):
            if sid not in self._stdio_specs or self._inflight.get(sid):
                continue
            if now - self._last_used.get(sid, now) >= max_idle_seconds:
                if await self.release(sid):
                    released.append(sid)
                    logger.info(f"MCP server {sid} idle for {int(max_idle_seconds)}s - stopped (restarts on next use)")
        return released

    def start_idle_reaper(self) -> Optional["asyncio.Task"]:
        """Background loop that releases idle stdio servers. None when disabled."""
        idle = _env_float("ODYSSEUS_MCP_IDLE_SECONDS", 900.0)
        if idle <= 0 or not mcp_lazy_enabled():
            return None
        if self._idle_task is not None and not self._idle_task.done():
            return self._idle_task

        async def _loop():
            interval = min(60.0, max(1.0, idle / 4))
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.release_idle(idle)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"MCP idle sweep failed: {e}")

        self._idle_task = asyncio.create_task(_loop(), name="mcp-idle-reaper")
        return self._idle_task

    async def _connect_sse(self, server_id: str, name: str, url: str) -> bool:
        """Connect to an MCP server via SSE transport."""
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
            from contextlib import AsyncExitStack

            stack = AsyncExitStack()
            try:
                transport = await stack.enter_async_context(sse_client(url))
                read_stream, write_stream = transport
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))

                await session.initialize()

                # Discover tools
                tools_result = await session.list_tools()
            except Exception:
                await stack.aclose()
                raise
            tools = []
            for tool in tools_result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    # MCP tool annotations (readOnlyHint / destructiveHint) drive
                    # plan-mode read-only gating. Absent on many servers, so we
                    # fall back to a name heuristic in mcp_tool_is_readonly().
                    "annotations": getattr(tool, 'annotations', None),
                })

            self._sessions[server_id] = session
            self._stacks[server_id] = stack
            self._tools[server_id] = tools
            self._connections[server_id] = {
                "status": "connected",
                "name": name,
                "transport": "sse",
                "tool_count": len(tools),
            }

            logger.info(f"MCP server connected: {name} ({server_id}) - {len(tools)} tools via SSE")
            return True

        except ImportError:
            logger.warning("MCP package not installed. Install with: pip install mcp")
            self._connections[server_id] = {"status": "error", "error": "mcp package not installed", "name": name}
            return False

    async def _start_http_connect(self, server_id: str, name: str, url: str, wait: float = 8.0) -> bool:
        """Begin a Streamable HTTP connect in the background. Returns within
        `wait` seconds: True if it connected (cached-token path), otherwise the
        flow is awaiting browser authorization and status becomes 'needs_auth'."""
        import asyncio
        self._connections[server_id] = {"status": "connecting", "name": name, "transport": "http"}
        task = asyncio.create_task(self._connect_http(server_id, name, url))
        self._connect_tasks[server_id] = task
        done, _ = await asyncio.wait({task}, timeout=wait)
        if task in done:
            try:
                return task.result()
            except Exception as e:
                self._connections[server_id] = {"status": "error", "error": str(e), "name": name}
                return False
        # Still running → either awaiting authorization, or discovery/DCR is
        # still in flight. If _on_redirect already published needs_auth+auth_url,
        # leave it; otherwise mark needs_auth (auth_url filled in once it fires).
        from src.mcp_oauth import pop_auth_url
        cur = self._connections.get(server_id, {})
        if cur.get("status") != "needs_auth":
            self._connections[server_id] = {
                "status": "needs_auth", "name": name, "transport": "http",
                "auth_url": pop_auth_url(server_id),
            }
        return False

    async def _connect_http(self, server_id: str, name: str, url: str) -> bool:
        """Connect to a Streamable HTTP MCP server (with automatic OAuth)."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
            from contextlib import AsyncExitStack
            from src.mcp_oauth import build_provider, clear_auth_url

            def _on_redirect(auth_url):
                # Publish needs_auth the moment the URL is known, independent of
                # how long discovery/DCR took (may exceed the bounded start wait).
                self._connections[server_id] = {
                    "status": "needs_auth", "name": name, "transport": "http",
                    "auth_url": auth_url,
                }

            provider = build_provider(server_id, url, on_redirect=_on_redirect)
            stack = AsyncExitStack()
            transport = await stack.enter_async_context(streamablehttp_client(url, auth=provider))
            read_stream, write_stream, _get_session_id = transport
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()

            tools_result = await session.list_tools()
            tools = []
            for tool in tools_result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                })

            self._sessions[server_id] = session
            self._stacks[server_id] = stack
            self._tools[server_id] = tools
            self._connections[server_id] = {
                "status": "connected", "name": name, "transport": "http",
                "tool_count": len(tools),
            }
            clear_auth_url(server_id)
            # Tools changed (this can complete after connect_server already
            # returned, via the background OAuth flow), so bump the generation
            # to invalidate the tool-prompt cache.
            self._generation += 1
            logger.info(f"MCP server connected: {name} ({server_id}) - {len(tools)} tools via http")
            return True
        except ImportError:
            logger.warning("MCP package not installed. Install with: pip install mcp")
            self._connections[server_id] = {"status": "error", "error": "mcp package not installed", "name": name}
            return False
        except Exception as e:
            logger.error(f"Failed to connect HTTP MCP server {name} ({server_id}): {e}")
            self._connections[server_id] = {"status": "error", "error": str(e), "name": name}
            return False

    async def disconnect_server(self, server_id: str):
        """Disconnect from an MCP server."""
        # Cancel any in-flight HTTP/OAuth background connect so it stops
        # publishing status for a server that may be getting deleted.
        task = self._connect_tasks.pop(server_id, None)
        if task is not None and not task.done():
            task.cancel()
        try:
            from src.mcp_oauth import clear_auth_url
            clear_auth_url(server_id)
        except Exception:
            pass

        stack = self._stacks.pop(server_id, None)
        if stack:
            try:
                await stack.aclose()
            except Exception as e:
                logger.warning(f"Error closing MCP server {server_id}: {e}")

        self._sessions.pop(server_id, None)
        self._tools.pop(server_id, None)
        self._connections.pop(server_id, None)
        self._stdio_specs.pop(server_id, None)
        self._last_used.pop(server_id, None)
        self._inflight.pop(server_id, None)
        self._generation += 1
        logger.info(f"MCP server disconnected: {server_id}")

    async def disconnect_all(self):
        """Disconnect from all MCP servers."""
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        ids = list(dict.fromkeys([*self._sessions.keys(), *self._stacks.keys()]))
        for sid in ids:
            await self.disconnect_server(sid)

    async def connect_all_enabled(self):
        """Register every enabled MCP server from the database.

        stdio servers are lazy (see mcp_lazy_enabled): they are advertised from the tool cache and
        started on first use. Each server is handled on its own, so one that hangs or is
        misconfigured can no longer stop the ones after it from being set up.
        """
        from src.database import McpServer, SessionLocal

        db = SessionLocal()
        try:
            servers = [
                {
                    "id": srv.id, "name": srv.name, "transport": srv.transport, "command": srv.command,
                    "args": json.loads(srv.args) if srv.args else [],
                    "env": json.loads(srv.env) if srv.env else {},
                    "url": srv.url,
                }
                for srv in db.query(McpServer).filter(McpServer.is_enabled == True).all()
            ]
        finally:
            db.close()

        for s in servers:
            try:
                if s["transport"] == "stdio":
                    await self.register_stdio(s["id"], s["name"], s["command"], s["args"], s["env"])
                else:
                    await self.connect_server(
                        server_id=s["id"], name=s["name"], transport=s["transport"],
                        command=s["command"], args=s["args"], env=s["env"], url=s["url"],
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"MCP server {s['name']} ({s['id']}) failed to start: {type(e).__name__}: {e}")

    async def call_tool(self, qualified_name: str, arguments: Dict) -> Dict:
        """Call an MCP tool by its qualified name (mcp__{server_id}__{tool_name}).

        Returns a result dict compatible with agent_tools format.
        """
        parts = qualified_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return {"error": f"Invalid MCP tool name: {qualified_name}", "exit_code": 1}

        server_id = parts[1]
        tool_name = parts[2]

        session = self._sessions.get(server_id)
        if not session and server_id in self._stdio_specs:
            # Registered on demand (lazy): this is the first use since boot or since it went idle.
            try:
                await self.ensure_connected(server_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"On-demand start of MCP server {server_id} failed: {e}")
            session = self._sessions.get(server_id)
        if not session:
            return {"error": f"MCP server not connected: {server_id}", "exit_code": 1}

        self._inflight[server_id] = self._inflight.get(server_id, 0) + 1
        self._last_used[server_id] = time.monotonic()
        try:
            return await self._call_tool_session(server_id, qualified_name, tool_name, arguments, session)
        finally:
            left = self._inflight.get(server_id, 1) - 1
            if left > 0:
                self._inflight[server_id] = left
            else:
                self._inflight.pop(server_id, None)
            self._last_used[server_id] = time.monotonic()

    async def _call_tool_session(self, server_id: str, qualified_name: str, tool_name: str,
                                 arguments: Dict, session) -> Dict:
        try:
            result = await self._do_call(session, tool_name, arguments)
        except Exception as e:
            if _is_dead_connection(e) and server_id in self._stdio_specs:
                # The server process exited or was killed (e.g. the OS reclaimed memory): start a fresh one
                # and retry once. Safe to retry - the request never reached a live server.
                logger.warning(f"MCP server {server_id} connection is gone ({type(e).__name__}); restarting it")
                await self.release(server_id)
                if await self.ensure_connected(server_id) and self._sessions.get(server_id):
                    try:
                        return await self._do_call(self._sessions[server_id], tool_name, arguments)
                    except Exception as e2:
                        return {"error": str(e2) or type(e2).__name__, "exit_code": 1}
                return {"error": f"MCP server crashed and could not be restarted: {server_id}", "exit_code": 1}
            # Auto-reconnect for builtin servers whose subprocess may have died
            if self.is_builtin(server_id):
                logger.warning(f"MCP call failed for {qualified_name}, attempting reconnect: {e}")
                reconnected = await self._reconnect_builtin(server_id)
                if reconnected:
                    session = self._sessions.get(server_id)
                    if session:
                        try:
                            result = await self._do_call(session, tool_name, arguments)
                        except Exception as e2:
                            logger.error(f"MCP tool call failed after reconnect: {qualified_name}: {e2}")
                            return {"error": str(e2), "exit_code": 1}
                    else:
                        return {"error": f"Reconnected but no session for {server_id}", "exit_code": 1}
                else:
                    logger.error(f"MCP reconnect failed for {server_id}")
                    return {"error": f"MCP server crashed and reconnect failed: {server_id}", "exit_code": 1}
            else:
                logger.error(f"MCP tool call failed: {qualified_name}: {e!r}")
                return {"error": str(e) or type(e).__name__, "exit_code": 1}

        return result

    async def _do_call(self, session, tool_name: str, arguments: Dict) -> Dict:
        """Execute a single MCP tool call and return result dict."""
        result = await session.call_tool(tool_name, arguments)
        output_parts = []
        images = []
        for content in result.content:
            if hasattr(content, 'text'):
                output_parts.append(content.text)
            elif getattr(content, 'type', '') == 'image' and hasattr(content, 'data'):
                # Image content (e.g. Playwright screenshots)
                mime = getattr(content, 'mimeType', 'image/png')
                images.append({"data": content.data, "mimeType": mime})
                output_parts.append(f"[Screenshot captured ({mime})]")
            elif hasattr(content, 'data'):
                output_parts.append(str(content.data))

        output = "\n".join(output_parts)
        is_error = getattr(result, 'isError', False)

        result_dict = {
            "stdout": output if not is_error else "",
            "stderr": output if is_error else "",
            "exit_code": 1 if is_error else 0,
        }
        if images:
            result_dict["images"] = images
        return result_dict

    async def _reconnect_builtin(self, server_id: str) -> bool:
        """Tear down and reconnect a crashed builtin MCP server."""
        import sys
        from src.builtin_mcp import _BUILTIN_SERVERS

        if server_id not in _BUILTIN_SERVERS:
            return False

        script_rel, name = _BUILTIN_SERVERS[server_id]
        base_dir = get_app_root()
        script_path = os.path.join(base_dir, script_rel)

        # Clean up old connection
        await self.disconnect_server(server_id)

        try:
            ok = await self.connect_server(
                server_id=server_id,
                name=name,
                transport="stdio",
                command=sys.executable,
                args=[script_path],
                env={"PYTHONPATH": base_dir},
            )
            if ok:
                logger.info(f"Reconnected builtin MCP server: {name}")
            return ok
        except Exception as e:
            logger.error(f"Failed to reconnect builtin MCP server {name}: {e}")
            return False

    def get_all_openai_schemas(self, disabled_map: Optional[Dict[str, set]] = None) -> List[Dict]:
        """Return all MCP tools in OpenAI function-calling format.

        Tool names are namespaced as mcp__{server_id}__{tool_name}.
        disabled_map: optional {server_id: set_of_disabled_tool_names} to filter out.
        """
        schemas = []
        for server_id, tools in self._tools.items():
            # Skip builtin Python servers — they use the code-block tool format
            # But include NPX-based builtins (like browser) which need function calling
            if self.is_builtin(server_id) and server_id != "builtin_browser":
                continue
            conn = self._connections.get(server_id, {})
            server_name = conn.get("name", server_id)
            disabled = (disabled_map or {}).get(server_id, set())

            identity = conn.get("identity", "")
            label = f"{server_name} ({identity})" if identity else server_name

            for tool in tools:
                if tool["name"] in disabled:
                    continue
                qualified = f"mcp__{server_id}__{tool['name']}"
                schema = {
                    "type": "function",
                    "function": {
                        "name": qualified,
                        "description": f"[MCP:{label}] {tool['description']}",
                        "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                    },
                }
                schemas.append(schema)

        return schemas

    def get_all_tools(self, disabled_map: Optional[Dict[str, set]] = None) -> List[Dict]:
        """Return a flat list of all discovered tools with server info."""
        result = []
        for server_id, tools in self._tools.items():
            conn = self._connections.get(server_id, {})
            disabled = (disabled_map or {}).get(server_id, set())
            for tool in tools:
                result.append({
                    "server_id": server_id,
                    "server_name": conn.get("name", server_id),
                    "name": tool["name"],
                    "qualified_name": f"mcp__{server_id}__{tool['name']}",
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema") or {},
                    "is_disabled": tool["name"] in disabled,
                })
        return result

    def plan_mode_blocked_mcp(self) -> Tuple[Dict[str, Set[str]], Set[str]]:
        """Plan mode: block every MCP tool that isn't clearly read-only.

        Returns (disabled_map, qualified_names):
          - disabled_map: {server_id: {tool_name, ...}} to hide write tools from
            the prompt/schemas (merged into the existing mcp_disabled_map).
          - qualified_names: {"mcp__<server>__<tool>", ...} for runtime rejection
            in execute_tool_block (which matches the qualified name).
        """
        disabled_map: Dict[str, Set[str]] = {}
        qualified: Set[str] = set()
        for server_id, tools in self._tools.items():
            for tool in tools:
                if not mcp_tool_is_readonly(tool):
                    disabled_map.setdefault(server_id, set()).add(tool["name"])
                    qualified.add(f"mcp__{server_id}__{tool['name']}")
        return disabled_map, qualified

    def is_builtin(self, server_id: str) -> bool:
        """Check if a server is a built-in (auto-registered) server."""
        return server_id.startswith("builtin_") or server_id in {
            "image_gen",
            "memory",
            "rag",
            "email",
        }

    def get_server_status(self, server_id: str) -> Dict:
        """Get connection status for a server."""
        return self._connections.get(server_id, {"status": "disconnected"})

    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get connection statuses for all servers."""
        return dict(self._connections)

    _cached_prompt_desc = None
    _cached_prompt_desc_key = None

    def get_tool_descriptions_for_prompt(self, disabled_map: Optional[Dict[str, set]] = None) -> str:
        """Generate text describing MCP tools for the agent system prompt. Cached."""
        cache_key = (
            frozenset((k, frozenset(v)) for k, v in (disabled_map or {}).items()),
            len(self._tools),
            self._generation,
        )
        if self._cached_prompt_desc is not None and self._cached_prompt_desc_key == cache_key:
            return self._cached_prompt_desc
        tools = self.get_all_tools(disabled_map)
        if not tools:
            return ""

        lines = ["\n\nYou also have access to external MCP tool servers. These tools are called via native function calling:"]
        by_server = {}
        for t in tools:
            # Skip builtin Python servers — they're already in the agent prompt
            # But include NPX-based builtins (like browser) which aren't hardcoded
            if self.is_builtin(t["server_id"]) and t["server_id"] != "builtin_browser":
                continue
            if t.get("is_disabled"):
                continue
            sn = t["server_name"]
            if sn not in by_server:
                by_server[sn] = []
            by_server[sn].append(t)

        if not by_server:
            return ""

        for server_name, server_tools in by_server.items():
            # Include identity (e.g. email address) if available
            sid = server_tools[0]["server_id"] if server_tools else ""
            identity = self._connections.get(sid, {}).get("identity", "")
            label = f"{server_name} ({identity})" if identity else server_name
            lines.append(f"\n**{label}:**")
            for t in server_tools:
                # Truncate long descriptions
                desc = t['description'][:120] + '...' if len(t['description']) > 120 else t['description']
                # Include the tool's declared inputs so the model calls it with
                # real argument names instead of guessing from the description
                # alone (issue #2509).
                args_hint = _format_mcp_params(t.get("input_schema"))
                lines.append(f"  - {t['qualified_name']}: {desc}{args_hint}")

        result = "\n".join(lines)
        self._cached_prompt_desc = result
        self._cached_prompt_desc_key = cache_key
        return result
