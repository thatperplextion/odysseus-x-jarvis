"""
Odysseus OS API - the HTTP surface behind the desktop shell served at ``/os``.

Everything is admin-only (``routes/_os_guard.py``). File access goes through the
shared sandbox (named mounts, Home by default); the terminal runs real commands as
the server's OS user and is audited; anything the *assistant* wants to change waits
for a human to approve it. Blocking work runs on worker threads, never on the event
loop.
"""

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import platform
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from core.atomic_io import atomic_write_json
from routes._os_guard import os_admin_guard
from services.os_shell import procs, terminal
from services.os_shell.approvals import ApprovalStore
from services.os_shell.planner import Planner, describe
from services.os_shell.sandbox import SandboxError

logger = logging.getLogger(__name__)

MAX_SESSION_BYTES = 128 * 1024
PLAN_APPROVAL_TTL = 300
# Identifies this server process. The desktop compares it across a lost connection (GET /session is its probe) to
# tell "the same server came back" from "Odysseus restarted", and refreshes its data either way without a reload.
BOOT_ID = uuid.uuid4().hex[:12]

# GET /session is the desktop's liveness probe, so it must answer even when everything else is slow. It therefore never
# touches the shared worker pool (which long scans and mail handlers can fill): the session document is served from
# memory once read, and its one-off disk read / the write-through on PUT use this single private worker.
_SESSION_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="os-session")
_SESSION_CACHE: Dict[str, Dict[str, Any]] = {}

# Apps the assistant may open (must match static/os/js/main.js).
OS_APPS = ["jarvis", "files", "terminal", "taskmgr", "settings", "editor", "viewer", "automations",
           "chat", "notes", "documents", "email", "calendar", "tasks", "memory", "gallery", "cookbook"]


# ------------------------------------------------------------------ request models
class WriteRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    content: str
    version: Optional[str] = Field(None, max_length=128)
    encoding: str = "utf-8"
    bom: bool = False
    eol: str = "lf"
    create: bool = True


class PathRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)


class RenameRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    name: str = Field(..., max_length=512)


class TransferRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    src: str = Field(..., min_length=1, max_length=4096)
    dst_dir: str = Field(..., min_length=1, max_length=4096)
    name: Optional[str] = Field(None, max_length=512)
    do_copy: bool = Field(False, alias="copy")  # JSON field is "copy"; that name shadows BaseModel.copy
    overwrite: bool = False


class TrashIdRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)


class MountRequest(BaseModel):
    name: str = Field(..., max_length=64)
    path: str = Field(..., min_length=1, max_length=4096)
    readonly: bool = False


class MountPatch(BaseModel):
    readonly: bool


class TerminateRequest(BaseModel):
    force: bool = False


class JobRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=20000)
    cwd: Optional[str] = Field(None, max_length=4096)
    timeout: int = Field(300, ge=1, le=3600)


class ExecRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=50000)
    cwd: Optional[str] = Field(None, max_length=4096)
    shell: Optional[str] = Field(None, max_length=32)
    timeout: float = Field(terminal.DEFAULT_TIMEOUT, ge=1, le=terminal.DEFAULT_TIMEOUT)


class AssistantRequest(BaseModel):
    message: str = Field("", max_length=8000)
    confirm_token: Optional[str] = Field(None, max_length=128)
    history: List[Dict[str, str]] = Field(default_factory=list, max_length=24)
    context: Dict[str, Any] = Field(default_factory=dict)


class CancelApprovalRequest(BaseModel):
    confirm_token: str = Field(..., max_length=128)


class TodoToggleRequest(BaseModel):
    ref: str = Field(..., min_length=3, max_length=64)       # "<note id prefix>#<item index>", from a to-do card
    done: Optional[bool] = None                              # set instead of flip


class NotificationRead(BaseModel):
    id: str = Field(..., max_length=128)


# ----------------------------------------------------------------------- helpers
def _jarvis(request: Request):
    jarvis = getattr(request.app.state, "jarvis", None)
    if not jarvis or jarvis.state != "running" or getattr(jarvis, "os_fs", None) is None:
        reason = getattr(request.app.state, "jarvis_error", None)
        state = getattr(jarvis, "state", "not started") if jarvis else "not started"
        raise HTTPException(503, f"Jarvis OS is not running ({state})" + (f": {reason}" if reason else ""))
    return jarvis


