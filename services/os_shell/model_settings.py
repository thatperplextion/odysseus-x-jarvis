"""Which model Odysseus uses: read it, validate a choice, and save it.

Writes go through Odysseus's own settings store (``src.settings.save_settings``: atomic write, in-process
caches invalidated; other processes pick the file up when their 2 second settings cache expires).
Only the model keys are touched. Nothing here reads or returns an API key.

Settings keys (all global, which is what admins resolve to):
``default_endpoint_id``/``default_model``/``default_model_fallbacks`` - the chat model and its chain;
``utility_endpoint_id``/``utility_model``/``utility_model_fallbacks`` - background jobs and Jarvis planning.
Chain entries look like ``{"endpoint_id": "...", "model": "..."}``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .model_bench import EndpointInfo, classify, load_endpoints

KEEP = object()          # "leave this part of the selection unchanged"
MAX_CHAIN = 6


class SelectionError(ValueError):
    """The requested endpoint/model cannot be used (unknown, disabled or hidden)."""


def describe_ref(endpoint_id: str, model: str, endpoints: List[EndpointInfo]) -> Dict[str, Any]:
    by_id = {e.id: e for e in endpoints}
    ep = by_id.get(endpoint_id)
    out: Dict[str, Any] = {"endpoint_id": endpoint_id, "model": model, "endpoint_name": ep.name if ep else "",
                           "provider": "", "tier": "unknown", "tier_note": "", "available": False, "problem": None}
    if ep is None:
        out["problem"] = "endpoint no longer exists"
        return out
    provider, tier, note = classify(ep.base_url, model)
    out.update(provider=provider, tier=tier, tier_note=note)
    if not ep.enabled:
        out["problem"] = "endpoint is disabled"
    elif model and model not in ep.models:
        out["problem"] = "model is not available on this endpoint"
    elif not model:
        out["problem"] = "no model chosen"
    else:
        out["available"] = True
    return out


def _chain(raw: Any) -> List[Tuple[str, str]]:
    return [(str(e.get("endpoint_id") or ""), str(e.get("model") or "")) for e in (raw or []) if isinstance(e, dict)]


def current_selection(settings: Optional[Dict[str, Any]] = None, endpoints: Optional[List[EndpointInfo]] = None) -> Dict[str, Any]:
    """The default / utility models and their fallback chains, each annotated with endpoint name,
    cost tier and whether it can still be reached (a deleted or disabled endpoint is flagged)."""
    if settings is None:
        from src.settings import load_settings
        settings = load_settings()
    endpoints = endpoints if endpoints is not None else load_endpoints()

    def one(ep_key: str, model_key: str) -> Optional[Dict[str, Any]]:
        ep_id = str(settings.get(ep_key) or "").strip()
        model = str(settings.get(model_key) or "").strip()
        return describe_ref(ep_id, model, endpoints) if ep_id else None

    return {
        "default": one("default_endpoint_id", "default_model"),
        "fallbacks": [describe_ref(i, m, endpoints) for i, m in _chain(settings.get("default_model_fallbacks"))],
        "utility": one("utility_endpoint_id", "utility_model"),
        "utility_fallbacks": [describe_ref(i, m, endpoints) for i, m in _chain(settings.get("utility_model_fallbacks"))],
    }


def _clean_ref(ref: Any, endpoints: List[EndpointInfo], what: str) -> Dict[str, str]:
    """Validate one ``{endpoint_id, model}`` against the live endpoint list."""
    get = (lambda k: ref.get(k)) if isinstance(ref, dict) else (lambda k: getattr(ref, k, None))
    ep_id = str(get("endpoint_id") or "").strip()
    model = str(get("model") or "").strip()
    ep = next((e for e in endpoints if e.id == ep_id), None)
    if ep is None:
        raise SelectionError(f"{what}: unknown endpoint '{ep_id}'")
    if not ep.enabled:
        raise SelectionError(f"{what}: endpoint '{ep.name}' is disabled")
    if not model or model not in ep.models:
        raise SelectionError(f"{what}: model '{model}' is not available on '{ep.name}'")
    return {"endpoint_id": ep_id, "model": model}


def _clean_chain(refs: Any, endpoints: List[EndpointInfo], what: str, exclude: Optional[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = {(exclude["endpoint_id"], exclude["model"])} if exclude else set()
    for i, ref in enumerate(refs or [], 1):
        clean = _clean_ref(ref, endpoints, f"{what} {i}")
        key = (clean["endpoint_id"], clean["model"])
        if key in seen:
            continue                      # a repeat of the primary or an earlier entry would only waste a retry
        seen.add(key)
        out.append(clean)
    if len(out) > MAX_CHAIN:
        raise SelectionError(f"{what}: at most {MAX_CHAIN} fallbacks")
    return out


def apply_selection(
    default: Any,
    fallbacks: Any = KEEP,
    utility: Any = KEEP,
    utility_fallbacks: Any = KEEP,
    *,
    endpoints: Optional[List[EndpointInfo]] = None,
) -> Dict[str, Any]:
    """Validate and save. ``default`` is required; ``fallbacks``/``utility``/``utility_fallbacks`` keep their
    current value when omitted (``KEEP``). ``utility=None`` means "same as the chat model". Raises
    ``SelectionError`` before writing anything if any reference is invalid."""
    import json
    from src import settings as store

    endpoints = endpoints if endpoints is not None else load_endpoints()
    changes: Dict[str, Any] = {}
    primary = _clean_ref(default, endpoints, "default model")
    changes["default_endpoint_id"], changes["default_model"] = primary["endpoint_id"], primary["model"]
    if fallbacks is not KEEP:
        changes["default_model_fallbacks"] = _clean_chain(fallbacks, endpoints, "fallback", primary)
    if utility is not KEEP:
        if utility is None:
            changes["utility_endpoint_id"], changes["utility_model"] = "", ""
            util_primary = None
        else:
            util_primary = _clean_ref(utility, endpoints, "utility model")
            changes["utility_endpoint_id"], changes["utility_model"] = util_primary["endpoint_id"], util_primary["model"]
    else:
        util_primary = None
        cur_ep = str(store.get_setting("utility_endpoint_id", "") or "")
        cur_model = str(store.get_setting("utility_model", "") or "")
        if cur_ep and cur_model:
            util_primary = {"endpoint_id": cur_ep, "model": cur_model}
    if utility_fallbacks is not KEEP:
        changes["utility_model_fallbacks"] = _clean_chain(utility_fallbacks, endpoints, "utility fallback", util_primary)

    # Merge into what is saved on disk (not the defaults-merged view) so unrelated settings stay exactly as they were.
    try:
        with open(store.SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            saved = {}
    except (OSError, ValueError):
        saved = {}
    saved.update(changes)
    store.save_settings(saved)
    return changes
