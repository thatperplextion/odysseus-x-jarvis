"""An AI-prompt automation with no pinned model must fall back to the model set in Settings > AI models.

Found by the Odysseus OS QA pass: on a data dir with no chat sessions, "Run now" on an AI automation failed with
"No model/endpoint configured" although a default model was configured, because the scheduler only borrowed the
model of the most recent chat session.
"""

from __future__ import annotations

import sys
import types

from src.task_scheduler import TaskScheduler


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self.row


class _Db:
    def __init__(self, row=None):
        self.row = row

    def query(self, *a, **k):
        return _Query(self.row)


def _scheduler():
    return TaskScheduler.__new__(TaskScheduler)


def _patch_resolver(monkeypatch, result):
    mod = types.ModuleType("src.endpoint_resolver")
    calls = []

    def resolve_endpoint(prefix, *a, **k):
        calls.append(prefix)
        return result

    mod.resolve_endpoint = resolve_endpoint
    monkeypatch.setitem(sys.modules, "src.endpoint_resolver", mod)
    return calls


def test_falls_back_to_the_configured_model_when_there_is_no_chat_session(monkeypatch):
    calls = _patch_resolver(monkeypatch, ("https://api.example/v1/chat/completions", "gpt-test", {}))
    assert _scheduler()._resolve_defaults(_Db(None), None) == ("https://api.example/v1/chat/completions", "gpt-test")
    assert calls == ["task"]    # task -> utility -> default chat model is the resolver's own chain


def test_a_recent_chat_session_still_wins(monkeypatch):
    calls = _patch_resolver(monkeypatch, ("https://api.example/v1/chat/completions", "gpt-test", {}))
    recent = types.SimpleNamespace(endpoint_url="http://localhost:11434/v1/chat/completions", model="qwen")
    assert _scheduler()._resolve_defaults(_Db(recent), None) == ("http://localhost:11434/v1/chat/completions", "qwen")
    assert calls == []


def test_nothing_configured_still_returns_none(monkeypatch):
    _patch_resolver(monkeypatch, (None, None, None))
    assert _scheduler()._resolve_defaults(_Db(None), "owner") == (None, None)