def _user(request: Request) -> str:
    return getattr(request.state, "current_user", None) or "local"


async def _io(fn, *args, **kwargs):
    """Run blocking work on a thread and translate sandbox/OS errors to HTTP errors."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except SandboxError as e:
        raise HTTPException(e.status, str(e))
    except PermissionError:
        raise HTTPException(403, "Permission denied by the operating system")
    except FileNotFoundError:
        raise HTTPException(404, "Not found")
    except OSError as e:
        raise HTTPException(400, str(e))


def _audit(jarvis, request: Request, event: str, details: Dict[str, Any], severity: str = "info"):
    try:
        jarvis.audit(event, {"user": _user(request), **details}, severity, "os_shell")
    except Exception:  # noqa: BLE001 - auditing must never break the operation
        logger.debug("audit failed", exc_info=True)


def _safe_name(user: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]", "_", user)[:48]
    if clean != user or not clean:
        clean = f"{clean}-{hashlib.sha1(user.encode()).hexdigest()[:8]}"
    return clean


def _utility_candidates() -> list:
    """The planner's model chain: the Utility model first (which resolves to the Default Chat model when
    Utility is unset), then the configured Utility fallbacks. ``resolve_utility_fallback_candidates`` alone
    is only the fallbacks, so with none configured the assistant wrongly reported "no model"."""
    from src.endpoint_resolver import resolve_endpoint, resolve_utility_fallback_candidates

    chain = []
    url, model, headers = resolve_endpoint("utility")
    if url and model:
        chain.append((url, model, headers or {}))
    chain.extend(resolve_utility_fallback_candidates())
    return chain


def _llm_configured() -> bool:
    try:
        return bool(_utility_candidates())
    except Exception:  # noqa: BLE001
        return False


def _suggest_mounts(jarvis) -> List[Dict[str, str]]:
    """Common folders in the server user's home that exist and are not mounted yet (Settings -> Folders)."""
    mounted = {os.path.normcase(os.path.realpath(str(m.root))) for m in jarvis.os_sandbox.mounts}
    taken = {m.name.lower() for m in jarvis.os_sandbox.mounts}
    out = []
    home = Path.home()
    for name in ("Documents", "Downloads", "Desktop", "Pictures", "Music", "Videos", "Projects", "source"):
        p = home / name
        if p.is_dir() and os.path.normcase(os.path.realpath(str(p))) not in mounted and name.lower() not in taken:
            out.append({"name": name, "path": str(p)})
    return out


# ------------------------------------------------------------------- assistant planning
async def _odysseus_llm(messages: List[Dict[str, str]]) -> str:
    """The model configured in Odysseus (same one Chat uses for utility calls)."""
    from src.llm_core import _dedupe_candidates, llm_call_async

    candidates = _dedupe_candidates(await asyncio.to_thread(_utility_candidates))
    if not candidates:
        raise RuntimeError("no language model is configured in Odysseus")
    # The same chain as llm_call_async_with_fallback, with two cheap retries on the *same* model before moving on:
    # a short rate-limit wait (free tiers allow only a few planner calls a minute) and, for gpt-oss models that
    # sometimes emit a native tool call Groq rejects, one nudge to answer in plain JSON text.
    last: Optional[Exception] = None
    for url, model, headers in candidates:
        msgs = messages
        for attempt in range(2):
            try:
                return await llm_call_async(url, model, msgs, headers=headers, temperature=0.2, max_tokens=1500)
            except Exception as e:  # noqa: BLE001 - any failure moves on to the next model
                last = e
                text = f"{getattr(e, 'detail', '')} {e}"
                wait = re.search(r"try again in ([\d.]+)\s*s", text)
                if attempt == 0 and re.search(r"\b429\b|rate.?limit", text, re.I) and wait and float(wait.group(1)) <= 12:
                    await asyncio.sleep(float(wait.group(1)) + 0.5)
                    continue
                if attempt == 0 and "tool choice is none" in text.lower():
                    msgs = messages + [{"role": "user", "content": "Answer with the JSON object as plain text; do not call a function or tool natively."}]
                    continue
                break
    raise last if last else RuntimeError("no language model answered")


