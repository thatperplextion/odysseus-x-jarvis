"""
Odysseus OS "AI models" API: which models are free, how good they are, and which one is the default.

* ``POST /api/os/models/bench``          run the benchmark; streams server-sent events
* ``POST /api/os/models/bench/cancel``   stop a running benchmark
* ``GET  /api/os/models/bench/latest``   the last saved results (+ whether a run is in progress)
* ``GET  /api/os/models/current``        default / utility models and their fallback chains
* ``POST /api/os/models/default``        set them (validated against the live endpoints)

Admin only, like the rest of ``/api/os`` (``routes/_os_guard.py``). The benchmark calls models through
Odysseus's own client, so API keys stay inside the server process; no response contains one. Blocking
work (database reads, file writes) runs on worker threads. A benchmark keeps running if the browser
that started it goes away, and another request simply attaches to the run in progress.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from routes._os_guard import os_admin_guard
from services.os_shell import model_bench, model_settings
from services.os_shell.model_settings import KEEP, SelectionError

logger = logging.getLogger(__name__)

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
KEEPALIVE_S = 15.0


# ------------------------------------------------------------------ request models
class ModelRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint_id: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=300)


class BenchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: List[str] = Field(default_factory=list, max_length=40)   # only test models matching these substrings
    include_paid: bool = False                                        # paid providers cost money: opt-in only
    merge: bool = False                                               # fold into the earlier results (re-test a few models)


class SelectionRequest(BaseModel):
    """The whole chain at once. A field left out keeps its current value; ``utility: null`` means
    "same as the chat model"."""
    model_config = ConfigDict(extra="forbid")
    default: ModelRef
    fallbacks: Optional[List[ModelRef]] = Field(None, max_length=10)
    utility: Optional[ModelRef] = None
    utility_fallbacks: Optional[List[ModelRef]] = Field(None, max_length=10)


# ------------------------------------------------------------- seams (replaced in tests)
def _caller():
    return model_bench.odysseus_caller


def _load_endpoints():
    return model_bench.load_endpoints()


# ---------------------------------------------------------------------- run registry
class _Run:
    """One benchmark in progress. Every event is kept so a late subscriber can replay the run."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.subscribers: List[asyncio.Queue] = []
        self.task: Optional[asyncio.Task] = None
        self.finished = False
        self.total = 0
        self.done = 0

    def publish(self, event: Dict[str, Any]) -> None:
        if event["type"] == "start":
            self.total = len(event.get("models", []))
        elif event["type"] == "model_done":
            self.done += 1
        self.events.append(event)
        for q in list(self.subscribers):
            q.put_nowait(event)

    def finish(self, event: Dict[str, Any]) -> None:
        self.publish(event)
        self.finished = True
        for q in list(self.subscribers):
            q.put_nowait(None)


_run: Optional[_Run] = None


def _running() -> bool:
    return _run is not None and not _run.finished


async def _execute(run: _Run, body: BenchRequest) -> None:
    try:
        endpoints = await asyncio.to_thread(_load_endpoints)
        candidates, skipped = model_bench.discover_candidates(endpoints, only=body.models, include_paid=body.include_paid)
        if not candidates:
            run.finish({"type": "error", "message": "No models to test: nothing matched, or all were skipped as paid."})
            return
        # The engine's own "done" is not forwarded: the final one is sent below, after merging and saving.
        data = await model_bench.run_benchmark(candidates, _caller(), skipped=skipped,
                                               on_event=lambda e: None if e["type"] == "done" else run.publish(e))
        if body.merge:
            data = model_bench.merge_runs(await asyncio.to_thread(model_bench.load_results), data)
        await asyncio.to_thread(model_bench.save_results, data)
        run.finish({"type": "done", "data": data})
    except asyncio.CancelledError:
        run.finish({"type": "cancelled"})
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("model benchmark failed")
        run.finish({"type": "error", "message": model_bench.scrub(f"Benchmark failed: {exc}")})


def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


async def _stream(run: _Run):
    queue: asyncio.Queue = asyncio.Queue()
    # Replay what already happened, then follow live. No await between the two steps, so no event is missed.
    backlog = list(run.events)
    run.subscribers.append(queue)
    try:
        for event in backlog:
            yield _sse(event)
        if run.finished:
            return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event is None:
                return
            yield _sse(event)
    finally:
        if queue in run.subscribers:
            run.subscribers.remove(queue)


# -------------------------------------------------------------------------- router
def setup_os_models_routes() -> APIRouter:
    router = APIRouter(prefix="/api/os/models", tags=["os"], dependencies=[Depends(os_admin_guard)])

    @router.get("/current")
    async def current():
        endpoints = await asyncio.to_thread(_load_endpoints)
        from src.settings import load_settings
        selection = await asyncio.to_thread(model_settings.current_selection, dict(load_settings()), endpoints)
        selection["endpoints"] = [{"id": e.id, "name": e.name, "enabled": e.enabled, "models": len(e.models)} for e in endpoints]
        return selection

    @router.get("/bench/latest")
    async def latest():
        data = await asyncio.to_thread(model_bench.load_results)
        return {"results": data, "running": _running(),
                "progress": {"done": _run.done, "total": _run.total} if _run is not None and _running() else None}

    @router.post("/bench")
    async def bench(body: BenchRequest, request: Request):
        global _run
        if not _running():
            _run = run = _Run()
            run.task = asyncio.create_task(_execute(run, body))
        else:
            run = _run   # attach to the run in progress
        return StreamingResponse(_stream(run), media_type="text/event-stream", headers=SSE_HEADERS)

    @router.post("/bench/cancel")
    async def cancel():
        if not _running() or _run is None or _run.task is None:
            return {"ok": True, "cancelled": False}
        _run.task.cancel()
        return {"ok": True, "cancelled": True}

    @router.post("/default")
    async def set_default(body: SelectionRequest, request: Request):
        fields = body.model_fields_set

        def apply():
            endpoints = _load_endpoints()
            changes = model_settings.apply_selection(
                body.default.model_dump(),
                [r.model_dump() for r in body.fallbacks] if "fallbacks" in fields and body.fallbacks is not None else KEEP,
                (body.utility.model_dump() if body.utility else None) if "utility" in fields else KEEP,
                [r.model_dump() for r in body.utility_fallbacks] if "utility_fallbacks" in fields and body.utility_fallbacks is not None else KEEP,
                endpoints=endpoints,
            )
            from src.settings import load_settings
            return changes, model_settings.current_selection(dict(load_settings()), endpoints)

        try:
            changes, selection = await asyncio.to_thread(apply)
        except SelectionError as e:
            raise HTTPException(400, str(e))
        jarvis = getattr(request.app.state, "jarvis", None)
        try:
            if jarvis is not None:
                jarvis.audit("model_selection_changed", {
                    "user": getattr(request.state, "current_user", None) or "local",
                    "default": f"{changes['default_endpoint_id']}/{changes['default_model']}",
                    "at": datetime.now(timezone.utc).isoformat(),
                }, "info", "os_models")
        except Exception:  # noqa: BLE001 - auditing must never break the change
            logger.debug("audit failed", exc_info=True)
        return {"ok": True, "current": selection}

    return router