async def _llm_for(jarvis):
    """The model client for the planner, or None. A jarvis object that defines ``os_llm`` (tests) is
    authoritative; otherwise whatever Odysseus has configured."""
    if hasattr(jarvis, "os_llm"):
        return jarvis.os_llm
    return _odysseus_llm if await asyncio.to_thread(_llm_configured) else None


def _plan_store(jarvis) -> ApprovalStore:
    store = getattr(jarvis, "os_plan_approvals", None)
    if store is None:
        store = ApprovalStore(ttl_seconds=PLAN_APPROVAL_TTL, max_pending=20)
        jarvis.os_plan_approvals = store
    return store


def _system_summary() -> str:
    s = procs.system_snapshot()
    gb = 1024 ** 3
    disks = "; ".join(f"{d['mount']} {d['percent']:.0f}% used of {d['total'] / gb:.0f} GB" for d in s["disks"][:4])
    return (f"CPU {s['cpu']['percent']:.0f}% ({s['cpu']['threads']} threads), memory {s['memory']['percent']:.0f}% "
            f"({s['memory']['used'] / gb:.1f} of {s['memory']['total'] / gb:.1f} GB), up {int(s['uptime'] // 3600)} h, "
            f"{s['processes']} processes. Disks: {disks or 'n/a'}")


def _make_planner(jarvis, llm, request: Optional[Request] = None, hints: Optional[Dict[str, Any]] = None) -> Planner:
    """``request`` (the signed-in user's) enables the daily-cycle tools: automations, to-dos, calendar, reminders.
    ``hints`` is the browser's ``{"tz", "offset_min"}`` so "tomorrow at 11" means the user's tomorrow."""
    agent = jarvis.autonomous_agent
    personal = None
    if request is not None:
        from services.os_shell.assistant_tools import PersonalTools, TimeContext

        personal = PersonalTools(request, TimeContext.build(hints, getattr(jarvis, "os_clock", None)))

    async def run_command(command: str, cwd: Optional[str]):
        text, _data, ok = await agent._handle_execute_command({"command": command, "cwd": cwd}, {})
        return text, ok

    shells = terminal.available_shells()
    return Planner(
        jarvis.os_fs, llm, run_command, OS_APPS,
        os_name=platform.system(), shell=shells[0]["label"] if shells else "",
        system_summary=_system_summary, personal=personal,
    )


# Words that make a short sentence a request about the user's day, not a system query: "remember to call mom"
# must not become a memory search, "status of my morning brief automation" must not report Jarvis's status.
_PERSONAL_INTENT = re.compile(
    r"\b(remind\w*|remember (?:to|that)|don't forget|to-?dos?|to do list|calendar|agenda|automations?|schedul\w*|appointments?|meetings?|"
    r"every (?:day|morning|evening|night|week|weekday|month|hour|\d+ (?:minutes|hours))|my day|brief)\b", re.I)


def _wants_planner(jarvis, message: str) -> bool:
    """Explicit commands (run ..., read <path>, ls ..., status) keep the fast deterministic path;
    only open-ended requests go to the model."""
    from JARVIS.command_processor import IntentType

    intent, _ = jarvis.autonomous_agent.command_processor.parse(message)
    if intent in (IntentType.CHAT, IntentType.UNKNOWN):
        return True
    loose = (IntentType.MEMORY_SEARCH, IntentType.STATUS, IntentType.SYSTEM_METRICS, IntentType.LIST_PROCESSES)
    return intent in loose and bool(_PERSONAL_INTENT.search(message))


def _event_dict(e) -> Dict[str, Any]:
    sev = getattr(e, "severity", None)
    ts = getattr(e, "timestamp", None)
    return {
        "id": getattr(e, "id", ""),
        "type": getattr(e, "event_type", ""),
        "severity": getattr(sev, "value", sev),
        "source": getattr(e, "source", ""),
        "details": getattr(e, "details", {}) or {},
        "time": ts.isoformat() if hasattr(ts, "isoformat") else ts,
    }


# -------------------------------------------------------------------------- router
def setup_os_routes() -> APIRouter:
    router = APIRouter(prefix="/api/os", tags=["os"], dependencies=[Depends(os_admin_guard)])

    # ---------------------------------------------------------------- boot/meta
    @router.get("/boot")
    async def boot(request: Request):
        """Everything the desktop needs on first paint. Answers even when Jarvis is down so the
        shell can show *why* instead of a blank screen."""
        jarvis = getattr(request.app.state, "jarvis", None)
        running = bool(jarvis and jarvis.state == "running" and getattr(jarvis, "os_fs", None) is not None)
        out: Dict[str, Any] = {
            "ready": running,
            "jarvis_state": getattr(jarvis, "state", "not started") if jarvis else "not started",
            "jarvis_error": getattr(request.app.state, "jarvis_error", None),
            "user": _user(request),
            "auth_enabled": os.getenv("AUTH_ENABLED", "true").lower() != "false",
            "boot_id": BOOT_ID,
        }
        if not running:
            return out
        out.update({
            "version": jarvis.version,
            "system": await asyncio.to_thread(procs.system_info),
            "mounts": jarvis.os_fs.roots(),
            "shells": [{k: v for k, v in s.items() if k != "path"} for s in terminal.available_shells()],
            "limits": {
                "max_text_bytes": jarvis.os_fs.max_text_bytes,
                "max_upload_bytes": jarvis.os_fs.max_upload_bytes,
            },
            "assistant": {"llm": await asyncio.to_thread(_llm_configured)},
            "odysseus_connected": bool(jarvis.odysseus_components),
            "suggested_mounts": await asyncio.to_thread(_suggest_mounts, jarvis),
        })
        return out

    @router.get("/session")
    async def get_session(request: Request):
        jarvis = _jarvis(request)
        path = jarvis.jarvis_data_dir / "os_sessions" / f"{_safe_name(_user(request))}.json"

        def read():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return {}

        key = str(path)
        cached = _SESSION_CACHE.get(key)
        if cached is None:
            cached = await asyncio.get_running_loop().run_in_executor(_SESSION_POOL, read)
            _SESSION_CACHE.setdefault(key, cached)
        return {"session": cached, "boot_id": BOOT_ID}

    @router.put("/session")
    async def put_session(request: Request):
        jarvis = _jarvis(request)
        raw = await request.body()
        if len(raw) > MAX_SESSION_BYTES:
            raise HTTPException(413, "Session too large")
        try:
            data = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "Invalid JSON")
        if not isinstance(data, dict):
            raise HTTPException(400, "Session must be an object")
        path = jarvis.jarvis_data_dir / "os_sessions" / f"{_safe_name(_user(request))}.json"
        await asyncio.get_running_loop().run_in_executor(_SESSION_POOL, atomic_write_json, str(path), data)
        _SESSION_CACHE[str(path)] = data
        return {"ok": True}

    @router.get("/audit")
    async def audit_log(request: Request, limit: int = 100):
        jarvis = _jarvis(request)
        security = jarvis.subsystems.get("security")
        if not security:
            return {"events": []}
        events = security.get_security_events(limit=max(1, min(limit, 500)))
        return {"events": [_event_dict(e) for e in reversed(events)]}

    @router.get("/notifications")
    async def notifications(request: Request, unread_only: bool = False):
        jarvis = _jarvis(request)
        comm = jarvis.subsystems.get("communication")
        items = comm.get_notifications(unread_only=unread_only, limit=100) if comm else []
        return {"notifications": list(reversed(items))}

    @router.post("/notifications/read")
    async def notification_read(body: NotificationRead, request: Request):
        jarvis = _jarvis(request)
        comm = jarvis.subsystems.get("communication")
        ok = bool(comm and comm.notification_system.mark_as_read(body.id))
        return {"ok": ok}

    # -------------------------------------------------------------------- files
    @router.get("/fs/roots")
    async def fs_roots(request: Request):
        return {"mounts": _jarvis(request).os_fs.roots()}

    @router.get("/fs/list")
    async def fs_list(request: Request, path: str, hidden: bool = False):
        return await _io(_jarvis(request).os_fs.list_dir, path, hidden)

    @router.get("/fs/stat")
    async def fs_stat(request: Request, path: str):
        return await _io(_jarvis(request).os_fs.stat, path)

    @router.get("/fs/read")
    async def fs_read(request: Request, path: str):
        return await _io(_jarvis(request).os_fs.read_text, path)

    @router.put("/fs/write")
    async def fs_write(body: WriteRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(
            jarvis.os_fs.write_text, body.path, body.content,
            expected_version=body.version, encoding=body.encoding, bom=body.bom, eol=body.eol, create=body.create,
        )
        _audit(jarvis, request, "fs_write", {"path": out["path"], "size": out["size"]})
        return out

    @router.post("/fs/mkdir")
    async def fs_mkdir(body: PathRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(jarvis.os_fs.mkdir, body.path)
        _audit(jarvis, request, "fs_mkdir", {"path": out["path"]})
        return out

    @router.post("/fs/create")
    async def fs_create(body: PathRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(jarvis.os_fs.create_file, body.path)
        _audit(jarvis, request, "fs_create", {"path": out["path"]})
        return out

    @router.post("/fs/rename")
    async def fs_rename(body: RenameRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(jarvis.os_fs.rename, body.path, body.name)
        _audit(jarvis, request, "fs_rename", {"from": body.path, "to": out["path"]})
        return out

    @router.post("/fs/transfer")
    async def fs_transfer(body: TransferRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(jarvis.os_fs.transfer, body.src, body.dst_dir, body.name, copy=body.do_copy, overwrite=body.overwrite)
        _audit(jarvis, request, "fs_copy" if body.do_copy else "fs_move", {"from": body.src, "to": out["path"]})
        return out

    @router.post("/fs/delete")
    async def fs_delete(body: PathRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(jarvis.os_fs.delete, body.path)
        _audit(jarvis, request, "fs_delete", {"path": body.path, "trash_id": out["id"]})
        return out

    @router.get("/fs/search")
    async def fs_search(request: Request, path: str, q: str):
        return await _io(_jarvis(request).os_fs.search, path, q)

    @router.get("/fs/raw")
    async def fs_raw(request: Request, path: str, download: bool = False):
        real, filename, mime, inline_ok = await _io(_jarvis(request).os_fs.open_for_download, path)
        inline = inline_ok and not download
        # Only images/audio/video are ever rendered inline; HTML/SVG/JS would run with the admin's
        # session if served from this origin, so everything else is forced to download.
        return FileResponse(
            real,
            media_type=mime if inline_ok else "application/octet-stream",
            filename=filename,
            content_disposition_type="inline" if inline else "attachment",
            headers={"Cache-Control": "no-cache", "Content-Security-Policy": "sandbox; default-src 'none'"},
        )

    @router.put("/fs/upload")
    async def fs_upload(request: Request, path: str, overwrite: bool = False):
        jarvis = _jarvis(request)
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > jarvis.os_fs.max_upload_bytes:
            raise HTTPException(413, "Upload too large")
        writer = await _io(jarvis.os_fs.begin_upload, path, overwrite)
        try:
            async for chunk in request.stream():
                await _io(writer.write, chunk)
            out = await _io(writer.commit)
        except BaseException:
            await asyncio.to_thread(writer.abort)
            raise
        _audit(jarvis, request, "fs_upload", {"path": out["path"], "size": out["size"]})
        return out

    # -------------------------------------------------------------------- trash
    @router.get("/fs/trash")
    async def trash_list(request: Request):
        return {"items": await _io(_jarvis(request).os_fs.trash_list)}

    @router.post("/fs/trash/restore")
    async def trash_restore(body: TrashIdRequest, request: Request):
        jarvis = _jarvis(request)
        out = await _io(jarvis.os_fs.trash_restore, body.id)
        _audit(jarvis, request, "trash_restore", {"path": out["path"]})
        return out

    @router.post("/fs/trash/purge")
    async def trash_purge(body: TrashIdRequest, request: Request):
        jarvis = _jarvis(request)
        await _io(jarvis.os_fs.trash_purge, body.id)
        _audit(jarvis, request, "trash_purge", {"id": body.id})
        return {"ok": True}

    @router.post("/fs/trash/empty")
    async def trash_empty(request: Request):
        jarvis = _jarvis(request)
        count = await _io(jarvis.os_fs.trash_empty)
        _audit(jarvis, request, "trash_empty", {"items": count}, "low")
        return {"emptied": count}

    # ------------------------------------------------------------------- mounts
    @router.post("/mounts")
    async def mount_add(body: MountRequest, request: Request):
        jarvis = _jarvis(request)

        def add():
            jarvis.os_sandbox.add_mount(body.name, body.path, body.readonly)
            jarvis.os_config.save(jarvis.os_sandbox)

        await _io(add)
        _audit(jarvis, request, "mount_add", {"name": body.name, "path": body.path, "readonly": body.readonly}, "medium")
        return {"mounts": jarvis.os_fs.roots()}

    @router.patch("/mounts/{name}")
    async def mount_patch(name: str, body: MountPatch, request: Request):
        jarvis = _jarvis(request)

        def patch():
            jarvis.os_sandbox.set_readonly(name, body.readonly)
            jarvis.os_config.save(jarvis.os_sandbox)

        await _io(patch)
        _audit(jarvis, request, "mount_readonly", {"name": name, "readonly": body.readonly}, "medium")
        return {"mounts": jarvis.os_fs.roots()}

    @router.delete("/mounts/{name}")
    async def mount_remove(name: str, request: Request):
        jarvis = _jarvis(request)

        def remove():
            jarvis.os_sandbox.remove_mount(name)
            jarvis.os_config.save(jarvis.os_sandbox)

        await _io(remove)
        _audit(jarvis, request, "mount_remove", {"name": name}, "medium")
        return {"mounts": jarvis.os_fs.roots()}

    # ---------------------------------------------------------------- processes
    @router.get("/processes")
    async def processes(request: Request):
        _jarvis(request)
        rows = await asyncio.to_thread(procs.list_processes)
        return {"processes": rows, "time": time.time()}

    @router.post("/processes/{pid}/terminate")
    async def process_terminate(pid: int, body: TerminateRequest, request: Request):
        jarvis = _jarvis(request)
        try:
            out = await asyncio.to_thread(procs.terminate, pid, body.force)
        except procs.ProcessError as e:
            _audit(jarvis, request, "process_terminate_refused", {"pid": pid, "reason": str(e)}, "low")
            raise HTTPException(e.status, str(e))
        _audit(jarvis, request, "process_terminate", {"pid": pid, "name": out.get("name"), "force": body.force}, "medium")
        return out

    @router.get("/system")
    async def system(request: Request):
        _jarvis(request)
        return await asyncio.to_thread(procs.system_snapshot)

    # --------------------------------------------------------------------- jobs
    def _kernel(jarvis):
        kernel = jarvis.subsystems.get("kernel")
        if not kernel:
            raise HTTPException(503, "Kernel unavailable")
        return kernel

    @router.get("/jobs")
    async def jobs(request: Request):
        kernel = _kernel(_jarvis(request))
        rows = [j for j in kernel.process_manager.get_all_processes() if j]
        rows.sort(key=lambda j: j.get("created_at") or "", reverse=True)
        for r in rows:  # list view stays small; fetch /jobs/{id} for the output
            r["result"] = {"exit_code": (r.get("result") or {}).get("exit_code")} if r.get("result") else None
        return {"jobs": rows[:200]}

    @router.post("/jobs")
    async def job_create(body: JobRequest, request: Request):
        jarvis = _jarvis(request)
        kernel = _kernel(jarvis)
        cwd = None
        if body.cwd:
            cwd = str((await _io(jarvis.os_sandbox.resolve, body.cwd)).path)
        else:
            home = jarvis.os_sandbox.get_mount("Home")
            cwd = str(home.root) if home else None
        metadata = {"source": "taskmanager", "timeout": body.timeout, "user": _user(request)}
        if cwd:
            metadata["cwd"] = cwd
        job_id = await kernel.execute_command(body.command, priority=5, metadata=metadata)
        _audit(jarvis, request, "job_start", {"command": body.command[:300], "cwd": cwd})
        return {"id": job_id}

    @router.get("/jobs/{job_id}")
    async def job_get(job_id: str, request: Request):
        kernel = _kernel(_jarvis(request))
        status = kernel.process_manager.get_process_status(job_id)
        if not status:
            raise HTTPException(404, "No such job")
        return status

    @router.post("/jobs/{job_id}/cancel")
    async def job_cancel(job_id: str, request: Request):
        jarvis = _jarvis(request)
        kernel = _kernel(jarvis)
        ok = await kernel.process_manager.cancel_process(job_id)
        if not ok:
            raise HTTPException(409, "Job is not running or queued")
        _audit(jarvis, request, "job_cancel", {"id": job_id})
        return {"ok": True}

    # ----------------------------------------------------------------- terminal
    @router.get("/terminal/shells")
    async def terminal_shells(request: Request):
        _jarvis(request)
        return {"shells": [{k: v for k, v in s.items() if k != "path"} for s in terminal.available_shells()]}

    @router.post("/terminal/exec")
    async def terminal_exec(body: ExecRequest, request: Request):
        """Run one command and stream its output as SSE events (see services/os_shell/terminal.py).
        Closing the connection kills the command and everything it started."""
        jarvis = _jarvis(request)

        cwd = body.cwd
        if cwd:
            first = re.split(r"[\\/]", cwd.strip("\\/"), maxsplit=1)[0] if cwd.strip("\\/") else ""
            if jarvis.os_sandbox.get_mount(first):  # a virtual path such as /Home/Projects
                cwd = str((await _io(jarvis.os_sandbox.resolve, cwd)).path)
        else:
            home = jarvis.os_sandbox.get_mount("Home")
            cwd = str(home.root) if home else os.path.expanduser("~")

        agen = terminal.stream_command(body.command, cwd, body.shell, body.timeout)
        try:
            first_event = await agen.__anext__()
        except terminal.TerminalBusy as e:
            raise HTTPException(429, str(e))
        except terminal.UnknownShell as e:
            raise HTTPException(400, str(e))
        except FileNotFoundError as e:
            raise HTTPException(400, str(e))
        except OSError as e:
            raise HTTPException(500, f"Could not start the shell: {e}")

        _audit(jarvis, request, "terminal_exec",
               {"command": body.command[:300], "shell": first_event.get("shell"), "cwd": cwd, "pid": first_event.get("pid")})

        # Server-sent events, like every other stream in Odysseus (chat, shell, research). That is not
        # cosmetic: the app's GZipMiddleware skips text/event-stream, but it buffers any other small
        # chunked body until it ends -- as NDJSON this stream reached browsers all at once, at the end.
        async def events():
            try:
                yield f"data: {json.dumps(first_event)}\n\n"
                async for ev in agen:
                    yield f"data: {json.dumps(ev)}\n\n"
            finally:
                await agen.aclose()  # client disconnect -> kill the process tree

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # ---------------------------------------------------------------- assistant
    @router.post("/assistant")
    async def assistant(body: AssistantRequest, request: Request):
        jarvis = _jarvis(request)
        user = _user(request)

        if body.confirm_token:
            plan = _plan_store(jarvis).take(body.confirm_token, user)
            if plan is not None:
                return await _run_plan(jarvis, request, plan, body.context)
            # not a plan approval: it may belong to the command parser's own store
        elif not body.message.strip():
            raise HTTPException(400, "message is required")
        elif _wants_planner(jarvis, body.message):
            llm = await _llm_for(jarvis)
            if llm is not None:
                return await _plan_turn(jarvis, request, llm, body)

        context: Dict[str, Any] = {"user": user}
        if body.confirm_token:
            context["confirm_token"] = body.confirm_token
        result = await jarvis.process_command(body.message, context)

        intent = result.get("intent")
        keep_data = intent in ("list_directory", "system_metrics", "list_processes")
        return {
            "response": result.get("response", ""),
            "success": bool(result.get("success")),
            "intent": intent,
            "requires_confirmation": bool(result.get("requires_confirmation")),
            "confirm_token": result.get("confirm_token"),
            "action": result.get("action"),
            "expires_in": result.get("expires_in"),
            "data": result.get("data") if keep_data else None,
        }

    async def _plan_turn(jarvis, request: Request, llm, body: AssistantRequest):
        planner = _make_planner(jarvis, llm, request, body.context)
        try:
            outcome = await planner.turn(body.message, body.history)
        except Exception as e:  # noqa: BLE001 - a flaky model must not take the desktop down
            logger.warning("assistant planner failed: %s", e)
            return {"response": f"I couldn't reach the language model: {e}", "success": False, "intent": "plan",
                    "requires_confirmation": False, "confirm_token": None, "action": None, "data": None}
        reply: Dict[str, Any] = {
            "response": outcome.say or ("Done." if not outcome.pending else ""),
            "say": outcome.say, "success": True, "intent": "plan",
            "requires_confirmation": False, "confirm_token": None, "action": None, "expires_in": None,
            "data": None, "ui_actions": outcome.ui_actions, "steps": outcome.steps, "cards": outcome.cards,
        }
        if outcome.pending:
            lines = [describe(a) for a in outcome.pending]
            token = _plan_store(jarvis).create({"actions": outcome.pending}, _user(request))
            _audit(jarvis, request, "assistant_plan_proposed", {"actions": lines})
            n = len(lines)
            reply.update(
                requires_confirmation=True, confirm_token=token, expires_in=PLAN_APPROVAL_TTL, success=False,
                action={"kind": "plan", "title": f"Jarvis wants to make {n} change{'s' if n != 1 else ''}",
                        "detail": "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1)),
                        # one entry per step; daily-cycle steps carry a structured preview for the card
                        "items": [{"label": line, **(a.get("preview") or {})} for a, line in zip(outcome.pending, lines)]},
            )
        return reply

    async def _run_plan(jarvis, request: Request, plan: Dict[str, Any], hints: Optional[Dict[str, Any]] = None):
        llm = await _llm_for(jarvis)
        planner = _make_planner(jarvis, llm, request, hints)
        lines, ok, results = await planner.execute_detailed(plan["actions"])
        _audit(jarvis, request, "assistant_plan_run",
               {"actions": [describe(a) for a in plan["actions"]], "ok": ok, "results": [r.get("line") or r.get("title") for r in results]},
               "info" if ok else "low")
        return {
            "response": "\n".join(lines) or "Done.", "success": ok, "intent": "plan_result",
            "requires_confirmation": False, "confirm_token": None, "action": None, "expires_in": None, "data": None,
            "results": results,
        }

    @router.get("/assistant/run-result")
    async def assistant_run_result(request: Request, task_id: str, since: str):
        """Where "run my morning brief now" gets its result: the newest run of the user's own automation."""
        from services.os_shell.assistant_tools import PersonalTools, TimeContext, ToolArgError

        jarvis = _jarvis(request)
        tools = PersonalTools(request, TimeContext.build(None, getattr(jarvis, "os_clock", None)))
        try:
            return await tools.run_result(task_id[:64], since[:40])
        except ToolArgError as e:
            raise HTTPException(404, str(e))

    @router.post("/assistant/todos/toggle")
    async def assistant_todo_toggle(body: TodoToggleRequest, request: Request):
        """The to-do card's checkboxes: the user's own click, so no approval card. Owner-scoped like Notes."""
        from services.os_shell.assistant_tools import PersonalTools, TimeContext, ToolArgError

        jarvis = _jarvis(request)
        tools = PersonalTools(request, TimeContext.build(None, getattr(jarvis, "os_clock", None)))
        try:
            res = await tools.toggle_todo(body.ref, want_done=body.done)
        except ToolArgError as e:
            raise HTTPException(404, str(e))
        _audit(jarvis, request, "assistant_todo_toggle", {"ref": body.ref, "done": res["done"]})
        return {"ok": True, **res}

    @router.post("/assistant/cancel")
    async def assistant_cancel(body: CancelApprovalRequest, request: Request):
        jarvis = _jarvis(request)
        user = _user(request)
        agent = jarvis.autonomous_agent
        ok = _plan_store(jarvis).cancel(body.confirm_token, user)
        ok = bool(agent and agent.approvals.cancel(body.confirm_token, user)) or ok
        return {"ok": ok}

    return router
